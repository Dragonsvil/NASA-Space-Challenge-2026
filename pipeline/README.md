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
6. **Validation.** Each known analog's tile is ranked like any other tile, and evaluated only on its own
   target (from `analog_for`) and the profiles its `used_for` names (keywords fixed before the results, see
   "Validation" below). Success = more than half of the analogs in the top 10% on one of their mapped target × profiles.
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

## Target values

`data/targets.csv` (from C) holds one value per target × dimension; its `source` column is a short citation, shown
unchanged on the website (`targets[].sources`). Caveats and pipeline notes (categorical conversion, dropped
dimensions) are only here. C's original file with the full source texts is kept
locally as `data/raw/targets_C.csv` (not in git).

| target · dimension | value | citation | notes |
|---|---|---|---|
| jezero · name / body / lat / lon | Jezero Crater, Mars, 18.4, 77.5 | NASA Mars 2020 landing site | crater centre |
| jezero · temp_range | 65.21 °C | Mars Odyssey THEMIS (Christensen et al. 2004) | mean of 3 day − mean of 5 night THEMIS observations; provisional, not a full diurnal mean. Reference to verify by C |
| jezero · temp_min | −84.24 °C | Mars Odyssey THEMIS (Christensen et al. 2004) | mean of 5 night observations (I02413002, I13035002, I26775011, I48277005, I75405013); provisional. Reference to verify by C |
| jezero · albedo | 0.15 | MGS TES albedo (Christensen et al. 2001) | single observation (THEMIS I75667014), not a regional average; TES albedo is not the same quantity as MODIS broadband albedo. Reference to verify by C |
| jezero · slope | 2.48° | MGS MOLA MEGDR (Smith et al. 2001) | product megt44n000hb; 28×28 km box at 18.4°N 77.5°E, resampled to ~500 m, Horn 3×3 slope. Reference to verify by C |
| jezero · roughness | 3.17° | MGS MOLA MEGDR (Smith et al. 2001) | standard deviation of slope in the same box; ddof (0 or 1) not confirmed. Reference to verify by C |
| jezero · mafic | high | Science Advances 2022, doi:10.1126/sciadv.abo3399 | crater-floor geology; **citation not verified yet (C)**. Pipeline: categorical `high` → Earth's 85th percentile of `mafic_idx` over the scored tiles (0.983 in the final run) |
| jezero · aridity | 0 mm/yr | project assumption | no liquid precipitation on present-day Mars |
| jezero · dust | high | qualitative | frequent Martian dust activity, not a numeric AOD. Pipeline: dimension dropped, no Earth dust data (`dust_aod` empty for every tile; listed in `meta.dropped_dimensions`), so no dust score |
| jezero · sun_angle | n/a | – | lunar-only dimension |
| lunar_south_pole · name / body / lat / lon | Lunar south pole, Moon, −90, 0 | centre of C's LOLA/Diviner box | – |
| lunar_south_pole · temp_range | 24.5 °C | LRO Diviner (Williams et al. 2017) | Polar Cumulative Products, 2009-07-05 – 2019-02-17, 28×28 km box, summer + winter pooled; mean day − mean night with day = local time 06–18 h (not sunlit/unlit); `diviner_temps.py`, `finalize_temps.py`. The max − min spread (253.5 °C) is not used |
| lunar_south_pole · temp_min | −193.7 °C | LRO Diviner (Williams et al. 2017) | same as above (mean night, local time 18–06 h) |
| lunar_south_pole · albedo | n/a | – | pending: LOLA 1064 nm reflectance is not comparable to MODIS broadband albedo |
| lunar_south_pole · slope | 15.35° | LRO LOLA LDEM_80S (Barker et al. 2023) | LDEM_80S_80MPP_ADJ, 28×28 km box on the pole, resampled 80 m → 500 m (average), Horn 3×3, 3136 px; `lola_slope.py`. **Pixel scale to confirm (C)**: slope depends on it |
| lunar_south_pole · roughness | 9.91° | LRO LOLA LDEM_80S (Barker et al. 2023) | population std (ddof = 0) |
| lunar_south_pole · mafic | low | Lunar Prospector GRS (Lawrence et al. 2002) | anorthositic highlands with low FeO (JGR 107(E12)); Pipeline: categorical `low` → Earth's 15th percentile of `mafic_idx` over the scored tiles (0.831 in the final run) |
| lunar_south_pole · aridity | 0 mm/yr | – | no atmosphere, no precipitation |
| lunar_south_pole · dust | n/a | – | no atmosphere |
| lunar_south_pole · sun_angle | 1.54° | NASA Moon Fact Sheet | 90 − \|lat\| + axial tilt 1.54°; C to verify the tilt |

"Reference to verify by C" = author-year reference added by the pipeline (D), not supplied by C.

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

Output of `src/validate.py` (`out/validation.md`), final run.

### Method

Each known analog is evaluated only where it is a claimed analog, with a rule fixed before looking at the results. **Target** = its body (`analog_for`): Mars → jezero, Moon → lunar_south_pole. **Profiles** = the mission profiles its `used_for` text names, by keyword (an analog can map to several): **rover**: rover, mobility, field operations, instrument, drilling · **geology**: geology, geolog, volcan, mineral, impact, biosignature, life-detection, life detection, astrobiology, habitab · **polar**: polar, permafrost, ice, cold. An analog **succeeds** if its tile is in the top 10% of all scored Earth tiles on at least one of its mapped target × profiles; the method succeeds if more than half of the analogs do. Analogs whose tile is excluded (e.g. vegetated) count as failures. The scores themselves are not changed by this rule, and the weights were not tuned on the analogs.

### Results

| Analog | Analog for | Used for | Mapped profiles | Rank and top % on each mapped target × profile | In top 10%? |
|---|---|---|---|---|---|
| Atacama Desert (Yungay sector), Chile | Mars | Hyperarid soils, extreme dryness and low biomass; testing life-detection instruments and drilling | rover, geology | jezero × rover: 809 / 142,573 (0.6%) ✓<br>jezero × geology: 6,448 / 142,573 (4.5%) ✓ | yes |
| McMurdo Dry Valleys, Antarctica | Mars | Cold hyperarid polar desert, permafrost and microbial survival; habitability and biosignature studies | geology, polar | jezero × geology: 105,997 / 142,573 (74.3%)<br>jezero × polar: 128,274 / 142,573 (90.0%) | no |
| Haughton Impact Crater, Devon Island, Canada | Mars, Moon | Impact-crater geology in a cold polar desert with permafrost; rover operations and subsurface-life studies | rover, geology, polar | jezero × rover: 9,438 / 142,573 (6.6%) ✓<br>jezero × geology: 23,207 / 142,573 (16.3%)<br>jezero × polar: 38,354 / 142,573 (26.9%)<br>lunar_south_pole × rover: 25,112 / 142,573 (17.6%)<br>lunar_south_pole × geology: 126,342 / 142,573 (88.6%)<br>lunar_south_pole × polar: 59,129 / 142,573 (41.5%) | yes |
| Rio Tinto, Spain | Mars | Acidic, iron-rich waters and mineral alteration; extremophile and habitability studies | geology | – (excluded: vegetated tile (NDVI 0.58)) | no (excluded) |
| Kilauea Volcano (summit region), Hawaii, USA | Moon, Mars | Basaltic volcanic terrain and lava features; planetary volcanism and rover field-geology studies | rover, geology | – (excluded: vegetated tile (NDVI 0.42)) | no (excluded) |
| Mojave Desert, California, USA | Mars | Arid terrain and temperature extremes; rover mobility, instrument testing and field operations | rover | jezero × rover: 3,915 / 142,573 (2.7%) ✓ | yes |
| Svalbard, Norway | Mars | Arctic cold, permafrost and ice-related landforms; astrobiology and polar-environment studies | geology, polar | jezero × geology: 141,820 / 142,573 (99.5%)<br>jezero × polar: 139,386 / 142,573 (97.8%) | no |
| University Valley, McMurdo Dry Valleys, Antarctica | Mars | Extremely dry permafrost and ice-cemented ground; subsurface sampling, drilling and habitability studies | rover, geology, polar | jezero × rover: 137,884 / 142,573 (96.7%)<br>jezero × geology: 123,511 / 142,573 (86.6%)<br>jezero × polar: 130,761 / 142,573 (91.7%) | no |
| Moab, Utah, USA | Mars | Desert biological soil crusts and microbial colonization; astrobiology and life-detection research | geology | jezero × geology: 101,230 / 142,573 (71.0%) | no |
| Icelandic volcanic fields (Askja region), Iceland | Mars, Moon | Basaltic volcanic and subglacial landforms; volcanism, ice-rock interactions and planetary field studies | geology, polar | jezero × geology: 105,997 / 142,573 (74.3%)<br>jezero × polar: 43,757 / 142,573 (30.7%)<br>lunar_south_pole × geology: 104,336 / 142,573 (73.2%)<br>lunar_south_pole × polar: 85,197 / 142,573 (59.8%) | no |

**3 of 10 known analogs in the top 10% on at least one of their mapped target × profiles (2 excluded: no valid tile).** Success = more than half: **no**.

Per target: jezero (Mars): 3 of 10 Mars analogs (8 with a valid tile); lunar_south_pole (Moon): 0 of 3 Moon analogs (2 with a valid tile).

Per target × profile (analogs mapped to it, passing on that exact target × profile):

- jezero × rover: 3 of 5 mapped analogs pass (1 excluded)
- jezero × geology: 1 of 9 mapped analogs pass (2 excluded)
- jezero × polar: 0 of 5 mapped analogs pass
- lunar_south_pole × rover: 0 of 2 mapped analogs pass (1 excluded)
- lunar_south_pole × geology: 0 of 3 mapped analogs pass (1 excluded)
- lunar_south_pole × polar: 0 of 2 mapped analogs pass

### Limitations of this validation

- The keyword mapping is mechanical: e.g. "drilling" maps University Valley to rover, "ice-rock interactions" maps Iceland to polar. It was fixed before the results and not edited afterwards.
- Our dimensions do not measure ground ice or permafrost, which is what polar analogs (McMurdo, University Valley, Svalbard) are mostly used for.
- Earth polar sites have a 1–2 °C mean day–night range (the Sun barely moves in their sky) vs 65 °C at Jezero, and mean nights no colder than about −35 °C vs −84 °C: they are cold, but not Jezero-like.

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
