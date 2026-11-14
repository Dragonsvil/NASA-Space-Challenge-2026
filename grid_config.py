"""
grid_config.py -- shared global grid definition (A and B MUST use this file).

Grid: regular lat/lon, 0.25 deg, 1440 columns x 720 rows, origin at top-left (-180, 90).
tile_id = row * N_COLS + col   (row 0 = northernmost, col 0 = westernmost)
lat/lon in the CSV are the tile CENTERS.
"""
import numpy as np

RES = 0.25
N_COLS = 1440
N_ROWS = 720
X_MIN, Y_MAX = -180.0, 90.0

CRS = "EPSG:4326"
# [xScale, xShear, xTranslation, yShear, yScale, yTranslation]
CRS_TRANSFORM = [RES, 0, X_MIN, 0, -RES, Y_MAX]

NODATA = -9999.0  # value written for masked pixels in exports


def tile_id(row, col):
    return row * N_COLS + col


def tile_center(row, col):
    lat = Y_MAX - RES * (row + 0.5)
    lon = X_MIN + RES * (col + 0.5)
    return lat, lon


def latlon_to_rowcol(lat, lon):
    row = int((Y_MAX - lat) // RES)
    col = int((lon - X_MIN) // RES)
    return min(max(row, 0), N_ROWS - 1), min(max(col, 0), N_COLS - 1)


def grid_arrays():

    rows, cols = np.meshgrid(np.arange(N_ROWS), np.arange(N_COLS), indexing="ij")
    ids = rows * N_COLS + cols
    lat = Y_MAX - RES * (rows + 0.5)
    lon = X_MIN + RES * (cols + 0.5)
    return ids, lat, lon