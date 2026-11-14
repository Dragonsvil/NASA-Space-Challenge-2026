"""
Lunar south pole target: slope_mean and slope_std on a 28 x 28 km footprint
using the LOLA DEM (LDEM_80S_80MPP_ADJ.TIF, 80 m/pixel) resampled to 500 m.

Same recipe as the Earth tiles:
  1. cut the footprint out of the DEM
  2. resample to 500 m (average)
  3. slope per pixel in degrees
  4. mean and standard deviation over the footprint
"""
import json
import os
import urllib.request
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.enums import Resampling

# --- settings you can change ------------------------------------------------
DEM_URL = "https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF"
DEM = "LDEM_80S_80MPP_ADJ.TIF"          # local file name after download
CX, CY = 0.0, 0.0      # centre of the site in south polar stereographic metres (0,0 = the pole)
HALF = 14000.0         # half width of the footprint: 14 km -> 28 x 28 km box
PIX = 500.0            # target pixel size in metres
DDOF = 0               # 0 = population std (numpy default). Use the same setting as Jezero.
# ---------------------------------------------------------------------------

# Ensure the DEM file is available locally
if not os.path.exists(DEM):
    print(f"Downloading {DEM} from {DEM_URL} ...")
    urllib.request.urlretrieve(DEM_URL, DEM)
    print("Download complete.")
else:
    print(f"Using existing {DEM}")

def horn_slope(z, d):
    """Slope in degrees with Horn's 3x3 method (same idea as gdaldem slope).
    z has shape (n, n); the result has shape (n-2, n-2)."""
    a, b, c = z[:-2, :-2], z[:-2, 1:-1], z[:-2, 2:]
    dd, f = z[1:-1, :-2], z[1:-1, 2:]
    g, h, i = z[2:, :-2], z[2:, 1:-1], z[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * dd + g)) / (8 * d)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * d)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))

with rasterio.open(DEM) as src:
    print("CRS:", src.crs)
    print("pixel size (m):", src.res, "dtype:", src.dtypes[0],
          "scale/offset:", src.scales[0], src.offsets[0], "nodata:", src.nodata)

    margin = HALF + PIX                      # one extra pixel ring so edge slopes are valid
    n = int(round(2 * margin / PIX))         # 58 pixels of 500 m
    win = from_bounds(CX - margin, CY - margin, CX + margin, CY + margin, src.transform)
    z = src.read(1, window=win, out_shape=(n, n),
                 resampling=Resampling.average, masked=True)
    z = np.ma.filled(z.astype("float64"), np.nan) * src.scales[0] + src.offsets[0]

nan_frac = float(np.isnan(z).mean())
slope = horn_slope(z, PIX)                   # 56 x 56 = 28 x 28 km
vals = slope[~np.isnan(slope)]

result = {
    "centre_xy_m": [CX, CY],
    "footprint_km": 2 * HALF / 1000,
    "dem_pixel_m": PIX,
    "n_pixels": int(vals.size),
    "nodata_fraction": round(nan_frac, 4),
    "elev_min_m": float(np.nanmin(z)),
    "elev_max_m": float(np.nanmax(z)),
    "slope_mean_deg": float(vals.mean()),
    "slope_std_deg": float(vals.std(ddof=DDOF)),
}
print(json.dumps(result, indent=2))
with open("moon_slope_result.json", "w") as f:
    json.dump(result, f, indent=2)
