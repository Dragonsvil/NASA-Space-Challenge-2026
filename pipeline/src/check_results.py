"""
check_results.py — validate out/results.json against the OUTPUT CONTRACT in CLAUDE.md.

    python src/check_results.py                     (checks out/results.json)
    python src/check_results.py path/to/results.json

Prints ERRORS (contract broken: the website may crash) and WARNINGS, then the file size
and site count. Exit code: 0 = OK, 1 = errors.
"""

import csv
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIM_IDS = ["temp_range", "temp_min", "albedo", "slope", "roughness",
           "mafic", "aridity", "dust", "sun_angle"]
PROFILE_IDS = ["rover", "geology", "polar"]
TARGET_IDS = ["jezero", "lunar_south_pole"]
SIZE_LIMIT_MB = 5
TOP_N = 500
MAX_GEMS = 15            # hidden gems per target, at most
GEM_SPACING_KM = 300     # two gems of the same target must be further apart than this

errors, warnings = [], []


def error(msg):
    if len(errors) < 50:            # don't flood the screen
        errors.append(msg)


def need_keys(obj, keys, where):
    """Error for every key missing in dict obj. Returns True if all present."""
    if not isinstance(obj, dict):
        error(f"{where}: expected an object, got {type(obj).__name__}")
        return False
    missing = [k for k in keys if k not in obj]
    if missing:
        error(f"{where}: missing keys {missing}")
    return not missing


def is_int_or_null(x):
    return x is None or (isinstance(x, int) and not isinstance(x, bool))


def is_num_or_null(x):
    return x is None or (isinstance(x, (int, float)) and not isinstance(x, bool))


def check_meta(meta):
    if not need_keys(meta, ["generated", "tiles_scored", "dimensions", "profiles"], "meta"):
        return
    ts = meta["tiles_scored"]
    for t in TARGET_IDS:
        if not isinstance(ts.get(t), int) or ts.get(t, 0) <= 0:
            error(f"meta.tiles_scored.{t} must be a positive integer, got {ts.get(t)!r}")
    dim_ids = [d.get("id") for d in meta["dimensions"]]
    if dim_ids != DIM_IDS:
        error(f"meta.dimensions ids {dim_ids} != {DIM_IDS}")
    for d in meta["dimensions"]:
        need_keys(d, ["id", "label", "unit"], f"meta.dimensions[{d.get('id')}]")
    prof_ids = [p.get("id") for p in meta["profiles"]]
    if prof_ids != PROFILE_IDS:
        error(f"meta.profiles ids {prof_ids} != {PROFILE_IDS}")
    for p in meta["profiles"]:
        need_keys(p, ["id", "label"], f"meta.profiles[{p.get('id')}]")


def check_targets(targets):
    """Returns {target: dims list} for the next checks."""
    dims_of = {}
    for t in TARGET_IDS:
        if t not in targets:
            error(f"targets.{t} missing")
            continue
        tg = targets[t]
        if not need_keys(tg, ["name", "body", "lat", "lon", "values", "dims"], f"targets.{t}"):
            continue
        dims = tg["dims"]
        bad = [d for d in dims if d not in DIM_IDS]
        if bad:
            error(f"targets.{t}.dims has unknown ids {bad}")
        for d in dims:
            if not is_num_or_null(tg["values"].get(d)) or tg["values"].get(d) is None:
                error(f"targets.{t}.values.{d} must be a number (dim is in dims)")
        extra = set(tg["values"]) - set(dims)
        if extra:
            warnings.append(f"targets.{t}.values has values for dims not in dims: {sorted(extra)}")
        dims_of[t] = dims
    return dims_of


def check_sites(sites, dims_of):
    ids = set()
    for s in sites:
        where = f"site {s.get('id')}"
        if not need_keys(s, ["id", "lat", "lon", "region", "values", "scores",
                             "cluster", "hidden_gem", "known_analog"], where):
            continue
        if not re.fullmatch(r"t_\d+", str(s["id"])):
            error(f"{where}: id must look like 't_123'")
        if s["id"] in ids:
            error(f"{where}: duplicated id")
        ids.add(s["id"])
        if not (-90 <= s["lat"] <= 90 and -180 <= s["lon"] <= 180):
            error(f"{where}: lat/lon out of range")
        missing_vals = [d for d in DIM_IDS if d not in s["values"]]
        if missing_vals:
            error(f"{where}: values missing {missing_vals} (use null if unknown)")
        if not all(is_num_or_null(v) for v in s["values"].values()):
            error(f"{where}: values must be numbers or null")
        for t, dims in dims_of.items():
            st = s["scores"].get(t)
            if st is None:
                error(f"{where}: scores.{t} missing")
                continue
            for p in PROFILE_IDS:
                sp = st.get(p)
                if not need_keys(sp, ["total", "dims"], f"{where}: scores.{t}.{p}"):
                    continue
                if not is_int_or_null(sp["total"]):
                    error(f"{where}: scores.{t}.{p}.total must be an int or null")
                if sorted(sp["dims"]) != sorted(dims):
                    error(f"{where}: scores.{t}.{p}.dims keys {sorted(sp['dims'])} "
                          f"!= targets.{t}.dims {sorted(dims)}")
                for d, v in sp["dims"].items():
                    if not is_int_or_null(v) or (v is not None and not 0 <= v <= 100):
                        error(f"{where}: scores.{t}.{p}.dims.{d} = {v!r}, must be int 0-100 or null")
        if not is_int_or_null(s["cluster"]):
            error(f"{where}: cluster must be an int or null")
        if s["known_analog"] is not None and not isinstance(s["known_analog"], str):
            error(f"{where}: known_analog must be a name or null")

    # Every target × profile should have its top 500 in the file
    for t in dims_of:
        for p in PROFILE_IDS:
            n = sum(1 for s in sites if s["scores"].get(t, {}).get(p, {}).get("total") is not None)
            if n < TOP_N:
                warnings.append(f"only {n} sites with a {t} × {p} total (expected >= {TOP_N})")


def check_known_analogs(known, sites, tiles_scored):
    site_by_analog = {s["known_analog"]: s for s in sites if s.get("known_analog")}
    for a in known:
        where = f"known_analog '{a.get('name')}'"
        if not need_keys(a, ["name", "lat", "lon", "analog_for", "used_for", "scores"], where):
            continue
        any_null = False
        for t in TARGET_IDS:
            for p in PROFILE_IDS:
                sc = a["scores"].get(t, {}).get(p)
                if not need_keys(sc, ["total", "global_rank"], f"{where}: scores.{t}.{p}"):
                    continue
                if not is_int_or_null(sc["total"]) or not is_int_or_null(sc["global_rank"]):
                    error(f"{where}: scores.{t}.{p} total/global_rank must be int or null")
                if (sc["global_rank"] is not None and t in tiles_scored
                        and not 1 <= sc["global_rank"] <= tiles_scored[t]):
                    error(f"{where}: {t}.{p}.global_rank {sc['global_rank']} not in 1..tiles_scored")
                if sc["total"] is None:
                    any_null = True
                # Same tile as its site: totals must match
                site = site_by_analog.get(a["name"])
                if site and sc["total"] != site["scores"][t][p]["total"]:
                    error(f"{where}: {t}.{p} total {sc['total']} != its site's total "
                          f"{site['scores'][t][p]['total']}")
        if any_null and "tile_note" not in a:
            error(f"{where}: has null scores but no tile_note explaining why")
        if not any_null and a["name"] not in site_by_analog:
            error(f"{where}: has scores but no site has known_analog = this name")


def km_between(a, b):
    """Great-circle distance in km between two sites (haversine)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def check_hidden_gems(sites):
    """
    hidden_gem = {"jezero": bool, "lunar_south_pole": bool} on every site.
    Per target: at most MAX_GEMS true, no two within GEM_SPACING_KM, every gem has a cluster,
    and the flags match out/clusters.csv exactly: every gem tile is a site (even if not
    in any top 500, contract rule) and no other site is flagged.
    Uses out/site_index.csv to map site id -> tile_id.
    """
    flagged = {t: set() for t in TARGET_IDS}
    by_id = {s["id"]: s for s in sites}
    for s in sites:
        hg = s.get("hidden_gem")
        if not isinstance(hg, dict) or sorted(hg) != sorted(TARGET_IDS) \
                or not all(isinstance(v, bool) for v in hg.values()):
            error(f"site {s.get('id')}: hidden_gem must be {{\"jezero\": bool, "
                  f"\"lunar_south_pole\": bool}}, got {hg!r}")
            continue
        for t, v in hg.items():
            if v:
                flagged[t].add(s["id"])
                if s.get("cluster") is None:
                    error(f"site {s['id']}: hidden gem for {t} but cluster is null")

    for t in TARGET_IDS:
        if len(flagged[t]) > MAX_GEMS:
            error(f"{len(flagged[t])} hidden gems for {t}: at most {MAX_GEMS} allowed")
        gems = sorted(flagged[t])
        for i, a in enumerate(gems):
            for b in gems[i + 1:]:
                d = km_between(by_id[a], by_id[b])
                if d <= GEM_SPACING_KM:
                    error(f"{t}: gems {a} and {b} are only {d:.0f} km apart (min {GEM_SPACING_KM})")

    clusters_path, index_path = ROOT / "out" / "clusters.csv", ROOT / "out" / "site_index.csv"
    if not clusters_path.exists():
        if any(flagged.values()):
            error("sites flagged as hidden gems but out/clusters.csv does not exist")
        print("Hidden gems: out/clusters.csv not found (cluster.py not run), not cross-checked")
        return
    with open(clusters_path, newline="") as f:
        rows = list(csv.DictReader(f))
    with open(index_path, newline="") as f:
        site_of_tile = {int(r["tile_id"]): r["id"] for r in csv.DictReader(f)}

    for t in TARGET_IDS:
        gem_tiles = {int(r["tile_id"]) for r in rows if r.get(f"gem_{t}", "").lower() == "true"}
        missing = sorted(g for g in gem_tiles if site_of_tile.get(g) not in by_id)
        if missing:
            error(f"{t}: {len(missing)} hidden-gem tile(s) missing from sites, e.g. tile_id {missing[:5]}")
        expected = {site_of_tile[g] for g in gem_tiles if site_of_tile.get(g) in by_id}
        if expected - flagged[t]:
            error(f"{t}: hidden-gem site(s) not flagged: {sorted(expected - flagged[t])[:5]}")
        if flagged[t] - expected:
            error(f"{t}: site(s) flagged but not gems in out/clusters.csv: "
                  f"{sorted(flagged[t] - expected)[:5]}")
        print(f"Hidden gems {t}: {len(gem_tiles)} in out/clusters.csv, {len(flagged[t])} flagged in sites")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "out" / "results.json"
    if not path.exists():
        sys.exit(f"ERROR: {path} not found. Run first: python src/export_web.py")
    text = path.read_text(encoding="utf-8")
    if "NaN" in text or "Infinity" in text:
        error("File contains NaN/Infinity: not valid JSON for the browser")
    data = json.loads(text)

    if need_keys(data, ["meta", "targets", "sites", "known_analogs"], "top level"):
        check_meta(data["meta"])
        dims_of = check_targets(data["targets"])
        check_sites(data["sites"], dims_of)
        check_known_analogs(data["known_analogs"], data["sites"],
                            data["meta"].get("tiles_scored", {}))
        check_hidden_gems(data["sites"])

    size_mb = path.stat().st_size / 1e6
    print(f"{path}: {size_mb:.2f} MB, {len(data.get('sites', [])):,} sites, "
          f"{len(data.get('known_analogs', []))} known analogs")
    if size_mb > SIZE_LIMIT_MB:
        warnings.append(f"file is {size_mb:.2f} MB, above the ~{SIZE_LIMIT_MB} MB limit")
    for w in warnings:
        print(f"WARNING: {w}")
    for e in errors:
        print(f"ERROR:   {e}")
    if errors:
        print(f"\n{len(errors)} error(s): the website may break.")
        sys.exit(1)
    print("\nOK: results.json follows the contract.")


if __name__ == "__main__":
    main()
