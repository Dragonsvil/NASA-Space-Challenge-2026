# Planetary Analog Finder — data pipeline (NASA Space Apps 2026)

## Context
NASA Space Apps challenge: identify places on Earth that are analogs of candidate Moon-base and Mars sites.
Deadline: Sunday 15 Nov 2026, 23:59 Morocco time (submission at 22:30). Team of 6, basic Python, AI-assisted coding.
This repo is the **data pipeline: scoring, clustering, validation** (role D, also team coordinator).
Inputs come from teammates A and B (Earth features from Google Earth Engine) and C (targets, known analogs).
Output is `out/results.json`, consumed by the website (role E). `src/export_web.py` also copies it to
`../docs/data/results.json` (GitHub Pages only serves `docs/`). That copy is the ONLY file the pipeline writes outside `pipeline/`, and it is committed to git (never gitignore it). **The results.json contract below is fixed: do not change it without telling E.**

The method: Earth land is split into 0.25° tiles. Each tile is compared to a target site
(Jezero Crater on Mars, or the lunar south pole) dimension by dimension, **in physical units**.
Each dimension gets a 0–100 score = "how close this tile is, compared to the rest of Earth".
A weighted total is computed for 3 mission profiles. K-Means clustering flags "hidden gems":
unstudied tiles similar to known analogs. Known analogs are used to validate the method.

## Stack
- Python 3, pandas, numpy, scikit-learn, `reverse_geocoder` (offline, nearest town), `shapely` (country point-in-polygon
  with `data/ne_110m_admin_0_countries.geojson`, Natural Earth, downloaded once). Nothing else unless asked.
- Every script runnable as `python src/<name>.py`. `python src/run_all.py` runs the whole pipeline.
- `data/` = inputs (CSV from teammates), `out/` = generated files. Never commit raw Earth Engine exports > 50 MB.

## Input files (data/)
earth_features.csv   tile_id, lat, lon, lst_min_night, lst_max_day, lst_range, lst_mean_night, lst_mean_day, albedo, ndvi, precip_mm,
                     slope_mean, slope_std, mafic_idx, quartz_idx, dust_aod, max_sun_elev
targets.csv          target, feature, value, unit, source        (long format, one row per value)
known_analogs.csv    name, lat, lon, analog_for, used_for

- **The grid is defined ONLY in `../grid_config.py`** (single source of truth, shared with A and B). The pipeline
  imports it (`src/common.py` adds the parent folder to `sys.path`); never copy its formulas. If A/B change it, we follow.
- `tile_id` = **integer** `grid_config.tile_id(row, col)` = row × 1440 + col (row 0 = northernmost, col 0 = westernmost,
  origin −180, 90). `lat`/`lon` = the tile **center**, `grid_config.tile_center(row, col)` (e.g. −24.125, −70.125).
  A point → its tile: `grid_config.latlon_to_rowcol(lat, lon)` (`common.tile_of`).
- Missing values: exports write `grid_config.NODATA` (−9999). Every CSV is loaded through ONE function,
  `common.load_csv`, which turns −9999 (and any value < −9000) into NaN and prints the count per column.
  Never `pd.read_csv` an input directly. `check_csv.py` reports the same conversion and flags columns > 30% NaN after it.
- Temperatures in °C (MODIS LST raw = Kelvin × 0.02: must be converted before use), albedo 0–1, slopes in degrees, precipitation in mm/yr.
- `data/earth_features.csv` (gitignored) is BUILT by `src/merge_inputs.py` (step 0 of run_all) from A's and B's raw files in
  `data/raw/`, after the cleaning rules listed in README "Data cleaning". Extra columns precip_source,
  precip_era5_mm, land_frac are kept (not scored). Never edit it by hand.
- Target `value` may be a number, `low` / `med` / `high` (categorical), or `n/a`.

## Dimensions (CSV column → results.json id)
| results.json id | label                         | from CSV column | unit  | used by          |
|-----------------|-------------------------------|-----------------|-------|------------------|
| temp_range      | Mean day–night range          | lst_range       | °C    | both             |
| temp_min        | Mean night temperature        | lst_mean_night  | °C    | both             |
| albedo          | Albedo                        | albedo          |       | both             |
| slope           | Slope                         | slope_mean      | °     | both             |
| roughness       | Roughness                     | slope_std       | °     | both             |
| mafic           | Basaltic rock (mafic index)   | mafic_idx       |       | both             |
| aridity         | Aridity                       | precip_mm       | mm/yr | both             |
| dust            | Dust                          | dust_aod        | AOD   | Mars only        |
| sun_angle       | Low sun angle                 | max_sun_elev    | °     | Moon only        |
Not scored: lst_min_night, lst_max_day (3-year extremes), lst_mean_day (redundant: day = night + range, would
double-weight temperature), quartz_idx. Kept in the data, may be shown later. NDVI is a **filter**, not a score.

**Temperature is scored from MEANS only** (multi-year MODIS LST means, A's definitions):
- `temp_min` = `lst_mean_night`, the MEAN night temperature. The id stays "temp_min" so the website doesn't break.
- `temp_range` = `lst_range` = lst_mean_day − lst_mean_night, the MEAN day–night range. NOT lst_max_day − lst_min_night.
- Target values must use the same definitions (mean night temperature, mean day − mean night), see data/targets_HOWTO.md.

## Scoring method
Step 0 — filters BEFORE scoring, in this order. Column `scoring_filter` in out/scores.csv = the first rule that
removed the tile ("kept" otherwise). Print how many tiles each rule removes.
    1. "no DEM"    slope_mean is NaN. The Copernicus DEM only covers land: this is our land mask.
    2. "off land"  not inside a Natural Earth country polygon AND no reverse_geocoder town within 100 km
                   (the town rule keeps small islands like Lanzarote that the 110m polygons miss). `common.land_mask`.
    3. "vegetated" ndvi > 0.3 (vegetated land can never be a Moon/Mars analog). NDVI_MAX at the top of src/score.py.
    4. "no NDVI"   ndvi is NaN and |lat| <= 60 (polar tiles without NDVI are kept: ice/snow often has none).
    The kept tiles = the "scored population". Everything below (percentiles, categorical values, ranks) uses only them.
    (This is separate from the clustering filter, ndvi < 0.2 OR lst_mean_night < -10 °C.)
Safety rule, per target × profile (before any tile): if the target's dims (after n/a and dropped dims) carry
< 2/3 of the profile's TOTAL weight (MIN_PROFILE_WEIGHT), the profile is UNAVAILABLE for that target: total and
rank null for every tile, listed in meta.unavailable_profiles. Unavailable profiles are skipped by rule 6 below.
Then, per target (a tile failing these gets total = null for ALL profiles of that target and is not ranked;
column scored_<target> in out/scores.csv = True for the tiles that pass, = the tiles_scored population):
    5. more than half of the target's dims NaN → dropped.
    6. weight coverage: for EVERY profile, Σ w(p,d) over the dims the tile has / Σ w(p,d) over the target's dims
       must be ≥ 2/3 (MIN_WEIGHT_COVERAGE). Stops a tile with missing dims winning by renormalization.
       Applied over all profiles, not per profile, so every profile of a target ranks the same tiles and
       meta.tiles_scored stays one number per target.

For each tile t in the scored population, target T, dimension d:
    gap(t,d)   = |earth_value(t,d) - target_value(T,d)|          (real units, NEVER z-score per planet)
    score(t,d) = 100 * (1 - percentile_rank(gap(t,d)) among the scored population), ties averaged, rounded to int
    total(t,p) = Σ_d w(p,d) * score(t,d) / Σ_d w(p,d)             over dims that are valid for this tile and target
    global_rank(t,T,p) = rank of the int total among the scored population, 1 = best, ties → min rank

Special cases:
- Categorical target (low/med/high) → use the 15th / 50th / 85th percentile of that feature over the scored population. Print the value used.
- Target value `n/a`, or dimension not in that target's dims → dimension skipped for that target.
- Earth value NaN → that dimension skipped for that tile, weights renormalized (only if rules 5 and 6 above pass).
- max_sun_elev: Earth value = 90 − |lat| + 23.44, clipped to [0, 90].

## Mission profiles (weights 0–3, roadmap weights, FINAL: NOT tuned on the known analogs (overfitting); ONE dict at the top of src/score.py)
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
1. Keep arid / polar / volcanic tiles: ndvi < 0.2 OR lst_mean_night < -10 °C (MEAN night, consistent with scoring).
2. StandardScaler on Earth features only (Earth vs Earth is fine), K-Means k = 8..12, pick by silhouette.
   Population: tiles scored for at least one target (step 0 filters), then rule 1. random_state=42.
3. Hidden gems are PER TARGET. Body of the target: jezero = Mars, lunar_south_pole = Moon (`body` row of targets.csv).
   Candidate for target T = top 10% for T on its best profile (min over profiles of global_rank ≤ 0.10 × tiles_scored[T])
   AND in a cluster containing at least one known analog whose `analog_for` contains T's body ("Mars, Moon" counts for both)
   AND > 300 km (haversine) from every known analog (all analogs, even excluded ones).
4. Keep the best 15 per target (by best rank), greedily: skip a candidate within 300 km of a gem already kept for that target.
   Output: out/clusters.csv (tile_id, cluster, gem_<target>...), out/hidden_gems.csv (one row per target × gem:
   target, gem, tile_id, lat, lon, region, cluster, best_profile, best_total, best_rank, tiles_scored, top_pct, nearest_analog_km).

## Validation
For each known analog: nearest valid tile (within 50 km, say so if not the exact tile), its percentile rank per target × profile.
`analog_for` may separate bodies with ";" or ",": `common.load_csv` normalizes it to "Mars, Moon".
Two analogs on the same tile (own or validation tile) → WARNING and a note in validation.md (not independent checks).
Each analog is evaluated ONLY on its mapped target × profiles (rule fixed before the results, never edited to make
an analog pass): target = its body from analog_for (Mars → jezero, Moon → lunar_south_pole); profiles = keywords in
used_for (PROFILE_KEYWORDS in src/validate.py: rover|mobility|field operations|instrument|drilling → rover;
geology|geolog|volcan|mineral|impact|biosignature|life-detection|life detection|astrobiology|habitab → geology;
polar|permafrost|ice|cold → polar; several allowed). Success = top 10% on at least one of ITS mapped target × profiles;
method success = more than half of the analogs (excluded analogs count as failures). Report per-target counts too.
diagnose_validation.py uses the same rule. Output out/validation.csv + out/validation.md (table for the slides).
If analogs rank badly: check units and target values FIRST, weights last.

## OUTPUT CONTRACT: out/results.json (for the website, role E)
Written to `out/results.json` AND copied to `../docs/data/results.json` (the website folder; create it if missing).
Check it with `python src/check_results.py`.
```json
{
  "meta": {
    "generated": "2026-11-14T20:00:00Z",
    "tiles_scored": {"jezero": 184000, "lunar_south_pole": 184000},
    "dropped_dimensions": [{"id": "dust", "reason": "no data"}],
    "unavailable_profiles": [{"target": "lunar_south_pole", "profile": "geology", "reason": "available weight 7 of 12 ..."}],
    "dimensions": [
      {"id": "temp_range", "label": "Mean day–night range",       "unit": "°C"},
      {"id": "temp_min",   "label": "Mean night temperature",     "unit": "°C"},
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
      "hidden_gem": {"jezero": true, "lunar_south_pole": false},
      "known_analog": "Atacama Desert"
    }
  ],
  "known_analogs": [
    {"name": "Atacama Desert", "lat": -24.5, "lon": -69.25, "analog_for": "Mars",
     "used_for": "life detection, rover tests",
     "scores": {
       "jezero": {
         "rover":   {"total": 81, "global_rank": 312},
         "geology": {"total": 77, "global_rank": 1450},
         "polar":   {"total": 52, "global_rank": 40210}
       },
       "lunar_south_pole": {"rover": {}, "geology": {}, "polar": {}}
     },
     "tile_note": "nearest valid tile, 12 km away"}
  ]
}
```
Rules for this file:
- `hidden_gem` = object with one boolean per target (changed from a single boolean at E's request): true if the tile
  is one of that target's ≤ 15 hidden gems. check_results.py checks ≤ 15 true per target, > 300 km apart.
- `sites` = union of the top 500 tiles per target × profile, PLUS every hidden-gem tile (any target), PLUS the tile of every known analog (so the site can show validation even when an analog is not top 500).
  An analog with no valid tile (excluded by the vegetation filter, or none within 50 km) has no site: its
  `known_analogs` entry carries null scores and a `tile_note`. Each site carries ALL its scores (both targets, all profiles).
- `id` = "t_" + row index; keep `tile_id` mapping in out/site_index.csv (columns id, tile_id (grid_config integer), lat, lon).
- `known_analog` = analog name if the tile is a known analog's tile, else null. `region` = "Country, near Town".
  Country: lat < -60 → "Antarctica"; else the Natural Earth 110m polygon containing the point (shapely); if none
  (small islands, coasts), the country of reverse_geocoder's nearest town only if that town is < 100 km away;
  never snap to the nearest polygon (Lanzarote would become Morocco). ", near Town" only if the town is < 100 km.
  Nothing found → null.
- `meta.tiles_scored[target]` = number of Earth tiles with a valid total for that target (added at E's request).
  This is the ranking population: tiles that passed all of step 0 (land mask, vegetation) and rules 5–6 for that
  target (see Scoring method). It is NOT the (stricter) clustering filter population.
  The same tiles are valid for every profile of a target (NaN/drop rules are per tile × target), so one count per target.
- `known_analogs[].scores` (added at E's request): for BOTH targets and ALL 3 profiles, even if the analog is not top 500.
  - `total` = the tile's total (same number as in `sites`).
  - `global_rank` = rank of that total among all `tiles_scored` tiles for that target × profile, 1 = best on Earth,
    ties get the best (minimum) rank (pandas `rank(method="min", ascending=False)`).
  - No percentile field: the site computes it as `global_rank / tiles_scored`.
  - Tile used = the tile containing the analog's coordinates. If it has no valid total (ocean / coast / NaN), use the
    nearest valid tile within 50 km (haversine) and add `"tile_note": "nearest valid tile, X km away"` (X rounded to int).
    Exact tile → no `tile_note` key. No valid tile within 50 km → `total` and `global_rank` null,
    `"tile_note": "no valid tile within 50 km"`.
  - Exception: if the analog's own tile exists but was removed by the vegetation filter, do NOT substitute a
    neighbour: `total` and `global_rank` null, `"tile_note": "excluded: vegetated tile (NDVI 0.42)"`
    (or `"excluded: no NDVI, not polar"`). Same wording in out/validation.csv / validation.md. Never silently missing.
    Own tile removed as "no DEM" / "off land", or by rules 5–6: that is the ocean/coast/NaN case, use the nearest valid tile.
  - This must be the same tile as the analog's entry in `sites` (`known_analog` field) and in out/validation.csv.
- `meta.dropped_dimensions` (always present, `[]` if none): dimensions whose Earth column is 100% empty
  (e.g. dust_aod not exported). score.py never scores them (warning printed); they stay in `meta.dimensions`
  (labels) and in the weights. DISPLAY ONLY (E's request): a dropped dim stays in `targets[].dims` of a target that
  has a value for it (dust in jezero's dims; not in lunar_south_pole's, whose value is n/a), with
  `targets[].values[dim]` = null and the reason appended to `sources[dim]`. It has NO score anywhere: absent from
  every `sites[].scores[t][p].dims`. Totals and ranks are unaffected. check_results.py checks this.
- `known_analogs[].validated_targets` / `validated_profiles` (E's request): the target(s) and profile(s) the analog is
  validated on, from validate.analog_mapping (analog_for → targets, used_for keywords → profiles). export_web.py calls
  the same function; check_results.py recomputes it and compares with out/validation.csv (site = validation.md).
- `targets[].sources` = the short citation from targets.csv `source` (caveats are in README "Target values").
- `meta.unavailable_profiles` (always present, `[]` if none): target × profiles failing the safety rule. Every
  site's and known analog's `total` (and `global_rank`) is null for them; check_results.py checks it.
- `meta.profiles[].weights` and `targets[].sources` are additions E did not ask for: harmless, E can ignore them.
- Weights in `meta.profiles[].weights` are for DISPLAY only. The website does not recompute scores (no sliders):
  `total` and `global_rank` in this file are the single source of truth. Changing weights = rerun the pipeline.
- `targets[].values` = the number actually used per dim in `dims` (for low/med/high: the Earth percentile value,
  explained in `sources`; null for a dropped dim). Dims not in `dims` are left out.
- Numbers rounded (scores int, values 1–2 decimals). Missing = null. Keep the file under ~5 MB; print its size.
- `values` holds RAW physical values, never scores. Never invent numbers: everything comes from the input CSVs.

## Rules
- Simple, commented code: teammates with basic Python must be able to read it.
- Any script with a missing input file must fail with a clear message saying which teammate provides it.
- Target value sources: a dimension row of targets.csv with an empty or "FAKE" source = ERROR naming teammate C
  (check_csv.py). Only `run_all.py --no-merge` (all fake) and `--test-targets` downgrade it to a warning.
- `run_all.py --test-targets`: REAL data/earth_features.csv + FAKE targets/known_analogs from data/fake/ (until C
  delivers). results.json is then NOT copied to ../docs/data/: the website must never show real Earth data scored
  against fake targets. `out/run_inputs.json` records which inputs the last run used (diagnose_validation.py reads it).
- Real inputs: `data/` (`earth_features.csv` built by merge_inputs.py, gitignored; `targets.csv`, `known_analogs.csv`
  from C, tracked). Fake inputs: `data/fake/` (all three, tracked, written by src/make_fake_data.py). Every script reads
  the inputs from `common.INPUT_DIR`: `data/`, or `data/fake/` when `run_all.py --no-merge` sets PIPELINE_FAKE=1.
  Switching fake ↔ real = no code change.
