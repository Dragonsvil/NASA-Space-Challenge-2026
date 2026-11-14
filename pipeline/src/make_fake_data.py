"""
make_fake_data.py — write FAKE but realistic input files into data/.

    python src/make_fake_data.py

Writes:
    data/earth_features.csv   ~20,000 land tiles on the 0.25° grid   (real version: teammates A + B)
    data/targets.csv          Jezero + lunar south pole, long format (real version: teammate C)
    data/known_analogs.csv    10 real analog sites, real lat/lon     (real version: teammate C)

The Earth values are invented with simple rules (latitude + rough boxes for deserts,
rainforests, mountains, volcanic areas, ice sheets). They are only meant to make the
pipeline run end-to-end and give sensible-looking results. NEVER present them as real data.
When the real CSVs arrive, just replace the files in data/: no code change needed.

The grid (tile_id, tile centers, no-data value) comes from ../grid_config.py, like the
real Earth Engine exports. Missing values are written as -9999, like the real exports.
"""

import numpy as np
import pandas as pd

from common import FAKE_DIR, grid_config, land_mask

SEED = 42            # same seed -> same fake data every run
N_TILES = 20_000     # roughly how many land tiles we want

rng = np.random.default_rng(SEED)


# ---------------------------------------------------------------------------
# 1. Tile grid helpers (thin wrappers around grid_config)
# ---------------------------------------------------------------------------

def rowcol_of(lats, lons):
    """Grid (row, col) arrays for many points, using grid_config.latlon_to_rowcol."""
    rc = [grid_config.latlon_to_rowcol(a, b) for a, b in zip(lats, lons)]
    return np.array([r for r, _ in rc]), np.array([c for _, c in rc])


# ---------------------------------------------------------------------------
# 2. Very rough "land" boxes: (name, lat_min, lat_max, lon_min, lon_max)
#    Not a real coastline, just enough so tiles land roughly on continents.
# ---------------------------------------------------------------------------
LAND_BOXES = [
    ("North America north", 50, 70, -165, -60),
    ("North America mid",   30, 50, -124, -70),
    ("Mexico",              15, 30, -115, -90),
    ("Central America",      8, 18,  -92, -78),
    ("Arctic Canada",       70, 80, -120, -70),
    ("Greenland",           60, 82,  -55, -20),
    ("South America north",-20, 10,  -80, -35),
    ("South America south",-55,-20,  -73, -57),
    ("Europe",              36, 70,  -10,  40),
    ("Iceland",          63.4, 66.5, -24, -13.5),
    ("Svalbard",         76.5, 80,    10,  28),
    ("Sahara / N Africa",   15, 37,  -17,  35),
    ("Central Africa",      -5, 15,  -17,  50),
    ("Southern Africa",    -35, -5,   12,  40),
    ("Arabia",              12, 32,   35,  58),
    ("Asia",                25, 75,   40, 140),
    ("India",                8, 30,   68,  90),
    ("South-East Asia",     -8, 25,   95, 125),
    ("Australia",          -38,-12,  114, 153),
    ("Antarctica",         -85,-65, -180, 180),
    ("Hawaii",           18.9, 20.3,-156.1,-154.8),   # Big Island
    ("Canary Islands",   27.6, 29.5, -18.2, -13.3),
]

# Every known analog site gets a small block of tiles around it, so validation always
# finds a tile (fake land boxes might otherwise miss small islands).
KNOWN_ANALOGS = [
    # name, lat, lon, analog_for, used_for   (real coordinates)
    ("Atacama Desert",       -24.08,  -70.01, "Mars",
     "hyperarid soils, life detection, rover tests"),
    ("McMurdo Dry Valleys",  -77.50,  162.00, "Mars",
     "cold desert, permafrost, extremophile life"),
    ("Haughton Crater",       75.38,  -89.68, "Mars, Moon",
     "impact crater in polar desert, rover and EVA tests (HMP)"),
    ("Mauna Kea",             19.82, -155.47, "Moon, Mars",
     "basaltic regolith, ISRU and rover tests (PISCES)"),
    ("Iceland lava fields",   64.87,  -16.83, "Mars, Moon",
     "fresh basalt flows, astronaut and rover training"),
    ("Rio Tinto",             37.72,   -6.56, "Mars",
     "acidic iron-rich waters, drilling tests (MARTE)"),
    ("MDRS Utah",             38.41, -110.79, "Mars",
     "desert habitat simulations (Mars Desert Research Station)"),
    ("Svalbard",              79.42,   13.42, "Mars",
     "volcanic and permafrost geology, instrument tests (AMASE)"),
    ("Death Valley",          36.50, -117.00, "Mars",
     "hot desert, playas, rover and instrument tests"),
    ("Lanzarote",             29.00,  -13.75, "Mars, Moon",
     "basaltic volcanic landscape, astronaut geology training (PANGAEA)"),
]


def in_box(lat, lon, lat_min, lat_max, lon_min, lon_max):
    """Boolean mask: which points are inside the lat/lon box."""
    return (lat >= lat_min) & (lat <= lat_max) & (lon >= lon_min) & (lon <= lon_max)


def pick_land_tiles():
    """Pick ~N_TILES unique tile centers inside the land boxes."""
    # Draw random points, more than needed, spread over the boxes by real area
    # (a degree of longitude shrinks towards the poles: multiply by cos(latitude))
    areas = np.array([(b[2] - b[1]) * (b[4] - b[3]) * np.cos(np.radians((b[1] + b[2]) / 2))
                      for b in LAND_BOXES])
    # x 2.5: the boxes include sea, which is removed below
    n_per_box = np.maximum(50, (areas / areas.sum() * N_TILES * 2.5)).astype(int)

    lats, lons = [], []
    for (name, la0, la1, lo0, lo1), n in zip(LAND_BOXES, n_per_box):
        lats.append(rng.uniform(la0, la1, n))
        lons.append(rng.uniform(lo0, lo1, n))
    row, col = rowcol_of(np.concatenate(lats), np.concatenate(lons))

    tiles = add_grid_info(pd.DataFrame({"row": row, "col": col}).drop_duplicates())
    tiles = tiles[on_land(tiles)]
    if len(tiles) > N_TILES:
        tiles = tiles.sample(N_TILES, random_state=SEED)

    # Add a 5x5 block of tiles around each known analog
    extra = []
    for _, a_lat, a_lon, _, _ in KNOWN_ANALOGS:
        a_row, a_col = grid_config.latlon_to_rowcol(a_lat, a_lon)
        for d_row in range(-2, 3):
            for d_col in range(-2, 3):
                extra.append((a_row + d_row, a_col + d_col))
    extra = add_grid_info(pd.DataFrame(extra, columns=["row", "col"]))
    tiles = pd.concat([tiles, extra[on_land(extra)]])
    tiles = tiles.drop_duplicates("tile_id").sort_values(["row", "col"]).reset_index(drop=True)
    return tiles


def add_grid_info(tiles):
    """Add tile_id and tile center, exactly as grid_config defines them."""
    tiles = tiles.copy()
    tiles["tile_id"] = grid_config.tile_id(tiles["row"], tiles["col"])
    tiles["lat"], tiles["lon"] = grid_config.tile_center(tiles["row"], tiles["col"])
    return tiles


def on_land(tiles):
    """Same land test as the pipeline (Natural Earth country or a town within 100 km)."""
    return land_mask(tiles["lat"], tiles["lon"])[0]


# ---------------------------------------------------------------------------
# 3. Fake physical values
# ---------------------------------------------------------------------------

def make_features(tiles):
    lat = tiles["lat"].to_numpy()
    lon = tiles["lon"].to_numpy()
    n = len(tiles)
    alat = np.abs(lat)

    def noise(scale):
        return rng.normal(0, scale, n)

    # --- Default: temperate land, depends on latitude ---------------------
    elevation = np.clip(rng.gamma(2.0, 200, n), 0, 2000)    # metres
    t_mean = 28 - 0.55 * np.maximum(0, alat - 12)          # °C, colder towards poles
    amplitude = np.full(n, 22.0)                           # day-night spread, °C
    precip = np.clip(1400 - 12 * alat + noise(250), 150, None)  # mm/yr
    albedo = 0.17 + noise(0.02)
    ndvi = np.clip(0.25 + precip / 2500, 0, 0.85) + noise(0.05)
    slope = rng.gamma(1.5, 1.5, n)                         # degrees, mostly flat
    mafic = rng.uniform(0.15, 0.40, n)
    quartz = rng.uniform(0.25, 0.50, n)
    dust = np.clip(0.12 + noise(0.04), 0.02, None)

    # --- Tundra / high latitudes ------------------------------------------
    m = alat > 60
    precip[m] = np.clip(350 + noise(100)[m], 100, None)
    ndvi[m] = rng.uniform(0.1, 0.4, m.sum())
    dust[m] = rng.uniform(0.03, 0.08, m.sum())

    # --- Hot deserts: hot, dry, bright, dusty, big day-night range ----------
    hot_deserts = [
        (15, 32, -15, 35),     # Sahara
        (15, 32, 36, 58),      # Arabia
        (-32, -20, 120, 145),  # Australian outback
        (31, 38, -118, -109),  # Mojave / Sonoran / Colorado plateau
    ]
    for box in hot_deserts:
        m = in_box(lat, lon, *box)
        t_mean[m] += 4
        amplitude[m] = rng.uniform(35, 50, m.sum())
        precip[m] = rng.uniform(5, 150, m.sum())
        albedo[m] = rng.uniform(0.28, 0.42, m.sum())
        ndvi[m] = rng.uniform(0.02, 0.12, m.sum())
        quartz[m] = rng.uniform(0.55, 0.85, m.sum())
        dust[m] = rng.uniform(0.30, 0.55, m.sum())
    m = in_box(lat, lon, 15, 32, -15, 58)                 # Sahara + Arabia: dustiest on Earth
    dust[m] += rng.uniform(0.1, 0.3, m.sum())

    # --- Atacama: hyperarid -----------------------------------------------
    m = in_box(lat, lon, -28, -18, -71.5, -68.5)
    amplitude[m] = rng.uniform(35, 45, m.sum())
    precip[m] = rng.uniform(0.5, 15, m.sum())
    albedo[m] = rng.uniform(0.25, 0.35, m.sum())
    ndvi[m] = rng.uniform(0.0, 0.05, m.sum())
    dust[m] = rng.uniform(0.08, 0.2, m.sum())

    # --- Cold deserts (Gobi, Taklamakan) ----------------------------------
    m = in_box(lat, lon, 36, 46, 75, 110)
    t_mean[m] -= 5
    amplitude[m] = rng.uniform(35, 48, m.sum())
    precip[m] = rng.uniform(20, 200, m.sum())
    albedo[m] = rng.uniform(0.25, 0.35, m.sum())
    ndvi[m] = rng.uniform(0.03, 0.15, m.sum())
    dust[m] = rng.uniform(0.25, 0.45, m.sum())

    # --- Rainforests: wet, green, dark, small day-night range ---------------
    rainforests = [(-12, 3, -75, -48),   # Amazon
                   (-5, 5, 12, 30),      # Congo
                   (-8, 10, 95, 120)]    # South-East Asia
    for box in rainforests:
        m = in_box(lat, lon, *box)
        amplitude[m] = rng.uniform(6, 12, m.sum())
        precip[m] = rng.uniform(1800, 3200, m.sum())
        albedo[m] = rng.uniform(0.10, 0.14, m.sum())
        ndvi[m] = rng.uniform(0.75, 0.90, m.sum())
        dust[m] = rng.uniform(0.05, 0.15, m.sum())

    # --- Mountains: high and steep ----------------------------------------
    mountains = [((27, 36, 75, 100), 4500),     # Himalaya / Tibet
                 ((-45, 5, -78, -66), 3500),    # Andes
                 ((38, 55, -120, -105), 2500),  # Rockies
                 ((44, 48, 5, 15), 2200)]       # Alps
    for box, height in mountains:
        m = in_box(lat, lon, *box)
        elevation[m] = rng.uniform(0.5, 1.1, m.sum()) * height
        slope[m] = rng.uniform(10, 32, m.sum())
    m = in_box(lat, lon, -26, -20, -71, -69)              # Atacama central valley: flat plain
    slope[m] = rng.uniform(1, 8, m.sum())

    # --- Volcanic / basaltic areas: high mafic index, dark rock -----------
    basalt = [(63.4, 66.5, -24, -13.5),    # Iceland
              (18.9, 20.3, -156.1, -154.8),# Hawaii Big Island
              (27.6, 29.5, -18.2, -13.3),  # Canary Islands
              (17, 23, 73, 78),            # Deccan Traps
              (7, 14, 36, 42),             # Ethiopian highlands
              (43, 48, -121, -116),        # Columbia River basalts
              (79, 80, 12, 15)]            # NW Svalbard (Bockfjorden volcanics)
    for box in basalt:
        m = in_box(lat, lon, *box)
        mafic[m] = rng.uniform(0.65, 0.95, m.sum())
        quartz[m] = rng.uniform(0.05, 0.20, m.sum())
        albedo[m] = rng.uniform(0.07, 0.12, m.sum())
        slope[m] = slope[m] + rng.uniform(2, 8, m.sum())
    m = in_box(lat, lon, 27.6, 29.5, -18.2, -13.3)      # Canaries: dry, little vegetation
    precip[m] = rng.uniform(100, 300, m.sum())
    ndvi[m] = rng.uniform(0.05, 0.2, m.sum())

    # Mauna Kea summit: very high, cold, dry
    m = in_box(lat, lon, 19.6, 20.0, -155.7, -155.3)
    elevation[m] = rng.uniform(3000, 4200, m.sum())
    precip[m] = rng.uniform(200, 400, m.sum())
    ndvi[m] = rng.uniform(0.02, 0.1, m.sum())

    # --- Antarctica and Greenland ice sheet --------------------------------
    ice = (lat < -65) | in_box(lat, lon, 65, 82, -50, -25)
    t_mean[ice] = np.where(lat[ice] < 0, -25 - 0.9 * (alat[ice] - 65), -28) + noise(3)[ice]
    elevation[ice] = rng.uniform(1500, 3500, ice.sum())
    amplitude[ice] = rng.uniform(15, 25, ice.sum())
    precip[ice] = rng.uniform(20, 200, ice.sum())
    albedo[ice] = rng.uniform(0.70, 0.88, ice.sum())
    ndvi[ice] = rng.uniform(-0.05, 0.02, ice.sum())
    slope[ice] = rng.gamma(1.2, 0.8, ice.sum())
    dust[ice] = rng.uniform(0.01, 0.04, ice.sum())

    # McMurdo Dry Valleys: ice-free rock, extremely dry
    m = in_box(lat, lon, -78.2, -76.8, 160, 164)
    ice[m] = False
    t_mean[m] = rng.uniform(-30, -22, m.sum())
    elevation[m] = rng.uniform(100, 1500, m.sum())
    amplitude[m] = rng.uniform(25, 35, m.sum())
    precip[m] = rng.uniform(5, 50, m.sum())
    albedo[m] = rng.uniform(0.15, 0.25, m.sum())
    slope[m] = rng.uniform(5, 18, m.sum())
    mafic[m] = rng.uniform(0.4, 0.7, m.sum())          # dolerite sills

    # --- Temperatures (all in °C) ------------------------------------------
    t_mean = t_mean - 6.5 * elevation / 1000              # lapse rate: -6.5 °C per km
    lst_max_day = t_mean + 0.6 * amplitude + noise(2)
    lst_min_night = t_mean - 0.4 * amplitude + noise(2) - 10   # coldest nights of the year
    # Multi-year MEAN day / night temperatures (these two are scored, not the extremes)
    lst_mean_day = np.minimum(t_mean + 0.3 * amplitude + noise(1), lst_max_day)
    lst_mean_night = np.maximum(t_mean - 0.2 * amplitude + noise(1), lst_min_night)
    lst_range = lst_mean_day - lst_mean_night                  # MEAN daily day-night range

    # Roughness = spread of slopes inside the tile, grows with slope
    slope = np.clip(slope, 0, 60)
    slope_std = np.clip(0.6 * slope + rng.gamma(1.5, 0.7, n), 0, 30)

    # Max sun elevation: rule from CLAUDE.md
    max_sun_elev = np.clip(90 - alat + 23.44, 0, 90)

    df = pd.DataFrame({
        "tile_id": tiles["tile_id"].to_numpy(),
        "lat": lat,
        "lon": lon,
        "lst_min_night": lst_min_night,
        "lst_max_day": lst_max_day,
        "lst_range": lst_range,
        "lst_mean_night": lst_mean_night,
        "lst_mean_day": lst_mean_day,
        "albedo": np.clip(albedo, 0.03, 0.9),
        "ndvi": np.clip(ndvi, -0.1, 0.95),
        "precip_mm": np.clip(precip, 0, None),
        "slope_mean": slope,
        "slope_std": slope_std,
        "mafic_idx": np.clip(mafic, 0, 1),
        "quartz_idx": np.clip(quartz, 0, 1),
        "dust_aod": np.clip(dust, 0, 2),
        "max_sun_elev": max_sun_elev,
    })

    # Ice sheets: no rock visible -> no mineral index (realistic NaN, tests the NaN case)
    df.loc[ice, ["mafic_idx", "quartz_idx"]] = np.nan

    # A few random gaps (clouds, missing pixels), ~1% per column
    for col in ["lst_mean_night", "albedo", "ndvi", "precip_mm", "slope_mean", "dust_aod"]:
        gaps = rng.random(n) < 0.01
        df.loc[gaps, col] = np.nan
    # lst_range and lst_mean_day come from the same MODIS means: NaN together with lst_mean_night
    df.loc[df["lst_mean_night"].isna(), ["lst_range", "lst_mean_day"]] = np.nan

    # A handful of tiles with almost nothing -> tests the "more than half NaN -> dropped" rule
    bad = rng.choice(n, 20, replace=False)
    df.loc[bad, ["lst_mean_night", "lst_range", "albedo", "slope_mean", "slope_std",
                 "mafic_idx", "precip_mm"]] = np.nan

    # Round like a real export would
    for col in ["lst_min_night", "lst_max_day", "lst_range", "lst_mean_night", "lst_mean_day", "precip_mm",
                "slope_mean", "slope_std", "max_sun_elev"]:
        df[col] = df[col].round(2)
    for col in ["albedo", "ndvi", "mafic_idx", "quartz_idx", "dust_aod"]:
        df[col] = df[col].round(3)
    return df


# ---------------------------------------------------------------------------
# 4. Targets (FAKE values, plausible orders of magnitude)
# ---------------------------------------------------------------------------
# Feature names = the dimension ids from CLAUDE.md (temp_range, temp_min, ...).
# Rows "name", "body", "lat", "lon" give the target's metadata for results.json.
# Some values are low/med/high and n/a on purpose, to test those code paths.
TARGET_ROWS = [
    # target, feature, value, unit
    ("jezero", "name",       "Jezero Crater", ""),
    ("jezero", "body",       "Mars",          ""),
    ("jezero", "lat",        "18.4",          "°"),
    ("jezero", "lon",        "77.5",          "°"),
    ("jezero", "temp_range", "75",            "°C"),
    ("jezero", "temp_min",   "-85",           "°C"),
    ("jezero", "albedo",     "0.16",          ""),
    ("jezero", "slope",      "2.5",           "°"),
    ("jezero", "roughness",  "2",             "°"),
    ("jezero", "mafic",      "high",          ""),       # categorical -> 85th percentile of Earth
    ("jezero", "aridity",    "0",             "mm/yr"),
    ("jezero", "dust",       "med",           "AOD"),    # categorical -> 50th percentile
    ("jezero", "sun_angle",  "n/a",           "°"),      # not used for Mars

    ("lunar_south_pole", "name",       "Lunar south pole", ""),
    ("lunar_south_pole", "body",       "Moon",             ""),
    ("lunar_south_pole", "lat",        "-89.9",            "°"),
    ("lunar_south_pole", "lon",        "0",                "°"),
    ("lunar_south_pole", "temp_range", "110",              "°C"),
    ("lunar_south_pole", "temp_min",   "-200",             "°C"),
    ("lunar_south_pole", "albedo",     "0.20",             ""),
    ("lunar_south_pole", "slope",      "8",                "°"),
    ("lunar_south_pole", "roughness",  "high",             "°"),   # categorical -> 85th percentile
    ("lunar_south_pole", "mafic",      "low",              ""),    # anorthositic highlands -> 15th
    ("lunar_south_pole", "aridity",    "0",                "mm/yr"),
    ("lunar_south_pole", "dust",       "n/a",              "AOD"), # no atmosphere
    ("lunar_south_pole", "sun_angle",  "1.5",              "°"),
]


# ---------------------------------------------------------------------------
# 5. Write everything
# ---------------------------------------------------------------------------

def main():
    FAKE_DIR.mkdir(parents=True, exist_ok=True)

    tiles = pick_land_tiles()
    earth = make_features(tiles)
    # Real exports write missing pixels as grid_config.NODATA (-9999): do the same
    n_missing = int(earth.isna().sum().sum())
    earth = earth.fillna(grid_config.NODATA)
    earth.to_csv(FAKE_DIR / "earth_features.csv", index=False)
    print(f"Wrote data/fake/earth_features.csv  ({len(earth):,} tiles, "
          f"{n_missing:,} missing values written as {grid_config.NODATA:g})")

    targets = pd.DataFrame(TARGET_ROWS, columns=["target", "feature", "value", "unit"])
    targets["source"] = "FAKE"
    targets.to_csv(FAKE_DIR / "targets.csv", index=False)
    print(f"Wrote data/fake/targets.csv         ({len(targets)} rows)")

    analogs = pd.DataFrame(KNOWN_ANALOGS,
                           columns=["name", "lat", "lon", "analog_for", "used_for"])
    analogs.to_csv(FAKE_DIR / "known_analogs.csv", index=False)
    print(f"Wrote data/fake/known_analogs.csv   ({len(analogs)} analogs)")

    print("\nREMINDER: these are FAKE values, in data/fake/ (used by: python src/run_all.py --no-merge). "
          "Real inputs live in data/.")


if __name__ == "__main__":
    main()
