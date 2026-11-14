"""
b_export_features.py -- member B: terrain + geology exports on the SHARED grid.

Usage (same style as A's a_export_climate.py):
    python b_export_features.py terrain test     # quick check on a small Atacama box, prints rows
    python b_export_features.py terrain one      # launches ONE big land block (do this before "run")
    python b_export_features.py terrain run      # launches the world export tasks
    python b_export_features.py geology test
    python b_export_features.py geology run

Needs grid_config.py (A's file) in the same folder.
Tasks run on Earth Engine servers; watch them at https://code.earthengine.google.com (Tasks tab)
or just wait for the CSVs to appear in the Drive folder.
"""
import os
import sys
import ee
from grid_config import CRS, CRS_TRANSFORM, RES, N_COLS, X_MIN, Y_MAX

# >>> put YOUR Earth Engine Cloud project id here (or set env var EE_PROJECT) <<<
PROJECT = os.environ.get("EE_PROJECT", "nasa-space-challenge-514710")
FOLDER = "SpaceApps_B"        # Drive folder that Earth Engine will create
LAT_STEP, LON_STEP = 10, 15   # chunk size in degrees (lower = safer, more tasks)
TEST_BOX = [-70, -24, -68, -22]  # small Atacama box (2x2 deg = 64 tiles): lon_min, lat_min, lon_max, lat_max


def build_terrain():
    """Copernicus DEM -> ~500 m -> slope -> mean/std per 0.25 deg tile."""
    tile_proj = ee.Projection(CRS, CRS_TRANSFORM)
    p500 = ee.Projection(CRS, [1 / 240, 0, -180, 0, -1 / 240, 90])  # ~463 m, like MOLA
    col = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM")
    # mosaic() loses its projection, so restore the original one
    dem30 = col.mosaic().setDefaultProjection(col.first().projection())
    # LIGHT version: let Earth Engine use its built-in image pyramid (block-averaged levels)
    # instead of averaging every 30 m pixel ourselves (that ran out of memory).
    dem500 = dem30.reproject(p500)
    slope = ee.Terrain.slope(dem500).rename("s")  # degrees
    reducer = ee.Reducer.mean().combine(reducer2=ee.Reducer.stdDev(), sharedInputs=True)
    stats = slope.reduceResolution(reducer=reducer, maxPixels=4096).reproject(tile_proj)
    rename = {"slope_mean": "s_mean", "slope_std": "s_stdDev"}
    return stats, rename, tile_proj


def build_geology():
    """ASTER GED emissivity -> Ninomiya mafic + quartz indices, mean per tile."""
    tile_proj = ee.Projection(CRS, CRS_TRANSFORM)
    a = ee.Image("NASA/ASTER_GED/AG100_003")
    b10, b11, b12, b13 = [a.select(f"emissivity_band{i}").multiply(0.001) for i in (10, 11, 12, 13)]
    mafic = b12.divide(b13).rename("mafic_idx")                       # MI = b12 / b13
    quartz = b11.multiply(b11).divide(b10.multiply(b12)).rename("quartz_idx")  # QI = b11^2/(b10*b12)
    # Earth Engine allows < 65536 pixels per output cell, and one 0.25 deg tile holds ~77,000
    # ASTER pixels. So we average in two stages: 100 m -> 0.0625 deg (4900 px per cell),
    # then 0.0625 deg -> 0.25 deg tile (4 x 4 cells).
    mid_proj = ee.Projection(CRS, [RES / 4, 0, X_MIN, 0, -RES / 4, Y_MAX])
    stage1 = (mafic.addBands(quartz)
              .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=8192)
              .reproject(mid_proj))
    stats = (stage1
             .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=256)
             .reproject(tile_proj))
    rename = {"mafic_idx": "mafic_idx", "quartz_idx": "quartz_idx"}
    return stats, rename, tile_proj


def tiles_for(stats, rename, tile_proj, region):
    """Sample one value per tile centre and build rows with the shared tile_id formula."""
    samples = stats.sample(region=region, projection=tile_proj, geometries=True, dropNulls=True)

    def to_feature(f):
        c = ee.List(f.geometry().coordinates())
        lon = ee.Number(c.get(0))
        lat = ee.Number(c.get(1))
        row = ee.Number(Y_MAX).subtract(lat).divide(RES).floor()   # row 0 = NORTH (A's convention)
        col = lon.subtract(X_MIN).divide(RES).floor()
        props = {"tile_id": row.multiply(N_COLS).add(col).int(), "lat": lat, "lon": lon}
        for out_name, src in rename.items():
            props[out_name] = f.get(src)
        return ee.Feature(None, props)

    return samples.map(to_feature)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("terrain", "geology") or sys.argv[2] not in ("test", "one", "run"):
        sys.exit(__doc__)
    what, mode = sys.argv[1], sys.argv[2]
    ee.Initialize(project=PROJECT)

    stats, rename, tile_proj = build_terrain() if what == "terrain" else build_geology()
    selectors = ["tile_id", "lat", "lon"] + list(rename.keys())

    if mode == "test":
        region = ee.Geometry.Rectangle(TEST_BOX, CRS, False)
        fc = tiles_for(stats, rename, tile_proj, region)
        print("tiles in test box (expect ~64):", fc.size().getInfo())
        for feat in fc.limit(5).getInfo()["features"]:
            print(feat["properties"])
        return

    # "one" = launch a single big land block (lat 0-30N, lon 0-90E: Africa/Middle East/India)
    # to check that a full-size chunk works BEFORE launching all 24.
    lat_range = range(0, LAT_STEP, LAT_STEP) if mode == "one" else range(-90, 90, LAT_STEP)
    lon_range = range(0, LON_STEP, LON_STEP) if mode == "one" else range(-180, 180, LON_STEP)
    n = 0
    for lat0 in lat_range:
        for lon0 in lon_range:
            region = ee.Geometry.Rectangle([lon0, lat0, lon0 + LON_STEP, lat0 + LAT_STEP], CRS, False)
            task = ee.batch.Export.table.toDrive(
                collection=tiles_for(stats, rename, tile_proj, region),
                description=f"B_{what}_lat{lat0}_lon{lon0}",
                folder=FOLDER,
                fileFormat="CSV",
                selectors=selectors,
            )
            task.start()
            n += 1
    print(f"Started {n} tasks. Monitor them in the Earth Engine editor > Tasks tab.")


if __name__ == "__main__":
    main()