"""
common.py — small helpers shared by several pipeline scripts.

The tile grid is NOT defined here: it comes from ../grid_config.py (the file A and B use
for their Earth Engine exports). If they change it, the pipeline follows automatically.
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent      # the pipeline/ folder
DATA_DIR = ROOT / "data"
FAKE_DIR = DATA_DIR / "fake"         # fake inputs (make_fake_data.py), tracked in git, for testing
# Where the pipeline inputs are read from (run_all.py sets the environment variables):
#   normal run                     earth_features + targets + known_analogs from data/
#   --no-merge (PIPELINE_FAKE=1)   all three from data/fake/  (everything fake)
#   --test-targets (PIPELINE_TEST_TARGETS=1)
#                                  REAL earth_features from data/, FAKE targets + known_analogs from
#                                  data/fake/ (C not delivered yet). results.json is NOT copied to the website.
FAKE_RUN = os.environ.get("PIPELINE_FAKE") == "1"
TEST_TARGETS = os.environ.get("PIPELINE_TEST_TARGETS") == "1"
EARTH_DIR = FAKE_DIR if FAKE_RUN else DATA_DIR             # earth_features.csv
TARGETS_DIR = FAKE_DIR if (FAKE_RUN or TEST_TARGETS) else DATA_DIR   # targets.csv, known_analogs.csv
FAKE_TARGETS_OK = FAKE_RUN or TEST_TARGETS                 # "FAKE" sources: warning instead of error
RUN_INPUTS_FILE = ROOT / "out" / "run_inputs.json"         # written by run_all.py: which inputs the last run used
OUT_DIR = ROOT / "out"
ANALOG_MAX_KM = 50          # an analog may use a neighbour tile up to this distance
COUNTRIES_FILE = DATA_DIR / "ne_110m_admin_0_countries.geojson"
COUNTRIES_URL = ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
                 "master/geojson/ne_110m_admin_0_countries.geojson")
NEAR_TOWN_KM = 100          # a town this close: "near <town>", and the tile counts as land

# --- Shared grid definition: ../grid_config.py ------------------------------
sys.path.insert(0, str(ROOT.parent))
sys.dont_write_bytecode = True   # don't leave a __pycache__/ folder in the website folder
try:
    import grid_config  # noqa: E402
except ImportError:
    sys.exit(f"ERROR: {ROOT.parent / 'grid_config.py'} not found. It defines the tile grid "
             f"shared with A and B: pull the latest version of the repo.")

NODATA_BELOW = -9000        # -9999 (grid_config.NODATA) or anything below this = missing value


# ---------------------------------------------------------------------------
# Loading CSVs
# ---------------------------------------------------------------------------

def nodata_to_nan(df, name="", quiet=False):
    """
    Replace -9999 (and any value < -9000) by NaN in every numeric column, in place.
    Prints how many values were converted per column (unless quiet). Returns {column: count}.
    """
    converted = {}
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            mask = df[col] < NODATA_BELOW
            if mask.any():
                converted[col] = int(mask.sum())
                df.loc[mask, col] = np.nan
    label = f"{name}: " if name else ""
    if converted and not quiet:
        details = ", ".join(f"{c} {n:,}" for c, n in converted.items())
        print(f"  {label}{grid_config.NODATA:g} (no data) -> NaN: {details}")
    return converted


def load_csv(path, who):
    """
    Read a CSV, or stop with a message saying who provides it / which script makes it.
    Every pipeline script loads its CSVs through here, so no-data values are always handled.
    """
    path = Path(path)
    if not path.exists():
        sys.exit(f"ERROR: {path} is missing. {who}")
    # keep_default_na=False: otherwise pandas turns the text "n/a" into NaN
    df = pd.read_csv(path, keep_default_na=False, na_values=[""])
    nodata_to_nan(df, path.name)
    if "analog_for" in df.columns:                  # known_analogs.csv
        df["analog_for"] = df["analog_for"].map(normalize_analog_for)
    return df


def normalize_analog_for(text):
    """
    "Mars; Moon" or "Mars,Moon" -> "Mars, Moon": one separator everywhere (website, slides, tables).
    Both ";" and "," are accepted in known_analogs.csv.
    """
    parts = [p.strip() for p in str(text).replace(";", ",").split(",")]
    return ", ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Grid helpers (all built on grid_config)
# ---------------------------------------------------------------------------

def tile_of(lat, lon):
    """(tile_id, center_lat, center_lon) of the tile containing one point."""
    row, col = grid_config.latlon_to_rowcol(lat, lon)
    center_lat, center_lon = grid_config.tile_center(row, col)
    return grid_config.tile_id(row, col), center_lat, center_lon


def tile_ids_of(lats, lons):
    """tile_id for many points (numpy array)."""
    return np.array([tile_of(a, b)[0] for a, b in zip(lats, lons)], dtype=np.int64)


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Works with numbers or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


# ---------------------------------------------------------------------------
# Regions: country from Natural Earth polygons, town from reverse_geocoder
# ---------------------------------------------------------------------------

_countries = None          # loaded once, then reused


def load_countries():
    """
    Return (shapes, names, name_by_code). Downloads the file once if missing.
    name_by_code maps a 2-letter country code (e.g. "ES") to the Natural Earth name.
    """
    global _countries
    if _countries is not None:
        return _countries
    import json
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
    _countries = (shapes, names, name_by_code)
    return _countries


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


def land_mask(lats, lons):
    """
    Which points are on land (CLAUDE.md, Scoring method, step 0)?
    Land = inside a Natural Earth country polygon (Antarctica included)
           OR reverse_geocoder's nearest town is < NEAR_TOWN_KM away
           (keeps small islands like Lanzarote that the coarse 110m polygons miss).
    Returns (on_land, in_polygon) boolean numpy arrays.
    """
    import reverse_geocoder as rg
    import shapely
    from shapely import STRtree

    lats, lons = np.asarray(lats, dtype=float), np.asarray(lons, dtype=float)
    shapes, _, _ = load_countries()
    points = shapely.points(lons, lats)                      # shapely: x = lon, y = lat
    hit_point, _ = STRtree(shapes).query(points, predicate="within")
    in_polygon = np.zeros(len(lats), dtype=bool)
    in_polygon[hit_point] = True

    on_land = in_polygon.copy()
    rest = np.flatnonzero(~in_polygon)                      # only check towns where needed
    if len(rest):
        towns = rg.search(list(zip(lats[rest], lons[rest])), mode=1, verbose=False)
        t_lat = np.array([float(t["lat"]) for t in towns])
        t_lon = np.array([float(t["lon"]) for t in towns])
        on_land[rest] = haversine_km(lats[rest], lons[rest], t_lat, t_lon) < NEAR_TOWN_KM
    return on_land, in_polygon


# ---------------------------------------------------------------------------
# Ranking population
# ---------------------------------------------------------------------------

def count_tiles_scored(scores, target_ids, profile_ids):
    """
    {target: number of tiles with a valid total} = meta.tiles_scored in results.json.
    The count is the same for every profile of a target (checked here).
    """
    tiles_scored = {}
    for t in target_ids:
        counts = {int(scores[f"total_{t}_{p}"].notna().sum()) for p in profile_ids}
        if len(counts) != 1:
            print(f"WARNING: {t}: scored-tile count differs between profiles: {counts}")
        tiles_scored[t] = max(counts)
    return tiles_scored


# ---------------------------------------------------------------------------
# Known analogs -> tile
# ---------------------------------------------------------------------------

def find_analog_tiles(scores, analogs, target_ids):
    """
    Decide which tile represents each known analog (rules in CLAUDE.md, OUTPUT CONTRACT).

    scores   = out/scores.csv as a DataFrame (one row per tile)
    analogs  = data/known_analogs.csv
    Returns a list (same order as analogs) of dicts:
        {"row": row index in scores or None, "note": tile_note text or None}
    A tile is "valid" when it has a total for every target.
    """
    total_cols = [f"total_{t}_rover" for t in target_ids]
    valid = scores[total_cols].notna().all(axis=1)
    row_of_tile = pd.Series(scores.index, index=scores["tile_id"])

    results = []
    for _, a in analogs.iterrows():
        own_id = tile_of(a["lat"], a["lon"])[0]
        own_row = row_of_tile.get(own_id)

        if own_row is not None and valid[own_row]:
            results.append({"row": own_row, "note": None})
            continue

        # Own tile exists but the vegetation filter removed it: report it, no substitute
        reason = scores.loc[own_row, "scoring_filter"] if own_row is not None else None
        if reason in ("vegetated", "no NDVI"):
            if reason == "vegetated":
                note = f"excluded: vegetated tile (NDVI {scores.loc[own_row, 'ndvi']:.2f})"
            else:
                note = "excluded: no NDVI, not polar"
            results.append({"row": None, "note": note})
            continue

        # Own tile missing, off land / no DEM (ocean, coast) or too many NaN:
        # nearest valid tile within 50 km
        cand = scores[valid]
        dist = haversine_km(a["lat"], a["lon"], cand["lat"].to_numpy(), cand["lon"].to_numpy())
        i = int(np.argmin(dist))
        if dist[i] <= ANALOG_MAX_KM:
            results.append({"row": cand.index[i],
                            "note": f"nearest valid tile, {round(dist[i])} km away"})
        else:
            results.append({"row": None, "note": f"no valid tile within {ANALOG_MAX_KM} km"})
    return results
