"""
score.py — score every Earth tile against each target (Jezero, lunar south pole).

    python src/score.py

Method (see "Scoring method" in CLAUDE.md):
    0. filters BEFORE scoring, in this order (column 'scoring_filter' says which one removed a tile):
       - "no DEM":    slope_mean missing (the Copernicus DEM only covers land: our land mask)
       - "off land":  not inside a Natural Earth country and no town within 100 km
       - "vegetated": NDVI > 0.3
       - "no NDVI":   NDVI missing and not polar (|lat| <= 60)
       Per target, a tile is also dropped if more than half its dims are missing, or if the dims it
       has cover less than 2/3 of a profile's total weight (for ANY profile, so every profile of a
       target ranks the same tiles and meta.tiles_scored stays one number per target).
       Only the remaining tiles are ranked.
    gap(t,d)   = |earth_value(t,d) - target_value(T,d)|      in REAL units (no z-scores)
    score(t,d) = 100 * (1 - percentile_rank(gap)) among the kept tiles, ties averaged, int
    total(t,p) = weighted mean of the dimension scores, weights from PROFILES below,
                 over the dimensions that are valid for this tile and target

Reads:  data/earth_features.csv, data/targets.csv
Writes: out/scores.csv          one row per tile: raw values, scores, totals, global ranks
        out/target_values.csv   the target value actually used for each dimension
"""

import numpy as np
import pandas as pd

from common import EARTH_DIR, TARGETS_DIR, OUT_DIR, land_mask, load_csv, region_names

# ---------------------------------------------------------------------------
# MISSION PROFILES — weights 0..3 per dimension. Tune them HERE (and only here).
# ---------------------------------------------------------------------------
PROFILES = {
    "rover":   {"slope": 3, "roughness": 3, "albedo": 2, "mafic": 1, "aridity": 1,
                "temp_min": 1, "temp_range": 1, "dust": 2, "sun_angle": 2},
    "geology": {"slope": 1, "roughness": 1, "albedo": 1, "mafic": 3, "aridity": 3,
                "temp_min": 1, "temp_range": 1, "dust": 1, "sun_angle": 0},
    "polar":   {"slope": 1, "roughness": 1, "albedo": 1, "mafic": 0, "aridity": 1,
                "temp_min": 3, "temp_range": 3, "dust": 0, "sun_angle": 3},
}

# Vegetation filter: vegetated land can never be a Moon/Mars analog.
NDVI_MAX = 0.3          # tiles with mean NDVI above this are not scored
POLAR_LAT = 60          # tiles with NDVI missing are kept only if |lat| > POLAR_LAT

# A tile gets a total only if the dims it has carry at least this share of a profile's weight
MIN_WEIGHT_COVERAGE = 2 / 3

# Dimension id -> (CSV column, which bodies use it)
DIMENSIONS = {
    "temp_range": ("lst_range",     ["Mars", "Moon"]),
    "temp_min":   ("lst_mean_night", ["Mars", "Moon"]),   # id kept for the website; MEAN night temp
    "albedo":     ("albedo",        ["Mars", "Moon"]),
    "slope":      ("slope_mean",    ["Mars", "Moon"]),
    "roughness":  ("slope_std",     ["Mars", "Moon"]),
    "mafic":      ("mafic_idx",     ["Mars", "Moon"]),
    "aridity":    ("precip_mm",     ["Mars", "Moon"]),
    "dust":       ("dust_aod",      ["Mars"]),
    "sun_angle":  ("max_sun_elev",  ["Moon"]),
}

# Categorical target values -> percentile of the Earth distribution of that feature
CATEGORY_PERCENTILE = {"low": 15, "med": 50, "high": 85}



# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_earth():
    # load_csv also turns -9999 (no data) into NaN and prints the counts
    earth = load_csv(EARTH_DIR / "earth_features.csv",
                     "It is provided by teammates A and B (Earth Engine export). "
                     "For testing: python src/make_fake_data.py")
    # Sun angle: Earth value comes from the latitude, as CLAUDE.md says
    # (max sun elevation at noon on the summer solstice).
    earth["max_sun_elev"] = (90 - earth["lat"].abs() + 23.44).clip(0, 90)
    return earth


def load_targets():
    """Return {target_id: {"name", "body", "lat", "lon", "raw": {dim: text value}}}."""
    rows = load_csv(TARGETS_DIR / "targets.csv",
                    "It is provided by teammate C (targets). For testing: python src/make_fake_data.py")
    rows["value"] = rows["value"].astype(str).str.strip()
    targets = {}
    for target_id, group in rows.groupby("target", sort=False):
        values = dict(zip(group["feature"], group["value"]))
        targets[target_id] = {
            "name": values.get("name", target_id),
            "body": values.get("body", ""),
            "lat": values.get("lat"),
            "lon": values.get("lon"),
            "raw": {d: values[d] for d in DIMENSIONS if d in values},
        }
    return targets


# ---------------------------------------------------------------------------
# Filters applied before scoring: land mask, then vegetation
# ---------------------------------------------------------------------------

def apply_filters(earth):
    """
    Add a column 'scoring_filter' = "kept", "no DEM", "off land", "vegetated" or "no NDVI"
    (the FIRST rule that removed the tile). Only "kept" tiles are scored and ranked.
    Validation uses this column to explain why a known analog has no score.
    """
    earth["scoring_filter"] = "kept"

    def remove(mask, reason):
        mask = mask & (earth["scoring_filter"] == "kept")      # only count each tile once
        earth.loc[mask, "scoring_filter"] = reason
        return int(mask.sum())

    print(f"\nFilters before scoring ({len(earth):,} tiles):")
    n = remove(earth["slope_mean"].isna(), "no DEM")
    print(f"  no DEM:    {n:>7,} removed (slope_mean missing: DEM covers land only)")

    still = earth["scoring_filter"] == "kept"
    on_land, in_polygon = land_mask(earth.loc[still, "lat"], earth.loc[still, "lon"])
    off_land = pd.Series(False, index=earth.index)
    off_land[still] = ~on_land
    n = remove(off_land, "off land")
    print(f"  off land:  {n:>7,} removed (outside every country and no town within 100 km; "
          f"{int((on_land & ~in_polygon).sum()):,} kept only thanks to a nearby town)")

    ndvi = earth["ndvi"]
    polar = earth["lat"].abs() > POLAR_LAT
    n = remove(ndvi > NDVI_MAX, "vegetated")
    print(f"  vegetated: {n:>7,} removed (NDVI > {NDVI_MAX})")
    n = remove(ndvi.isna() & ~polar, "no NDVI")
    print(f"  no NDVI:   {n:>7,} removed (NDVI missing, not polar |lat| <= {POLAR_LAT})")
    kept = earth["scoring_filter"] == "kept"
    print(f"  kept:      {int(kept.sum()):>7,}")
    return kept


# ---------------------------------------------------------------------------
# Target values
# ---------------------------------------------------------------------------

def empty_dimensions(earth):
    """Dimensions whose Earth column is 100% empty (e.g. dust_aod not exported): dropped for every target."""
    return [d for d, (col, _) in DIMENSIONS.items() if earth[col].isna().all()]


def resolve_target_values(targets, earth, dropped=()):
    """
    For each target, decide which dimensions are used and with which number.
    `earth` must be the scored population only (categorical percentiles use it).
    `dropped` = dimensions with no Earth data at all: skipped for every target (note "dropped: no data").
    Returns a table: target, dim, raw, used (float or NaN), note.
    """
    rows = []
    for target_id, t in targets.items():
        for dim, (col, bodies) in DIMENSIONS.items():
            raw = t["raw"].get(dim)
            used, note = np.nan, ""
            if dim in dropped:
                note = f"dropped: no data ({col} is empty for every tile)"
            elif t["body"] not in bodies:
                note = f"skipped: not used for {t['body']}"
            elif raw is None:
                note = "skipped: no value in targets.csv"
            elif raw.lower() == "n/a":
                note = "skipped: n/a"
            elif raw.lower() in CATEGORY_PERCENTILE:
                pct = CATEGORY_PERCENTILE[raw.lower()]
                used = float(np.nanpercentile(earth[col], pct))
                note = f"categorical '{raw}' -> {pct}th percentile of Earth {col}"
            else:
                used = float(raw)
                note = "number"
            rows.append({"target": target_id, "dim": dim, "raw": raw,
                         "used": used, "note": note})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_target(earth, kept, target_id, dims, target_value):
    """
    Add score / total / rank columns for one target to `earth` (in place).
    kept = boolean mask of tiles that passed the land and vegetation filters.
    dims = list of dimension ids used for this target.
    target_value = {dim: number}.
    """
    has = earth[[DIMENSIONS[d][0] for d in dims]].notna()
    has.columns = dims

    # 1a. More than half the dims NaN -> dropped
    too_many_nan = kept & (has.sum(axis=1) < len(dims) / 2)
    # 1b. The dims it has must carry >= 2/3 of the weight of EVERY profile.
    #     Stops a tile with missing dims from winning thanks to renormalisation.
    low_coverage = pd.Series(False, index=earth.index)
    for profile, weights in PROFILES.items():
        w = pd.Series({d: weights.get(d, 0) for d in dims})
        coverage = (has * w).sum(axis=1) / w.sum()
        low_coverage |= coverage < MIN_WEIGHT_COVERAGE
    low_coverage &= kept & ~too_many_nan
    valid = kept & ~too_many_nan & ~low_coverage
    print(f"  {target_id}: {too_many_nan.sum():,} dropped (more than half of {len(dims)} dims missing), "
          f"{low_coverage.sum():,} dropped (dims present < {MIN_WEIGHT_COVERAGE:.0%} of a profile's weight)"
          f" -> {valid.sum():,} tiles scored (= tiles_scored)")

    # 2. One 0-100 score per dimension
    for dim in dims:
        col = DIMENSIONS[dim][0]
        gap = (earth[col] - target_value[dim]).abs()
        gap[~valid] = np.nan                         # filtered / dropped tiles are not ranked
        # pct=True gives a rank between 0 and 1 (smallest gap = closest to 0);
        # NaN gaps stay NaN, ties get the average rank
        pct = gap.rank(method="average", pct=True)
        earth[f"score_{target_id}_{dim}"] = (100 * (1 - pct)).round().astype("Int64")

    # 3. Weighted total per profile, renormalised over the dims this tile has
    for profile, weights in PROFILES.items():
        weighted_sum = pd.Series(0.0, index=earth.index)
        weight_sum = pd.Series(0.0, index=earth.index)
        for dim in dims:
            w = weights.get(dim, 0)
            s = earth[f"score_{target_id}_{dim}"].astype(float)
            has = s.notna()
            weighted_sum[has] += w * s[has]
            weight_sum[has] += w
        total = (weighted_sum / weight_sum.replace(0, np.nan)).round().astype("Int64")
        total[~valid] = pd.NA
        earth[f"total_{target_id}_{profile}"] = total

        # 4. Global rank among all scored tiles: 1 = best on Earth, ties -> best rank
        earth[f"rank_{target_id}_{profile}"] = (
            total.astype(float).rank(method="min", ascending=False).astype("Int64"))


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

def print_top10(earth, targets):
    for target_id in targets:
        for profile in PROFILES:
            col = f"total_{target_id}_{profile}"
            if col not in earth:
                continue
            top = earth.dropna(subset=[col]).nlargest(10, col)
            print(f"\n=== {target_id} × {profile}: top 10 "
                  f"(of {earth[col].notna().sum():,} scored tiles)")
            regions = region_names(top["lat"].tolist(), top["lon"].tolist())
            print(f"{'rank':>4}  {'total':>5}  {'lat':>8}  {'lon':>9}  region")
            for (_, row), region in zip(top.iterrows(), regions):
                print(f"{row[f'rank_{target_id}_{profile}']:>4}  {row[col]:>5}  "
                      f"{row['lat']:>8.3f}  {row['lon']:>9.3f}  {region}")


# ---------------------------------------------------------------------------

def main():
    earth = load_earth()
    targets = load_targets()
    print(f"Loaded {len(earth):,} Earth tiles, targets: {list(targets)}")

    dropped = empty_dimensions(earth)
    for d in dropped:
        print(f"\nWARNING: dimension '{d}' DROPPED for every target: column {DIMENSIONS[d][0]} is "
              f"100% empty in earth_features.csv (recorded in results.json meta.dropped_dimensions)")

    kept = apply_filters(earth)
    target_values = resolve_target_values(targets, earth[kept], dropped)
    print("\nTarget values used:")
    for _, r in target_values.iterrows():
        used = f"{r['used']:.3f}" if pd.notna(r["used"]) else "-"
        print(f"  {r['target']:<17} {r['dim']:<11} raw={str(r['raw']):<6} used={used:<9} {r['note']}")

    print("\nScoring:")
    for target_id in targets:
        tv = target_values[(target_values["target"] == target_id) & target_values["used"].notna()]
        dims = tv["dim"].tolist()
        if not dims:
            print(f"  {target_id}: no usable dimension, skipped")
            continue
        score_target(earth, kept, target_id, dims, dict(zip(tv["dim"], tv["used"])))

    OUT_DIR.mkdir(exist_ok=True)
    earth.to_csv(OUT_DIR / "scores.csv", index=False)
    target_values.to_csv(OUT_DIR / "target_values.csv", index=False)
    print(f"\nWrote out/scores.csv ({len(earth):,} rows, {earth.shape[1]} columns) "
          f"and out/target_values.csv")

    print_top10(earth, targets)


if __name__ == "__main__":
    main()
