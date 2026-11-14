"""
common.py — small helpers shared by several pipeline scripts.

The tile grid is NOT defined here: it comes from ../grid_config.py (the file A and B use
for their Earth Engine exports). If they change it, the pipeline follows automatically.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent      # the pipeline/ folder
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
ANALOG_MAX_KM = 50          # an analog may use a neighbour tile up to this distance

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
    return df


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
        if own_row is not None and scores.loc[own_row, "vegetation_filter"] != "kept":
            tile = scores.loc[own_row]
            if tile["vegetation_filter"] == "vegetated":
                note = f"excluded: vegetated tile (NDVI {tile['ndvi']:.2f})"
            else:
                note = "excluded: no NDVI, not polar"
            results.append({"row": None, "note": note})
            continue

        # Own tile missing (ocean / coast) or too many NaN: nearest valid tile within 50 km
        cand = scores[valid]
        dist = haversine_km(a["lat"], a["lon"], cand["lat"].to_numpy(), cand["lon"].to_numpy())
        i = int(np.argmin(dist))
        if dist[i] <= ANALOG_MAX_KM:
            results.append({"row": cand.index[i],
                            "note": f"nearest valid tile, {round(dist[i])} km away"})
        else:
            results.append({"row": None, "note": f"no valid tile within {ANALOG_MAX_KM} km"})
    return results
