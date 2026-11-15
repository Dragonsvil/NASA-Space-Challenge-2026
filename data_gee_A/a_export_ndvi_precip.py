
import io
import os
import sys
import time

import ee
import numpy as np
import pandas as pd

from grid_config import RES, N_COLS, N_ROWS, X_MIN, Y_MAX

PROJECT = "space-app-01"
OUT_DIR = os.path.join("data", "raw_A")
NODATA = -9999.0

NDVI_YEARS = [2021, 2022, 2023]
PRECIP_START, PRECIP_END = "2016-01-01", "2021-01-01"
# D asked for the ANNUAL MAXIMUM NDVI (green-in-summer tundra must count as vegetated).
# "max" = mean of the yearly maxima ; "mean" = plain mean over the period (old behaviour)
NDVI_MODE = "max"

BLOCK_ROWS, BLOCK_COLS = 120, 360      # 6 x 4 = 24 first-level requests
MIN_BLOCK = 8                          # smallest block (tiles) before giving up on it
DEADLINE_MS = 90_000                   # max time for one request
BAND_BUDGET_S = 600                    # max 10 min per band: after that, remaining blocks stay -9999

# NDVI is not needed over polar ice/ocean: rows outside 80N..60S are left at -9999 on purpose
NDVI_ROW_MIN = int((Y_MAX - 80.0) / RES)        # 40
NDVI_ROW_MAX = int((Y_MAX - (-60.0)) / RES)     # 600 (exclusive)


# ======================================================================================
# Sources. Each builder returns one single-band image (already in the right unit).
# ======================================================================================
def _keep_1_15():
    return ee.Filter.Or(*[ee.Filter.calendarRange(d, d, "day_of_month") for d in (1, 15)])


def _ndvi_composite(col_ndvi):
    """col_ndvi: collection with one NDVI band in [-1, 1]."""
    if NDVI_MODE == "max":
        yearly = [col_ndvi.filterDate(f"{y}-01-01", f"{y + 1}-01-01").max() for y in NDVI_YEARS]
        img = ee.ImageCollection(yearly).mean()
    else:
        img = col_ndvi.mean()
    return img.max(0).rename("ndvi")


def ndvi_from_mcd43a4():
    # same product family/projection as the albedo layer that already exported fine
    c = (ee.ImageCollection("MODIS/061/MCD43A4")
         .filterDate(f"{NDVI_YEARS[0]}-01-01", f"{NDVI_YEARS[-1] + 1}-01-01").filter(_keep_1_15()))
    nd = c.map(lambda im: im.normalizedDifference(["Nadir_Reflectance_Band2", "Nadir_Reflectance_Band1"])
               .rename("ndvi").copyProperties(im, ["system:time_start"]))
    return _ndvi_composite(nd).setDefaultProjection(c.first().select(0).projection())


def ndvi_from_mod13c1():
    c = (ee.ImageCollection("MODIS/061/MOD13C1")
         .filterDate(f"{NDVI_YEARS[0]}-01-01", f"{NDVI_YEARS[-1] + 1}-01-01")
         .select("CMG_0_05_Deg_16_Days_NDVI"))
    nd = c.map(lambda im: im.multiply(0.0001).rename("ndvi").copyProperties(im, ["system:time_start"]))
    return _ndvi_composite(nd).setDefaultProjection(c.first().projection())


def ndvi_from_mod13a2():
    c = (ee.ImageCollection("MODIS/061/MOD13A2")
         .filterDate(f"{NDVI_YEARS[0]}-01-01", f"{NDVI_YEARS[-1] + 1}-01-01").select("NDVI"))
    nd = c.map(lambda im: im.multiply(0.0001).rename("ndvi").copyProperties(im, ["system:time_start"]))
    return _ndvi_composite(nd).setDefaultProjection(c.first().projection())


def imerg(version):
    def build():
        c = (ee.ImageCollection(f"NASA/GPM_L3/IMERG_MONTHLY_{version}")
             .filterDate(PRECIP_START, PRECIP_END).select("precipitation"))
        return (c.mean().multiply(24 * 365.25).rename("precip_mm")          # mm/hr -> mm/yr
                .setDefaultProjection(c.first().projection()))
    return build


def era5_land():
    c = (ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR")
         .filterDate(PRECIP_START, PRECIP_END).select("total_precipitation_sum"))
    return (c.mean().multiply(12 * 1000).rename("precip_era5_mm")           # m/month -> mm/yr
            .setDefaultProjection(c.first().projection()))


# band -> candidate sources, tried in order
BANDS = {
    "ndvi":           [("MOD13C1", ndvi_from_mod13c1), ("MCD43A4", ndvi_from_mcd43a4),
                       ("MOD13A2", ndvi_from_mod13a2)],
    "precip_mm":      [("IMERG V07", imerg("V07")), ("IMERG V06", imerg("V06"))],
    "precip_era5_mm": [("ERA5-Land", era5_land)],
}
LAYERS = {"ndvi": ["ndvi"], "precip": ["precip_mm", "precip_era5_mm"]}

# test block for choosing a source: 8x8 tiles in the Sahara (lat ~23N, lon ~13E)
TEST_BLOCK = (int((Y_MAX - 25.0) / RES), 8, int((13.0 - X_MIN) / RES), 8)


# ======================================================================================
# Download
# ======================================================================================
def fetch(img, band, row0, n_rows, col0, n_cols):
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
    if isinstance(out, (bytes, bytearray)):          # older earthengine-api returns raw .npy bytes
        out = np.load(io.BytesIO(out))
    arr = out[band] if out.dtype.names else out
    return np.asarray(arr, dtype=np.float64).reshape(n_rows, n_cols)


def prepare(builder, band):
    return builder().select([0], [band]).unmask(NODATA, False).toFloat()


def choose_source(band):
    r, nr, c, nc = TEST_BLOCK
    for name, builder in BANDS[band]:
        try:
            img = prepare(builder, band)
            v = fetch(img, band, r, nr, c, nc)
            good = v[(v != NODATA) & np.isfinite(v)]
            if good.size == 0:
                print(f"  [{band}] source {name}: answered but only no-data, next")
                continue
            print(f"  [{band}] source {name}: OK (test block median {np.median(good):.3f})")
            return name, img
        except Exception as e:
            print(f"  [{band}] source {name}: failed -> {str(e)[:150]}")
    return None, None


def fetch_block(img, band, out, failed, row0, col0, n_rows, n_cols, t_end):
    if time.time() > t_end:                          # time budget used up: give up on this block
        failed.append((row0, col0, n_rows, n_cols, "time budget exceeded"))
        return
    msg = ""
    for attempt in (1, 2, 3):
        try:
            out[row0:row0 + n_rows, col0:col0 + n_cols] = fetch(img, band, row0, n_rows, col0, n_cols)
            return
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            if "too many" in low or "quota" in low or "429" in low or "rate" in low:
                time.sleep(5 * attempt)              # quota: wait and retry the same block
                continue
            break                                    # geometry / timeout / other: split instead
    if n_rows <= MIN_BLOCK and n_cols <= MIN_BLOCK:
        failed.append((row0, col0, n_rows, n_cols, msg[:100]))
        return
    h, w = max(n_rows // 2, 1), max(n_cols // 2, 1)
    rows = [(row0, n_rows)] if n_rows <= MIN_BLOCK else [(row0, h), (row0 + h, n_rows - h)]
    cols = [(col0, n_cols)] if n_cols <= MIN_BLOCK else [(col0, w), (col0 + w, n_cols - w)]
    for r, nr in rows:
        for c, nc in cols:
            fetch_block(img, band, out, failed, r, c, nr, nc, t_end)


def download_band(band):
    out = np.full((N_ROWS, N_COLS), NODATA, dtype=np.float64)
    name, img = choose_source(band)
    if img is None:
        print(f"  !! [{band}] no source worked: column left at -9999 (D's pipeline copes with it)")
        return out, None
    row_lo, row_hi = (NDVI_ROW_MIN, NDVI_ROW_MAX) if band == "ndvi" else (0, N_ROWS)
    failed, t0 = [], time.time()
    t_end = t0 + BAND_BUDGET_S
    blocks = [(r, c) for r in range(row_lo, row_hi, BLOCK_ROWS) for c in range(0, N_COLS, BLOCK_COLS)]
    for k, (r0, c0) in enumerate(blocks, 1):
        nr, nc = min(BLOCK_ROWS, row_hi - r0), min(BLOCK_COLS, N_COLS - c0)
        fetch_block(img, band, out, failed, r0, c0, nr, nc, t_end)
        print(f"  [{band}] block {k}/{len(blocks)} done  ({time.time() - t0:5.0f}s, "
              f"small blocks lost so far: {len(failed)})")
    if failed:
        lost = sum(nr * nc for (_, _, nr, nc, _) in failed)
        print(f"  [{band}] {len(failed)} small blocks left at -9999 ({lost} tiles, "
              f"{lost / (N_ROWS * N_COLS):.2%} of the grid). First ones:")
        for (r, c, nr, nc, m) in failed[:5]:
            print(f"      lat {Y_MAX - (r + nr) * RES:7.2f}..{Y_MAX - r * RES:7.2f}  "
                  f"lon {X_MIN + c * RES:8.2f}..{X_MIN + (c + nc) * RES:8.2f}  {m}")
    return out, name


# ======================================================================================
# Output + checks
# ======================================================================================
CHECKS = [  # name, lat, lon, {band: (min_ok, max_ok)}
    ("Sahara",            23.0,  13.0,  {"ndvi": (0, 0.15), "precip_mm": (0, 100), "precip_era5_mm": (0, 150)}),
    ("Amazon",            -3.0, -60.0,  {"ndvi": (0.6, 0.98), "precip_mm": (1500, 4500), "precip_era5_mm": (1200, 5000)}),
    ("Atacama",          -24.5, -69.25, {"ndvi": (0, 0.15), "precip_mm": (0, 100), "precip_era5_mm": (0, 200)}),
    ("Paris",             48.9,   2.4,  {"ndvi": (0.4, 0.95), "precip_mm": (400, 1100), "precip_era5_mm": (400, 1200)}),
]


def land_ids():
    path = os.path.join(OUT_DIR, "A_land_b0_0.csv")
    if not os.path.exists(path):
        return None
    d = pd.read_csv(path)
    ids = d.loc[d["land_frac"] >= 0.5, "tile_id"].unique()
    return ids[(ids >= 0) & (ids < N_ROWS * N_COLS)]        # sample() adds ids past the grid edge


def export_layer(layer):
    print(f"\n========== {layer} ==========")
    t0 = time.time()
    df = pd.DataFrame({"tile_id": np.arange(N_ROWS * N_COLS, dtype=np.int64)})
    sources = {}
    for band in LAYERS[layer]:
        arr, src = download_band(band)
        sources[band] = src
        v = arr.ravel()
        v[~np.isfinite(v)] = NODATA
        df[band] = np.round(v, 4)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"A_{layer}_b0_0.csv")
    df.to_csv(path, index=False)
    print(f"\n  wrote {path}  ({len(df):,} rows, {time.time() - t0:.0f}s)  sources: {sources}")

    try:                                             # report only: can never lose the CSV
        lids = land_ids()
        for band in LAYERS[layer]:
            v = df[band]
            ok = v[v != NODATA]
            line = f"  {band:15s} "
            if lids is not None:
                land_v = df.loc[lids, band]
                line += f"LAND tiles with data: {(land_v != NODATA).mean():6.1%}   "
            if len(ok):
                line += f"min {ok.min():9.3f}  median {ok.median():9.3f}  max {ok.max():9.3f}"
            else:
                line += "NO DATA AT ALL"
            print(line)
        for name, lat, lon, rules in CHECKS:
            tid = int((Y_MAX - lat) // RES) * N_COLS + int((lon - X_MIN) // RES)
            parts = []
            for band in LAYERS[layer]:
                val = df.at[tid, band]
                lo, hi = rules[band]
                parts.append(f"{band}={val:.3f} {'OK' if lo <= val <= hi else 'CHECK'}")
            print(f"  {name:8s} " + "  ".join(parts))
    except Exception as e:
        print(f"  (report skipped: {e}) -- the CSV itself is written and fine")


if __name__ == "__main__":
    ee.Initialize(project=PROJECT)
    ee.data.setDeadline(DEADLINE_MS)
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for layer in (list(LAYERS) if which == "all" else [which]):
        try:
            export_layer(layer)
        except Exception as e:
            print(f"\n!! {layer} stopped: {e}\n   Send this line to D.")
    print("\nNext: python a_merge_csv.py   then   python a_sanity_check.py")
