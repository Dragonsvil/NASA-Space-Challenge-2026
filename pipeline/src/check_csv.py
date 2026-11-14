"""
check_csv.py — check an input CSV BEFORE sending it to the pipeline.

    python src/check_csv.py data/earth_features.csv     (A and B)
    python src/check_csv.py data/targets.csv            (C)
    python src/check_csv.py data/known_analogs.csv      (C)

The file type is detected from its columns, so the file name does not matter.
Missing values written as -9999 (grid_config.NODATA, or anything < -9000) are converted
to NaN first, and the count per column is reported.
Prints ERRORS (must fix), WARNINGS (look at them), then NaN % and min/max per column.
Exit code: 0 = no errors, 1 = errors.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from common import grid_config, nodata_to_nan

# ---------------------------------------------------------------------------
# Expected schemas (exact column names and order, from CLAUDE.md)
# ---------------------------------------------------------------------------
SCHEMAS = {
    "earth_features": ["tile_id", "lat", "lon", "lst_min_night", "lst_max_day", "lst_range",
                       "lst_mean_night", "lst_mean_day",
                       "albedo", "ndvi", "precip_mm", "slope_mean", "slope_std",
                       "mafic_idx", "quartz_idx", "dust_aod", "max_sun_elev"],
    "targets": ["target", "feature", "value", "unit", "source"],
    "known_analogs": ["name", "lat", "lon", "analog_for", "used_for"],
}

# Sanity ranges for earth_features: column -> (min allowed, max allowed, hint if outside)
EARTH_RANGES = {
    "lat":           (-90, 90,     "latitude in degrees"),
    "lon":           (-180, 180,   "longitude in degrees, -180..180 (not 0..360)"),
    "lst_min_night": (-100, 60,    "°C expected (yearly minimum, not scored)"),
    "lst_max_day":   (-90, 80,     "°C expected (yearly maximum, not scored)"),
    "lst_mean_night": (-90, 50,    "°C expected (MEAN night temperature)"),
    "lst_mean_day":  (-90, 70,     "°C expected (MEAN day temperature)"),
    "lst_range":     (None, 100,   "°C, MEAN daily day-night range"),
    "albedo":        (0, 1,        "albedo is 0-1 (MODIS raw is x1000: divide by 1000)"),
    "ndvi":          (-1, 1,       "NDVI is -1..1 (MODIS raw is x10000: divide by 10000)"),
    "precip_mm":     (0, 15000,    "mm per YEAR"),
    "slope_mean":    (0, 90,       "degrees (not %, not radians)"),
    "slope_std":     (0, 90,       "degrees"),
    "mafic_idx":     (None, None,  ""),
    "quartz_idx":    (None, None,  ""),
    "dust_aod":      (0, 5,        "AOD is unitless, usually 0-2"),
    "max_sun_elev":  (0, 90,       "degrees"),
}

TEMP_COLS = ["lst_min_night", "lst_max_day", "lst_range", "lst_mean_night", "lst_mean_day"]
DIM_IDS = ["temp_range", "temp_min", "albedo", "slope", "roughness",
           "mafic", "aridity", "dust", "sun_angle"]
META_FEATURES = ["name", "body", "lat", "lon"]       # target metadata rows in targets.csv
CATEGORIES = ["low", "med", "high"]
MAX_NAN_SHARE = 0.30        # flag columns with more NaN than this (after -9999 conversion)
# Extra columns allowed after the schema columns (written by merge_inputs.py, not scored).
# Text columns among them get no numeric checks.
ALLOWED_EXTRAS = {"earth_features": ["precip_source", "precip_era5_mm", "land_frac"]}

errors = []
warnings = []


def error(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


# ---------------------------------------------------------------------------
# Generic checks
# ---------------------------------------------------------------------------

def detect_kind(columns):
    """Return the schema name whose columns best match this file."""
    best, best_overlap = None, 0
    for kind, expected in SCHEMAS.items():
        overlap = len(set(columns) & set(expected))
        if overlap > best_overlap:
            best, best_overlap = kind, overlap
    return best


def check_columns(df, kind):
    expected = SCHEMAS[kind]
    cols = list(df.columns)
    missing = [c for c in expected if c not in cols]
    allowed = ALLOWED_EXTRAS.get(kind, [])
    known_extra = [c for c in cols if c in allowed]
    if known_extra:
        print(f"Extra columns (kept, not scored): {known_extra}")
    cols = [c for c in cols if c not in allowed]
    extra = [c for c in cols if c not in expected]
    if missing:
        error(f"Missing columns: {missing}")
    if extra:
        error(f"Unexpected columns: {extra}  (check spelling / remove them)")
    if not missing and not extra and cols != expected:
        warn(f"Columns are in a different order than expected: {expected}")
    stripped = [c for c in cols if c != c.strip()]
    if stripped:
        error(f"Column names with spaces around them: {stripped}")


def print_summary(df):
    """NaN % and min / max for each column."""
    print(f"\n{'column':<15} {'type':<8} {'NaN %':>6} {'min':>14} {'max':>14}")
    print("-" * 61)
    for col in df.columns:
        s = df[col]
        nan_pct = 100 * s.isna().mean()
        if pd.api.types.is_numeric_dtype(s):
            lo, hi = s.min(), s.max()
            lo = f"{lo:.3f}" if pd.notna(lo) else "-"
            hi = f"{hi:.3f}" if pd.notna(hi) else "-"
            kind = "number"
        else:
            lo, hi, kind = "", "", "text"
        print(f"{col:<15} {kind:<8} {nan_pct:>5.1f}% {lo:>14} {hi:>14}")


def check_numeric(df, cols):
    """Columns that must be numbers: report text values that are not."""
    for col in cols:
        if col not in df.columns:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            bad = df[col][pd.to_numeric(df[col], errors="coerce").isna() & df[col].notna()]
            error(f"'{col}' must be numeric, found text values like {bad.unique()[:5].tolist()}")
            df[col] = pd.to_numeric(df[col], errors="coerce")


# ---------------------------------------------------------------------------
# earth_features.csv
# ---------------------------------------------------------------------------

def check_earth(df):
    check_numeric(df, [c for c in SCHEMAS["earth_features"] if c != "tile_id"])
    if "tile_id" not in df.columns or "lat" not in df.columns or "lon" not in df.columns:
        return

    # --- tile_id: integer row * N_COLS + col, from ../grid_config.py ------
    ids = pd.to_numeric(df["tile_id"], errors="coerce")
    n_tiles = grid_config.N_ROWS * grid_config.N_COLS
    bad = ids.isna() | (ids % 1 != 0) | (ids < 0) | (ids >= n_tiles)
    if bad.any():
        error(f"{bad.sum()} tile_id(s) are not integers in 0..{n_tiles - 1} "
              f"(grid_config: tile_id = row * {grid_config.N_COLS} + col), "
              f"e.g. {df['tile_id'][bad].head(3).tolist()}")
    ok = ~bad
    ids_ok = ids[ok].astype(np.int64)

    # lat / lon must be the CENTER of that tile, as grid_config.tile_center says
    row, col = ids_ok // grid_config.N_COLS, ids_ok % grid_config.N_COLS
    exp_lat, exp_lon = grid_config.tile_center(row, col)
    wrong = ((df.loc[ok, "lat"] - exp_lat).abs() > 1e-6) | ((df.loc[ok, "lon"] - exp_lon).abs() > 1e-6)
    if wrong.any():
        i = wrong[wrong].index[0]
        error(f"{wrong.sum()} row(s) where lat/lon is not the center of tile_id "
              f"(grid_config.tile_center), e.g. row {i}: tile_id {df.loc[i, 'tile_id']} "
              f"-> center ({exp_lat[i]}, {exp_lon[i]}), file has ({df.loc[i, 'lat']}, {df.loc[i, 'lon']}). "
              f"Corner instead of center, or rows/cols swapped?")

    dups = ids.duplicated() & ids.notna()
    if dups.any():
        error(f"{dups.sum()} duplicated tile_id(s), e.g. {df['tile_id'][dups].head(3).tolist()}")

    # --- units sanity -----------------------------------------------------
    for col in TEMP_COLS:
        s = df[col].dropna()
        if s.empty:
            continue
        if s.median() > 1000:
            error(f"'{col}' median = {s.median():.0f}: looks like RAW MODIS LST (Kelvin x 50). "
                  f"Convert: value * 0.02 - 273.15")
        elif s.median() > 150 and col != "lst_range":
            error(f"'{col}' median = {s.median():.0f}: looks like KELVIN. Convert: value - 273.15")

    for col, (lo, hi, hint) in EARTH_RANGES.items():
        if hi is None or col not in df.columns:
            continue
        s = df[col]
        out = (s > hi) if lo is None else (s < lo) | (s > hi)
        if out.any():
            error(f"{out.sum()} value(s) of '{col}' outside [{lo}, {hi}] "
                  f"(min {s.min():.3f}, max {s.max():.3f}). {hint}")

    if df["slope_mean"].max() <= 1.6 and df["slope_mean"].max() > 0:
        warn("slope_mean never above 1.6: are slopes in RADIANS? Must be degrees.")
    if df["albedo"].max() <= 0.01:
        warn("albedo max <= 0.01: scaled twice?")

    # lst_range = MEAN daily day-night range (CLAUDE.md). Negative: warning (merge_inputs clips it to 0).
    # A mean daily range can't exceed (warmest day - coldest night).
    neg = df["lst_range"] < 0
    if neg.any():
        warn(f"{neg.sum()} negative lst_range value(s) (min {df['lst_range'].min():.2f}): "
             f"merge_inputs.py clips them to 0")
    wrong = df["lst_range"] > df["lst_max_day"] - df["lst_min_night"] + 0.5
    if wrong.any():
        warn(f"{wrong.sum()} row(s) where lst_range (mean daily range) > lst_max_day - lst_min_night")
    # lst_range = lst_mean_day - lst_mean_night (where not clipped to 0 by merge_inputs)
    pos = df["lst_mean_day"] >= df["lst_mean_night"]
    off = pos & ((df["lst_mean_day"] - df["lst_mean_night"] - df["lst_range"]).abs() > 0.5)
    if off.any():
        warn(f"{off.sum()} row(s) where lst_range != lst_mean_day - lst_mean_night (by > 0.5 °C)")
    # a mean lies between the extremes
    below = df["lst_mean_night"] < df["lst_min_night"] - 0.5
    above = df["lst_mean_day"] > df["lst_max_day"] + 0.5
    if below.any() or above.any():
        warn(f"{below.sum()} row(s) with lst_mean_night < lst_min_night, "
             f"{above.sum()} with lst_mean_day > lst_max_day: means outside the extremes?")
    if (df["lst_min_night"] > df["lst_max_day"]).any():
        error("Some rows have lst_min_night > lst_max_day: columns swapped?")

    # max_sun_elev rule from CLAUDE.md
    expected_sun = (90 - df["lat"].abs() + 23.44).clip(0, 90)
    off = (df["max_sun_elev"] - expected_sun).abs() > 0.5
    if off.any():
        warn(f"{off.sum()} row(s) where max_sun_elev != clip(90 - |lat| + 23.44, 0, 90)")

    for col in df.columns:
        if col in ALLOWED_EXTRAS["earth_features"] and not pd.api.types.is_numeric_dtype(df[col]):
            continue                                   # text extra (precip_source): no numeric checks
        if df[col].isna().all():
            error(f"Column '{col}' is completely empty (after -9999 -> NaN)")
        elif df[col].isna().mean() > MAX_NAN_SHARE:
            warn(f"Column '{col}' is {100 * df[col].isna().mean():.0f}% NaN after -9999 -> NaN "
                 f"(more than {100 * MAX_NAN_SHARE:.0f}%): wrong band, mask too strict, or bad scaling?")

    print(f"Tiles: {len(df):,}")


# ---------------------------------------------------------------------------
# targets.csv
# ---------------------------------------------------------------------------

def check_targets(df):
    if not {"target", "feature", "value"}.issubset(df.columns):
        return
    for target in ["jezero", "lunar_south_pole"]:
        if target not in set(df["target"]):
            error(f"Target '{target}' missing (expected targets: jezero, lunar_south_pole)")

    # Empty values (e.g. an unfilled targets_TEMPLATE.csv): one clear error, then ignore those rows
    empty = df["value"].isna() | (df["value"].astype(str).str.strip() == "")
    if empty.any():
        rows = (df.loc[empty, "target"] + "/" + df.loc[empty, "feature"]).tolist()
        error(f"{empty.sum()} empty value(s), fill them in (number, low/med/high or n/a): {rows}")
    df = df[~empty].copy()
    df["value"] = df["value"].astype(str).str.strip()

    other = sorted(set(df["target"]) - {"jezero", "lunar_south_pole"})
    if other:
        warn(f"Extra target(s) {other}: the pipeline will ignore them unless told otherwise")

    unknown = sorted(set(df["feature"]) - set(DIM_IDS) - set(META_FEATURES))
    if unknown:
        error(f"Unknown feature(s) {unknown}. Allowed: {DIM_IDS} + metadata {META_FEATURES}")

    dup = df.duplicated(["target", "feature"])
    if dup.any():
        error(f"Duplicated (target, feature) rows: {df.loc[dup, ['target', 'feature']].values.tolist()}")

    for _, row in df.iterrows():
        feat, val = row["feature"], row["value"]
        where = f"{row['target']}/{feat}"
        if feat in ("name", "body"):
            continue
        if val.lower() in CATEGORIES or val.lower() == "n/a":
            if feat in ("lat", "lon"):
                error(f"{where}: lat/lon must be a number, got '{val}'")
            continue
        try:
            x = float(val)
        except ValueError:
            error(f"{where}: value '{val}' is not a number, low/med/high, or n/a")
            continue
        if feat == "albedo" and not 0 <= x <= 1:
            error(f"{where}: albedo {x} not in 0-1")
        if feat in ("slope", "roughness", "sun_angle") and not 0 <= x <= 90:
            error(f"{where}: {x} not in 0-90 degrees")
        if feat == "temp_min" and x > 100:
            error(f"{where}: {x} looks like Kelvin, must be °C")
        if feat == "aridity" and x < 0:
            error(f"{where}: precipitation can't be negative")

    for target in df["target"].unique():
        feats = set(df.loc[df["target"] == target, "feature"])
        missing_meta = [f for f in META_FEATURES if f not in feats]
        if missing_meta:
            warn(f"{target}: missing metadata rows {missing_meta} (needed for results.json)")

    if "source" in df.columns:
        no_source = df["source"].isna() | (df["source"].astype(str).str.strip() == "")
        dim_rows = df["feature"].isin(DIM_IDS)
        if (no_source & dim_rows).any():
            missing = (df.loc[no_source & dim_rows, "target"] + "/"
                       + df.loc[no_source & dim_rows, "feature"]).tolist()
            error(f"{len(missing)} value(s) without a source (paper, PDS product or NASA page URL): {missing}")
        if (no_source & ~dim_rows).any():
            warn(f"{(no_source & ~dim_rows).sum()} name/body/lat/lon row(s) without a source")
        if (df["source"].astype(str).str.upper() == "FAKE").any():
            warn("Some sources are 'FAKE': replace with real references before the demo")

    print(f"Rows: {len(df)}")


# ---------------------------------------------------------------------------
# known_analogs.csv
# ---------------------------------------------------------------------------

def check_analogs(df):
    check_numeric(df, ["lat", "lon"])
    if "lat" in df.columns:
        if ((df["lat"] < -90) | (df["lat"] > 90)).any():
            error("Some lat values are outside -90..90")
    if "lon" in df.columns:
        if ((df["lon"] < -180) | (df["lon"] > 180)).any():
            error("Some lon values are outside -180..180")
    if "name" in df.columns and df["name"].duplicated().any():
        error(f"Duplicated names: {df.loc[df['name'].duplicated(), 'name'].tolist()}")
    if "analog_for" in df.columns:
        bad = ~df["analog_for"].astype(str).str.contains("Mars|Moon")
        if bad.any():
            error(f"analog_for must mention Mars and/or Moon, got {df.loc[bad, 'analog_for'].tolist()}")
    print(f"Analogs: {len(df)}")


# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) != 2:
        print("Usage: python src/check_csv.py <file.csv>")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: file not found: {path}")
        sys.exit(1)

    # keep_default_na=False: otherwise pandas silently turns the text "n/a" into NaN
    df = pd.read_csv(path, keep_default_na=False, na_values=[""])
    kind = detect_kind(list(df.columns))
    if kind is None:
        print(f"ERROR: {path} does not look like any of {list(SCHEMAS)}. Columns: {list(df.columns)}")
        sys.exit(1)
    print(f"Checking {path} as '{kind}'\n")

    # Same -9999 -> NaN conversion as the pipeline (common.load_csv), with a report
    converted = nodata_to_nan(df, quiet=True)
    if converted:
        print(f"No-data values (< -9000) converted to NaN, per column:")
        for col, n in converted.items():
            print(f"  {col:<15} {n:>8,}  ({100 * n / len(df):.1f}%)")
    else:
        print("No -9999 / no-data values found.")
    print()

    check_columns(df, kind)
    if df.empty:
        error("File has no rows")
    elif kind == "earth_features":
        check_earth(df)
    elif kind == "targets":
        check_targets(df)
    else:
        check_analogs(df)

    print_summary(df)

    print()
    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR:   {e}")
    if errors:
        print(f"\n{len(errors)} error(s): fix them before sending the file.")
        sys.exit(1)
    print(f"\nOK ({len(warnings)} warning(s)).")


if __name__ == "__main__":
    main()
