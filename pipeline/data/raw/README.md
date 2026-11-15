# data/raw/ — raw input files (NOT in git)

The raw exports are too large for the repository. They are **attached to the GitHub release
[`v1.4-final`](https://github.com/Dragonsvil/NASA-Space-Challenge-2026/releases/tag/v1.4-final)**.
Download them into this folder, then run the pipeline from `pipeline/`:

```bash
cd pipeline
gh release download v1.4-final --repo Dragonsvil/NASA-Space-Challenge-2026 --dir data/raw --pattern "*.csv"
python src/run_all.py
```

Without `gh`, download each file from the release page into `pipeline/data/raw/`.
Without these files at all: `python src/run_all.py --no-merge` (from `pipeline/`) runs on the fake inputs in
`pipeline/data/fake/`.

`src/merge_inputs.py` (step 0 of `run_all.py`) reads the first four files and builds `pipeline/data/earth_features.csv`
(also not in git). Grid, `tile_id` and the `-9999` no-data value: [`grid_config.py`](../../../grid_config.py) at the repo root.

| file | produced by | columns | how it was made |
|---|---|---|---|
| `earth_features_A.csv` | A | `tile_id, lat, lon, lst_min_night, lst_max_day, lst_range, albedo, ndvi, precip_mm, precip_source, precip_era5_mm` | Google Earth Engine export, scripts in [`data_gee_A/`](../../../data_gee_A/) (repo root) |
| `earth_features_A_extra.csv` | A | `tile_id, lst_mean_night, lst_mean_day` | same (multi-year mean night / day LST, °C) |
| `land_tiles.csv` | A | `tile_id, lat, lon, land_frac` | same (MCD12Q1 land fraction) |
| `earth_features_B.csv` | B | `tile_id, lat, lon, slope_mean, slope_std, mafic_idx, quartz_idx, dust_aod, max_sun_elev` | Google Earth Engine export, scripts in [`data_gee_B/`](../../../data_gee_B/) (repo root). `lat`, `lon`, `max_sun_elev` are ignored (recomputed from the grid) |
| `targets_C.csv` | C | `target, feature, value, unit, source` | C's original target file with the full source texts. **Not needed to run**: the pipeline reads `data/targets.csv` (in git), converted from it |

All four Earth files have one row per 0.25° tile (`tile_id` = row × 1440 + col). A's three files cover the same
337,612 tiles; B's covers 331,469.
