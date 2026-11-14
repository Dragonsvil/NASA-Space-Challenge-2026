"""
MEMBER B - script 3: merge the Earth Engine CSVs, add max_sun_elev, run sanity checks.

How to use:
  1. Have the folder ./exports contain both the terrain and geology csv files
  2. pip install pandas numpy
  3. python B3_postprocess.py ./exports land_tiles.csv 
Output: B_features.csv  (columns: tile_id, lat, lon, slope_mean, slope_std,
                         mafic_idx, quartz_idx, dust_aod, max_sun_elev)
"""
import sys, glob
import numpy as np
import pandas as pd

folder = sys.argv[1] if len(sys.argv) > 1 else "./exports"


def tile_id(lat, lon):
    """Shared grid formula (same as in the Earth Engine scripts)."""
    row = np.floor((90 - np.asarray(lat)) / 0.25).astype(int)  # row 0 = NORTH, like grid_config.py
    col = np.floor((np.asarray(lon) + 180) / 0.25).astype(int)
    return row * 1440 + col


def load(pattern):
    files = sorted(glob.glob(f"{folder}/{pattern}"))
    if not files:
        sys.exit(f"No files matching {pattern} in {folder}")
    print(f"{pattern}: {len(files)} files")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    return df.drop_duplicates("tile_id")


terrain = load("B_terrain_*.csv")
geology = load("B_geology_*.csv")
print("terrain tiles:", len(terrain), "| geology tiles:", len(geology))

# outer join: keep tiles that have terrain even if ASTER has no data (mafic/quartz stay empty)
df = terrain.merge(geology[["tile_id", "mafic_idx", "quartz_idx"]], on="tile_id", how="left")

# ASTER ratios can blow up where emissivity is ~0 (ice, water, bad pixels). Real values are ~0.9-1.1,
# so anything outside 0.5-2.0 is clearly broken: set it to empty (NaN) instead of keeping it.
for col in ("mafic_idx", "quartz_idx"):
    bad = (df[col] < 0.5) | (df[col] > 2.0)
    print(f"{col}: {int(bad.sum())} impossible values set to empty")
    df.loc[bad, col] = np.nan

# max solar elevation over the year (degrees), from the roadmap formula, capped at 90
df["max_sun_elev"] = np.minimum(90, 90 - df["lat"].abs() + 23.44)
df["dust_aod"] = np.nan  # optional dimension, left empty unless you export it

# optional: keep only land tiles, using A's land_tiles.csv (needs a tile_id column)
if len(sys.argv) > 2:
    land = pd.read_csv(sys.argv[2])
    if "land_frac" in land.columns:          # A_land_b0_0.csv format: keep land_frac >= 0.5
        land = land[land["land_frac"] >= 0.5]
    before = len(df)
    df = df[df["tile_id"].isin(land["tile_id"])]
    print(f"land filter: {before} -> {len(df)} tiles")

# consistency check of the tile_id formula against lat/lon
assert (tile_id(df["lat"], df["lon"]) == df["tile_id"]).all(), "tile_id mismatch!"

df = df[["tile_id", "lat", "lon", "slope_mean", "slope_std",
         "mafic_idx", "quartz_idx", "dust_aod", "max_sun_elev"]]
df.to_csv("B_features.csv", index=False)
print("Saved B_features.csv:", len(df), "rows")
print(df.describe().T[["count", "min", "mean", "max"]])

# ---- sanity checks: nearest tile to some places we know ----
checks = {
    "Sahara (flat)": (24, 10),
    "Atacama": (-24, -69),
    "Himalaya (steep)": (28, 86),
    "Alps (steep)": (46.5, 8.5),
    "Antarctica Dry Valleys": (-77.5, 162.5),
    "Iceland": (64.5, -19),
}
for name, (la, lo) in checks.items():
    tid = tile_id(la, lo)
    row = df[df.tile_id == tid]
    print("\n" + name, "->", "NOT FOUND" if row.empty else "")
    if not row.empty:
        print(row.round(3).to_string(index=False))
print("\nExpected: Sahara slope_mean < 1-2 deg, Himalaya/Alps > 8 deg, mafic_idx roughly 0.9-1.1, "
      "quartz_idx roughly 0.9-1.2. Anything wildly different = tell D and fix before continuing.")