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
2. **Per-dimension scores.** For each dimension (mean day–night range, mean night temperature, albedo, slope,
   roughness, mafic index, aridity, dust or sun angle), the gap to the target is measured in real units.
   Score 0–100 = how close the tile is compared to all other kept tiles (percentile rank of the gap).
   `low` / `med` / `high` target values use Earth's 15th / 50th / 85th percentile.
   Temperature uses multi-year MEANS only (`lst_mean_night`, and `lst_range` = mean day − mean night);
   the 3-year extremes `lst_min_night` / `lst_max_day` and the redundant `lst_mean_day` are kept but not scored.
3. **Weighted profiles.** Three mission profiles (rover navigation, geology / science, polar & thermal ops)
   weight the dimensions 0–3 (`PROFILES` in `src/score.py`). Missing dimensions are skipped and weights
   renormalised, **but** a tile only gets a total if the dimensions it has carry at least 2/3 of every
   profile's weight (and at most half are missing). This stops incomplete tiles winning by renormalisation.
   **Safety rule:** a whole target × profile is marked *unavailable* (total = null for every site, listed in
   `meta.unavailable_profiles` with the reason) if the target's own dimensions (after `n/a` values and dropped
   dimensions) carry less than 2/3 of the profile's total weight. With the final targets, none is unavailable.
4. **Global rank.** Each total is ranked among all scored tiles for that target × profile (1 = best on Earth).
5. **Hidden gems.** K-Means (k = 8–12, best silhouette) on arid / cold tiles. Per target, a gem is in the
   top 10% on its best profile, in a cluster containing a known analog for that body (Mars / Moon), and
   more than 300 km from every known analog. Best 15 per target, at least 300 km apart.
6. **Validation.** Each known analog's tile is ranked like any other tile.
   Success = most analogs in the top 10% of at least one target × profile.
7. **Weights are not tuned.** The profile weights are the roadmap weights, unchanged.
   We do **not** tune them on the known analogs: they are our only independent check, and tuning weights
   until the analogs rank well would be overfitting (validation would then prove nothing).

## Input files (`data/`)

| file | provided by | content |
|---|---|---|
| `raw/earth_features_A.csv`, `raw/earth_features_A_extra.csv`, `raw/land_tiles.csv` | A | raw export (not in git); `_extra` = mean night / day LST |
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
| 3 | `lst_min_night` and `lst_mean_night` < −40 °C where \|lat\| < 45° → NaN; full list in `out/cleaning_rule3_tiles.csv` | bad pixels (e.g. −108.7 °C in Congo, −59.8 °C in Sumatra). Not applied at 45–60°: Siberian and Canadian winters really reach −40 to −60 °C there (a \|lat\| < 60° limit removed ~5,100 real values) |
| 4 | `precip_era5_mm` > 12,000 mm/yr → NaN (applied before rule 2) | implausible values (max was 26,259) |
| 5 | `ndvi` minimum 0: no change | A clipped water to 0 on purpose |
| 6 | `lst_range` → NaN where `lst_mean_night` or `lst_mean_day` is NaN (applied after rule 3) | `lst_range` is defined as their difference (~1,400 tiles near the South Pole had a range but no means) |

Also: below ±60°, if IMERG is missing but ERA5-Land exists, ERA5-Land is used (`precip_source = "era5land"`).
`max_sun_elev` is recomputed from latitude (B's `max_sun_elev`, `lat`, `lon` are ignored). Tiles with no B data keep
NaN in B's columns (then removed by the "no DEM" land mask). A column that is 100% empty (e.g. `dust_aod`) drops
its dimension for every target: no scores (`meta.dropped_dimensions` in results.json). For display, it stays in
the `dims` of a target that has a value for it (dust in Jezero's), with `values` null.

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
python src/run_all.py --no-merge       # skip the merge, run on the FAKE inputs in data/fake/ (testing)
python src/run_all.py --test-targets   # REAL Earth data + FAKE targets/analogs (data/fake/) until C delivers;
                                       # results.json is NOT copied to ../docs/data/
python src/diagnose_validation.py      # optional: per-dimension breakdown for each known analog
```

`run_all.py` stops at the first failure and says which step (and, for input files, which teammate) to fix.
**Real vs fake inputs.** Real inputs live in `data/`. `data/earth_features.csv` is built by `merge_inputs.py`,
is large, and is **not in git** (rebuild it from `data/raw/`). `data/targets.csv` and `data/known_analogs.csv`
(from C, small) are in git. **Fake** inputs for testing live in `data/fake/` (in git, all three files,
regenerated by `python src/make_fake_data.py`); `run_all.py --no-merge` reads only those.

## Data sources

| column(s) / value | dataset | ID | period | provided by |
|---|---|---|---|---|
| `lst_mean_night`, `lst_mean_day`, `lst_range` (+ `lst_min_night`, `lst_max_day`, not scored) | MODIS Terra Land Surface Temperature, 8-day, 1 km | MOD11A2 | 2021–2023 | A |
| `albedo` | MODIS BRDF/Albedo, daily, 500 m | MCD43A3 | 2023 | A |
| `ndvi` (filter, not scored) | MODIS vegetation indices (CMG) / MODIS NBAR reflectance | MOD13C1 / MCD43A4 | 2021–2023 | A |
| `precip_mm` (\|lat\| ≤ 60°) | GPM IMERG | V07 | 2016–2020 | A |
| `precip_mm` (\|lat\| > 60°, and gaps), `precip_era5_mm` | ERA5-Land (ECMWF) | ERA5-Land | 2016–2020 | A |
| `land_frac` (not scored) | MODIS Land Cover Type | MCD12Q1 | 2021 | A |
| `slope_mean`, `slope_std` | Copernicus DEM | GLO-30 | – | B |
| `mafic_idx`, `quartz_idx` | ASTER Global Emissivity Dataset, 100 m | ASTER GED AG100 | – | B |
| `dust_aod` | none: not exported (dimension dropped) | – | – | – |
| Jezero slope / roughness | MGS MOLA MEGDR | megt44n000hb | – | C |
| Jezero temperatures, albedo | Mars Odyssey THEMIS (and TES albedo) | observation IDs in `targets.csv` | – | C |
| Lunar slope / roughness | LRO LOLA | LDEM_80S_80MPP_ADJ (Barker et al. 2023) | – | C |
| Lunar temperatures | LRO Diviner | Polar Cumulative Products (south pole) | 2009-07-05 – 2019-02-17 | C |
| Lunar mafic (`low`) | Lunar Prospector Gamma-Ray Spectrometer | Lawrence et al. 2002, JGR 107(E12) | – | C |
| country borders | Natural Earth admin-0 countries 1:110m | – | – | pipeline |
| region names | `reverse_geocoder` (GeoNames cities) | – | – | pipeline |

Every target value's exact source is in the `source` column of `data/targets.csv` (also `targets[].sources`
in results.json). Values still to confirm with C are listed at the end of `out/diagnosis.md`.

## Validation

Output of `src/validate.py` (`out/validation.md`), final run:

| Analog | Analog for | Best target × profile | Rank | Top % | In top 10%? |
|---|---|---|---|---|---|
| Atacama Desert (Yungay sector), Chile | Mars | jezero × polar | 463 / 142,573 | 0.3% | yes |
| McMurdo Dry Valleys, Antarctica | Mars | lunar_south_pole × rover | 358 / 142,573 | 0.3% | yes |
| Haughton Impact Crater, Devon Island, Canada | Mars, Moon | jezero × rover | 9,438 / 142,573 | 6.6% | yes |
| Rio Tinto, Spain | Mars | – | – | – | – (excluded: vegetated tile (NDVI 0.58)) |
| Kilauea Volcano (summit region), Hawaii, USA | Moon, Mars | – | – | – | – (excluded: vegetated tile (NDVI 0.42)) |
| Mojave Desert, California, USA | Mars | jezero × rover | 3,915 / 142,573 | 2.7% | yes |
| Svalbard, Norway | Mars | lunar_south_pole × rover | 3,761 / 142,573 | 2.6% | yes |
| University Valley, McMurdo Dry Valleys, Antarctica | Mars | lunar_south_pole × rover | 849 / 142,573 | 0.6% | yes |
| Moab, Utah, USA | Mars | lunar_south_pole × rover | 14,954 / 142,573 | 10.5% | no |
| Icelandic volcanic fields (Askja region), Iceland | Mars, Moon | lunar_south_pole × rover | 14,954 / 142,573 | 10.5% | no |

**6 of 10 known analogs in the top 10% of at least one profile (2 excluded: no valid tile).** Success = more than half: **yes**.

Rio Tinto and Kilauea are excluded by the vegetation filter (NDVI > 0.3), not substituted by a neighbour.
Per-dimension explanation of every rank: `out/diagnosis.md` (`python src/diagnose_validation.py`).

## Known limitations

- **One-pixel sampling for some layers.** Some MODIS layers (LST, albedo, NDVI) were sampled at one pixel at the
  tile centre, not averaged over the ~28 km tile, so a tile can reflect a single spot (a lake, a field, a glacier edge).
- **Mineral index gaps.** ASTER GED (`mafic_idx`, `quartz_idx`) is missing on ~33% of tiles, including Iceland
  and Antarctica. There the mafic dimension is skipped (completeness rules), so basaltic analogs like Iceland are
  scored without their main geological feature. `mafic_idx` is a simple multispectral index, not hyperspectral
  matching of the target's minerals, and the targets' `high` / `low` are qualitative.
- **No dust data.** `dust_aod` was not exported: the dust dimension is dropped for every target
  (`meta.dropped_dimensions`).
- **IMERG may overestimate rain in hyperarid deserts.** Example: the Atacama (Yungay) tile has 108 mm/yr in
  IMERG vs 9 mm/yr in ERA5-Land. IMERG is used below ±60°, so hyperarid analogs can lose aridity points.
- **Earth can't reproduce the environment.** No analog matches Mars or Moon gravity, vacuum, a thin CO₂
  atmosphere, or the surface radiation environment. The scores compare surface conditions only.
- **Sun angle.** On Earth the maximum sun elevation is never below ~23° (90° − 90° + 23.44° at the poles), while the
  lunar south pole's is 1.54°. The sun-angle dimension can only reward being close to a pole; no Earth tile is close.
- **Weights not tuned.** Profile weights are the roadmap weights (see Method, step 7), not optimised on any data.
- **Provisional target values.** Several target values come from few observations (e.g. Jezero temperatures from
  3 day / 5 night THEMIS observations, Jezero albedo from one TES observation); see `out/diagnosis.md`.
