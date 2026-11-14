"""
Albedo for the lunar south pole target (28 x 28 km box centred on the pole), written into the CSV.

Method (needs a source you can cite):
  1. Mean LOLA 1064 nm normal albedo A_L inside the box, from the polar LOLA albedo map
     (LDAM_50S_1000M, 1 km/pixel, Lemelin et al. 2016; browse page https://imbrium.mit.edu/BROWSE/LOLA_GDR/ALBEDO/).
  2. Convert to an equivalent broadband (bolometric) solar albedo with the factor F = 0.49 from
     Hayne et al. 2017 (JGR Planets; arXiv 1711.00977): A_solar = F * A_L. That factor was derived
     against Diviner equatorial data and a global LOLA map, so using it at the pole and on the
     1 km polar map is an APPROXIMATION. The script says so in the CSV source cell.

!! UNTESTED on the real file (the author's sandbox cannot reach NASA). Tested on a synthetic file only.
!! Download LDAM_50S_1000M (the .LBL and the .IMG, or the FLOAT_IMG version) into the folder
!! next to this script, set ALBEDO_FILE below, and run:  python albedo_moon.py
!! Check the printed raw values first: LOLA normal albedo should be roughly 0.2-0.4 inside the box.
"""
import json, os, sys
import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import from_bounds

# --- settings ---------------------------------------------------------------
ALBEDO_FILE = "LDAM_50S_1000M.LBL"   # the .LBL label (GDAL reads the .IMG through it) or a GeoTIFF
CX, CY, HALF = 0.0, 0.0, 14000.0     # same 28 x 28 km box as the slope and temperature scripts
F = 0.49                             # LOLA 1064 nm normal albedo -> broadband solar albedo (Hayne et al. 2017)
CSV_IN = CSV_OUT = "targets_moon_south_pole.csv"
# -----------------------------------------------------------------------------

if not os.path.exists(ALBEDO_FILE):
    sys.exit(f"Cannot find {ALBEDO_FILE} in {os.getcwd()}.\n"
             "Download the LOLA south pole albedo map (the .LBL and the .IMG with the same name) into this folder,\n"
             "then set ALBEDO_FILE at the top of this script to the .LBL file name.")

with rasterio.open(ALBEDO_FILE) as src:
    print("CRS:", src.crs)
    print("bounds (m):", src.bounds, " pixel size (m):", src.res)
    print("dtype:", src.dtypes[0], " scale/offset:", src.scales[0], src.offsets[0], " nodata:", src.nodata)
    win = from_bounds(CX - HALF, CY - HALF, CX + HALF, CY + HALF, src.transform)
    z = src.read(1, window=win, masked=True)
    z = np.ma.filled(z.astype("float64"), np.nan) * src.scales[0] + src.offsets[0]

v = z[np.isfinite(z)]
if v.size == 0:
    raise SystemExit("No valid pixels in the box: check the file, its CRS/bounds and the box settings.")

raw = {"n_pixels": int(v.size), "nodata_fraction": round(float(1 - v.size / z.size), 4),
       "A_L_mean": round(float(v.mean()), 4), "A_L_median": round(float(np.median(v)), 4),
       "A_L_std": round(float(v.std()), 4), "A_L_min": round(float(v.min()), 4), "A_L_max": round(float(v.max()), 4)}
albedo = round(F * float(v.mean()), 3)
raw["albedo_broadband_estimate"] = albedo
print(json.dumps(raw, indent=2))
json.dump(raw, open("moon_albedo_result.json", "w"), indent=2)

src_text = ("LOLA 1064 nm normal albedo map LDAM_50S_1000M (Lemelin et al. 2016), mean over 28x28 km box centred on pole, "
            f"x {F} to broadband solar albedo (Hayne et al. 2017); approximate: factor derived at equatorial/global scale; "
            "computed with albedo_moon.py")
df = pd.read_csv(CSV_IN, keep_default_na=False)
df["value"] = df["value"].astype(object)
m = (df.target == "moon_south_pole") & (df.feature == "albedo")
df.loc[m, "value"] = albedo
df.loc[m, "source"] = src_text
df.to_csv(CSV_OUT, index=False)
print("updated", CSV_OUT, "-> albedo =", albedo)