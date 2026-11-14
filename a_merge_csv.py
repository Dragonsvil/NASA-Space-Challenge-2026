"""
a_merge_csv.py -- merge the block CSVs exported from Earth Engine into
    data/earth_features_A.csv  (land tiles, role A features)
    data/land_tiles.csv        (tile_id, lat, lon, land_frac) -> share with B and D
"""
import glob
import os
import numpy as np
import pandas as pd
from grid_config import N_COLS, N_ROWS, RES, X_MIN, Y_MAX

RAW, OUT = "data/raw_A", "data"
os.makedirs(OUT, exist_ok=True)

LAYERS = {
    "A_land":   ["land_frac"],
    "A_lst":    ["lst_min_night", "lst_max_day", "lst_range"],
    "A_albedo": ["albedo"],
    "A_ndvi":   ["ndvi"],
    "A_precip": ["precip_mm", "precip_era5_mm"],
}


def read_layer(prefix, bands):
    files = [f for f in glob.glob(os.path.join(RAW, f"{prefix}_b*.csv")) if "(" not in f]
    assert files, f"No CSV found for {prefix} in {RAW}"
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    df = df.drop_duplicates("tile_id")
    df = df.replace(-9999, np.nan)
    for b in bands:                      # a column fully empty is absent from the CSV
        if b not in df.columns:
            df[b] = np.nan
    print(f"{prefix}: {len(files)} files, {len(df)} rows")
    return df[["tile_id"] + bands]


# full grid skeleton (every tile of the world)
ids = np.arange(N_ROWS * N_COLS)
full = pd.DataFrame({"tile_id": ids})
full["lat"] = Y_MAX - RES * (ids // N_COLS + 0.5)
full["lon"] = X_MIN + RES * (ids % N_COLS + 0.5)

for prefix, bands in LAYERS.items():
    full = full.merge(read_layer(prefix, bands), on="tile_id", how="left")

# land mask: >= 50% non-water pixels
land = full[full["land_frac"] >= 0.5].copy()
land[["tile_id", "lat", "lon", "land_frac"]].to_csv(f"{OUT}/land_tiles.csv", index=False)

# precipitation: IMERG, with ERA5-Land as fallback where IMERG is missing (poles)
land["precip_source"] = np.where(land["precip_mm"].notna(), "imerg", "era5land")
land["precip_mm"] = land["precip_mm"].fillna(land["precip_era5_mm"]).clip(lower=0)

cols = ["tile_id", "lat", "lon", "lst_min_night", "lst_max_day", "lst_range",
        "albedo", "ndvi", "precip_mm", "precip_source", "precip_era5_mm"]
land[cols].round(4).to_csv(f"{OUT}/earth_features_A.csv", index=False)

print("Land tiles:", len(land))
print(land[cols].isna().mean().round(3).to_string())   # share of missing values