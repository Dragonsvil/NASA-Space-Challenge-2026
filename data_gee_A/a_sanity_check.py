"""
a_sanity_check.py -- are the exported values physically plausible?
Checks Sahara, Antarctica, Amazon (+ Atacama as a bonus) and draws global maps.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from grid_config import latlon_to_rowcol, tile_id, N_ROWS, N_COLS

df = pd.read_csv("data/earth_features_A.csv").set_index("tile_id")

# (name, lat, lon, {feature: (min_ok, max_ok)})  -- generous ranges
CHECKS = [
    ("Sahara (Algeria/Libya)", 23.0, 13.0, {
        "lst_max_day": (40, 62), "lst_min_night": (-10, 20), "albedo": (0.2, 0.5),
        "ndvi": (0, 0.1), "precip_mm": (0, 100)}),
    ("Antarctic plateau", -80.4, 77.1, {
        "lst_max_day": (-50, -5), "lst_min_night": (-100, -45), "albedo": (0.65, 0.98),
        "ndvi": (0, 0.05), "precip_mm": (0, 250)}),
    ("Amazon (Brazil)", -3.0, -60.0, {
        "lst_max_day": (27, 42), "lst_min_night": (14, 25), "lst_range": (4, 16),
        "albedo": (0.05, 0.2), "ndvi": (0.6, 0.95), "precip_mm": (1500, 4500)}),
    ("Atacama (bonus)", -24.5, -69.25, {
        "lst_max_day": (25, 55), "albedo": (0.15, 0.45),
        "ndvi": (0, 0.1), "precip_mm": (0, 80)}),
]

print("=" * 70)
for name, lat, lon, rules in CHECKS:
    r, c = latlon_to_rowcol(lat, lon)
    tid = tile_id(r, c)
    if tid not in df.index:
        print(f"{name}: tile {tid} not in land tiles (check land mask!)\n")
        continue
    row = df.loc[tid]
    print(f"{name}  (tile {tid}, lat {row.lat}, lon {row.lon})")
    for feat, (lo, hi) in rules.items():
        v = row[feat]
        ok = (not np.isnan(v)) and lo <= v <= hi
        print(f"   {'PASS' if ok else 'FAIL'}  {feat:15s} = {v:9.3f}   expected [{lo}, {hi}]")
    print()

# ---- global sanity: ranges and missing data
print("=" * 70)
print(df[["lst_min_night", "lst_max_day", "lst_range", "albedo", "ndvi", "precip_mm"]]
      .describe().round(2).to_string())

# ---- global maps for a visual check
feats = ["lst_min_night", "lst_max_day", "lst_range", "albedo", "ndvi", "precip_mm"]
fig, axes = plt.subplots(3, 2, figsize=(14, 12))
for ax, f in zip(axes.ravel(), feats):
    grid = np.full(N_ROWS * N_COLS, np.nan)
    grid[df.index.values] = df[f].values
    vmax = np.nanpercentile(grid, 98) if f == "precip_mm" else None
    im = ax.imshow(grid.reshape(N_ROWS, N_COLS), extent=[-180, 180, -90, 90],
                   cmap="viridis", vmax=vmax)
    ax.set_title(f)
    plt.colorbar(im, ax=ax, shrink=0.7)
plt.tight_layout()
plt.savefig("data/A_sanity_maps.png", dpi=110)
print("Saved data/A_sanity_maps.png")