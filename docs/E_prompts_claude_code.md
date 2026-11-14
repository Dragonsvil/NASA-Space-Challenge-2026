# Role E: Website, map & Orbi — tasks + Claude Code prompts

Setup (5 min): create an empty folder/repo `analog-finder-site`, put `CLAUDE.md` at its root,
put `orbi_mascot.html` in a `reference/` folder, open Claude Code in that folder.
**One prompt = one step.** Check the result in the browser before the next prompt.
Commit to Git after each step that works (`git commit -am "step X"`), so you can always go back.

---

## Step 0 — Tell D the data contract (now, 2 min)
Send D the `CLAUDE.md` "Data contract" section. Two key points for D:
1. Export `results.json` in exactly that shape.
2. Only the **top ~500 tiles per target × profile**, not the 200k tiles (the browser would choke).

---

## Step 1 — Skeleton on mock data (now → 13:30)
Skill: **pick-ui-library**

> Read CLAUDE.md. Use the pick-ui-library skill to choose the radar-chart library (lightweight, CDN, no build step) and confirm Leaflet for the map. Then create the site skeleton:
> - `index.html`, `css/style.css`, `js/app.js`, `data/results.mock.json`
> - Generate realistic mock data following the data contract exactly: 2 targets, 3 profiles, ~300 sites spread over real deserts, polar and volcanic regions, ~10 known analogs at their real locations, a few `hidden_gem: true`, and some `null` values.
> - Layout: top bar (title + target selector Jezero / Lunar south pole + mission-profile selector), full-screen dark world map, side panel on the right (empty for now).
> - Map: sites as circle markers colored by total score for the selected target × profile; known analogs with a distinct marker; hidden gems with a star.
> - A single constant at the top of app.js switches between mock and real data.
> Keep the code simple and commented. Don't style it heavily yet.

## Step 2 — Site panel + radar chart (13:30 → 16:00)

> When I click a site on the map, fill the side panel with:
> 1. Site header: region, coordinates, total score as a big number, badges (Hidden gem / Known analog).
> 2. Radar chart: one axis per dimension used by the selected target, site scores (0–100) vs. the target (100 on every axis).
> 3. Dimension list: label, score bar, the site's real value with unit, and the target's value.
> 4. "Works for…": the 2 best dimensions turned into a plain sentence (e.g. "Good for testing rover navigation on slopes similar to Jezero").
> 5. "Where the analogy breaks" in red: always gravity, atmosphere, radiation (text from CLAUDE.md), plus every dimension below 40.
> Changing target or profile must update the map colors and the open panel.

## Step 3 — Ranking + validation view (16:00 → 18:00)

> Add a "Top sites" tab in the side panel: top 10 sites for the current target × profile, clickable (fly the map to the site and open its card).
> Add a "Validation" tab: table of known analogs with their score and rank for the current target × profile, to show that the method finds known sites. Highlight in green those in the top 10%.

## Step 4 — Landing / intro screen (18:00 → 20:00)
Skills: **prototype**, then **apple-design**

> Use the prototype skill to make 2 versions of an intro screen shown before the map: project name, one-sentence pitch ("We scan the whole Earth to find the best places to prepare for the Moon and Mars"), and an "Explore the map" button. Dark space theme. Show me both side by side.

(Pick one, then:)

> Apply the apple-design skill to the chosen intro and to the top bar and side panel: typography, spacing, glass/depth for the panel. Keep the map readable.

**Limit: 1h for this step.** It's polish, not core.

## Step 5 — Plug real data (Sat night / Sun morning, when D delivers)

> The real data is in `data/results.json`. Switch the constant to real data. Check that everything works: list any field in the real file that does not match the contract, and handle it in the code rather than asking to change the data. Make sure null values and missing dimensions don't break the radar chart or the panel.

## Step 6 — Stress test (Sun ~10:00 → 11:30)
Skill: **break-ui**

> Use the break-ui skill on the site: very long region names, sites with all values null, a target with only 3 dimensions, 0 sites for a profile, 2000 sites, a slow network loading results.json (add a loading state), clicking fast between sites. Fix what breaks.

## Step 7 — Mobile (Sun 11:30 → 12:30)
Skill: **mobile-native**

> Use the mobile-native skill: on phones the side panel becomes a bottom sheet, selectors stay reachable with a thumb, the map stays usable. The jury may open the link on a phone.

## Step 8 — Integrate Orbi (Sun 14:00 → 17:00, only if steps 1–5 work)
Skills: **animate**, **find-animation-opportunities**

> Read `reference/orbi_mascot.html`. Extract the mascot into `js/orbi.js` and `css/orbi.css` (remove the demo page parts) and include him on every page.
> Connect him to the site:
> - Intro screen: he invites the user to click him, then plays the pitch.
> - Target and profile selectors: `data-orbi` lines explaining each choice (keep them short and fun).
> - Clicking a site: `Orbi.sayAll([...])` with the site's real total score, best dimension, weakest dimension, and one "breaks" line, built from results.json.
> - Clicking a hidden gem: a special excited line + `Orbi.jump()`.
> - He must never cover the side panel or the map controls (on mobile: smaller and in a corner, speech bubble above).
> Use the animate skill for any new animation.

Then:

> Use find-animation-opportunities on the whole site. Only apply the 2–3 that clearly help understanding (e.g. map flying to a site, panel opening). Skip the rest.

## Step 9 — Final polish + deploy (Sun 17:00 → 18:30)
Skills: **emil-design-eng**, **review-animations**

> Use the emil-design-eng skill for a final polish pass, then review-animations on all motion. Don't add features. Then prepare the site for GitHub Pages (relative paths, no local-only files) and give me the exact steps to publish it.

Test the public link on another computer and on a phone. Send the link to F for the submission.

---

## Tips for your Claude usage
- Start a **new Claude Code session per step**: CLAUDE.md keeps the context, so you don't burn tokens on old history.
- If something breaks after 2 attempts, `git checkout .` and re-prompt more precisely, instead of looping.
- Don't let polish eat the evening: the checkpoint is **real data in the site by Saturday midnight**.
