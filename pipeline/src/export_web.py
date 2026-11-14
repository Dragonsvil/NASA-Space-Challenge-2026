"""
export_web.py — build out/results.json for the website (role E).

    python src/export_web.py          (run src/score.py first)

Follows the OUTPUT CONTRACT in CLAUDE.md exactly. Writes:
    out/results.json              the file for the website
    ../docs/data/results.json     copy inside the website folder (GitHub Pages serves docs/)
    out/site_index.csv            site id -> tile_id mapping
"""

import json
import shutil
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from common import (TARGETS_DIR, TEST_TARGETS, OUT_DIR, ROOT, count_tiles_scored, find_analog_tiles,
                    load_csv, region_names)
from score import DIMENSIONS, PROFILES, unavailable_profiles

TOP_N = 500                    # top tiles kept per target × profile
SIZE_LIMIT_MB = 5
WEB_COPY = ROOT.parent / "docs" / "data" / "results.json"

# Labels and units shown on the website (CLAUDE.md, "Dimensions" table)
DIM_LABELS = {
    "temp_range": ("Mean day–night range", "°C"),
    "temp_min":   ("Mean night temperature", "°C"),
    "albedo":     ("Albedo", ""),
    "slope":      ("Slope", "°"),
    "roughness":  ("Roughness", "°"),
    "mafic":      ("Basaltic rock (mafic index)", ""),
    "aridity":    ("Aridity", "mm/yr"),
    "dust":       ("Dust", "AOD"),
    "sun_angle":  ("Low sun angle", "°"),
}
PROFILE_LABELS = {"rover": "Rover navigation",
                  "geology": "Geology / science",
                  "polar": "Polar & thermal ops"}
# Decimals for raw values: small 0-1 indices need 2, the rest 1
DECIMALS = {"albedo": 2, "mafic": 2, "dust": 2}


# ---------------------------------------------------------------------------
# Small conversion helpers: NaN -> None, numpy -> plain Python
# ---------------------------------------------------------------------------

def num(x, decimals=1):
    if x is None or pd.isna(x):
        return None
    return round(float(x), decimals)


def whole(x):
    if x is None or pd.isna(x):
        return None
    return int(x)


# ---------------------------------------------------------------------------
# Building the JSON
# ---------------------------------------------------------------------------

def build_targets(target_values, targets_csv):
    """targets section: metadata, values actually used, sources, dims."""
    targets = {}
    for target_id, rows in targets_csv.groupby("target", sort=False):
        meta = dict(zip(rows["feature"], rows["value"]))
        sources = dict(zip(rows["feature"], rows["source"]))
        tv = target_values[target_values["target"] == target_id]
        # dims = the dims actually scored, PLUS dropped dims this target has a value for (display only,
        # at E's request: e.g. dust stays in jezero's dims). A dropped dim has value null and no score.
        dropped = tv["note"].fillna("").str.startswith("dropped") & \
            (tv["raw"].astype(str).str.strip().str.lower() != "n/a")
        tv = tv[tv["used"].notna() | dropped]
        dims = tv["dim"].tolist()
        values, srcs = {}, {}
        for _, r in tv.iterrows():
            values[r["dim"]] = num(r["used"], 3)        # null for a dropped dim
            srcs[r["dim"]] = sources.get(r["dim"])
            if r["note"].startswith(("categorical", "dropped")):   # say where the number comes from
                srcs[r["dim"]] = f"{srcs[r['dim']]} ({r['note']})"
        targets[target_id] = {
            "name": meta.get("name", target_id),
            "body": meta.get("body"),
            "lat": num(meta.get("lat"), 2),
            "lon": num(meta.get("lon"), 2),
            "values": values,
            "sources": srcs,
            "dims": dims,
        }
    return targets


def site_values(row):
    """Raw physical values of one tile, by dimension id."""
    return {dim: num(row[col], DECIMALS.get(dim, 1)) for dim, (col, _) in DIMENSIONS.items()}


def site_scores(row, targets):
    """
    {target: {profile: {"total", "dims"}}} for one tile, both targets, all profiles.
    A dropped dimension (in the target's dims for display, value null) has no score: left out of "dims".
    """
    out = {}
    for target_id, t in targets.items():
        dims = {d: whole(row.get(f"score_{target_id}_{d}")) for d in t["dims"]
                if t["values"].get(d) is not None}
        out[target_id] = {p: {"total": whole(row.get(f"total_{target_id}_{p}")), "dims": dims}
                          for p in PROFILES}
    return out


def add_clusters(scores, target_ids):
    """
    Add 'cluster' and one 'gem_<target>' column per target from out/clusters.csv (cluster.py).
    Without that file: cluster = NaN (null in JSON), no hidden gems.
    """
    path = OUT_DIR / "clusters.csv"
    scores["cluster"] = np.nan
    for t in target_ids:
        scores[f"gem_{t}"] = False
    if not path.exists():
        print("NOTE: out/clusters.csv not found (cluster.py not run): cluster = null, no hidden gems")
        return
    if path.stat().st_mtime < (OUT_DIR / "scores.csv").stat().st_mtime:
        print("WARNING: out/clusters.csv is older than out/scores.csv: rerun python src/cluster.py")
    clusters = load_csv(path, "Run first: python src/cluster.py").set_index("tile_id")
    scores["cluster"] = scores["tile_id"].map(clusters["cluster"])
    for t in target_ids:
        gem = scores["tile_id"].map(clusters[f"gem_{t}"])
        scores[f"gem_{t}"] = gem.astype(str).str.lower().eq("true")   # not clustered -> False
    print(f"Clusters: {scores['cluster'].notna().sum():,} tiles. Hidden gems: "
          + ", ".join(f"{t} {int(scores[f'gem_{t}'].sum())}" for t in target_ids))


def pick_site_rows(scores, target_ids, analog_rows):
    """Row indices of the sites: top 500 per target × profile + hidden gems + analog tiles."""
    rows = set()
    for t in target_ids:
        for p in PROFILES:
            col = f"rank_{t}_{p}"
            # sort by rank, then tile_id so ties are cut the same way every run
            top = scores.dropna(subset=[col]).sort_values([col, "tile_id"]).head(TOP_N)
            rows.update(top.index)
    for t in target_ids:                             # every hidden gem, even if not top 500
        rows.update(scores.index[scores[f"gem_{t}"]])
    rows.update(r for r in analog_rows if r is not None)
    return sorted(rows)


def main():
    scores = load_csv(OUT_DIR / "scores.csv", "Run first: python src/score.py")
    target_values = load_csv(OUT_DIR / "target_values.csv", "Run first: python src/score.py")
    targets_csv = load_csv(TARGETS_DIR / "targets.csv", "It is provided by teammate C (targets).")
    analogs = load_csv(TARGETS_DIR / "known_analogs.csv", "It is provided by teammate C (known analogs).")

    targets = build_targets(target_values, targets_csv)
    target_ids = list(targets)
    add_clusters(scores, target_ids)

    # tiles_scored: one count per target (same for every profile, checked here)
    tiles_scored = count_tiles_scored(scores, target_ids, PROFILES)

    # Which tile represents each known analog
    analog_tiles = find_analog_tiles(scores, analogs, target_ids)
    analog_name_by_row = {a["row"]: name for a, name in zip(analog_tiles, analogs["name"])
                          if a["row"] is not None}

    # Sites
    site_rows = pick_site_rows(scores, target_ids, [a["row"] for a in analog_tiles])
    sub = scores.loc[site_rows]
    regions = region_names(sub["lat"].tolist(), sub["lon"].tolist())
    sites = []
    for (i, row), region in zip(sub.iterrows(), regions):
        sites.append({
            "id": f"t_{i}",
            "lat": num(row["lat"], 3),
            "lon": num(row["lon"], 3),
            "region": region,
            "values": site_values(row),
            "scores": site_scores(row, targets),
            "cluster": whole(row["cluster"]),
            "hidden_gem": {t: bool(row[f"gem_{t}"]) for t in target_ids},
            "known_analog": analog_name_by_row.get(i),
        })

    # Known analogs, with their scores and global ranks
    known = []
    for (_, a), tile in zip(analogs.iterrows(), analog_tiles):
        entry = {"name": a["name"], "lat": num(a["lat"], 3), "lon": num(a["lon"], 3),
                 "analog_for": a["analog_for"], "used_for": a["used_for"], "scores": {}}
        r = scores.loc[tile["row"]] if tile["row"] is not None else None
        for t in target_ids:
            entry["scores"][t] = {
                p: {"total": whole(r[f"total_{t}_{p}"]) if r is not None else None,
                    "global_rank": whole(r[f"rank_{t}_{p}"]) if r is not None else None}
                for p in PROFILES}
        if tile["note"]:
            entry["tile_note"] = tile["note"]
        known.append(entry)

    result = {
        "meta": {
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tiles_scored": tiles_scored,
            # dimensions with no Earth data at all, removed from every target's dims (score.py)
            "dropped_dimensions": [
                {"id": d, "reason": "no data"} for d in dict.fromkeys(
                    target_values.loc[target_values["note"].fillna("").str.startswith("dropped"), "dim"])],
            # target × profiles with too little weight (safety rule): total = null everywhere
            "unavailable_profiles": unavailable_profiles(target_values),
            "dimensions": [{"id": d, "label": DIM_LABELS[d][0], "unit": DIM_LABELS[d][1]}
                           for d in DIMENSIONS],
            "profiles": [{"id": p, "label": PROFILE_LABELS[p], "weights": PROFILES[p]}
                         for p in PROFILES],
        },
        "targets": targets,
        "sites": sites,
        "known_analogs": known,
    }

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / "results.json"
    # allow_nan=False: crash rather than write NaN (which is not valid JSON)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, allow_nan=False, separators=(",", ":"))

    pd.DataFrame({"id": [s["id"] for s in sites],
                  "tile_id": sub["tile_id"].tolist(),
                  "lat": sub["lat"].tolist(), "lon": sub["lon"].tolist()}
                 ).to_csv(OUT_DIR / "site_index.csv", index=False)

    if not TEST_TARGETS:
        WEB_COPY.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out_path, WEB_COPY)

    size_mb = out_path.stat().st_size / 1e6
    print(f"Wrote out/results.json: {len(sites):,} sites, {len(known)} known analogs, "
          f"{size_mb:.2f} MB")
    if size_mb > SIZE_LIMIT_MB:
        print(f"WARNING: larger than {SIZE_LIMIT_MB} MB")
    if TEST_TARGETS:
        print(f"NOT copied to {WEB_COPY.relative_to(ROOT.parent)}: --test-targets (fake targets), "
              f"the website must never show real Earth data scored against fake targets")
    else:
        print(f"Copied to {WEB_COPY.relative_to(ROOT.parent)}")
    if result["meta"]["unavailable_profiles"]:
        print(f"Unavailable profiles: {result['meta']['unavailable_profiles']}")
    if result["meta"]["dropped_dimensions"]:
        print(f"Dropped dimensions: {result['meta']['dropped_dimensions']}")
    print("Wrote out/site_index.csv")
    print(f"tiles_scored: {tiles_scored}")
    for a, tile in zip(analogs["name"], analog_tiles):
        if tile["note"]:
            print(f"  analog {a}: {tile['note']}")


if __name__ == "__main__":
    main()
