# Planetary Analog Finder — website (NASA Space Apps 2026)

## Context
NASA Space Apps challenge: identify places on Earth that are analogs of candidate Moon-base and Mars sites.
Deadline: Sunday 15 Nov 2026, 23:59 Morocco time. This repo is the **website** (role E).
The data pipeline (Python + Google Earth Engine) is done by teammates and delivers `data/results.json`.

The method: Earth land is split into 0.25° tiles. Each tile is compared to a target site
(Jezero Crater on Mars, or the lunar south pole) dimension by dimension, in physical units.
Each dimension gets a 0–100 score = "how close this tile is, compared to the rest of Earth".
A weighted total is computed for 3 mission profiles: rover navigation, geology/science, polar & thermal ops.
K-Means clustering flags "hidden gems": unstudied tiles similar to known analogs.

## Stack (keep it simple)
- Static site, **no build step**: `index.html`, `css/`, `js/`, `data/`. Libraries from CDN.
- Map: Leaflet. Charts: one small library for the radar chart (decided once, see prompt 1).
- Deployed on GitHub Pages.
- Intro screen (`#intro` in `index.html`, `js/intro.js`, last section of `css/style.css`): shown on every visit, closed by
  "Explore the map" or Escape, skipped when the URL ends with `#map` (demo video). Its bottom-left corner stays free for the mascot.
- Mascot "Orbi" (animated alien guide) lives in `js/orbi.js` + `css/orbi.css`, API: `Orbi.say(text)`, `Orbi.sayAll([lines])`, `Orbi.wave()`, `Orbi.jump()`; any element with `data-orbi="text"` makes him talk on click.

## Data contract: data/results.json
```json
{
  "meta": {
    "generated": "2026-11-14T20:00:00Z",
    "tiles_scored": {"jezero": 200000, "lunar_south_pole": 200000},
    "dimensions": [
      {"id": "temp_range", "label": "Day–night temperature range", "unit": "°C"},
      {"id": "temp_min",   "label": "Minimum temperature",        "unit": "°C"},
      {"id": "albedo",     "label": "Albedo",                     "unit": ""},
      {"id": "slope",      "label": "Slope",                      "unit": "°"},
      {"id": "roughness",  "label": "Roughness",                  "unit": "°"},
      {"id": "mafic",      "label": "Basaltic rock (mafic index)","unit": ""},
      {"id": "aridity",    "label": "Aridity",                    "unit": "mm/yr"},
      {"id": "dust",       "label": "Dust",                       "unit": "AOD"},
      {"id": "sun_angle",  "label": "Low sun angle",              "unit": "°"}
    ],
    "profiles": [
      {"id": "rover",   "label": "Rover navigation",    "weights": {"slope": 3, "...": 1}},
      {"id": "geology", "label": "Geology / science",   "weights": {}},
      {"id": "polar",   "label": "Polar & thermal ops", "weights": {}}
    ]
  },
  "targets": {
    "jezero": {"name": "Jezero Crater", "body": "Mars", "lat": 18.4, "lon": 77.5,
               "values": {"slope": 0, "...": 0}, "dims": ["temp_range", "..."],
               "sources": {"slope": "MOLA elevation model", "...": "..."}},
    "lunar_south_pole": {"name": "Lunar south pole", "body": "Moon", "values": {}, "dims": []}
  },
  "sites": [
    {
      "id": "t_104233", "lat": -23.75, "lon": -69.25, "region": "Chile, near San Pedro de Atacama",
      "values": {"slope": 4.1, "temp_range": 38, "...": 0},
      "scores": {
        "jezero": {
          "rover":   {"total": 87, "dims": {"slope": 94, "albedo": 71, "...": 0}},
          "geology": {"total": 81, "dims": {}},
          "polar":   {"total": 40, "dims": {}}
        },
        "lunar_south_pole": {}
      },
      "cluster": null,
      "hidden_gem": {"jezero": false, "lunar_south_pole": false},
      "known_analog": "Atacama Desert"
    }
  ],
  "known_analogs": [
    {"name": "Atacama Desert", "lat": -24.5, "lon": -69.25, "analog_for": "Mars",
     "used_for": "life detection, rover tests",
     "tile_note": "nearest valid tile, 12 km away",
     "scores": {
       "jezero": {
         "rover":   {"total": 83, "global_rank": 1640, "percentile": 0.82},
         "geology": {"total": 71, "global_rank": 18540, "percentile": 9.27},
         "polar":   {"total": 60, "global_rank": 5920, "percentile": 2.96}
       },
       "lunar_south_pole": {}
     }},
    {"name": "Rio Tinto", "lat": 37.7, "lon": -6.55, "analog_for": "Mars",
     "used_for": "astrobiology, drilling tests",
     "tile_note": "excluded: vegetated tile (NDVI 0.78)",
     "scores": null}
  ]
}
```
Notes:
- `sites` contains only the **top ~500 tiles per target × profile** (not all 200k tiles), so the file stays small.
- Each target only uses the dimensions listed in its `dims` (e.g. `sun_angle` only for the Moon, `dust` only for Mars).
- **Vegetated tiles (NDVI > 0.3) are excluded before scoring.** So `meta.tiles_scored[target]` = number of **barren-land** tiles
  scored for that target (all of them, not only the ones in `sites`). In the UI always write "top X% of Earth's barren land",
  never "top X% of Earth".
- `known_analogs[].scores[target][profile]` is the analog tile's result among **all** scored tiles: `total` (0–100)
  and `global_rank` (1 = best barren-land tile). It is present **even when the analog's tile is not in `sites`**.
- `known_analogs[].scores` can be `null` (tile not scored, e.g. vegetated). `known_analogs[].tile_note` is an optional
  short string from the pipeline (e.g. "excluded: vegetated tile (NDVI 0.78)", "nearest valid tile, 12 km away").
  Validation tab: scores null → the note is shown in place of the rank and the analog does **not** count in the "X of N" summary
  (the summary says how many were left out); scores present + note → the note is shown small under the rank.
- `targets[target].sources` = `{dimension id: citation text}` for the target values. Shown as a small citation next to each
  target value on the site card, and listed in a "Sources" section at the bottom of the card. A dimension may have no source.
- `sites[].hidden_gem` is a **per-target object** (`{"jezero": true, "lunar_south_pole": false}`), with at most
  **15 gems per target**. The old format, a boolean (`true`/`false`, same answer for every target), is still accepted
  (see `isHiddenGem()` in `js/app.js`). A site is shown as a gem **only for the currently selected target**;
  `null` or a target missing from the object means "not a gem". Never read `site.hidden_gem` directly in the UI: call `isHiddenGem(site)`.
- `sites[].cluster` can be `null`, and there can be zero hidden gems (mock data, or a target without any):
  the UI must look complete with zero hidden gems (14 Nov file: 15 gems for Jezero, none for the lunar south pole).
  Older files had hundreds of gems: nothing in the UI may assume a small number.
- On the map a hidden gem is a **score-coloured circle with a NASA-red ring**, slightly larger than a normal site,
  drawn on the same canvas as the other sites (no separate element per gem). The legend key is the same red-ringed
  circle. The red star ★ is used only in the badges, the hover label and the lists.
- Hidden-gem card: one sentence says why it is a gem, built from `cluster` (see `gemReason()` in `js/panel.js`):
  the known analogs whose own site (`known_analog` set) has the same `cluster` value →
  "Same terrain family as Atacama Desert and Mauna Kea, but not a known analog site."; none (or `cluster` null) →
  "Unstudied site with a high match."
- "Top sites" tab: an "All sites / ★ Hidden gems" choice lists the 10 best hidden gems for the selected target and
  profile (hidden when the target has no gem).
- `sites[].region` is "Country" or "Country, near Town" (can be long).
- `meta.profiles[].weights` exists in the file but is **ignored** by the site.
- The site **always computes** "top X% of Earth's barren land" itself as `global_rank / meta.tiles_scored[target] × 100` (lower is better).
  The `percentile` field is **optional and ignored** by the site (the pipeline's convention may differ): never read it in the UI.
  So `global_rank` and `tiles_scored` are the two fields the Validation tab really needs.
- `sites[].scores[target][profile].total` can be `null`: too much of the tile's data is missing, so the pipeline did not
  rank it for that profile. Such a site is **not drawn** on the map for that profile and is left out of "Top sites" and of
  the gem lists and legend (all of this goes through `getTotal()` in `js/app.js`). If its card is open when the user switches to that
  profile, the card shows "Not enough data to score this site for this profile." in a neutral style instead of the score
  (`lacksData()` in `js/app.js`). Same for `known_analogs[].scores[target][profile]`: `total` and `global_rank` can be
  `null`, the analog is then treated as not scored in the Validation tab.
- Dimension values (`sites[].values`) and dimension scores (`dims`) can be `null` (e.g. `mafic` over ice): the card shows
  "no data" for that dimension, the radar leaves a gap, and the dimension is not used in "Works for…" or "Where the analogy breaks".
- Any value can be `null` (missing data): the UI must handle it.

## "Where the analogy breaks" (always shown on a site card)
Always list: gravity (Moon ≈ 1/6 g, Mars ≈ 0.38 g), atmosphere (Moon: vacuum; Mars: thin CO2, ~1% of Earth's pressure),
radiation (Earth is shielded by its atmosphere and magnetic field). Plus every dimension of that site scoring below 40.

## Rules
- Code simple and commented: teammates with basic coding skills must be able to read it.
- Never invent scientific numbers in the UI: everything comes from results.json or from the text above.
- Work on mock data (`data/results.mock.json`) until the real file arrives; switching must be one line.
