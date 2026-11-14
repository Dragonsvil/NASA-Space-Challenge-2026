/* =========================================================================
   ORBI v3 — the alien AI assistant (styles in css/orbi.css). No libraries.
   Extracted from reference/orbi_mascot.html.

   Flow: Orbi.greet() (called when the intro closes) -> greeting -> he docks into
   a round button above the legend -> click it -> Orbi pops up, the chat opens.

   API:
     Orbi.greet()                     show the greeting, then dock
     Orbi.dock()                      no greeting: just show the docked button
     Orbi.open() / Orbi.close()       open / close the chat
     Orbi.setData(results)            give him results.json (for the data answers)
     Orbi.setContext({target, profile, site})   current selection in the UI
     Orbi.say(text)                   Orbi writes a line in the chat (only when it is open)
     Orbi.onShowSite = (site, where) => {}   called by the "Show on map" buttons.
        `where` = {target, profile} the answer was about (can differ from the selection).
     Orbi.config.llmEndpoint = "https://..."  the AI backend (a small relay).
        POST {question, context} -> {answer}.

   HOW HE ANSWERS, in this order (see answer() near the end):
     1. dataAnswer(): built from results.json (best sites, hidden gems, known analogs…)
     2. faqAnswer():  the built-in FAQ
     3. llmAnswer():  the AI relay, ONLY when 1 and 2 have no answer (the free AI quota is small)
   ========================================================================= */
(function () {
  /* ---------- markup ----------
     Orbi builds his own HTML and puts it inside #map (see the top of css/orbi.css for why). */
  const root = document.createElement('div');
  root.id = 'orbi-root';
  root.innerHTML = `
  <div id="orbi-char" aria-hidden="true">
    <svg viewBox="0 0 200 215">
      <defs>
        <radialGradient id="ob-skin" cx="38%" cy="30%" r="78%">
          <stop offset="0" stop-color="#D2FADF"/><stop offset=".45" stop-color="#95EAB5"/><stop offset="1" stop-color="#5FC48C"/>
        </radialGradient>
        <radialGradient id="ob-iris" cx="40%" cy="35%" r="70%">
          <stop offset="0" stop-color="#4C63B8"/><stop offset=".55" stop-color="#22306E"/><stop offset="1" stop-color="#0E1436"/>
        </radialGradient>
        <linearGradient id="ob-hood" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#5A93F7"/><stop offset="1" stop-color="#2A5FD3"/>
        </linearGradient>
        <filter id="ob-glow" x="-150%" y="-150%" width="400%" height="400%"><feGaussianBlur stdDeviation="4"/></filter>
      </defs>
      <ellipse cx="100" cy="206" rx="40" ry="6" fill="#000" opacity=".28"/>
      <g class="rig">
        <!-- tiny feet -->
        <ellipse cx="84" cy="196" rx="13" ry="8" fill="url(#ob-skin)" stroke="#1E3A4C" stroke-width="3"/>
        <ellipse cx="116" cy="196" rx="13" ry="8" fill="url(#ob-skin)" stroke="#1E3A4C" stroke-width="3"/>
        <!-- left arm -->
        <ellipse cx="63" cy="164" rx="10" ry="15" transform="rotate(28 63 164)" fill="url(#ob-hood)" stroke="#1E3A4C" stroke-width="3"/>
        <circle cx="57" cy="177" r="7.5" fill="url(#ob-skin)" stroke="#1E3A4C" stroke-width="2.8"/>
        <!-- hoodie body (small bean) -->
        <path d="M68 150 C63 172 66 193 100 195 C134 193 137 172 132 150 C126 137 114 133 100 133 C86 133 74 137 68 150Z" fill="url(#ob-hood)" stroke="#1E3A4C" stroke-width="3" stroke-linejoin="round"/>
        <path d="M84 174 Q100 169 116 174 L117 186 Q100 190 83 186Z" fill="#1F4FB4" opacity=".45"/>
        <text x="100" y="164" text-anchor="middle" font-family="IBM Plex Mono, ui-monospace, monospace" font-weight="500" font-size="9.5" letter-spacing=".8" fill="#fff">FAKERS</text>
        <path d="M74 158 Q73 176 79 186" stroke="#fff" stroke-width="2.5" fill="none" opacity=".25" stroke-linecap="round"/>
        <!-- collar + strings -->
        <ellipse cx="100" cy="139" rx="29" ry="7" fill="#2453B8" stroke="#1E3A4C" stroke-width="2.5"/>
        <path d="M94 142 L93 152 M106 142 L107 152" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>
        <circle cx="93" cy="153.5" r="2.2" fill="#FC3D21"/><circle cx="107" cy="153.5" r="2.2" fill="#FC3D21"/>
        <!-- right arm (waves) -->
        <g class="arm-r">
          <ellipse cx="137" cy="164" rx="10" ry="15" transform="rotate(-28 137 164)" fill="url(#ob-hood)" stroke="#1E3A4C" stroke-width="3"/>
          <circle cx="143" cy="177" r="7.5" fill="url(#ob-skin)" stroke="#1E3A4C" stroke-width="2.8"/>
        </g>
        <!-- big head -->
        <g class="head">
          <g class="ant-l">
            <path d="M80 34 Q72 17 61 13" stroke="#1E3A4C" stroke-width="6.5" fill="none" stroke-linecap="round"/>
            <path d="M80 34 Q72 17 61 13" stroke="#8FE8B0" stroke-width="3" fill="none" stroke-linecap="round"/>
            <circle class="glow" cx="58" cy="12" r="9" fill="#F4FF8A" opacity=".75" filter="url(#ob-glow)"/>
            <circle cx="58" cy="12" r="6" fill="#ECFF7A" stroke="#1E3A4C" stroke-width="2.5"/>
            <circle cx="56" cy="10" r="1.8" fill="#fff"/>
          </g>
          <g class="ant-r">
            <path d="M120 34 Q128 17 139 13" stroke="#1E3A4C" stroke-width="6.5" fill="none" stroke-linecap="round"/>
            <path d="M120 34 Q128 17 139 13" stroke="#8FE8B0" stroke-width="3" fill="none" stroke-linecap="round"/>
            <circle class="glow" cx="142" cy="12" r="9" fill="#F4FF8A" opacity=".75" filter="url(#ob-glow)"/>
            <circle cx="142" cy="12" r="6" fill="#ECFF7A" stroke="#1E3A4C" stroke-width="2.5"/>
            <circle cx="140" cy="10" r="1.8" fill="#fff"/>
          </g>
          <ellipse cx="100" cy="84" rx="66" ry="58" fill="url(#ob-skin)" stroke="#1E3A4C" stroke-width="3"/>
          <ellipse cx="70" cy="49" rx="18" ry="8.5" fill="#fff" opacity=".5" transform="rotate(-25 70 49)"/>
          <circle cx="93" cy="38" r="3" fill="#fff" opacity=".45"/>
          <ellipse cx="54" cy="109" rx="9.5" ry="5.5" fill="#FF9DB5" opacity=".6"/>
          <ellipse cx="146" cy="109" rx="9.5" ry="5.5" fill="#FF9DB5" opacity=".6"/>
          <!-- big round sparkly eyes -->
          <g class="eye">
            <circle cx="72" cy="91" r="19.5" fill="url(#ob-iris)" stroke="#1E3A4C" stroke-width="2.5"/>
            <g class="shine"><circle cx="65" cy="83.5" r="7.2" fill="#fff"/><circle cx="80" cy="99" r="3.2" fill="#fff" opacity=".9"/>
              <path d="M81 80 l1.2 2.8 2.8 1.2 -2.8 1.2 -1.2 2.8 -1.2 -2.8 -2.8 -1.2 2.8 -1.2z" fill="#fff" opacity=".8"/></g>
          </g>
          <g class="eye">
            <circle cx="128" cy="91" r="19.5" fill="url(#ob-iris)" stroke="#1E3A4C" stroke-width="2.5"/>
            <g class="shine"><circle cx="121" cy="83.5" r="7.2" fill="#fff"/><circle cx="136" cy="99" r="3.2" fill="#fff" opacity=".9"/>
              <path d="M137 80 l1.2 2.8 2.8 1.2 -2.8 1.2 -1.2 2.8 -1.2 -2.8 -2.8 -1.2 2.8 -1.2z" fill="#fff" opacity=".8"/></g>
          </g>
          <path class="smile" d="M91 115 Q95.5 120 100 115.5 Q104.5 120 109 115" stroke="#1E3A4C" stroke-width="2.8" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
          <g class="mouth" style="display:none"><ellipse class="mo" cx="100" cy="117" rx="5.5" ry="4.5" fill="#5A1E3A" stroke="#1E3A4C" stroke-width="2"/>
            <ellipse cx="100" cy="119.5" rx="3" ry="1.3" fill="#FF8FA8"/></g>
        </g>
      </g>
    </svg>
  </div>

  <div id="orbi-bubble" role="status"><span class="who">ORBI</span><span class="txt"></span></div>

  <button id="orbi-fab" type="button" aria-label="Ask Orbi, the AI assistant" tabindex="-1">
    <svg viewBox="0 0 60 60" aria-hidden="true">
      <defs><radialGradient id="ob-fskin" cx="38%" cy="30%" r="78%"><stop offset="0" stop-color="#D2FADF"/><stop offset=".45" stop-color="#95EAB5"/><stop offset="1" stop-color="#5FC48C"/></radialGradient></defs>
      <path d="M23 14 Q19 7 14 6 M37 14 Q41 7 46 6" stroke="#1E3A4C" stroke-width="3.6" fill="none" stroke-linecap="round"/>
      <path d="M23 14 Q19 7 14 6 M37 14 Q41 7 46 6" stroke="#8FE8B0" stroke-width="1.6" fill="none" stroke-linecap="round"/>
      <circle cx="13" cy="6" r="3.4" fill="#ECFF7A" stroke="#1E3A4C" stroke-width="1.6"/><circle cx="47" cy="6" r="3.4" fill="#ECFF7A" stroke="#1E3A4C" stroke-width="1.6"/>
      <ellipse cx="30" cy="33" rx="23" ry="20" fill="url(#ob-fskin)" stroke="#1E3A4C" stroke-width="2"/>
      <circle cx="21" cy="34" r="7" fill="#22306E" stroke="#1E3A4C" stroke-width="1.4"/><circle cx="39" cy="34" r="7" fill="#22306E" stroke="#1E3A4C" stroke-width="1.4"/>
      <circle cx="18.5" cy="31.5" r="2.6" fill="#fff"/><circle cx="36.5" cy="31.5" r="2.6" fill="#fff"/>
      <circle cx="23.5" cy="37" r="1.1" fill="#fff"/><circle cx="41.5" cy="37" r="1.1" fill="#fff"/>
      <ellipse cx="13" cy="42" rx="3.4" ry="2" fill="#FF9DB5" opacity=".7"/><ellipse cx="47" cy="42" rx="3.4" ry="2" fill="#FF9DB5" opacity=".7"/>
      <path d="M27 43.5 Q28.5 45.5 30 43.8 Q31.5 45.5 33 43.5" stroke="#1E3A4C" stroke-width="1.4" fill="none" stroke-linecap="round"/>
    </svg>
    <span class="tip">Ask Orbi</span>
  </button>

  <section id="orbi-chat" aria-label="Chat with Orbi">
    <div class="orbi-head">
      <span class="dot"></span>
      <div class="title"><b>Orbi</b><span>AI assistant · Team FAKERS</span></div>
      <button type="button" class="orbi-icon-btn" data-act="mute" aria-label="Mute"></button>
      <button type="button" class="orbi-icon-btn" data-act="close" aria-label="Close chat">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
    </div>
    <div class="orbi-log" aria-live="polite"></div>
    <div class="orbi-chips"></div>
    <form class="orbi-form" autocomplete="off">
      <input type="text" maxlength="300" placeholder="Ask me anything about the map…" aria-label="Your question">
      <button type="submit" aria-label="Send"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M3 20l18-8L3 4v6l12 2-12 2z"/></svg></button>
    </form>
  </section>`;
  (document.getElementById('map') || document.body).appendChild(root);

  // Orbi sits inside the Leaflet map: without this, a click, a drag or the mouse wheel on
  // his chat would also move or zoom the map underneath.
  if (window.L) {
    L.DomEvent.disableClickPropagation(root);
    L.DomEvent.disableScrollPropagation(root);
  }

  const $ = (s, r = document) => r.querySelector(s);
  const char = $('#orbi-char'), bubble = $('#orbi-bubble'), fab = $('#orbi-fab');
  const chat = $('#orbi-chat'), log = $('.orbi-log', chat), chips = $('.orbi-chips', chat);
  const form = $('.orbi-form', chat), input = $('input', form), sendBtn = $('button', form);
  const head = $('.head', char), shines = char.querySelectorAll('.shine'), smile = $('.smile', char), mouth = $('.mouth', char), mo = $('.mo', char);
  const muteBtn = $('[data-act=mute]', chat);
  // Small screens: the chat is a bottom sheet (same limit as css/orbi.css and css/style.css)
  const smallScreen = window.matchMedia('(max-width: 700px)');

  const config = { llmEndpoint: null, typeSpeed: 22 };
  let data = null, ctx = { target: 'jezero', profile: 'rover', site: null };
  let state = 'hidden';   // hidden | greeting | docked | open
  let busy = false;
  let quotaReached = false;   // true once the AI relay answered 429 (no more AI calls until the page is reloaded)

  /* ---------- settings ---------- */
  const store = {
    get(k, d) { try { const v = localStorage.getItem('orbi.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('orbi.' + k, JSON.stringify(v)); } catch (e) {} }
  };
  let muted = store.get('muted', false);
  const ICON_ON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9v6h4l5 4V5L8 9z" fill="currentColor"/><path d="M16.5 8.5a5 5 0 010 7M19 6a8.5 8.5 0 010 12"/></svg>';
  const ICON_OFF = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9v6h4l5 4V5L8 9z" fill="currentColor"/><path d="M17 9l5 6M22 9l-5 6"/></svg>';
  function refreshMute() {
    muteBtn.innerHTML = muted ? ICON_OFF : ICON_ON; muteBtn.classList.toggle('muted', muted);
    muteBtn.title = muted ? 'Unmute Orbi' : 'Mute Orbi'; muteBtn.setAttribute('aria-label', muteBtn.title);
  }

  /* ---------- sound: alien babble ---------- */
  let ac = null;
  function audio() { if (!ac) ac = new (window.AudioContext || window.webkitAudioContext)(); if (ac.state === 'suspended') ac.resume(); return ac; }
  const FORMANT = { a: 900, e: 1700, i: 2300, o: 600, u: 450, y: 2000 };
  function syllable(ch, vowel) {
    if (muted) return;
    try {
      const a = audio(), t = a.currentTime, d = .1, base = 360 + ((ch.toLowerCase().charCodeAt(0) * 53) % 260);
      const o1 = a.createOscillator(), o2 = a.createOscillator(), lfo = a.createOscillator(), lg = a.createGain();
      const f = a.createBiquadFilter(), g = a.createGain();
      o1.type = 'sawtooth'; o2.type = 'triangle';
      o1.frequency.setValueAtTime(base, t); o2.frequency.setValueAtTime(base * 1.5, t);
      const glide = Math.random() < .5 ? 1.35 : .75;
      o1.frequency.exponentialRampToValueAtTime(base * glide, t + d); o2.frequency.exponentialRampToValueAtTime(base * 1.5 * glide, t + d);
      lfo.frequency.value = 34; lg.gain.value = 22; lfo.connect(lg); lg.connect(o1.frequency); lg.connect(o2.frequency);
      f.type = 'bandpass'; f.Q.value = 4; f.frequency.value = FORMANT[vowel] || 1200;
      g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(.13, t + .012); g.gain.exponentialRampToValueAtTime(.0001, t + d);
      o1.connect(f); o2.connect(f); f.connect(g); g.connect(a.destination);
      [o1, o2, lfo].forEach(o => { o.start(t); o.stop(t + d + .02); });
    } catch (e) {}
  }
  function blip(up) {
    if (muted) return;
    try {
      const a = audio(), t = a.currentTime, o = a.createOscillator(), g = a.createGain();
      o.frequency.setValueAtTime(up ? 300 : 1100, t); o.frequency.exponentialRampToValueAtTime(up ? 1300 : 260, t + .25);
      g.gain.setValueAtTime(.08, t); g.gain.exponentialRampToValueAtTime(.0001, t + .3);
      o.connect(g); g.connect(a.destination); o.start(t); o.stop(t + .3);
    } catch (e) {}
  }

  /* ---------- character animation ---------- */
  function flash(cls, ms) { char.classList.remove(cls); void char.offsetWidth; char.classList.add(cls); setTimeout(() => char.classList.remove(cls), ms); }
  (function blinkLoop() { setTimeout(() => { flash('blink', 130); blinkLoop(); }, 2500 + Math.random() * 2500); })();
  function setMouth(open, ch) {
    smile.style.display = open ? 'none' : ''; mouth.style.display = open ? '' : 'none';
    if (open) { const v = /[aeiouy]/i.test(ch); mo.setAttribute('ry', v ? 6 : 3); mo.setAttribute('rx', /[ou]/i.test(ch) ? 4.5 : 6.5); }
  }
  // His eyes and head follow the mouse
  document.addEventListener('pointermove', e => {
    if (!char.classList.contains('in')) return;
    const r = char.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height * .35;
    let dx = (e.clientX - cx) / 200, dy = (e.clientY - cy) / 200; const m = Math.hypot(dx, dy); if (m > 1) { dx /= m; dy /= m; }
    shines.forEach(el => el.setAttribute('transform', `translate(${(dx * 4).toFixed(1)} ${(dy * 3.5).toFixed(1)})`));
    head.style.transform = `rotate(${(dx * 5).toFixed(1)}deg)`;
  });
  function showChar(on) { char.classList.toggle('in', on); }
  // The docked button: shown or hidden (hidden = also out of the Tab key order)
  function showFab(on) { fab.classList.toggle('show', on); fab.tabIndex = on ? 0 : -1; if (!on) fab.classList.remove('pulse'); }

  /* ---------- the chat log follows the newest text, unless the user scrolled up to read ---------- */
  let followLog = true, userScrollAt = 0;
  // The user touches the log (wheel, finger, scrollbar, keys): stop following at once.
  // Where that scroll ends decides what happens next: back at the bottom = follow again.
  ['wheel', 'touchstart', 'touchmove', 'pointerdown', 'keydown'].forEach(ev =>
    log.addEventListener(ev, () => { userScrollAt = Date.now(); followLog = false; }, { passive: true }));
  log.addEventListener('scroll', () => {
    if (Date.now() - userScrollAt < 1500) followLog = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
  });
  function scrollLog(force) { if (force) followLog = true; if (followLog) log.scrollTop = log.scrollHeight; }

  /* ---------- typewriter into any element ---------- */
  const MAX_TYPING_MS = 6000;   // even a very long answer is fully written after 6 seconds
  function typeInto(el, text, done) {
    let i = 0, vowel = 'a';
    if (!text) { done && done(); return; }
    // Long answers (the AI can write a lot) are typed faster…
    const speed = text.length > 280 ? Math.min(config.typeSpeed, 9) : config.typeSpeed;
    // …and, when that is still too slow, several letters at a time
    const step = Math.max(1, Math.ceil(text.length * speed / MAX_TYPING_MS));
    const timer = setInterval(() => {
      const ch = text[i]; el.textContent += text.slice(i, i + step);
      if (/[aeiouy]/i.test(ch)) vowel = ch.toLowerCase();
      if (/[a-z]/i.test(ch) && (i / step) % 3 === 0) syllable(ch, vowel);
      setMouth(/[a-z]/i.test(ch), ch);
      if (log.contains(el)) scrollLog();
      i += step;
      if (i >= text.length) { clearInterval(timer); setMouth(false); done && done(); }
    }, speed);
  }

  /* ---------- greeting -> dock ---------- */
  let greetTimer = null;
  function greet() {
    if (state !== 'hidden') return;
    state = 'greeting'; blip(true);
    showChar(true);
    setTimeout(() => { flash('wave', 1700); }, 350);
    setTimeout(() => {
      if (state !== 'greeting') return;
      const txt = $('.txt', bubble); txt.textContent = ''; bubble.classList.add('show');
      typeInto(txt, "Hi, Earthling! I'm Orbi, your AI assistant. Feel free to ask me anything about this map: I'll be right here in the corner.",
        () => { if (state === 'greeting') greetTimer = setTimeout(dock, 3200); });
    }, 500);
  }
  function dock() {
    if (state === 'docked') return;
    clearTimeout(greetTimer);
    const wasGreeting = state === 'greeting';
    state = 'docked';
    bubble.classList.remove('show'); chat.classList.remove('show'); root.classList.remove('open');
    showChar(false);
    setTimeout(() => { if (state !== 'docked') return; showFab(true); if (wasGreeting) fab.classList.add('pulse'); }, 300);
  }

  /* ---------- open / close the chat ---------- */
  function open() {
    if (state === 'open') return;
    clearTimeout(greetTimer); bubble.classList.remove('show');
    blip(true);
    showFab(false);
    state = 'open'; root.classList.add('open');
    showChar(true); flash('hop', 600);
    setTimeout(() => {
      if (state !== 'open') return;
      chat.classList.add('show');
      renderChips();
      if (!log.children.length) botSay("What do you need? Ask me about the best sites, hidden gems, how the scores work, or anything about the Moon and Mars.");
      else botSay(pick(["What else do you need?", "I'm back! What's your question?", "Ask away, Earthling."]));
      // On phones, focusing the box would open the keyboard over the suggestions: let the user tap it
      if (!smallScreen.matches) setTimeout(() => input.focus(), 200);
    }, 250);
  }
  function close() { if (state !== 'open') return; blip(false); dock(); setTimeout(() => fab.focus({ preventScroll: true }), 350); }
  fab.addEventListener('click', open);
  chat.addEventListener('click', e => {
    const b = e.target.closest('[data-act]'); if (!b) return;
    if (b.dataset.act === 'close') close();
    if (b.dataset.act === 'mute') { muted = !muted; store.set('muted', muted); refreshMute(); }
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && state === 'open') close(); });
  // Keys typed in the chat must not reach the map (Leaflet moves and zooms with arrows, + and -)
  root.addEventListener('keydown', e => { if (e.key !== 'Escape') e.stopPropagation(); });

  /* ---------- chat log ---------- */
  function addMsg(who, text) {
    const m = document.createElement('div'); m.className = 'orbi-msg ' + who;
    if (who === 'bot') { const w = document.createElement('span'); w.className = 'who'; w.textContent = 'ORBI'; m.appendChild(w); }
    const t = document.createElement('span'); t.className = 'body'; if (text) t.textContent = text; m.appendChild(t);
    log.appendChild(m); scrollLog(true); return m;      // a new message: back to the bottom
  }
  function botSay(text, action) {
    const m = addMsg('bot', ''), body = $('.body', m);
    typeInto(body, text, () => {
      if (action && typeof Orbi.onShowSite === 'function') {
        const b = document.createElement('button'); b.type = 'button'; b.className = 'act'; b.textContent = action.label;
        b.addEventListener('click', () => {
          if (smallScreen.matches) close();     // the bottom sheet would hide the map and the card
          Orbi.onShowSite(action.site, { target: action.target, profile: action.profile });
        });
        m.appendChild(b); scrollLog();
      }
    });
  }
  function typingIndicator() {
    const m = addMsg('bot', ''); const d = document.createElement('span'); d.className = 'orbi-typing'; d.innerHTML = '<i></i><i></i><i></i>';
    $('.body', m).appendChild(d); return m;
  }

  /* ---------- asking ---------- */
  form.addEventListener('submit', async e => {
    e.preventDefault();
    const q = input.value.trim(); if (!q || busy) return;
    input.value = ''; busy = true; sendBtn.disabled = true; chips.classList.remove('nudge');
    addMsg('user', q);
    char.classList.add('thinking');
    const dots = typingIndicator();
    const started = Date.now();
    let reply;
    try { reply = await answer(q); } catch (err) { reply = { text: "Oops, my antenna lost the signal. Try again?" }; }
    await new Promise(r => setTimeout(r, Math.max(0, 650 - (Date.now() - started))));
    dots.remove(); char.classList.remove('thinking');
    botSay(reply.text, reply.action);
    if (reply.pointToChips) nudgeChips();
    busy = false; sendBtn.disabled = false;
    if (!smallScreen.matches) input.focus();
  });
  function renderChips() {
    chips.innerHTML = '';
    const list = ["What is this project?", "Best site for Mars?", "What's a hidden gem?", "Where does the analogy break?"];
    if (ctx.site) list.unshift("Tell me about this site");
    list.slice(0, 4).forEach(q => {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = q;
      b.addEventListener('click', () => { input.value = q; form.requestSubmit(); });
      chips.appendChild(b);
    });
  }
  // Make the suggestion chips flash, to show the user where they are
  function nudgeChips() { chips.classList.remove('nudge'); void chips.offsetWidth; chips.classList.add('nudge'); }

  /* =======================================================================
     THE BRAIN: data answers first, then the FAQ, then the AI (only when needed).
     ======================================================================= */
  const pick = a => a[Math.floor(Math.random() * a.length)];
  // Lower case, no accents, no punctuation, single spaces: "What's a Gem?" -> "what s a gem"
  const norm = s => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9%\s]/g, ' ').replace(/\s+/g, ' ').trim();
  // Does the question contain one of these words? A word matches from its START only:
  // "gem" matches "gems", but "hi" does not match "this" and "here" does not match "where".
  // (q always starts and ends with a space, see answer().)
  const has = (q, words) => words.some(w => q.includes(' ' + w));
  const TARGET_NAMES = { jezero: 'Jezero Crater (Mars)', lunar_south_pole: 'the lunar south pole' };
  const PROFILE_NAMES = { rover: 'rover navigation', geology: 'geology / science', polar: 'polar & thermal ops' };
  // A target or profile added later by the pipeline: use its name from the data file, not its id
  const targetName = t => { const x = data && data.targets && data.targets[t];
    return TARGET_NAMES[t] || (x && x.name ? x.name + (x.body ? ' (' + x.body + ')' : '') : t); };
  const profileName = p => { const x = data && data.meta && (data.meta.profiles || []).find(y => y.id === p);
    return PROFILE_NAMES[p] || (x && x.label ? x.label.toLowerCase() : p); };
  const round1 = v => Math.round(v * 10) / 10;      // scores are shown with one decimal at most

  function targetOf(q) { if (has(q, ['mars', 'jezero', 'martian'])) return 'jezero'; if (has(q, ['moon', 'lunar', 'south pole'])) return 'lunar_south_pole'; return ctx.target || 'jezero'; }
  function profileOf(q) { if (has(q, ['rover', 'navigat', 'drive', 'driving', 'wheel'])) return 'rover'; if (has(q, ['geolog', 'science', 'rock', 'mineral'])) return 'geology'; if (has(q, ['polar', 'thermal', 'cold', 'ice ', 'temperature'])) return 'polar'; return ctx.profile || 'rover'; }
  function total(site, t, p) { const s = site && site.scores && site.scores[t] && site.scores[t][p]; return s && typeof s.total === 'number' ? round1(s.total) : null; }
  function isGem(site, t) { const g = site.hidden_gem; return g === true || (g && typeof g === 'object' && g[t] === true); }
  function where(site) { const r = site.region || 'an unnamed area'; return `${r} (${fmtLat(site.lat)}, ${fmtLon(site.lon)})`; }
  function fmtLat(v) { return typeof v === 'number' ? `${Math.abs(v).toFixed(2)}° ${v >= 0 ? 'N' : 'S'}` : '?'; }
  function fmtLon(v) { return typeof v === 'number' ? `${Math.abs(v).toFixed(2)}° ${v >= 0 ? 'E' : 'W'}` : '?'; }
  function dimLabel(id) { const d = data && data.meta && (data.meta.dimensions || []).find(x => x.id === id); return d ? d.label.toLowerCase() : id; }
  // Every site that has a score for this target and profile, best first
  function ranked(t, p) { return (data && data.sites || []).filter(s => total(s, t, p) !== null).sort((a, b) => total(b, t, p) - total(a, t, p)); }

  /* ---- 1. answers built from results.json ---- */
  function dataAnswer(q) {
    if (!data) return null;
    const t = targetOf(q), p = profileOf(q);

    // about the selected site
    if (has(q, ['this site', 'this place', 'selected', 'this spot', 'this tile', 'here ']) && ctx.site) {
      const s = ctx.site, tt = ctx.target, pp = ctx.profile, sc = s.scores && s.scores[tt] && s.scores[tt][pp];
      if (!sc || sc.total == null) return { text: `I don't have enough data to score ${where(s)} for ${profileName(pp)}.` };
      const dims = Object.entries(sc.dims || {}).filter(([, v]) => typeof v === 'number').sort((a, b) => b[1] - a[1]);
      let txt = `${where(s)} scores ${round1(sc.total)}/100 against ${targetName(tt)} for ${profileName(pp)}.`;
      if (dims.length) txt += ` Its strongest point is ${dimLabel(dims[0][0])} (${round1(dims[0][1])}), its weakest is ${dimLabel(dims[dims.length - 1][0])} (${round1(dims[dims.length - 1][1])}).`;
      if (isGem(s, tt)) txt += " It's one of our hidden gems: very similar to known analog sites, but not studied as one.";
      if (s.known_analog) txt += ` It's also a known analog site: ${s.known_analog}.`;
      txt += ' And like everywhere on Earth: real gravity, thick air and a magnetic field. That part never matches.';
      return { text: txt };
    }

    // hidden gems
    if (has(q, ['gem', 'hidden', 'unknown', 'undiscovered', 'new site', 'unstudied'])) {
      const gems = ranked(t, p).filter(s => isGem(s, t));
      if (!gems.length) return { text: `I don't have hidden gems for ${targetName(t)} in this dataset yet. A hidden gem is a site that scores high and looks like known analogs, but nobody uses it as one.` };
      const top = gems.slice(0, 3).map(s => `${where(s)}: ${total(s, t, p)}/100`).join('\n• ');
      return { text: `${gems.length} hidden gems for ${targetName(t)}. The best for ${profileName(p)}:\n• ${top}\nThey're very similar to known analogs, but nobody studies them as one. Yet.`,
               action: { label: 'Show the best one on the map', site: gems[0], target: t, profile: p } };
    }

    // a known analog by name
    for (const a of (data.known_analogs || [])) {
      const key = norm(a.name).split(' ').filter(w => w.length > 3)[0];
      if (key && q.includes(' ' + key)) {
        const sc = a.scores && a.scores[t] && a.scores[t][p];
        if (!sc || sc.total == null || sc.global_rank == null) return { text: `${a.name} is a known analog site, but it isn't scored here${a.tile_note ? ': ' + a.tile_note : ''}.` };
        const n = data.meta && data.meta.tiles_scored && data.meta.tiles_scored[t];
        const pct = n ? (sc.global_rank / n * 100) : null;
        const rankTxt = pct == null ? `rank #${sc.global_rank}` : (pct <= 50 ? `top ${pct < 0.1 ? '0.1' : pct < 1 ? pct.toFixed(1) : Math.round(pct)}% of Earth's barren land (#${sc.global_rank})` : `in the lower half (#${sc.global_rank} of ${n})`);
        return { text: `${a.name} scores ${round1(sc.total)}/100 against ${targetName(t)} for ${profileName(p)}: ${rankTxt}.${a.used_for ? ' It\'s used for ' + a.used_for + '.' : ''}` };
      }
    }

    // best / top sites
    if (has(q, ['best', 'top ', 'highest', 'most similar', 'closest', 'recommend', 'where should', 'good place', 'ideal'])) {
      const list = ranked(t, p);
      if (!list.length) return { text: `I don't have scored sites for ${targetName(t)} yet.` };
      const [a, b, c] = list;
      let txt = `For ${targetName(t)} with the ${profileName(p)} profile, the best match is ${where(a)}, with ${total(a, t, p)}/100.`;
      if (b) txt += ` Next: ${where(b)} (${total(b, t, p)})${c ? ` and ${where(c)} (${total(c, t, p)})` : ''}.`;
      return { text: txt, action: { label: 'Show it on the map', site: a, target: t, profile: p } };
    }

    // counts
    if (has(q, ['how many sites', 'how many tiles', 'how many places', 'how many analog', 'number of sites', 'number of tiles'])) {
      const n = data.meta && data.meta.tiles_scored && data.meta.tiles_scored[t];
      return { text: `${n ? `We scored ${n.toLocaleString('en')} tiles of Earth's barren land against ${targetName(t)}. ` : ''}The map shows the ${(data.sites || []).length.toLocaleString('en')} best ones, and ${(data.known_analogs || []).length} known analog sites for comparison.` };
    }

    // validation
    if (has(q, ['validat', 'proof', 'prove', 'trust', 'accurate', 'reliable', 'does it work', 'known analog'])) {
      const n = data.meta && data.meta.tiles_scored && data.meta.tiles_scored[t];
      const body = (t === 'jezero' ? 'mars' : 'moon');
      const list = (data.known_analogs || []).filter(a => norm(a.analog_for || '').includes(body));
      const scored = list.filter(a => a.scores && a.scores[t] && a.scores[t][p] && a.scores[t][p].global_rank != null);
      const good = n ? scored.filter(a => a.scores[t][p].global_rank / n <= .1).length : null;
      if (good == null || !scored.length) return { text: "We check the method on famous analog sites (Atacama, Haughton Crater, Mauna Kea…): if it works, they should rank high. Open the Validation tab to see it." };
      return { text: `We test the method on sites scientists already use. Right now, ${good} of ${scored.length} known ${body === 'mars' ? 'Mars' : 'Moon'} analogs rank in the top 10% of Earth's barren land for ${profileName(p)}. The Validation tab has the full table.` };
    }
    return null;
  }

  /* ---- 2. the built-in FAQ ----
     k = words or phrases that trigger the answer (matched from the start of a word, like has()).
     topic: true = a general "what is X" card. It only answers a short question ("Mars?") or a
     definition question ("What is Jezero?", "Tell me about the Moon"). A precise question that
     just mentions the word ("How long is a day on Mars?") is left to the AI. */
  const FAQ = [
    { k: ['hello', 'hi ', 'hey ', 'salam', 'bonjour', 'yo '], a: () => pick(["Hello, Earthling! What do you want to know?", "Hi there! Ask me about the map, the scores, or the Moon and Mars."]) },
    { k: ['thank', 'merci', 'shukran'], a: () => pick(["Anytime! Zorp.", "You're welcome, Earthling!"]) },
    { k: ['who are you', 'your name', 'what are you'], a: () => "I'm Orbi, the AI assistant of the Planetary Analog Finder, built by Team FAKERS for the NASA Space Apps Challenge 2026. My hoodie says it all." },
    { k: ['fakers', 'team', 'who made', 'who built', 'creator'], a: () => "Team FAKERS built this for the NASA Space Apps Challenge 2026: 6 people on data, science, design and storytelling. I'm the one with antennae." },
    { k: ['what is this', 'this project', 'what does this', 'what is the project', 'about this', 'purpose', 'what do you do'], a: () => "We scan the whole Earth to find places that behave like a Moon base site or a Mars landing site. Testing rovers and gear on Earth is cheap; doing it up there is not. So each patch of barren land gets a similarity score, dimension by dimension." },
    { k: ['how does it work', 'how does this work', 'how do you', 'how is the score', 'how are the scores', 'how are scores', 'how do the scores', 'method', 'score', 'scoring', 'calculat', 'comput', 'algorithm', 'machine learning', 'ml ', 'cluster', 'k means'], a: () => "Each 0.25° tile of barren land is compared to the target in real units: temperature range, slope, roughness, albedo, rock type, dryness, dust, sun angle. Each dimension gets a 0–100 score (how close it gets compared to the rest of Earth), and a mission profile weights them into a total. Clustering then spots look-alikes of known analogs." },
    { k: ['data', 'satellite', 'source', 'modis', 'gibs'], a: () => "Earth side: NASA MODIS (temperature, albedo, vegetation), GPM (rain), ASTER (rock composition), Copernicus DEM (terrain), aerosol data for dust. Moon and Mars side: LRO (LOLA, Diviner), MOLA and other NASA mission data. The map background is NASA GIBS imagery." },
    { k: ['profile', 'rover navigation', 'polar'], a: () => "Three mission profiles: rover navigation (slopes, roughness, dust), geology / science (rock type, dryness) and polar & thermal ops (cold, low sun). Same data, different priorities." },
    { k: ['break', 'limit', 'differ', 'not similar', 'gravity', 'atmosphere', 'radiation', 'weakness'], a: () => "Earth can never copy three things: gravity (the Moon has about 1/6 of ours, Mars about 38%), the atmosphere (vacuum on the Moon, thin CO2 on Mars) and radiation, since Earth is shielded by its air and magnetic field. Every site card lists these, plus the dimensions where it scores low." },
    { k: ['how do i', 'how can i', 'how to use', 'help', 'navigate', 'click'], a: () => "Pick a target (Mars or Moon) and a mission profile at the top, then click any dot on the map: you'll see its score, a radar chart and where the analogy breaks. The Top sites and Validation tabs are in the side panel." },
    { k: ['morocco', 'maroc', 'tissint'], a: () => "Fun fact: a real Martian meteorite, Tissint, fell in Morocco in 2011 near Tata. Morocco also has plenty of dry, rocky desert worth checking on the map." },
    { k: ['joke', 'funny'], a: () => pick(["Why did the alien skip the Moon base party? No atmosphere.", "I tried to park my saucer in the Atacama. Too many rovers."]) },
    { topic: true, k: ['analog'], a: () => "An analog is a place on Earth that shares some conditions with the Moon or Mars: rocks, terrain, cold, dryness, dust… Teams use them to test instruments and train before flying. No place matches everything, so we show what matches and what doesn't." },
    { topic: true, k: ['jezero'], a: () => "Jezero Crater on Mars is an ancient lake with a river delta. The Perseverance rover has been exploring it since 2021, looking for signs of past life." },
    { topic: true, k: ['south pole', 'lunar', 'moon base', 'artemis'], a: () => "The lunar south pole is where NASA's Artemis program wants to go: some craters there never see sunlight and may hold water ice, while nearby ridges get sunlight most of the time. The sun stays very low on the horizon." },
    { topic: true, k: ['mars'], a: () => "Mars is cold, dry and dusty, with thin CO2 air and about 38% of Earth's gravity. Our Mars target is Jezero Crater." },
    { topic: true, k: ['moon'], a: () => "The Moon has no air, extreme temperatures and about 1/6 of Earth's gravity. Our Moon target is the south pole, where future bases are planned." }
  ];
  // "what is (a/an/the) …", "tell me about (the) …": the start of a definition question
  const DEFINITION = /^ (?:what is|what s|what are|who is|tell me about|explain|describe|define) (?:a |an |the )?/;
  function faqAnswer(q) {
    const short = q.trim().split(' ').length <= 3;
    const opener = q.match(DEFINITION);
    for (const f of FAQ) {
      const hit = f.topic
        ? f.k.some(k => (short && q.includes(' ' + k)) || (opener && q.slice(opener[0].length).startsWith(k)))
        : has(q, f.k);
      if (hit) return { text: f.a() };
    }
    return null;
  }

  /* ---- 3. the AI (through the relay) ---- */
  // What the AI is told about the screen: the selection, the open site and the 5 best sites.
  function llmContext() {
    const t = ctx.target, p = ctx.profile, s = ctx.site;
    const sc = s && s.scores && s.scores[t] && s.scores[t][p];
    return {
      target: t, target_name: targetName(t),
      profile: p, profile_name: profileName(p),
      // the selected site: region, coordinates, total and per-dimension scores (0–100) for this target × profile
      site: s ? { region: s.region || 'Unnamed area', lat: s.lat, lon: s.lon,
                  total: sc && sc.total != null ? sc.total : null, dims: (sc && sc.dims) || {} } : null,
      // the 5 best sites for this target × profile
      top_sites: ranked(t, p).slice(0, 5).map(x => ({ region: x.region || `Unnamed area (${fmtLat(x.lat)}, ${fmtLon(x.lon)})`, score: total(x, t, p) }))
    };
  }
  const QUOTA_REPLY = { text: "Too many questions today, my antenna needs a break! But I know these ones by heart: pick a suggestion just below.", pointToChips: true };
  async function llmAnswer(question) {
    if (!config.llmEndpoint) return null;
    if (quotaReached) return QUOTA_REPLY;          // do not ask again: the answer would be the same
    const ctrl = new AbortController(); const to = setTimeout(() => ctrl.abort(), 12000);
    try {
      const res = await fetch(config.llmEndpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: ctrl.signal,
        body: JSON.stringify({ question, context: llmContext() }) });
      if (res.status === 429) { quotaReached = true; return QUOTA_REPLY; }   // daily AI quota used up
      if (!res.ok) return null;
      const j = await res.json(); return j && j.answer ? { text: String(j.answer).trim() } : null;
    } catch (e) { return null; } finally { clearTimeout(to); }
  }

  async function answer(raw) {
    const q = ' ' + norm(raw) + ' ';
    return dataAnswer(q) || faqAnswer(q) || await llmAnswer(raw) || {
      text: "Hmm, that one's beyond my antennae. Try asking about the best sites for Mars or the Moon, hidden gems, how the scores work, or where the analogy breaks."
    };
  }

  /* ---------- public API ---------- */
  refreshMute();
  window.Orbi = {
    config, greet, dock, open, close,
    setData(d) { data = d; },
    setContext(c) { ctx = Object.assign({}, ctx, c); if (state === 'open') renderChips(); },
    say(text) { if (state === 'open') botSay(text); },
    onShowSite: null
  };
})();
