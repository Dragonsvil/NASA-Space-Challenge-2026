/* =====================================================================
   Orbi relay — Cloudflare Worker (Planetary Analog Finder, Team FAKERS)
   Receives Orbi's questions from the site, asks Gemini, returns the answer.
   The Gemini API key stays HERE (as a secret), never in the website.

   Setup in Cloudflare (Worker → Settings → Bindings → Add → Workers AI):
     variable name: AI      <- that's all you need (free daily allowance, no key)
   Optional backup (Settings → Variables and Secrets):
     GEMINI_API_KEY  (Secret)  Google AI Studio key, used only if Workers AI fails
     GEMINI_MODEL    (Text)    e.g. gemini-4-hydrogen
   ===================================================================== */

// Sites allowed to use this relay. Add your exact GitHub Pages address.
const ALLOWED_ORIGINS = [
  'https://dragonsvil.github.io',
  'http://localhost:8000',
];

const CF_MODEL = '@cf/meta/llama-4-scout-17b-16e-instruct'; // Workers AI model (free allowance)
const DEFAULT_GEMINI_MODEL = 'gemini-4-hydrogen';

const SYSTEM_PROMPT = `You are Orbi, a small, friendly alien who is the assistant of the website "Planetary Analog Finder", made by Team FAKERS for the NASA Space Apps Challenge 2026.

About the project:
- Goal: find places on Earth that are good analogs of two targets: Jezero Crater on Mars (ancient lake with a river delta, explored by the Perseverance rover) and the lunar south pole (candidate region for permanent Moon bases, low sun, permanently shadowed craters that may hold water ice).
- Method: Earth's barren land (vegetated tiles with NDVI > 0.3 are excluded) is split into 0.25° tiles. Each tile is compared to the target in physical units on several dimensions: day–night temperature range, mean night temperature, albedo, slope, roughness, basaltic rock (mafic index), aridity, dust (Mars) and low sun angle (Moon). Each dimension gets a 0–100 score = how close the tile gets compared to the rest of Earth. Three mission profiles weight the dimensions into a total: rover navigation, geology / science, polar & thermal ops.
- Clustering (K-Means) finds "hidden gems": high-scoring sites in the same terrain family as known analogs, but not studied as analogs.
- Validation: known analog sites (Atacama, Haughton Crater, McMurdo Dry Valleys, Mauna Kea, Iceland, Rio Tinto, Death Valley…) should rank high. The site shows their rank in the Validation tab.
- Data: NASA MODIS (land surface temperature, albedo, vegetation), NASA GPM (precipitation), NASA ASTER (rock composition), Copernicus DEM (terrain), aerosol data (dust); for the Moon and Mars, NASA mission data (LRO: LOLA, Diviner; Mars: MOLA and others). Map imagery: NASA GIBS and Esri.
- Limits: Earth can never reproduce Moon/Mars gravity (Moon ≈ 1/6 g, Mars ≈ 0.38 g), their atmosphere (Moon: vacuum; Mars: thin CO2, about 1% of Earth's pressure) or their radiation environment. Every site card says so.
- How to use the site: choose a target and a mission profile at the top, click a dot on the map to open its card (score, radar chart, where the analogy works and breaks). Side panel tabs: Site, Top sites, Validation.

Rules:
- Answer in the user's language, in 1 to 4 short sentences, friendly and a bit playful, like a cute alien. No markdown, no lists unless asked.
- Only give site scores or rankings that appear in the CONTEXT below. Never invent numbers, sites or sources. If you don't know, say so and suggest where to look on the site.
- If CONTEXT.dropped_dimensions lists dimensions, they were NOT scored in this version (e.g. no data): never present them as scored, and say so if asked about them.
- You can answer general questions about the Moon, Mars, planetary science and space exploration, accurately.
- Stay on topic. Politely decline unrelated requests (homework, code, personal advice, anything inappropriate) and steer back to the map or space.`;

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const allowed = ALLOWED_ORIGINS.includes(origin);
    const cors = {
      'Access-Control-Allow-Origin': allowed ? origin : ALLOWED_ORIGINS[0],
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Vary': 'Origin',
    };
    const reply = (obj, status = 200) =>
      new Response(JSON.stringify(obj), { status, headers: { ...cors, 'Content-Type': 'application/json' } });

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    if (request.method !== 'POST') return reply({ error: 'POST only' }, 405);
    if (!allowed) return reply({ error: 'origin not allowed' }, 403);
    if (!env.AI && !env.GEMINI_API_KEY) return reply({ error: 'server not configured' }, 500);

    let body;
    try { body = await request.json(); } catch { return reply({ error: 'bad JSON' }, 400); }
    const question = String(body.question || '').trim().slice(0, 400);
    if (!question) return reply({ error: 'empty question' }, 400);
    const context = JSON.stringify(body.context || {}).slice(0, 4000);

    const userText = `CONTEXT (current state of the site, JSON): ${context}\n\nQUESTION: ${question}`;

    // 1) Cloudflare Workers AI (free daily allowance, no key)
    if (env.AI) {
      try {
        const out = await env.AI.run(CF_MODEL, {
          messages: [{ role: 'system', content: SYSTEM_PROMPT }, { role: 'user', content: userText }],
          max_tokens: 300, temperature: 0.7,
        });
        const text = (typeof out?.response === 'string' ? out.response : out?.choices?.[0]?.message?.content || '').trim();
        if (text) return reply({ answer: text, via: 'workers-ai' });
      } catch (e) {
        const msg = String(e && e.message || e);
        if (!env.GEMINI_API_KEY) return reply({ error: /limit|quota|429|neuron/i.test(msg) ? 'rate limited' : 'ai failure' }, /limit|quota|429|neuron/i.test(msg) ? 429 : 502);
      }
    }

    // 2) Optional backup: Gemini (only if a key is configured)
    if (!env.GEMINI_API_KEY) return reply({ error: 'empty answer' }, 502);
    const model = env.GEMINI_MODEL || DEFAULT_GEMINI_MODEL;
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`;
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-goog-api-key': env.GEMINI_API_KEY },
        body: JSON.stringify({
          systemInstruction: { parts: [{ text: SYSTEM_PROMPT }] },
          contents: [{ role: 'user', parts: [{ text: userText }] }],
          generationConfig: { temperature: 0.7, maxOutputTokens: 800 },
        }),
      });
      if (res.status === 429) return reply({ error: 'rate limited' }, 429);
      if (!res.ok) return reply({ error: 'upstream error', status: res.status }, 502);
      const data = await res.json();
      const text = (data.candidates?.[0]?.content?.parts || []).map(p => p.text || '').join('').trim();
      if (!text) return reply({ error: 'empty answer' }, 502);
      return reply({ answer: text, via: 'gemini' });
    } catch (e) {
      return reply({ error: 'relay failure' }, 502);
    }
  },
};
