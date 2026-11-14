# Planetary Analog Finder — data pipeline (NASA Space Apps 2026)

## Context
NASA Space Apps challenge: identify places on Earth that are analogs of candidate Moon-base and Mars sites.
Deadline: Sunday 15 Nov 2026, 23:59 Morocco time (submission at 22:30). Team of 6, basic Python, AI-assisted coding.
This repo is the **data pipeline: scoring, clustering, validation** (role D, also team coordinator).
Inputs come from teammates A and B (Earth features from Google Earth Engine) and C (targets, known analogs).
Output is `out/results.json`, consumed by the website (role E). **The results.json contract below is fixed: do not change it without telling E.**

The method: Earth land is split into 0.25° tiles. Each tile is compared to a target site
(Jezero Crater on Mars, or the lunar south pole) dimension by dimension, **in physical units**.
Each dimension gets a 0–100 score = "how close this tile is, compared to the rest of Earth".
A weighted total is computed for 3 mission profiles. K-Means clustering flags "hidden gems":
unstudied tiles similar to known analogs. Known analogs are used to validate the method.

## Stack
- Python 3, pandas, numpy, scikit-learn, `reverse_geocoder` (offline, for region names). Nothing else unless asked.
- Every script runnable as `python src/<name>.py`. `python src/run_all.py` runs the whole pipeline.
- `data/` = inputs (CSV from teammates), `out/` = generated files. Never commit raw Earth Engine exports > 50 MB.

## Input files (data/)
earth_features.csv   tile_id, lat, lon, lst_min_night, lst_max_day, lst_range, albedo, ndvi, precip_mm,
                     slope_mean, slope_std, mafic_idx, quartz_idx, dust_aod, max_sun_elev
targets.csv          target, feature, value, unit, source        (long format, one row per value)
known_analogs.csv    name, lat, lon, analog_for, used_for

- `tile_id` = f"{lat:.3f}_{lon:.3f}" of the tile **center** on the 0.25° grid. A and B must use the same formula, otherwise the merge silently fails.
- Temperatures in °C (MODIS LST raw = Kelvin × 0.02: must be converted before use), albedo 0–1, slopes in degrees, precipitation in mm/yr.
- Target `value` may be a number, `low` / `med` / `high` (categorical), or `n/a`.

## Dimensions (CSV column → results.json id)
| results.json id | label                         | from CSV column | unit  | used by          |
|-----------------|-------------------------------|-----------------|-------|------------------|
| temp_range      | Day–night temperature range   | lst_range       | °C    | both             |
| temp_min        | Minimum temperature           | lst_min_night   | °C    | both             |
| albedo          | Albedo                        | albedo          |       | both             |
| slope           | Slope                         | slope_mean      | °     | both             |
| roughness       | Roughness                     | slope_std       | °     | both             |
| mafic           | Basaltic rock (mafic index)   | mafic_idx       |       | both             |
| aridity         | Aridity                       | precip_mm       | mm/yr | both             |
| dust            | Dust                          | dust_aod        | AOD   | Mars only        |
| sun_angle       | Low sun angle                 | max_sun_elev    | °     | Moon only        |
Not scored: lst_max_day, quartz_idx (kept in data, may be shown later). NDVI is a **filter** for clustering, not a score.

## Scoring method
For each tile t, target T, dimension d:
    gap(t,d)   = |earth_value(t,d) - target_value(T,d)|          (real units, NEVER z-score per planet)
    score(t,d) = 100 * (1 - percentile_rank(gap(t,d)) among all Earth tiles), ties averaged, rounded to int
    total(t,p) = Σ_d w(p,d) * score(t,d) / Σ_d w(p,d)             over dims that are valid for this tile and target

Special cases:
- Categorical target (low/med/high) → use the 15th / 50th / 85th percentile of the Earth distribution of that feature. Print the value used.
- Target value `n/a`, or dimension not in that target's dims → dimension skipped for that target.
- Earth value NaN → that dimension skipped for that tile, weights renormalized. If more than half the dims are NaN → tile dropped.
- max_sun_elev: Earth value = 90 − |lat| + 23.44, clipped to [0, 90].

## Mission profiles (weights 0–3, tuned Sunday; keep in ONE dict at the top of src/score.py)
| dim        | rover | geology | polar |
|------------|-------|---------|-------|
| slope      | 3     | 1       | 1     |
| roughness  | 3     | 1       | 1     |
| albedo     | 2     | 1       | 1     |
| mafic      | 1     | 3       | 0     |
| aridity    | 1     | 3       | 1     |
| temp_min   | 1     | 1       | 3     |
| temp_range | 1     | 1       | 3     |
| dust       | 2     | 1       | 0     |
| sun_angle  | 2     | 0       | 3     |

## Clustering and hidden gems
1. Keep arid / polar / volcanic tiles: ndvi < 0.2 OR lst_min_night < -20 °C.
2. StandardScaler on Earth features only (Earth vs Earth is fine), K-Means k = 8..12, pick by silhouette.
3. Clusters containing a known analog = "analog clusters".
4. Hidden gem = tile in an analog cluster AND total in the top 5% for some target × profile AND > 300 km (haversine) from every known analog.

## Validation
For each known analog: nearest valid tile (within 50 km, say so if not the exact tile), its percentile rank per target × profile.
Success = most analogs in the top 10% of at least one profile. Output out/validation.csv + out/validation.md (table for the slides).
If analogs rank badly: check units and target values FIRST, weights last.

## OUTPUT CONTRACT: out/results.json (for the website, role E)
```json
{
  "meta": {
    "generated": "2026-11-14T20:00:00Z",
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
      {"id": "rover",   "label": "Rover navigation",    "weights": {"slope": 3, "...": 0}},
      {"id": "geology", "label": "Geology / science",   "weights": {}},
      {"id": "polar",   "label": "Polar & thermal ops", "weights": {}}
    ]
  },
  "targets": {
    "jezero": {"name": "Jezero Crater", "body": "Mars", "lat": 18.4, "lon": 77.5,
               "values": {"slope": 0, "...": 0}, "sources": {"slope": "..."}, "dims": ["temp_range", "..."]},
    "lunar_south_pole": {"name": "Lunar south pole", "body": "Moon", "values": {}, "sources": {}, "dims": []}
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
     "used_for": "life detection, rover tests"}
  ]
}
```
Rules for this file:
- `sites` = union of the top 500 tiles per target × profile, PLUS every hidden-gem tile, PLUS the tile of every known analog (so the site can show validation even when an analog is not top 500). Each site carries ALL its scores (both targets, all profiles).
- `id` = "t_" + row index; keep `tile_id` mapping in out/site_index.csv.
- `known_analog` = analog name if the tile is a known analog's tile, else null. `region` = country (+ nearest place if cheap) from reverse_geocoder.
- `meta.profiles[].weights` and `targets[].sources` are additions E did not ask for: harmless, E can ignore them.
- Numbers rounded (scores int, values 1–2 decimals). Missing = null. Keep the file under ~5 MB; print its size.
- `values` holds RAW physical values, never scores. Never invent numbers: everything comes from the input CSVs.

## Rules
- Simple, commented code: teammates with basic Python must be able to read it.
- Any script with a missing input file must fail with a clear message saying which teammate provides it.
- Until real data arrives, use src/make_fake_data.py outputs. Switching to real data = replacing files in data/, no code change.
