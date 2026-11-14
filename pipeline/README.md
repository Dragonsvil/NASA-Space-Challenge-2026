# Planetary Analog Finder — data pipeline

Finds places on Earth that resemble a candidate Mars site (Jezero Crater) or Moon site (lunar south pole).
Every 0.25° land tile on Earth is compared to each target in physical units, scored for 3 mission profiles,
and validated against known analog sites; the result feeds the website (`../docs/`).

NASA Space Apps Challenge 2026. Full method and the results.json contract: [`CLAUDE.md`](CLAUDE.md).

## Method

1. **Filters before scoring.** A tile is kept only if:
   - it has DEM data (`slope_mean` not missing): the Copernicus DEM only covers land, so this is the land mask;
   - it is inside a Natural Earth country polygon, or has a town within 100 km (keeps small islands);
   - it is not vegetated: NDVI ≤ 0.3 (tiles without NDVI are kept only if polar, |lat| > 60°).
2. **Per-dimension scores.** For each dimension (temperature range, minimum temperature, albedo, slope,
   roughness, mafic index, aridity, dust or sun angle), the gap to the target is measured in real units.
   Score 0–100 = how close the tile is compared to all other kept tiles (percentile rank of the gap).
   `low` / `med` / `high` target values use Earth's 15th / 50th / 85th percentile.
3. **Weighted profiles.** Three mission profiles (rover navigation, geology / science, polar & thermal ops)
   weight the dimensions 0–3 (`PROFILES` in `src/score.py`). Missing dimensions are skipped and weights
   renormalised, **but** a tile only gets a total if the dimensions it has carry at least 2/3 of every
   profile's weight (and at most half are missing). This stops incomplete tiles winning by renormalisation.
4. **Global rank.** Each total is ranked among all scored tiles for that target × profile (1 = best on Earth).
5. **Hidden gems.** K-Means (k = 8–12, best silhouette) on arid / cold tiles. Per target, a gem is in the
   top 10% on its best profile, in a cluster containing a known analog for that body (Mars / Moon), and
   more than 300 km from every known analog. Best 15 per target, at least 300 km apart.
6. **Validation.** Each known analog's tile is ranked like any other tile.
   Success = most analogs in the top 10% of at least one target × profile.

## Input files (`data/`)

| file | provided by | content |
|---|---|---|
| `raw/earth_features_A.csv`, `raw/land_tiles.csv` | A | raw export (not in git) |
| `raw/earth_features_B.csv` | B | raw export (not in git): tile_id, slope_mean, slope_std, mafic_idx, quartz_idx, dust_aod |
| `earth_features.csv` | `merge_inputs.py` (A + B) | one row per land tile: temperatures, albedo, NDVI, precipitation, slope, mineral indices, dust |
| `targets.csv` | C | Jezero + lunar south pole values, long format. Template: `targets_TEMPLATE.csv`, guide: `targets_HOWTO.md` |
| `known_analogs.csv` | C | known Earth analog sites (name, lat, lon, analog_for, used_for) |
| `ne_110m_admin_0_countries.geojson` | Natural Earth | country borders, for the land mask and region names |

The tile grid (`tile_id`, tile centers, `-9999` = no data) is defined in [`../grid_config.py`](../grid_config.py),
shared with A and B. Check every input before sending it: `python src/check_csv.py data/<file>.csv`.

## Data cleaning

Applied by `src/merge_inputs.py` before writing `data/earth_features.csv`. Each rule prints how many values it changes.

| # | rule | why |
|---|---|---|
| 1 | `lst_range` = A's **mean daily** day–night range (mean(day) − mean(night)), kept as is; negative values → 0 | intended definition (not `lst_max_day − lst_min_night`, which are yearly extremes). Negatives (Antarctica, ~5,000 tiles) are noise around 0. Target values must use the same definition |
| 2 | beyond ±60° latitude: `precip_mm` = ERA5-Land (`precip_era5_mm`, `precip_source = "era5land"`); IMERG ignored there. Neither → NaN (`precip_source = "none"`) | IMERG is unreliable beyond ±60°: its exact zeros there are fill values. NaN is never scored as 0 mm: the aridity dimension is skipped (completeness rule) |
| 3 | `lst_min_night` < −40 °C where \|lat\| < 60° → NaN; full list in `out/cleaning_rule3_tiles.csv` | bad pixels (e.g. −108.7 °C in Congo) |
| 4 | `precip_era5_mm` > 12,000 mm/yr → NaN (applied before rule 2) | implausible values (max was 26,259) |
| 5 | `ndvi` minimum 0: no change | A clipped water to 0 on purpose |

Also: below ±60°, if IMERG is missing but ERA5-Land exists, ERA5-Land is used (`precip_source = "era5land"`).
`max_sun_elev` is recomputed from latitude. Tiles with no B data keep NaN in B's columns.

## Output files (`out/`, not in git)

| file | content |
|---|---|
| `results.json` | everything the website needs (copied to `../docs/data/results.json`, which **is** in git) |
| `scores.csv` | every tile: raw values, filter result, dimension scores, totals, global ranks |
| `target_values.csv` | the target value actually used per dimension |
| `clusters.csv`, `hidden_gems.csv` | clusters and hidden gems per target |
| `validation.csv`, `validation.md` | known-analog ranks; `validation.md` is the table for the slides |
| `diagnosis.md` | why each analog ranks where it does (from `diagnose_validation.py`) |
| `site_index.csv` | website site id → `tile_id` |

## How to run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python src/run_all.py                  # merge A + B, check inputs, score, cluster, validate, export, check results
python src/run_all.py --no-merge       # skip the merge: use data/earth_features.csv as it is (fake data)
python src/diagnose_validation.py      # optional: per-dimension breakdown for each known analog
```

`run_all.py` stops at the first failure and says which step (and, for input files, which teammate) to fix.
Without real data, `python src/make_fake_data.py` writes **fake** inputs for testing.

## Data sources

To be confirmed by the teammate who exports each dataset (product ID, version, date range, resolution).

| column(s) | dataset | ID / version | period | provided by |
|---|---|---|---|---|
| `lst_min_night`, `lst_max_day`, `lst_range` | MODIS Land Surface Temperature | TODO | TODO | A |
| `albedo` | TODO (MODIS albedo?) | TODO | TODO | A |
| `ndvi` | TODO (MODIS NDVI?) | TODO | TODO | A |
| `precip_mm` | TODO | TODO | TODO | TODO |
| `slope_mean`, `slope_std` | Copernicus DEM | TODO | – | B |
| `mafic_idx`, `quartz_idx` | TODO | TODO | TODO | B |
| `dust_aod` | TODO | TODO | TODO | TODO |
| target values | papers / PDS products / NASA pages, one per value (`source` column of `targets.csv`) | – | – | C |
| country borders | Natural Earth admin-0 countries 1:110m | – | – | pipeline |
| region names | `reverse_geocoder` (GeoNames cities) | – | – | pipeline |

## Known limitations

- **Point sampling for climate values.** MODIS LST, albedo and NDVI are sampled at **one pixel at the tile
  center**, not averaged over the ~28 km tile. A tile's climate can therefore reflect a single spot
  (a lake, a field, a glacier edge) rather than the whole tile.
  TODO (A): switch to tile-scale sampling (mean over the 0.25° tile) if time allows, then update this note.
- **Earth can't reproduce the environment.** No analog matches Mars or Moon gravity, vacuum or a thin CO₂
  atmosphere, or the surface radiation environment. The scores compare surface conditions only.
- **Mineralogy is a simple index.** `mafic_idx` and `quartz_idx` are simple multispectral indices (method: TODO B), not hyperspectral
  matching of the target's actual minerals.
