"""
merge_inputs.py — build data/earth_features.csv from the raw exports of A and B.
Step 0 of run_all.py.

    python src/merge_inputs.py

Reads (data/raw/, not in git):
    earth_features_A.csv   teammate A: tile_id, lat, lon, lst_min_night, lst_max_day, lst_range,
                           albedo, ndvi, precip_mm, precip_source, precip_era5_mm
    earth_features_A_extra.csv  teammate A: tile_id, lst_mean_night, lst_mean_day (°C, multi-year means)
    land_tiles.csv         teammate A: tile_id, lat, lon, land_frac
    earth_features_B.csv   teammate B: tile_id, slope_mean, slope_std, mafic_idx, quartz_idx, dust_aod

Does:
    1. checks every tile_id is a valid grid id and lat/lon = grid_config tile center
    2. cleaning rules 1-6 (README, "Data cleaning"), printing how many values each changes
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
FILE_A_EXTRA = RAW / "earth_features_A_extra.csv"
FILE_B = RAW / "earth_features_B.csv"
OUT_FILE = DATA_DIR / "earth_features.csv"

A_COLS = ["tile_id", "lat", "lon", "lst_min_night", "lst_max_day", "lst_range",
          "albedo", "ndvi", "precip_mm", "precip_source", "precip_era5_mm"]
B_COLS = ["tile_id", "slope_mean", "slope_std", "mafic_idx", "quartz_idx", "dust_aod"]
ERA5_MAX_MM = 12000           # cleaning rule 4
COLD_BAD_C = -40              # cleaning rule 3: nights colder than this ...
COLD_BAD_MAX_LAT = 45         # ... where |lat| < 45 are bad pixels (45-60° can really be that cold)
SHOW_TILES = 20               # rule 3: tiles printed (all of them go to out/cleaning_rule3_tiles.csv)
A_EXTRA_COLS = ["tile_id", "lst_mean_night", "lst_mean_day"]
EXTRA_COLS = ["precip_source", "precip_era5_mm", "land_frac"]   # kept, not used for scoring

# Reference places: (lat, lon, {column: (plausible min, plausible max)}).
# Ranges are deliberately wide: they catch unit / scaling / masking mistakes, not small biases.
# "nan" = the value is expected to be missing (NDVI south of 60°S, A's choice).
PLACES = {
    "Sahara (23N, 13E)": (23, 13, {
        "lst_min_night": (-5, 30), "lst_max_day": (35, 75), "lst_mean_night": (10, 30), "lst_mean_day": (30, 55), "albedo": (0.2, 0.5),
        "ndvi": (0, 0.15), "precip_mm": (0, 100)}),
    "Atacama (-24.5, -69.25)": (-24.5, -69.25, {
        "lst_min_night": (-20, 15), "lst_max_day": (20, 70), "lst_mean_night": (-15, 10), "lst_mean_day": (15, 45), "albedo": (0.1, 0.5),
        "ndvi": (0, 0.15), "precip_mm": (0, 150)}),
    "Amazon (-3, -60)": (-3, -60, {
        "lst_min_night": (10, 28), "lst_max_day": (22, 45), "lst_mean_night": (18, 26), "lst_mean_day": (25, 38), "albedo": (0.05, 0.2),
        "ndvi": (0.5, 1), "precip_mm": (1500, 4000)}),
    "Antarctic plateau (-80.4, 77.1)": (-80.4, 77.1, {
        "lst_min_night": (-100, -45), "lst_max_day": (-60, -10), "lst_mean_night": (-70, -40), "lst_mean_day": (-65, -35), "albedo": (0.7, 0.95),
        "ndvi": "nan", "precip_mm": (0, 100)}),
    "McMurdo Dry Valleys (-77.5, 162)": (-77.5, 162, {
        "lst_min_night": (-70, -15), "lst_max_day": (-35, 25), "lst_mean_night": (-40, -10), "lst_mean_day": (-35, 0), "albedo": (0.1, 0.9),
        "ndvi": "nan", "precip_mm": (0, 300)}),
}


# Same idea for B's terrain / mineral columns. "nan" = expected missing (B: no usable ASTER data in
# Iceland and Antarctica), "present" = must have a value, no plausible range known (index units).
A_PLACE_COLS = ["lst_mean_night", "lst_mean_day", "lst_range", "lst_min_night", "lst_max_day",
                "albedo", "ndvi", "precip_mm"]
B_PLACE_COLS = ["slope_mean", "slope_std", "mafic_idx", "quartz_idx"]
B_PLACES = {
    "Sahara (23N, 13E)": (23, 13, {"slope_mean": (0, 8), "slope_std": (0, 8), "mafic_idx": "present"}),
    "Atacama (-24.5, -69.25)": (-24.5, -69.25, {"slope_mean": (0, 15), "slope_std": (0, 12),
                                                "mafic_idx": "present"}),
    "Amazon (-3, -60)": (-3, -60, {"slope_mean": (0, 5), "slope_std": (0, 5)}),
    "Antarctic plateau (-80.4, 77.1)": (-80.4, 77.1, {"slope_mean": (0, 2), "slope_std": (0, 2),
                                                      "mafic_idx": "nan"}),
    "McMurdo Dry Valleys (-77.5, 162)": (-77.5, 162, {"slope_mean": (3, 30), "slope_std": (2, 20),
                                                      "mafic_idx": "nan"}),
    "Iceland lava field (64.0, -19.0)": (64.0, -19.0, {"slope_mean": (1, 20), "slope_std": (1, 15),
                                                       "mafic_idx": "nan"}),
    "Mauna Kea (19.8, -155.5)": (19.8, -155.5, {"slope_mean": (3, 25), "slope_std": (1, 15),
                                                "mafic_idx": "present"}),
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

    # Rule 3: impossibly cold nights at low/mid latitudes = bad pixels -> NaN.
    # Not up to 60°: Siberian / Canadian winters at 45-60° really reach -40..-60 °C.
    # Applied to the yearly minimum AND to the mean night temperature.
    changed_all = []
    for col in ["lst_min_night", "lst_mean_night"]:
        bad = (a[col] < COLD_BAD_C) & (a["lat"].abs() < COLD_BAD_MAX_LAT)
        print(f"  3. {col} < {COLD_BAD_C} °C, |lat| < {COLD_BAD_MAX_LAT} -> NaN:  {bad.sum():>8,} values")
        if bad.any():
            changed = a.loc[bad, ["tile_id", "lat", "lon", col, "ndvi"]].rename(columns={col: "value"})
            changed.insert(0, "column", col)
            changed_all.append(changed)
            bands = pd.cut(changed["lat"].abs(), [0, 15, 30, 45], right=False).value_counts().sort_index()
            print("       by |lat|: " + ", ".join(f"{b.left}-{b.right}°: {n:,}" for b, n in bands.items()))
            print(f"       of which pass the NDVI filter (ndvi <= {NDVI_MAX}): {(changed['ndvi'] <= NDVI_MAX).sum():,}")
            print(f"       {SHOW_TILES} coldest (full list: out/cleaning_rule3_tiles.csv):")
            for _, r in changed.sort_values("value").head(SHOW_TILES).iterrows():
                print(f"       tile {int(r['tile_id'])} ({r['lat']}, {r['lon']}): {r['value']:.2f} °C")
        a.loc[bad, col] = np.nan
    OUT_DIR.mkdir(exist_ok=True)
    if changed_all:
        pd.concat(changed_all).to_csv(OUT_DIR / "cleaning_rule3_tiles.csv", index=False)

    # Rule 6: lst_range is DEFINED as lst_mean_day - lst_mean_night: NaN if either mean is NaN
    # (after rule 3, which can remove a mean night)
    no_mean = (a["lst_mean_night"].isna() | a["lst_mean_day"].isna()) & a["lst_range"].notna()
    a.loc[no_mean, "lst_range"] = np.nan
    print(f"  6. lst_mean_night or lst_mean_day NaN -> lst_range NaN: {no_mean.sum():>6,} tiles")

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
        if s.isna().all():
            note = "EMPTY (100% NaN)"
        elif s.isna().mean() > 0.30:
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


def place_report(a, places=PLACES, cols=A_PLACE_COLS):
    print("\nReference places (tile containing the point):")
    by_id = a.set_index("tile_id")
    n_check = 0
    for place, (lat, lon, ranges) in places.items():
        tid, clat, clon = tile_of(lat, lon)
        print(f"\n  {place}: tile {tid} ({clat}, {clon})")
        if tid not in by_id.index:
            # e.g. a river or lake tile: use the nearest tile within 50 km, like the known analogs
            km = haversine_km(lat, lon, a["lat"].to_numpy(), a["lon"].to_numpy())
            if km.min() > ANALOG_MAX_KM:
                print(f"    CHECK: tile not in the file, none within {ANALOG_MAX_KM} km")
                n_check += 1
                continue
            tid = int(a["tile_id"].iloc[km.argmin()])
            print(f"    (not in the file: water? using nearest tile {tid} "
                  f"({by_id.at[tid, 'lat']}, {by_id.at[tid, 'lon']}), {km.min():.0f} km away)")
        t = by_id.loc[tid]
        for col in cols:
            v = t[col]
            expected = ranges.get(col)
            if expected is None:
                verdict, txt = "", ""
            elif expected == "nan":
                verdict, txt = ("PASS" if pd.isna(v) else "CHECK"), "expected missing"
            elif expected == "present":
                verdict, txt = ("PASS" if pd.notna(v) else "CHECK"), "expected a value"
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

    # Mean night / day temperatures (A's second file): must cover the same tiles
    extra = load_csv(FILE_A_EXTRA, "It is provided by teammate A (data/raw/earth_features_A_extra.csv).")
    check_columns(extra, A_EXTRA_COLS, FILE_A_EXTRA.name, "teammate A")
    check_grid(extra, FILE_A_EXTRA.name)
    missing = ~a["tile_id"].isin(extra["tile_id"])
    unknown = ~extra["tile_id"].isin(a["tile_id"])
    if missing.any() or unknown.any():
        print(f"  CHECK {FILE_A_EXTRA.name}: {missing.sum():,} A tiles missing (-> NaN), e.g. "
              f"{a.loc[missing, 'tile_id'].head(3).tolist()}; {unknown.sum():,} extra ids not in A "
              f"(dropped), e.g. {extra.loc[unknown, 'tile_id'].head(3).tolist()}")
    else:
        print(f"  OK  {FILE_A_EXTRA.name}: same {len(extra):,} tile_ids as {FILE_A.name}")
    a = a.merge(extra[A_EXTRA_COLS], on="tile_id", how="left")
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
    ignored = [c for c in ["lat", "lon", "max_sun_elev"] if c in b.columns]
    if ignored:
        print(f"  NOTE B's {ignored} ignored: lat/lon come from A (both checked against grid_config), "
              f"max_sun_elev is recomputed from lat")
    b = b[B_COLS]
    in_b = a["tile_id"].isin(b["tile_id"])
    b_only = ~b["tile_id"].isin(a["tile_id"])
    print(f"  A tiles found in B: {in_b.sum():,} of {len(a):,}")
    if (~in_b).any():
        bands = pd.cut(a.loc[~in_b, "lat"], [-90, -60, 0, 60, 83, 90]).value_counts().sort_index()
        print(f"  A tiles NOT in B (B columns = NaN): {(~in_b).sum():,}, by latitude: "
              + ", ".join(f"{iv.left:g}..{iv.right:g}: {n:,}" for iv, n in bands.items() if n))
    print(f"  B tiles NOT in A (dropped): {b_only.sum():,}"
          + (f", e.g. {b.loc[b_only, 'tile_id'].head(3).tolist()}" if b_only.any() else ""))
    if not in_b.any():
        stop("no tile_id in common between A and B: same grid_config.py?")

    # --- Merge ------------------------------------------------------------------
    merged = a.merge(b, on="tile_id", how="left")
    merged["max_sun_elev"] = (90 - merged["lat"].abs() + 23.44).clip(0, 90)
    merged = merged[SCHEMAS["earth_features"] + EXTRA_COLS]

    print("\n=== Merged report (A + A_extra + B) ===")
    column_stats(merged)
    empty = [c for c in B_COLS[1:] if merged[c].isna().all()]
    for c in empty:
        print(f"WARNING: {c} is 100% empty: score.py will DROP its dimension for every target")
    place_report(merged, B_PLACES, B_PLACE_COLS)

    # --- Write ------------------------------------------------------------------

    tmp = OUT_FILE.with_suffix(".csv.tmp")
    merged.to_csv(tmp, index=False, na_rep="")       # missing = empty (load_csv reads it as NaN)
    tmp.replace(OUT_FILE)                            # only now is the old file replaced
    print(f"\nWrote {OUT_FILE.relative_to(DATA_DIR.parent)}: {len(merged):,} tiles, "
          f"{len(merged.columns)} columns")


if __name__ == "__main__":
    main()
