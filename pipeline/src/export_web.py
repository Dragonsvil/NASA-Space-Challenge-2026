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

from common import (DATA_DIR, OUT_DIR, ROOT, count_tiles_scored, find_analog_tiles,
                    haversine_km, load_csv)
from score import DIMENSIONS, PROFILES

TOP_N = 500                    # top tiles kept per target × profile
SIZE_LIMIT_MB = 5
WEB_COPY = ROOT.parent / "docs" / "data" / "results.json"
COUNTRIES_FILE = DATA_DIR / "ne_110m_admin_0_countries.geojson"
COUNTRIES_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
                 "master/geojson/ne_110m_admin_0_countries.geojson")
NEAR_TOWN_KM = 100             # "near <town>" only if the town is closer than this

# Labels and units shown on the website (CLAUDE.md, "Dimensions" table)
DIM_LABELS = {
    "temp_range": ("Day–night temperature range", "°C"),
    "temp_min":   ("Minimum temperature", "°C"),
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
# Regions: country from Natural Earth polygons, town from reverse_geocoder
# ---------------------------------------------------------------------------

def load_countries():
    """
    Return (shapes, names, name_by_code). Downloads the file once if missing.
    name_by_code maps a 2-letter country code (e.g. "ES") to the Natural Earth name.
    """
    from shapely.geometry import shape
    if not COUNTRIES_FILE.exists():
        import urllib.request
        print(f"Downloading country borders to {COUNTRIES_FILE.name} (once) ...")
        try:
            urllib.request.urlretrieve(COUNTRIES_URL, COUNTRIES_FILE)
        except Exception as e:
            raise SystemExit(f"ERROR: could not download {COUNTRIES_URL}\n{e}\n"
                             f"Download it by hand into data/.")
    features = json.loads(COUNTRIES_FILE.read_text())["features"]
    shapes = [shape(f["geometry"]) for f in features]
    names = [f["properties"]["NAME"] for f in features]
    # ISO_A2_EH, not ISO_A2: ISO_A2 is "-99" for France and Norway in Natural Earth
    name_by_code = {f["properties"]["ISO_A2_EH"]: f["properties"]["NAME"] for f in features}
    return shapes, names, name_by_code


def region_names(lats, lons):
    """
    "Country, near Town" for each point.
      - lat < -60: "Antarctica"
      - country: Natural Earth polygon containing the point
      - point outside every polygon (small islands like the Canaries, coasts: the 110m
        polygons are coarse): use the country of reverse_geocoder's nearest town, but only
        if that town is < NEAR_TOWN_KM away. Never snap to the nearest polygon: it would
        put Lanzarote in Morocco.
      - "near Town" only if the town is < NEAR_TOWN_KM away
      - nothing found -> None (shown as null)
    """
    import reverse_geocoder as rg
    from shapely import STRtree
    from shapely.geometry import Point

    shapes, names, name_by_code = load_countries()
    tree = STRtree(shapes)
    towns = rg.search(list(zip(lats, lons)), mode=1, verbose=False)

    regions = []
    for lat, lon, town in zip(lats, lons, towns):
        town_is_near = haversine_km(lat, lon, float(town["lat"]), float(town["lon"])) < NEAR_TOWN_KM
        if lat < -60:
            country = "Antarctica"
        else:
            hits = tree.query(Point(lon, lat), predicate="within")   # shapely: x=lon, y=lat
            if len(hits):
                country = names[hits[0]]
            elif town_is_near:
                country = name_by_code.get(town["cc"])
            else:
                country = None
        town_part = f"near {town['name']}" if town_is_near else None
        parts = [x for x in (country, town_part) if x]
        regions.append(", ".join(parts) if parts else None)
    return regions


# ---------------------------------------------------------------------------
# Building the JSON
# ---------------------------------------------------------------------------

def build_targets(target_values, targets_csv):
    """targets section: metadata, values actually used, sources, dims."""
    targets = {}
    for target_id, rows in targets_csv.groupby("target", sort=False):
        meta = dict(zip(rows["feature"], rows["value"]))
        sources = dict(zip(rows["feature"], rows["source"]))
        tv = target_values[(target_values["target"] == target_id) & target_values["used"].notna()]
        dims = tv["dim"].tolist()
        values, srcs = {}, {}
        for _, r in tv.iterrows():
            values[r["dim"]] = num(r["used"], 3)
            srcs[r["dim"]] = sources.get(r["dim"])
            if r["note"].startswith("categorical"):     # say where the number comes from
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
    """{target: {profile: {"total", "dims"}}} for one tile, both targets, all profiles."""
    out = {}
    for target_id, t in targets.items():
        dims = {d: whole(row.get(f"score_{target_id}_{d}")) for d in t["dims"]}
        out[target_id] = {p: {"total": whole(row.get(f"total_{target_id}_{p}")), "dims": dims}
                          for p in PROFILES}
    return out


def pick_site_rows(scores, target_ids, analog_rows):
    """Row indices of the sites: top 500 per target × profile + hidden gems + analog tiles."""
    rows = set()
    for t in target_ids:
        for p in PROFILES:
            col = f"rank_{t}_{p}"
            # sort by rank, then tile_id so ties are cut the same way every run
            top = scores.dropna(subset=[col]).sort_values([col, "tile_id"]).head(TOP_N)
            rows.update(top.index)
    if "hidden_gem" in scores:                       # added by cluster.py later
        rows.update(scores.index[scores["hidden_gem"] == True])   # noqa: E712
    rows.update(r for r in analog_rows if r is not None)
    return sorted(rows)


def main():
    scores = load_csv(OUT_DIR / "scores.csv", "Run first: python src/score.py")
    target_values = load_csv(OUT_DIR / "target_values.csv", "Run first: python src/score.py")
    targets_csv = load_csv(DATA_DIR / "targets.csv", "It is provided by teammate C (targets).")
    analogs = load_csv(DATA_DIR / "known_analogs.csv", "It is provided by teammate C (known analogs).")

    targets = build_targets(target_values, targets_csv)
    target_ids = list(targets)

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
            "cluster": whole(row["cluster"]) if "cluster" in row else None,
            "hidden_gem": bool(row["hidden_gem"]) if "hidden_gem" in row else False,
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

    WEB_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out_path, WEB_COPY)

    size_mb = out_path.stat().st_size / 1e6
    print(f"Wrote out/results.json: {len(sites):,} sites, {len(known)} known analogs, "
          f"{size_mb:.2f} MB")
    if size_mb > SIZE_LIMIT_MB:
        print(f"WARNING: larger than {SIZE_LIMIT_MB} MB")
    print(f"Copied to {WEB_COPY.relative_to(ROOT.parent)}")
    print("Wrote out/site_index.csv")
    print(f"tiles_scored: {tiles_scored}")
    for a, tile in zip(analogs["name"], analog_tiles):
        if tile["note"]:
            print(f"  analog {a}: {tile['note']}")


if __name__ == "__main__":
    main()
