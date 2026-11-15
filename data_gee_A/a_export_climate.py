
import sys
from collections import Counter
import ee
from grid_config import RES, N_COLS, N_ROWS, X_MIN, Y_MAX

PROJECT = "space-app-01"
FOLDER = "SpaceApps2026_A"

LST_START, LST_END = "2021-01-01", "2024-01-01"
ALBEDO_START, ALBEDO_END = "2023-01-01", "2024-01-01"
NDVI_START, NDVI_END = "2021-01-01", "2024-01-01"
PRECIP_START, PRECIP_END = "2016-01-01", "2021-01-01"
LANDCOVER_YEAR = ("2021-01-01", "2022-01-01")
NODATA = -9999

GRID_TRANSFORM = [RES, 0, X_MIN, 0, -RES, Y_MAX]


def build_land():
    lc = ee.ImageCollection("MODIS/061/MCD12Q1").filterDate(*LANDCOVER_YEAR).first().select("LC_Type1")
    return lc.neq(17).rename("land_frac")


def build_lst():
    c = ee.ImageCollection("MODIS/061/MOD11A2").filterDate(LST_START, LST_END)
    to_c = lambda im: im.multiply(0.02).subtract(273.15)
    day = c.select("LST_Day_1km").map(to_c)
    night = c.select("LST_Night_1km").map(to_c)
    return ee.Image.cat([
        night.min().rename("lst_min_night"),
        day.max().rename("lst_max_day"),
        day.mean().subtract(night.mean()).rename("lst_range"),
    ])


def build_albedo():
    keep = ee.Filter.Or(*[ee.Filter.calendarRange(d, d, "day_of_month") for d in (1, 15)])
    c = (ee.ImageCollection("MODIS/061/MCD43A3")
         .filterDate(ALBEDO_START, ALBEDO_END).filter(keep)
         .select("Albedo_WSA_shortwave"))
    return c.map(lambda im: im.multiply(0.001)).mean().rename("albedo")


def build_ndvi():
    keep = ee.Filter.Or(*[ee.Filter.calendarRange(d, d, "day_of_month") for d in (1, 15)])
    c = (ee.ImageCollection("MODIS/061/MCD43A4")
         .filterDate(NDVI_START, NDVI_END).filter(keep))
    def calc_ndvi(im):
        return im.normalizedDifference(["Nadir_Reflectance_Band2", "Nadir_Reflectance_Band1"]).max(0).rename("ndvi")
    return c.map(calc_ndvi).mean().rename("ndvi")

def build_precip():
    imerg = (ee.ImageCollection("NASA/GPM_L3/IMERG_MONTHLY_V06")
             .filterDate(PRECIP_START, PRECIP_END).select("precipitation"))
    imerg_yr = imerg.mean().multiply(24 * 365.25).rename("precip_mm")
    era5 = (ee.ImageCollection("ECMWF/ERA5_LAND/MONTHLY_AGGR")
            .filterDate(PRECIP_START, PRECIP_END).select("total_precipitation_sum"))
    era5_yr = era5.mean().multiply(12 * 1000).rename("precip_era5_mm")
    return imerg_yr.addBands(era5_yr)


LAYERS = {
    "land": (build_land, ["land_frac"]),
    "lst": (build_lst, ["lst_min_night", "lst_max_day", "lst_range"]),
    "albedo": (build_albedo, ["albedo"]),
    "ndvi": (build_ndvi, ["ndvi"]),
    "precip": (build_precip, ["precip_mm", "precip_era5_mm"]),
}


def start_export(name):
    builder, bands = LAYERS[name]
    grid_proj = ee.Projection("EPSG:4326", GRID_TRANSFORM)

    lonlat = ee.Image.pixelLonLat().reproject(grid_proj)
    col_idx = lonlat.select("longitude").subtract(X_MIN).divide(RES).floor()
    row_idx = ee.Image.constant(Y_MAX).subtract(lonlat.select("latitude")).divide(RES).floor()
    tile_id = row_idx.multiply(N_COLS).add(col_idx).toInt64().rename("tile_id")

    img = tile_id.addBands(builder().unmask(NODATA))

    # [-180, -89.875, 180, 89.875] évite les pôles exacts où MODIS sinusoïdal et PLANAR divergent
    globe = ee.Geometry.Rectangle([-180, -89.875, 180, 89.875], "EPSG:4326", False)
    pts = img.sample(region=globe, projection=grid_proj, tileScale=4, geometries=False)

    tag = f"A_{name}_b0_0"
    task = ee.batch.Export.table.toDrive(
        collection=pts,
        description=tag,
        folder=FOLDER,
        fileNamePrefix=tag,
        fileFormat="CSV",
        selectors=["tile_id"] + bands,
    )
    task.start()
    print(f"Started fast global export '{tag}'")


def print_status():
    counts, errors = Counter(), {}
    for t in ee.batch.Task.list():
        d = t.status()
        desc = d.get("description", "")
        if desc.startswith("A_"):
            counts[(desc.split("_")[1], d["state"])] += 1
            if d["state"] == "FAILED":
                errors[desc] = d.get("error_message", "")
    for (layer, state), k in sorted(counts.items()):
        print(f"  {layer:8s} {state:10s} {k}")
    for desc, msg in list(errors.items())[:5]:
        print("ERROR", desc, "->", msg)


def cancel_all():
    k = 0
    for t in ee.batch.Task.list():
        d = t.status()
        if d.get("description", "").startswith("A_") and d["state"] in ("READY", "RUNNING"):
            t.cancel()
            k += 1
    print(f"Cancelled {k} tasks")


if __name__ == "__main__":
    ee.Initialize(project=PROJECT)
    arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    if arg == "status":
        print_status()
    elif arg == "cancel":
        cancel_all()
    else:
        for nm in (list(LAYERS) if arg == "all" else [arg]):
            start_export(nm)
