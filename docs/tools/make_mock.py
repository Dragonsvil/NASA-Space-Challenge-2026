"""Generate data/results.mock.json (MOCK data, same shape as the real results.json)."""
import json, math, random, sys

random.seed(42)
OUT = sys.argv[1]

DIMENSIONS = [
    {"id": "temp_range", "label": "Day–night temperature range", "unit": "°C"},
    {"id": "temp_min",   "label": "Minimum temperature",         "unit": "°C"},
    {"id": "albedo",     "label": "Albedo",                      "unit": ""},
    {"id": "slope",      "label": "Slope",                       "unit": "°"},
    {"id": "roughness",  "label": "Roughness",                   "unit": "°"},
    {"id": "mafic",      "label": "Basaltic rock (mafic index)", "unit": ""},
    {"id": "aridity",    "label": "Aridity",                     "unit": "mm/yr"},
    {"id": "dust",       "label": "Dust",                        "unit": "AOD"},
    {"id": "sun_angle",  "label": "Low sun angle",               "unit": "°"},
]
PROFILES = [
    {"id": "rover",   "label": "Rover navigation"},
    {"id": "geology", "label": "Geology / science"},
    {"id": "polar",   "label": "Polar & thermal ops"},
]

# Mock target values (placeholders until the pipeline delivers the real ones).
TARGETS = {
    "jezero": {
        "name": "Jezero Crater", "body": "Mars", "lat": 18.4, "lon": 77.5,
        "values": {"temp_range": 70, "temp_min": -85, "albedo": 0.17, "slope": 3.0,
                   "roughness": 2.5, "mafic": 0.8, "aridity": 0, "dust": 0.5},
        "dims": ["temp_range", "temp_min", "albedo", "slope", "roughness", "mafic", "aridity", "dust"],
        # Where each target value comes from (MOCK citations, the real ones come from the pipeline).
        "sources": {
            "temp_range": "MEDA, Perseverance rover (mock)",
            "temp_min": "MEDA, Perseverance rover (mock)",
            "albedo": "TES bolometric albedo, Mars Global Surveyor (mock)",
            "slope": "MOLA elevation model (mock)",
            "roughness": "MOLA elevation model (mock)",
            "mafic": "CRISM, Mars Reconnaissance Orbiter (mock)",
            "aridity": "No liquid precipitation on Mars (mock)",
            "dust": "MEDA, Perseverance rover (mock)",
        },
    },
    "lunar_south_pole": {
        "name": "Lunar south pole", "body": "Moon", "lat": -89.5, "lon": 0.0,
        "values": {"temp_range": 250, "temp_min": -200, "albedo": 0.12, "slope": 12.0,
                   "roughness": 9.0, "mafic": 0.3, "sun_angle": 1.5},
        "dims": ["temp_range", "temp_min", "albedo", "slope", "roughness", "mafic", "sun_angle"],
        "sources": {
            "temp_range": "Diviner, Lunar Reconnaissance Orbiter (mock)",
            "temp_min": "Diviner, Lunar Reconnaissance Orbiter (mock)",
            "albedo": "LOLA 1064 nm albedo (mock)",
            "slope": "LOLA elevation model (mock)",
            "roughness": "LOLA elevation model (mock)",
            # no source for "mafic": the UI must handle a missing source
            "sun_angle": "Lunar axial tilt, 1.5° (mock)",
        },
    },
}

# "Earth-wide spread" per dimension: a distance this big from the target scores 0.
SPREAD = {
    "jezero": {"temp_range": 70, "temp_min": 110, "albedo": 0.6, "slope": 20, "roughness": 14,
               "mafic": 0.9, "aridity": 1500, "dust": 0.55},
    "lunar_south_pole": {"temp_range": 250, "temp_min": 215, "albedo": 0.7, "slope": 22,
                         "roughness": 15, "mafic": 0.8, "sun_angle": 80},
}

# Profile weights (mock). Dimensions not listed get 0.5.
WEIGHTS = {
    "rover":   {"slope": 3, "roughness": 3, "dust": 2, "albedo": 1, "temp_range": 1},
    "geology": {"mafic": 3, "aridity": 2, "albedo": 1.5},
    "polar":   {"temp_min": 3, "sun_angle": 3, "temp_range": 2, "albedo": 1},
}

# Archetypes: (mean, sd) per dimension. sun_angle is derived from latitude.
ARCH = {
    "hot_desert":  {"temp_range": (32, 5), "temp_min": (-2, 5),   "albedo": (0.33, 0.05), "slope": (3, 2),
                    "roughness": (2.2, 1.2), "mafic": (0.15, 0.08), "aridity": (45, 30),  "dust": (0.38, 0.12)},
    "cold_desert": {"temp_range": (30, 5), "temp_min": (-27, 6),  "albedo": (0.25, 0.04), "slope": (4, 2.5),
                    "roughness": (3, 1.5),   "mafic": (0.22, 0.1),  "aridity": (90, 50),  "dust": (0.22, 0.08)},
    "ice":         {"temp_range": (12, 4), "temp_min": (-58, 10), "albedo": (0.78, 0.05), "slope": (1.5, 1),
                    "roughness": (1, 0.6),   "mafic": (0.03, 0.02), "aridity": (120, 60), "dust": (0.03, 0.01)},
    "polar_rock":  {"temp_range": (14, 4), "temp_min": (-42, 7),  "albedo": (0.22, 0.06), "slope": (9, 4),
                    "roughness": (6.5, 2.5), "mafic": (0.35, 0.12), "aridity": (130, 70), "dust": (0.04, 0.02)},
    "volcanic":    {"temp_range": (14, 5), "temp_min": (-8, 7),   "albedo": (0.12, 0.03), "slope": (9, 4),
                    "roughness": (6.5, 2.5), "mafic": (0.72, 0.1),  "aridity": (600, 300), "dust": (0.1, 0.05)},
    "volc_desert": {"temp_range": (30, 5), "temp_min": (-3, 5),   "albedo": (0.15, 0.03), "slope": (6, 3),
                    "roughness": (4.5, 2),   "mafic": (0.68, 0.1),  "aridity": (70, 40),  "dust": (0.3, 0.1)},
}
CLUSTER = {"hot_desert": 0, "cold_desert": 1, "ice": 2, "polar_rock": 3, "volcanic": 4, "volc_desert": 5}

# (region label, archetype, lat min, lat max, lon min, lon max, number of tiles, hidden-gem candidate)
REGIONS = [
    ("Chile",        "hot_desert",  -27.0, -20.0, -70.0, -68.5, 14, False),
    ("Argentina",    "cold_desert", -27.0, -23.0, -68.0, -66.5, 8,  True),
    ("Bolivia",      "cold_desert", -22.0, -19.5, -68.5, -66.5, 6,  False),
    ("Morocco",      "hot_desert",   29.5,  31.5,  -6.5,  -3.5, 10, False),
    ("Algeria",      "hot_desert",   23.0,  30.0,   0.0,   8.0, 14, False),
    ("Mauritania",   "hot_desert",   19.0,  24.0, -12.0,  -7.0, 8,  False),
    ("Libya",        "hot_desert",   23.0,  28.0,  14.0,  24.0, 12, False),
    ("Egypt",        "hot_desert",   23.0,  28.0,  26.0,  31.0, 8,  False),
    ("Chad",         "volc_desert",  19.5,  21.5,  16.5,  19.0, 7,  True),   # Tibesti
    ("Namibia",      "hot_desert",  -26.5, -21.0,  15.0,  16.5, 10, False),
    ("Saudi Arabia", "hot_desert",   19.0,  23.0,  46.0,  53.0, 10, False),
    ("Saudi Arabia", "volc_desert",  24.0,  27.0,  38.5,  40.5, 7,  True),   # Harrat lava fields
    ("Oman",         "hot_desert",   17.5,  20.5,  54.0,  57.0, 8,  False),
    ("Iran",         "hot_desert",   29.5,  32.0,  57.5,  59.5, 8,  False),  # Dasht-e Lut
    ("Ethiopia",     "volc_desert",  12.0,  14.5,  40.0,  41.5, 6,  True),   # Danakil
    ("India",        "hot_desert",   26.0,  28.0,  70.0,  72.5, 5,  False),  # Thar
    ("Mongolia",     "cold_desert",  42.0,  45.0,  98.0, 108.0, 12, False),  # Gobi
    ("China",        "cold_desert",  37.0,  40.0,  79.0,  87.0, 10, False),  # Taklamakan
    ("China",        "cold_desert",  36.5,  38.5,  90.5,  95.5, 8,  True),   # Qaidam
    ("USA",          "hot_desert",   34.5,  37.0, -117.5, -115.0, 8, False), # Mojave
    ("USA",          "hot_desert",   37.5,  39.0, -111.5, -109.5, 6, False), # Utah
    ("USA",          "volc_desert",  34.75, 35.75, -112.0, -110.75, 4, False), # N. Arizona
    ("USA",          "volcanic",     43.0,  43.75, -114.0, -113.0, 4, False), # Idaho lava
    ("USA",          "volcanic",     19.25, 19.75, -155.75, -155.25, 4, False), # Hawaii
    ("Australia",    "hot_desert",  -28.0, -22.0, 125.0, 137.0, 14, False),
    ("Australia",    "hot_desert",  -22.5, -20.5, 117.5, 120.5, 6,  False),  # Pilbara
    ("Spain",        "volcanic",     29.0,  29.0, -13.75, -13.5, 2, False),  # Lanzarote
    ("Spain",        "hot_desert",   37.5,  37.75, -6.75,  -6.5, 2, False),  # Rio Tinto
    ("Iceland",      "volcanic",     64.25, 65.5, -19.5, -15.5, 10, False),
    ("Russia",       "volcanic",     54.0,  57.0, 159.0, 161.0, 7,  True),   # Kamchatka
    ("Kenya",        "volcanic",      1.5,   4.0,  36.0,  37.5, 5,  False),  # Turkana rift
    ("Canada",       "polar_rock",   75.0,  75.75, -91.0, -84.0, 8, False),  # Devon Island
    ("Canada",       "polar_rock",   79.0,  81.5, -85.0, -70.0, 8,  True),   # Ellesmere
    ("Norway",       "polar_rock",   78.0,  79.25, 14.0,  19.0, 6,  False),  # Svalbard
    ("Greenland",    "ice",          68.0,  78.0, -48.0, -34.0, 12, False),
    ("Greenland",    "polar_rock",   81.0,  82.5, -40.0, -25.0, 5,  True),   # Peary Land
    ("Russia",       "polar_rock",   73.5,  76.0,  95.0, 108.0, 6,  False),  # Taymyr
    ("Antarctica",   "polar_rock",  -78.0, -77.0, 160.0, 163.5, 8,  False),  # Dry Valleys
    ("Antarctica",   "polar_rock",  -85.5, -84.0, 160.0, 178.0, 6,  True),   # Transantarctic Mts
    ("Antarctica",   "ice",         -82.0, -74.0,  20.0, 130.0, 12, False),  # East Antarctic plateau
]

KNOWN_ANALOGS = [
    {"name": "Atacama Desert", "lat": -24.5, "lon": -69.25, "analog_for": "Mars",
     "used_for": "life detection, rover tests"},
    {"name": "McMurdo Dry Valleys", "lat": -77.5, "lon": 162.0, "analog_for": "Mars",
     "used_for": "cold-desert soils, instrument tests"},
    {"name": "Haughton Crater, Devon Island", "lat": 75.4, "lon": -89.8, "analog_for": "Mars",
     "used_for": "crewed mission simulations, impact geology"},
    {"name": "Mars Desert Research Station, Utah", "lat": 38.4, "lon": -110.8, "analog_for": "Mars",
     "used_for": "crew simulations, field geology"},
    {"name": "Rio Tinto", "lat": 37.7, "lon": -6.55, "analog_for": "Mars",
     "used_for": "astrobiology, drilling tests"},
    {"name": "Ibn Battuta Centre, Erfoud", "lat": 31.4, "lon": -4.2, "analog_for": "Mars",
     "used_for": "rover and lander field tests"},
    {"name": "Dhofar Desert", "lat": 18.2, "lon": 55.3, "analog_for": "Mars",
     "used_for": "analog astronaut missions"},
    {"name": "Pilbara", "lat": -21.2, "lon": 119.3, "analog_for": "Mars",
     "used_for": "ancient biosignatures, science-team training"},
    {"name": "Mauna Loa (HI-SEAS)", "lat": 19.6, "lon": -155.5, "analog_for": "Mars",
     "used_for": "long-duration habitat simulations"},
    {"name": "Lanzarote", "lat": 29.0, "lon": -13.65, "analog_for": "Moon",
     "used_for": "astronaut geology training"},
    {"name": "Askja, Iceland", "lat": 65.05, "lon": -16.75, "analog_for": "Moon",
     "used_for": "Apollo astronaut geology training"},
    {"name": "Meteor Crater, Arizona", "lat": 35.03, "lon": -111.02, "analog_for": "Moon",
     "used_for": "Apollo crater geology training"},
    {"name": "Craters of the Moon, Idaho", "lat": 43.4, "lon": -113.5, "analog_for": "Moon",
     "used_for": "Apollo training, lava-terrain research"},
]


def snap(x):
    """Snap a coordinate to the 0.25° tile grid."""
    return round(x * 4) / 4


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


LIMITS = {"temp_range": (2, 80), "temp_min": (-89, 30), "albedo": (0.04, 0.9), "slope": (0, 35),
          "roughness": (0, 25), "mafic": (0, 1), "aridity": (0, 3000), "dust": (0.01, 1.2), "sun_angle": (0, 90)}
DECIMALS = {"temp_range": 1, "temp_min": 1, "albedo": 2, "slope": 1, "roughness": 1, "mafic": 2,
            "aridity": 0, "dust": 2, "sun_angle": 1}


def make_values(arch, lat):
    values = {}
    for dim, (mean, sd) in ARCH[arch].items():
        values[dim] = random.gauss(mean, sd)
    # Rough mean noon sun elevation from latitude.
    values["sun_angle"] = 90 - abs(lat) + random.gauss(0, 1.5)
    for dim in values:
        lo, hi = LIMITS[dim]
        v = round(clamp(values[dim], lo, hi), DECIMALS[dim])
        values[dim] = int(v) if DECIMALS[dim] == 0 else v
    return values


def dim_score(target_id, dim, value):
    if value is None:
        return None
    d = abs(value - TARGETS[target_id]["values"][dim])
    return round(100 * clamp(1 - d / SPREAD[target_id][dim], 0, 1))


def make_scores(values):
    scores = {}
    for tid, target in TARGETS.items():
        dims = {d: dim_score(tid, d, values.get(d)) for d in target["dims"]}
        scores[tid] = {}
        for p in PROFILES:
            num = den = 0
            for d, s in dims.items():
                if s is None:
                    continue
                w = WEIGHTS[p["id"]].get(d, 0.5)
                num += w * s
                den += w
            total = round(num / den) if den else None
            scores[tid][p["id"]] = {"total": total, "dims": dict(dims)}
    return scores


# ---- build the tiles -------------------------------------------------------
tiles = {}  # (lat, lon) -> dict
for region, arch, la0, la1, lo0, lo1, n, gem in REGIONS:
    tries = 0
    made = 0
    while made < n and tries < 200:
        tries += 1
        key = (snap(random.uniform(la0, la1)), snap(random.uniform(lo0, lo1)))
        if key in tiles:
            continue
        tiles[key] = {"region": region, "arch": arch, "gem_candidate": gem, "known_analog": None}
        made += 1

# Make sure each known analog has its own tile.
for a in KNOWN_ANALOGS:
    key = (snap(a["lat"]), snap(a["lon"]))
    if key not in tiles:
        # Reuse the region/archetype of the closest existing tile.
        near = min(tiles, key=lambda k: (k[0] - key[0]) ** 2 + (k[1] - key[1]) ** 2)
        tiles[key] = dict(tiles[near])
    tiles[key]["known_analog"] = a["name"]
    tiles[key]["gem_candidate"] = False

sites = []
for (lat, lon), t in sorted(tiles.items()):
    values = make_values(t["arch"], lat)
    # ~4% missing values
    for dim in list(values):
        if random.random() < 0.04:
            values[dim] = None
    # Tile id from its grid position (row * 1440 + column).
    tile_id = int((lat + 90) * 4) * 1440 + int((lon + 180) * 4)
    cluster = CLUSTER[t["arch"]] if random.random() < 0.85 else random.randint(0, 7)
    sites.append({
        "id": f"t_{tile_id}", "lat": lat, "lon": lon, "region": t["region"],
        "values": values, "scores": make_scores(values),
        "cluster": cluster, "hidden_gem": False, "known_analog": t["known_analog"],
        "_gem": t["gem_candidate"],
    })

# One tile with every value missing (worst case for the UI).
empty = next(s for s in sites if s["region"] == "Greenland" and not s["known_analog"])
empty["values"] = {d: None for d in empty["values"]}
empty["scores"] = make_scores(empty["values"])
empty["_gem"] = False


def best(s):
    totals = [p["total"] for t in s["scores"].values() for p in t.values() if p["total"] is not None]
    return max(totals) if totals else -1


# Hidden gems: the best tile of each "unstudied" candidate area.
seen = set()
for s in sorted(sites, key=best, reverse=True):
    area = (s["region"], round(s["lat"] / 6), round(s["lon"] / 12))
    if s["_gem"] and area not in seen and len(seen) < 8:
        s["hidden_gem"] = True
        seen.add(area)

# Like the real file: a tile outside a target's top list has no scores for it.
lunar = sorted(sites, key=lambda s: s["scores"]["lunar_south_pole"]["rover"]["total"] or 0)
for s in lunar[: len(sites) // 7]:
    if not s["hidden_gem"]:
        s["scores"]["lunar_south_pole"] = {}

for s in sites:
    del s["_gem"]

# ---- global rank of the known analogs --------------------------------------
# The real pipeline scores EVERY land tile of Earth and tells us, for each known analog,
# its rank among all of them. The mock only has a few hundred tiles, so the global rank
# is made up here with a simple curve: the further a score is below the best score of
# that target x profile, the worse the rank.
# Because it is made up, it does not match the order of the mock `sites` exactly.
TILES_SCORED = {"jezero": 200000, "lunar_south_pole": 200000}   # mock: same order of magnitude as the real grid
BEST_SHARE = 0.004  # a tile with the best score is in the top 0.4% of Earth
RANK_CURVE = 7      # every 7 points below the best score, about 2.7 times further down the ranking

# Known analogs whose tile is NOT delivered in `sites` (to test that case in the UI):
# Rio Tinto is excluded before scoring (vegetated), McMurdo is scored but too far down the ranking.
NOT_IN_SITES = {"Rio Tinto", "McMurdo Dry Valleys"}

# Vegetated tiles (NDVI > 0.3) are excluded before scoring: the analog then has
# "scores": null and a "tile_note" that says why.
EXCLUDED = {"Rio Tinto": "excluded: vegetated tile (NDVI 0.78)"}
# A scored analog can also carry a note.
TILE_NOTES = {"Pilbara": "nearest valid tile, 12 km away"}

site_by_analog = {s["known_analog"]: s for s in sites if s["known_analog"]}
analog_values = dict((name, make_scores(s["values"])) for name, s in site_by_analog.items())
for a in KNOWN_ANALOGS:
    if a["name"] in EXCLUDED:
        a["scores"] = None
        a["tile_note"] = EXCLUDED[a["name"]]
        continue
    if a["name"] in TILE_NOTES:
        a["tile_note"] = TILE_NOTES[a["name"]]
    a["scores"] = {}
    for tid in TARGETS:
        a["scores"][tid] = {}
        n_tiles = TILES_SCORED[tid]
        for p in PROFILES:
            best_total = max(s["scores"][tid][p["id"]]["total"] or 0 for s in sites if s["scores"][tid])
            total = analog_values[a["name"]][tid][p["id"]]["total"]
            if total is None:
                a["scores"][tid][p["id"]] = {"total": None, "global_rank": None, "percentile": None}
                continue
            # fraction of Earth that scores better (between 0 and 1)
            share = BEST_SHARE * math.exp((best_total - total) / RANK_CURVE)
            rank = int(clamp(round(share * n_tiles), 1, n_tiles))
            a["scores"][tid][p["id"]] = {
                "total": total,
                "global_rank": rank,
                "percentile": round(100 * rank / n_tiles, 2),      # "top X% of Earth"
            }

sites = [s for s in sites if s["known_analog"] not in NOT_IN_SITES]

# ---- last details of the real file -----------------------------------------
# Until Sunday the pipeline has no clustering yet: cluster is null and no tile is a hidden gem.
# Set this to True to get mock hidden gems back (to work on the stars).
GEMS_READY = False
if not GEMS_READY:
    for s in sites:
        s["cluster"] = None
        s["hidden_gem"] = False

# region is "Country" or "Country, near Town". A second random generator is used here,
# so the numbers above stay the same as before.
NEAR = {
    "Chile": "San Pedro de Atacama", "Morocco": "Erfoud", "Oman": "Thumrait", "Iceland": "Mývatn",
    "Canada": "Resolute Bay", "Norway": "Longyearbyen", "Namibia": "Lüderitz", "Mongolia": "Dalanzadgad",
    "Antarctica": "McMurdo Station", "Saudi Arabia": "Al-Madinah al-Munawwarah",
}
rng_region = random.Random(7)
for s in sites:
    if s["region"] in NEAR and rng_region.random() < 0.5:
        s["region"] = s["region"] + ", near " + NEAR[s["region"]]

data = {
    "meta": {"generated": "2026-11-14T12:00:00Z", "tiles_scored": TILES_SCORED,
             "dimensions": DIMENSIONS,
             # the real file also gives the weights of each profile (the site does not use them)
             "profiles": [dict(p, weights=WEIGHTS[p["id"]]) for p in PROFILES]},
    "targets": TARGETS,
    "sites": sites,
    "known_analogs": KNOWN_ANALOGS,
}

# One site per line: readable and small.
with open(OUT, "w", encoding="utf-8") as f:
    head = {k: v for k, v in data.items() if k != "sites"}
    text = json.dumps(head, ensure_ascii=False, indent=2)
    site_lines = ",\n".join("    " + json.dumps(s, ensure_ascii=False) for s in sites)
    # insert "sites" before "known_analogs"
    marker = '  "known_analogs"'
    text = text.replace(marker, '  "sites": [\n' + site_lines + "\n  ],\n" + marker)
    f.write(text + "\n")

print(len(sites), "sites,", sum(s["hidden_gem"] for s in sites), "hidden gems,",
      sum(1 for s in sites if s["known_analog"]), "analog tiles")
for tid in TARGETS:
    for p in PROFILES:
        ts = sorted(s["scores"][tid][p["id"]]["total"] for s in sites
                    if s["scores"][tid] and s["scores"][tid][p["id"]]["total"] is not None)
        print(tid, p["id"], "n", len(ts), "min", ts[0], "median", ts[len(ts) // 2], "max", ts[-1])

print("known analogs: top X% of Earth's barren land")
for a in KNOWN_ANALOGS:
    if a["scores"] is None:
        print(" ", a["analog_for"], a["name"].ljust(36), a["tile_note"])
        continue
    print(" ", a["analog_for"], a["name"].ljust(36),
          " ".join(f"{tid[:3]}/{p['id'][:3]}={a['scores'][tid][p['id']]['percentile']}" for tid in TARGETS for p in PROFILES))
