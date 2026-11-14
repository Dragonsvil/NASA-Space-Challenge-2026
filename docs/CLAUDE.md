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
      {"id": "rover",   "label": "Rover navigation"},
      {"id": "geology", "label": "Geology / science"},
      {"id": "polar",   "label": "Polar & thermal ops"}
    ]
  },
  "targets": {
    "jezero": {"name": "Jezero Crater", "body": "Mars", "lat": 18.4, "lon": 77.5,
               "values": {"slope": 0, "...": 0}, "dims": ["temp_range", "..."]},
    "lunar_south_pole": {"name": "Lunar south pole", "body": "Moon", "values": {}, "dims": []}
  },
  "sites": [
    {
      "id": "t_104233", "lat": -23.75, "lon": -69.25, "region": "Chile",
      "values": {"slope": 4.1, "temp_range": 38, "...": 0},
      "scores": {
        "jezero": {
          "rover":   {"total": 87, "dims": {"slope": 94, "albedo": 71, "...": 0}},
          "geology": {"total": 81, "dims": {}},
          "polar":   {"total": 40, "dims": {}}
        },
        "lunar_south_pole": {}
      },
      "cluster": 3,
      "hidden_gem": false,
      "known_analog": "Atacama Desert"
    }
  ],
  "known_analogs": [
    {"name": "Atacama Desert", "lat": -24.5, "lon": -69.25, "analog_for": "Mars",
     "used_for": "life detection, rover tests",
     "scores": {
       "jezero": {
         "rover":   {"total": 83, "global_rank": 1640, "percentile": 0.82},
         "geology": {"total": 71, "global_rank": 18540, "percentile": 9.27},
         "polar":   {"total": 60, "global_rank": 5920, "percentile": 2.96}
       },
       "lunar_south_pole": {}
     }}
  ]
}
```
Notes:
- `sites` contains only the **top ~500 tiles per target × profile** (not all 200k tiles), so the file stays small.
- Each target only uses the dimensions listed in its `dims` (e.g. `sun_angle` only for the Moon, `dust` only for Mars).
- `meta.tiles_scored[target]` = number of Earth tiles the pipeline scored for that target (all of them, not only the ones in `sites`).
- `known_analogs[].scores[target][profile]` is the analog tile's result among **all** scored tiles: `total` (0–100)
  and `global_rank` (1 = best tile on Earth). It is present **even when the analog's tile is not in `sites`**.
- The site **always computes** "top X% of Earth" itself as `global_rank / meta.tiles_scored[target] × 100` (lower is better).
  The `percentile` field is **optional and ignored** by the site (the pipeline's convention may differ): never read it in the UI.
  So `global_rank` and `tiles_scored` are the two fields the Validation tab really needs.
- Any value can be `null` (missing data): the UI must handle it.

## "Where the analogy breaks" (always shown on a site card)
Always list: gravity (Moon ≈ 1/6 g, Mars ≈ 0.38 g), atmosphere (Moon: vacuum; Mars: thin CO2, ~1% of Earth's pressure),
radiation (Earth is shielded by its atmosphere and magnetic field). Plus every dimension of that site scoring below 40.

## Rules
- Code simple and commented: teammates with basic coding skills must be able to read it.
- Never invent scientific numbers in the UI: everything comes from results.json or from the text above.
- Work on mock data (`data/results.mock.json`) until the real file arrives; switching must be one line.
