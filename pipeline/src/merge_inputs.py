"""
merge_inputs.py — build data/earth_features.csv from the raw exports of A and B.
Step 0 of run_all.py.

    python src/merge_inputs.py

Reads (data/raw/, not in git):
    earth_features_A.csv   teammate A: tile_id, lat, lon, lst_min_night, lst_max_day, lst_range,
                           albedo, ndvi, precip_mm, precip_source, precip_era5_mm
    land_tiles.csv         teammate A: tile_id, lat, lon, land_frac
    earth_features_B.csv   teammate B: tile_id, slope_mean, slope_std, mafic_idx, quartz_idx, dust_aod

Does:
    1. checks every tile_id is a valid grid id and lat/lon = grid_config tile center
    2. cleaning rules 1-5 (README, "Data cleaning"), printing how many values each changes
    3. A-only report: stats per column, values at 5 reference places (PASS / CHECK), NDVI filter count
    4. if B's file is missing: STOP ("waiting for teammate B"), data/earth_features.csv untouched
    5. joins A + B on tile_id, recomputes max_sun_elev from lat, writes data/earth_features.csv
       (shared column order, then the extra columns precip_source, precip_era5_mm, land_frac)

data/earth_features.csv is only ever replaced by a COMPLETE merge (written to a temporary
file first, then renamed), never by partial data.
"""

import sys

import numpy as np
import pandas as pd

from check_csv import EARTH_RANGES, SCHEMAS
from common import ANALOG_MAX_KM, DATA_DIR, OUT_DIR, grid_config, haversine_km, load_csv, tile_of
from score import NDVI_MAX, POLAR_LAT

RAW = DATA_DIR / "raw"
FILE_A = RAW / "earth_features_A.csv"
FILE_LAND = RAW / "land_tiles.csv"
FILE_B = RAW / "earth_features_B.csv"
OUT_FILE = DATA_DIR / "earth_features.csv"

A_COLS = ["tile_id", "lat", "lon", "lst_min_night", "lst_max_day", "lst_range",
          "albedo", "ndvi", "precip_mm", "precip_source", "precip_era5_mm"]
B_COLS = ["tile_id", "slope_mean", "slope_std", "mafic_idx", "quartz_idx", "dust_aod"]
ERA5_MAX_MM = 12000           # cleaning rule 4
COLD_BAD_C = -40              # cleaning rule 3 (outside the polar regions)
SHOW_TILES = 20               # rule 3: tiles printed (all of them go to out/cleaning_rule3_tiles.csv)
EXTRA_COLS = ["precip_source", "precip_era5_mm", "land_frac"]   # kept, not used for scoring

# Reference places: (lat, lon, {column: (plausible min, plausible max)}).
# Ranges are deliberately wide: they catch unit / scaling / masking mistakes, not small biases.
# "nan" = the value is expected to be missing (NDVI south of 60°S, A's choice).
PLACES = {
    "Sahara (23N, 13E)": (23, 13, {
        "lst_min_night": (-5, 30), "lst_max_day": (35, 75), "albedo": (0.2, 0.5),
        "ndvi": (0, 0.15), "precip_mm": (0, 100)}),
    "Atacama (-24.5, -69.25)": (-24.5, -69.25, {
        "lst_min_night": (-20, 15), "lst_max_day": (20, 70), "albedo": (0.1, 0.5),
        "ndvi": (0, 0.15), "precip_mm": (0, 150)}),
    "Amazon (-3, -60)": (-3, -60, {
        "lst_min_night": (10, 28), "lst_max_day": (22, 45), "albedo": (0.05, 0.2),
        "ndvi": (0.5, 1), "precip_mm": (1500, 4000)}),
    "Antarctic plateau (-80.4, 77.1)": (-80.4, 77.1, {
        "lst_min_night": (-100, -45), "lst_max_day": (-60, -10), "albedo": (0.7, 0.95),
        "ndvi": "nan", "precip_mm": (0, 100)}),
    "McMurdo Dry Valleys (-77.5, 162)": (-77.5, 162, {
        "lst_min_night": (-70, -15), "lst_max_day": (-35, 25), "albedo": (0.1, 0.9),
        "ndvi": "nan", "precip_mm": (0, 300)}),
}


def stop(message):
    print(f"\nSTOPPED: {message}\ndata/earth_features.csv was NOT changed.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_grid(df, name):
    """Every tile_id a valid integer grid id, lat/lon = its center, no duplicates. Stops otherwise."""
    n_tiles = grid_config.N_ROWS * grid_config.N_COLS
    ids = pd.to_numeric(df["tile_id"], errors="coerce")
    bad = ids.isna() | (ids % 1 != 0) | (ids < 0) | (ids >= n_tiles)
    if bad.any():
        stop(f"{name}: {bad.sum():,} tile_id(s) not integers in 0..{n_tiles - 1}, "
             f"e.g. {df.loc[bad, 'tile_id'].head(3).tolist()}")
    if ids.duplicated().any():
        stop(f"{name}: {ids.duplicated().sum():,} duplicated tile_id(s), "
             f"e.g. {df.loc[ids.duplicated(), 'tile_id'].head(3).tolist()}")
    msg = f"{name}: {len(df):,} tile_ids, all valid grid ids, no duplicates"
    if "lat" in df.columns:
        row, col = ids // grid_config.N_COLS, ids % grid_config.N_COLS
        exp_lat, exp_lon = grid_config.tile_center(row, col)
        wrong = ((df["lat"] - exp_lat).abs() > 1e-6) | ((df["lon"] - exp_lon).abs() > 1e-6)
        if wrong.any():
            i = wrong[wrong].index[0]
            stop(f"{name}: {wrong.sum():,} row(s) where lat/lon is not the grid_config tile center, "
                 f"e.g. tile_id {df.loc[i, 'tile_id']}: expected ({exp_lat[i]}, {exp_lon[i]}), "
                 f"file has ({df.loc[i, 'lat']}, {df.loc[i, 'lon']})")
        msg += ", lat/lon = tile centers"
    print(f"  OK  {msg}")


def check_columns(df, expected, name, who):
    missing = [c for c in expected if c not in df.columns]
    if missing:
        stop(f"{name} is missing columns {missing}. Ask {who}.")


def clean(a):
    """
    Cleaning rules decided by the team (README, "Data cleaning"). Each prints how many values it changes.
    Order matters: ERA5 outliers are removed (rule 4) before ERA5 is used for precipitation (rule 2).
    """
    print("\nCleaning rules:")
    polar = a["lat"].abs() > POLAR_LAT

    # Rule 1: lst_range = mean daily day-night range (A's definition, kept). Negative -> 0.
    neg = a["lst_range"] < 0
    a.loc[neg, "lst_range"] = 0.0
    print(f"  1. lst_range < 0 -> 0:                         {neg.sum():>8,} values")

    # Rule 4: implausible ERA5 precipitation -> NaN
    wet = a["precip_era5_mm"] > ERA5_MAX_MM
    a.loc[wet, "precip_era5_mm"] = np.nan
    print(f"  4. precip_era5_mm > {ERA5_MAX_MM} -> NaN:             {wet.sum():>8,} values")

    # Rule 2: beyond ±60° IMERG is not trusted (exact zeros = fill values): ERA5-Land, or NaN.
    # NaN is never scored as 0: the aridity dimension is then skipped (completeness rule).
    use_era5 = polar & a["precip_era5_mm"].notna()
    no_rain = polar & a["precip_era5_mm"].isna()
    was_imerg = a["precip_source"].eq("imerg")
    imerg_zero = was_imerg & a["precip_mm"].eq(0)          # counted before we overwrite
    a.loc[use_era5, "precip_mm"] = a.loc[use_era5, "precip_era5_mm"]
    a.loc[use_era5, "precip_source"] = "era5land"
    a.loc[no_rain, "precip_mm"] = np.nan
    a.loc[no_rain, "precip_source"] = "none"
    print(f"  2. |lat| > {POLAR_LAT}: precip_mm from ERA5-Land:       {use_era5.sum():>8,} tiles "
          f"(replacing IMERG on {(use_era5 & was_imerg).sum():,}, of which exact 0: "
          f"{(use_era5 & imerg_zero).sum():,})")
    print(f"     |lat| > {POLAR_LAT}, no ERA5 -> precip_mm NaN:   {no_rain.sum():>8,} tiles "
          f"(IMERG dropped on {(no_rain & was_imerg).sum():,}, of which exact 0: "
          f"{(no_rain & imerg_zero).sum():,})")
    #     (below ±60°: IMERG missing but ERA5 present -> ERA5, same as A's merge)
    fill = ~polar & a["precip_mm"].isna() & a["precip_era5_mm"].notna()
    a.loc[fill, "precip_mm"] = a.loc[fill, "precip_era5_mm"]
    a.loc[fill, "precip_source"] = "era5land"
    print(f"     |lat| <= {POLAR_LAT}, IMERG missing -> ERA5-Land:   {fill.sum():>8,} tiles")

    # Rule 3: impossibly cold nights outside the polar regions = bad pixels -> NaN
    bad = (a["lst_min_night"] < COLD_BAD_C) & (a["lat"].abs() < POLAR_LAT)
    print(f"  3. lst_min_night < {COLD_BAD_C} °C, |lat| < {POLAR_LAT} -> NaN:  {bad.sum():>8,} values")
    changed = a.loc[bad, ["tile_id", "lat", "lon", "lst_min_night", "ndvi"]]
    bands = pd.cut(changed["lat"].abs(), [0, 45, 50, 55, 60], right=False).value_counts().sort_index()
    print("       by |lat|: " + ", ".join(f"{b.left}-{b.right}°: {n:,}" for b, n in bands.items()))
    print(f"       of which pass the NDVI filter (ndvi <= {NDVI_MAX}): {(changed['ndvi'] <= NDVI_MAX).sum():,}")
    print(f"       {SHOW_TILES} coldest (full list: out/cleaning_rule3_tiles.csv):")
    for _, r in changed.sort_values("lst_min_night").head(SHOW_TILES).iterrows():
        print(f"       tile {int(r['tile_id'])} ({r['lat']}, {r['lon']}): {r['lst_min_night']:.2f} °C")
    OUT_DIR.mkdir(exist_ok=True)
    changed.to_csv(OUT_DIR / "cleaning_rule3_tiles.csv", index=False)
    a.loc[bad, "lst_min_night"] = np.nan

    # Rule 5: ndvi min 0 is intended (A clipped water to 0): no change.
    print(f"  5. ndvi: no change (water clipped to 0 by A; min {a['ndvi'].min():.2f})")
    print("  precip_source: " + ", ".join(f"{k} {v:,}" for k, v in
                                          a["precip_source"].value_counts(dropna=False).items()))


# ---------------------------------------------------------------------------
# A-only report
# ---------------------------------------------------------------------------

def column_stats(a):
    print(f"\n{'column':<15} {'NaN %':>6} {'min':>10} {'median':>10} {'max':>10}  check")
    print("-" * 75)
    for col in a.columns:
        s = a[col]
        if not pd.api.types.is_numeric_dtype(s):          # text column: no numeric checks
            print(f"{col:<15} {100 * s.isna().mean():>5.1f}%  (text: "
                  + ", ".join(f"{k} {v:,}" for k, v in s.value_counts().items()) + ")")
            continue
        note = ""
        if col in EARTH_RANGES and EARTH_RANGES[col][1] is not None:
            lo, hi, _ = EARTH_RANGES[col]
            lo = -np.inf if lo is None else lo
            out = ((s < lo) | (s > hi)).sum()
            rng = f"<= {hi}" if lo == -np.inf else f"in [{lo}, {hi}]"
            note = f"OK, {rng}" if not out else f"CHECK: {out:,} not {rng}"
        if s.isna().mean() > 0.30:
            note += "  CHECK: > 30% NaN"
        print(f"{col:<15} {100 * s.isna().mean():>5.1f}% {s.min():>10.2f} {s.median():>10.2f} "
              f"{s.max():>10.2f}  {note}")

    # lst_range = MEAN daily range: can't be larger than (warmest day - coldest night)
    off = a["lst_range"] > a["lst_max_day"] - a["lst_min_night"] + 0.5
    if off.any():
        print(f"\nCHECK lst_range: {off.sum():,} tiles where the mean daily range is larger than "
              f"lst_max_day - lst_min_night")
    neg = (a["lst_range"] < 0).sum()
    if neg:
        print(f"CHECK lst_range: {neg:,} negative values (min {a['lst_range'].min():.2f})")


def place_report(a):
    print("\nReference places (tile containing the point):")
    by_id = a.set_index("tile_id")
    n_check = 0
    for place, (lat, lon, ranges) in PLACES.items():
        tid, clat, clon = tile_of(lat, lon)
        print(f"\n  {place}: tile {tid} ({clat}, {clon})")
        if tid not in by_id.index:
            # e.g. a river or lake tile: use the nearest tile within 50 km, like the known analogs
            km = haversine_km(lat, lon, a["lat"].to_numpy(), a["lon"].to_numpy())
            if km.min() > ANALOG_MAX_KM:
                print(f"    CHECK: tile not in A's file, none within {ANALOG_MAX_KM} km")
                n_check += 1
                continue
            tid = int(a["tile_id"].iloc[km.argmin()])
            print(f"    (not in A's file: water? using nearest tile {tid} "
                  f"({by_id.at[tid, 'lat']}, {by_id.at[tid, 'lon']}), {km.min():.0f} km away)")
        t = by_id.loc[tid]
        for col in ["lst_min_night", "lst_max_day", "lst_range", "albedo", "ndvi", "precip_mm"]:
            v = t[col]
            expected = ranges.get(col)
            if expected is None:
                verdict, txt = "", ""
            elif expected == "nan":
                verdict, txt = ("PASS" if pd.isna(v) else "CHECK"), "expected missing"
            else:
                ok = pd.notna(v) and expected[0] <= v <= expected[1]
                verdict, txt = ("PASS" if ok else "CHECK"), f"plausible {expected[0]}..{expected[1]}"
            n_check += verdict == "CHECK"
            val = "NaN" if pd.isna(v) else f"{v:.2f}"
            extra = f" ({t['precip_source']})" if col == "precip_mm" else ""
            print(f"    {verdict:<5} {col:<14} {val:>9}{extra}  {txt}")
    print(f"\n  {n_check} CHECK(s) at reference places")


def ndvi_filter_report(a):
    """Same rule as score.py step 0 (rules 3-4), before the land mask / DEM rules."""
    polar = a["lat"].abs() > POLAR_LAT
    vegetated = a["ndvi"] > NDVI_MAX
    no_ndvi = a["ndvi"].isna() & ~polar
    kept = ~vegetated & ~no_ndvi
    n = len(a)
    print(f"\nNDVI filter (ndvi <= {NDVI_MAX}, or NaN and |lat| > {POLAR_LAT}):")
    print(f"  pass:              {kept.sum():>8,} ({100 * kept.mean():.1f}%)"
          f"  of which polar NaN {(a['ndvi'].isna() & polar).sum():,}")
    print(f"  removed vegetated: {vegetated.sum():>8,} ({100 * vegetated.mean():.1f}%)")
    print(f"  removed no NDVI:   {no_ndvi.sum():>8,} ({100 * no_ndvi.mean():.1f}%)  (NaN, |lat| <= {POLAR_LAT})")
    print(f"  total:             {n:>8,}")


# ---------------------------------------------------------------------------

def main():
    print("=== Teammate A ===")
    a = load_csv(FILE_A, "It is provided by teammate A (data/raw/earth_features_A.csv).")
    land = load_csv(FILE_LAND, "It is provided by teammate A (data/raw/land_tiles.csv).")
    check_columns(a, A_COLS, FILE_A.name, "teammate A")
    check_columns(land, ["tile_id", "land_frac"], FILE_LAND.name, "teammate A")
    check_grid(a, FILE_A.name)
    check_grid(land, FILE_LAND.name)
    not_in_land = ~a["tile_id"].isin(land["tile_id"])
    if not_in_land.any():
        print(f"  NOTE {not_in_land.sum():,} A tiles are not in land_tiles.csv (land_frac = NaN)")
    a = a.merge(land[["tile_id", "land_frac"]], on="tile_id", how="left")
    clean(a)

    print("\n=== A-only report ===")
    column_stats(a)
    place_report(a)
    ndvi_filter_report(a)

    # --- B ---------------------------------------------------------------------
    print("\n=== Teammate B ===")
    if not FILE_B.exists():
        stop(f"waiting for teammate B ({FILE_B.relative_to(DATA_DIR.parent)}: "
             f"{', '.join(B_COLS)}).")
    b = load_csv(FILE_B, "It is provided by teammate B.")
    check_columns(b, B_COLS, FILE_B.name, "teammate B")
    check_grid(b, FILE_B.name)
    if "lat" in b.columns or "lon" in b.columns:
        print("  NOTE B's lat/lon ignored (A's are used; both are checked against grid_config)")
    b = b[B_COLS]
    in_b = a["tile_id"].isin(b["tile_id"])
    print(f"  A tiles found in B: {in_b.sum():,} of {len(a):,}; "
          f"B tiles not in A (dropped): {(~b['tile_id'].isin(a['tile_id'])).sum():,}")
    if not in_b.any():
        stop("no tile_id in common between A and B: same grid_config.py?")

    # --- Merge + write --------------------------------------------------------
    merged = a.merge(b, on="tile_id", how="left")
    merged["max_sun_elev"] = (90 - merged["lat"].abs() + 23.44).clip(0, 90)
    merged = merged[SCHEMAS["earth_features"] + EXTRA_COLS]

    tmp = OUT_FILE.with_suffix(".csv.tmp")
    merged.to_csv(tmp, index=False, na_rep="")       # missing = empty (load_csv reads it as NaN)
    tmp.replace(OUT_FILE)                            # only now is the old file replaced
    print(f"\nWrote {OUT_FILE.relative_to(DATA_DIR.parent)}: {len(merged):,} tiles, "
          f"{len(merged.columns)} columns")


if __name__ == "__main__":
    main()
