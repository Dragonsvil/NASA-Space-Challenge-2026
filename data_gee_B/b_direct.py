"""
The script asks Earth Engine for small blocks of the 0.25 deg grid
(computePixels), several at a time in parallel, skips blocks that contain no land, and splits
or retries blocks that fail. It reuses the exact image-building code of b_export_features.py,
so the numbers are the same as the export method.

Usage (same folder as grid_config.py and b_export_features.py):
    python b_direct.py terrain test      # one 8x8-tile block in the Atacama, prints values
    python b_direct.py terrain run       # whole world
    python b_direct.py geology test
    python b_direct.py geology run

Output: exports/B_terrain_direct.csv  /  exports/B_geology_direct.csv
        columns: tile_id, lat, lon, <features>   (only tiles with data)
        -> B3_postprocess.py reads these files unchanged (it matches B_terrain_*.csv / B_geology_*.csv)
"""
import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import numpy as np
import pandas as pd

from grid_config import RES, N_COLS, N_ROWS, X_MIN, Y_MAX
import b_export_features as bf

NODATA = -9999.0
OUT_DIR = os.environ.get("B_OUT", "exports")
BLOCK = 16          # first-level block: 16 x 16 tiles (4 x 4 degrees)
MIN_BLOCK = 4       # smallest block before giving up on it
WORKERS = int(os.environ.get("B_WORKERS", "6"))   # parallel requests
DEADLINE_MS = 120_000


def fetch(img, bands, row0, n_rows, col0, n_cols):
    params = {
        "expression": img,
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {
            "dimensions": {"width": int(n_cols), "height": int(n_rows)},
            "affineTransform": {"scaleX": RES, "shearX": 0, "translateX": X_MIN + col0 * RES,
                                "shearY": 0, "scaleY": -RES, "translateY": Y_MAX - row0 * RES},
            "crsCode": "EPSG:4326",
        },
    }
    out = ee.data.computePixels(params)
    if isinstance(out, (bytes, bytearray)):
        out = np.load(io.BytesIO(out))
    return {b: np.asarray(out[b], dtype=np.float64).reshape(n_rows, n_cols) for b in bands}


def fetch_block(img, bands, store, failed, row0, col0, n_rows, n_cols):
    msg = ""
    for attempt in (1, 2, 3):
        try:
            res = fetch(img, bands, row0, n_rows, col0, n_cols)
            for b in bands:
                store[b][row0:row0 + n_rows, col0:col0 + n_cols] = res[b]
            return
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            if "too many" in low or "quota" in low or "429" in low or "rate" in low:
                time.sleep(5 * attempt)
                continue
            break
    if n_rows <= MIN_BLOCK and n_cols <= MIN_BLOCK:
        failed.append((row0, col0, n_rows, n_cols, msg[:120]))
        return
    h, w = max(n_rows // 2, 1), max(n_cols // 2, 1)
    rows = [(row0, n_rows)] if n_rows <= MIN_BLOCK else [(row0, h), (row0 + h, n_rows - h)]
    cols = [(col0, n_cols)] if n_cols <= MIN_BLOCK else [(col0, w), (col0 + w, n_cols - w)]
    for r, nr in rows:
        for c, nc in cols:
            fetch_block(img, bands, store, failed, r, c, nr, nc)


def load_land():
    cands = [os.environ.get("LAND_CSV", ""),
             os.path.join("data", "raw_A", "A_land_b0_0.csv"),
             os.path.join("..", "data", "raw_A", "A_land_b0_0.csv")]
    for p in cands:
        if p and os.path.exists(p):
            d = pd.read_csv(p)
            ids = d.loc[d["land_frac"] >= 0.5, "tile_id"].to_numpy()
            ids = ids[(ids >= 0) & (ids < N_ROWS * N_COLS)]
            land = np.zeros(N_ROWS * N_COLS, dtype=bool)
            land[ids] = True
            print(f"land mask from {p}: {land.sum():,} land tiles -> ocean blocks are skipped")
            return land.reshape(N_ROWS, N_COLS)
    print("no land file found: ocean blocks will NOT be skipped (slower)")
    return None


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("terrain", "geology") or sys.argv[2] not in ("test", "run"):
        sys.exit(__doc__)
    what, mode = sys.argv[1], sys.argv[2]
    ee.Initialize(project=bf.PROJECT)
    ee.data.setDeadline(DEADLINE_MS)

    stats, rename, _ = bf.build_terrain() if what == "terrain" else bf.build_geology()
    out_names = list(rename.keys())
    img = stats.select([rename[n] for n in out_names], out_names).unmask(NODATA, False).toFloat()

    if mode == "test":
        r0 = int((Y_MAX - (-22.0)) / RES)           # Atacama, 8x8 tiles
        c0 = int((-70.0 - X_MIN) / RES)
        res = fetch(img, out_names, r0, 8, c0, 8)
        for b in out_names:
            v = res[b][res[b] != NODATA]
            print(f"{b}: {v.size}/64 tiles with data, min {v.min():.3f} median {np.median(v):.3f} max {v.max():.3f}"
                  if v.size else f"{b}: NO DATA")
        return

    store = {b: np.full((N_ROWS, N_COLS), NODATA) for b in out_names}
    failed = []
    land = load_land()
    blocks = []
    for r in range(0, N_ROWS, BLOCK):
        for c in range(0, N_COLS, BLOCK):
            nr, nc = min(BLOCK, N_ROWS - r), min(BLOCK, N_COLS - c)
            if land is None or land[r:r + nr, c:c + nc].any():
                blocks.append((r, c, nr, nc))
    print(f"{len(blocks):,} blocks to download with {WORKERS} parallel requests")

    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(fetch_block, img, out_names, store, failed, r, c, nr, nc) for (r, c, nr, nc) in blocks]
        for f in futs:
            f.result()
            done += 1
            if done % 100 == 0 or done == len(futs):
                el = time.time() - t0
                print(f"  {done}/{len(futs)} blocks  ({el / 60:.1f} min, ~{el / done * (len(futs) - done) / 60:.0f} min left, "
                      f"{len(failed)} small blocks lost)")

    if failed:
        print(f"{len(failed)} small blocks left empty. First ones:")
        for (r, c, nr, nc, m) in failed[:5]:
            print(f"   lat {Y_MAX - (r + nr) * RES:.2f}..{Y_MAX - r * RES:.2f} lon {X_MIN + c * RES:.2f}..{X_MIN + (c + nc) * RES:.2f}: {m}")

    valid = np.zeros((N_ROWS, N_COLS), dtype=bool)
    for b in out_names:
        valid |= (store[b] != NODATA) & np.isfinite(store[b])
    rr, cc = np.nonzero(valid)
    df = pd.DataFrame({"tile_id": rr * N_COLS + cc,
                       "lat": Y_MAX - RES * (rr + 0.5),
                       "lon": X_MIN + RES * (cc + 0.5)})
    for b in out_names:
        v = store[b][rr, cc]
        df[b] = np.round(np.where(v == NODATA, np.nan, v), 4)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"B_{what}_direct.csv")
    df.to_csv(path, index=False)
    print(f"wrote {path}: {len(df):,} tiles")


if __name__ == "__main__":
    main()
