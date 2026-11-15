# Planetary Analog Finder

**We scan all of Earth's barren land to find the best places to prepare for the Moon and Mars, and we show where each analogy works and where it breaks.**

Team **FAKERS** · NASA Space Apps Challenge 2026 · [Live site](https://dragonsvil.github.io/NASA-Space-Challenge-2026) 

> Open the live site in a private window to see the intro and Orbi's greeting like a first-time visitor.

---

## The problem

Analog research (testing rovers, instruments and procedures on Earth before sending them to the Moon or Mars) concentrates on a handful of famous sites. Some of the best test sites may never have been looked at. And no place on Earth matches everything about the Moon or Mars, so a good analog must also say where it fails.

## What it does

Planetary Analog Finder is a search engine for Earth analogs. Pick a target and a mission, and it returns a ranked, explained list of test sites on Earth.

- **Targets:** Jezero Crater (Mars) and the lunar south pole.
- **Method:** Earth's barren land is split into 0.25° tiles (about 28 km). Each tile is compared to a target dimension by dimension, in physical units (°C, degrees, albedo), never by z-scoring Earth and Mars separately. Each dimension gets a 0-100 closeness score.
- **Mission profiles:** three profiles weight the dimensions into a total score: _rover navigation_, _geology / science_, and _polar & thermal ops_.
- **Discovery:** K-Means clustering finds **hidden gems**: high-scoring sites in the same terrain family as known analogs, but not studied as analogs. 15 per target.
- **Honest limits:** every site card has a "where the analogy breaks" section (gravity, atmosphere, radiation, plus any dimension where the site scores low).
- **Orbi:** an assistant that answers data questions straight from our results, and uses an open AI model (Llama, on Cloudflare Workers AI) for everything else.

## Does it work? Validation

Validated against sites that scientists already use as analogs (details in [`pipeline/validation.md`](pipeline/validation.md)):

- For the Jezero Crater target (rover navigation profile), 3 of the 4 rover analogs we could score rank in the top 7% of Earth's barren land: **Atacama (0.6%)**, **Mojave (2.7%)** and **Haughton Crater (6.6%)**. A fourth, Rio Tinto, is excluded because its tile is vegetated.
- **Honest failure:** polar analogs fail on Jezero's 65 °C day-night swing. Earth's poles cannot reproduce it. This is a real physical limit, and the tool shows it.

Only 1 known analog could be scored for the lunar south pole, so **Moon results are not yet validated**.

## Dimensions and data sources

Everything is compared in physical units. Earth values come from Google Earth Engine; target values come from published papers and planetary data products.

|Dimension|Earth data|Target data|
|---|---|---|
|Temperature (night minimum, day maximum, day-night range)|MODIS land surface temperature|LRO Diviner (Moon), Mars Odyssey THEMIS (Mars)|
|Albedo|MODIS MCD43|Published LRO / TES albedo|
|Slope and roughness|Copernicus DEM GLO-30, resampled to about 500 m, slope mean and standard deviation per tile|LRO LOLA (Moon), Mars Global Surveyor MOLA (Mars)|
|Mineralogy (mafic and quartz indices)|ASTER Global Emissivity Dataset v3 (`NASA/ASTER_GED/AG100_003`), indices from Ninomiya et al. (2005)|Published geology of each site|
|Aridity and vegetation|GPM IMERG precipitation, ERA5-Land precipitation, MODIS NDVI|0 for both targets|
|Low sun angle (Moon only)|Computed from latitude: min(90, 90 - abs(lat) + 23.44)|Lunar pole: Sun stays near the horizon|
|Dust|Optional aerosol dimension (not scored for Jezero: no data)|n/a|

Full list with references:

- **Copernicus DEM GLO-30**, ESA / European Commission. _Contains modified Copernicus data._ Earth Engine ID `COPERNICUS/DEM/GLO30` (marked deprecated in Earth Engine, superseded by `COPERNICUS/DEM/GLO30_2024_1`; it still worked and gave sensible results).
- **ASTER Global Emissivity Dataset v3 (100 m)**, NASA / METI / AIST / Japan Space Systems and the US/Japan ASTER Science Team, distributed by NASA LP DAAC. Hulley et al. (2015), _Geophysical Research Letters_ 42, 7966-7976.
- **Mineral index formulas** (mafic = band 12 / band 13; quartz = band 11² / (band 10 × band 12)): Ninomiya, Fu & Cudahy (2005), _Remote Sensing of Environment_ 99, 127-139.
- **MODIS** land surface temperature, albedo (MCD43) and NDVI, NASA.
- **GPM IMERG** precipitation, NASA / JAXA. **ERA5-Land**, ECMWF / Copernicus Climate Change Service.
- **LRO Diviner and LOLA** (Moon), **Mars Odyssey THEMIS** and **Mars Global Surveyor MOLA** (Mars), NASA Planetary Data System.
- **Google Earth Engine:** Gorelick et al. (2017), _Remote Sensing of Environment_ 202, 18-27.
- **Map imagery:** NASA GIBS and Esri. Satellite imagery in deep dives: NASA Worldview / Copernicus Sentinel-2 (credited where shown).
- **Orbi's AI:** Llama model on Cloudflare Workers AI.

## How it was built

```
Earth Engine data -> 0.25 degree grid of land tiles (A: climate, B: terrain and geology)
  -> merge into one table of Earth features
  -> per-dimension closeness score vs. each target (percentile of the gap, in real units)
  -> weighted total per mission profile
  -> K-Means clustering -> hidden-gem candidates
  -> validation against known analogs
  -> static website (Leaflet map + Plotly charts) with site cards and Orbi
```

### Shared grid

All Earth features use one grid defined in `grid_config.py`: 0.25°, 1440 columns by 720 rows, origin at the top-left (-180, 90). `tile_id = row * 1440 + col` (row 0 is the northernmost row); `lat` and `lon` in the CSVs are tile centres. Land tiles are those with `land_frac >= 0.5` (`land_tiles.csv`).

### Scoring

For each tile `t` and dimension `d`:

```
gap(t, d)   = | earth_value(t, d) - target_value(d) |          (real units)
score(t, d) = 100 * (1 - percentile_rank of gap(t, d) among all Earth tiles)
total(t, p) = sum_d w(p, d) * score(t, d)  /  sum_d w(p, d)     (profile p)
```

A score of 95 for a dimension means "this tile is in the top 5% closest on Earth for that dimension". Weights per mission profile and the validation results are documented in [`pipeline/`](https://claude.ai/chat/pipeline/).

## Repository layout
```
data               climate layers exports
data_gee_A/        climate layers .py files (temperature, albedo, NDVI, precipitation, land mask)
data_gee_B/        terrain and geology .py files (slope, roughness, mafic/quartz indices)
docs/              website folder
pipeline/          scoring, clustering, validation (validation.md)
LICENSE
README.md
grid_config.py
```

## How to reproduce

You need Python 3, a free (non-commercial) [Google Earth Engine](https://earthengine.google.com/) account with a Cloud project, and the packages `earthengine-api`, `pandas`, `numpy`, `scikit-learn`.

```bash
pip install earthengine-api geemap pandas numpy scikit-learn
earthengine authenticate
```

**1. Climate layers.** Set your Earth Engine project ID in the scripts, then from the folder that contains `grid_config.py`:

```bash
cd data_gee_A
python a_export_climate.py lst
python a_export_climate.py albedo
python a_export_ndvi_precip.py
python a_merge_csv.py
python a_sanity_check.py
```

**2. Terrain and geology.** Copy `grid_config.py` and `land_tiles.csv` into `data_gee_B/`, set your Earth Engine project ID in `b_export_features.py` (`PROJECT`), then:

```bash
cd data_gee_B
python b_direct.py terrain test     # quick check on a small Atacama block
python b_direct.py terrain run      # whole world, about 15 minutes
python b_direct.py geology run      # whole world, about 1 hour
python B3_postprocess.py ./exports land_tiles.csv
```

`B3_postprocess.py` merges the two CSVs, keeps land tiles only, adds the max sun elevation, blanks impossible mineral values and writes `B_features.csv`. (`b_export_features.py` holds the Earth Engine image definitions that `b_direct.py` reuses; it can also export to Google Drive with `... run`, which is slower.)

**3. Scoring, clustering, validation (D).**

> TODO (D): list the exact commands and output files, for example the script that builds `results.csv` and the one that writes `validation.md`.

**4. Website.**

The website is static (HTML, CSS, JavaScript): no build, no install. From the repo root:

```bash
cd docs
python3 -m http.server 8000
```

Then open http://localhost:8000. Opening `index.html` directly does not work: the browser blocks loading `data/results.json` from a local file. The site reads `docs/data/results.json` from step 3; set `USE_MOCK_DATA = true` in `docs/js/app.js` to use the mock file instead. Map tiles and Orbi's AI answers need an internet connection.

Deployment: GitHub Pages serves the `docs/` folder of the `main` branch (Settings → Pages → `main` / `/docs`). Every push to `main` redeploys the site within 1–2 minutes: https://dragonsvil.github.io/NASA-Space-Challenge-2026/

**5. Orbi's AI relay.** 

`relay/worker.js` is a Cloudflare Worker: create a Worker, paste the file, and add a Workers AI binding named `AI`. No API key is stored in the code.

### Method notes for terrain and geology

- Elevation is resampled to about 500 m (the scale of Mars MOLA data) using Earth Engine's image pyramid, slope is computed at that scale, then the mean and standard deviation are taken per 0.25° tile.
- ASTER indices are computed from emissivity at 100 m, then averaged per tile in two stages (Earth Engine limits the pixels per output cell).
- Terrain data stops at about 83.4°N, so a few thousand land tiles in the far Arctic and some small islands have no slope values.

## Limits and next steps

|Limit|Next step|
|---|---|
|Tiles are 0.25° (about 28 km), coarse next to a single crater or valley|Re-score the hidden gems and top sites at 30 m with the same method|
|Few known Moon analogs to validate against (1 scored for the lunar south pole)|Add more lunar analogs and polar field sites; Moon results are not yet validated|
|Dust not scored for Jezero (no data); rock-type data missing for many tiles (ASTER gaps, for example over ice)|Add an aerosol dataset and a second mineralogy source|
|Earth cannot reproduce Moon/Mars gravity, atmosphere or radiation|Stated on every site card; the tool ranks what Earth can match|
|Profile weights are expert choices, not learned|Publish them and let users adjust them in a future version|
|No subsurface, caves or biology dimensions yet|Add lava-tube and cave databases, and extremophile data|

## Super Intelligence (SI) / AI use

Stated as the NASA Space Apps rules ask (SI-generated code acknowledged, SI-generated images labelled):

- **Code:** AI coding assistants helped write the website code (`docs/`).
- **Artwork:** Orbi, the website's mascot, is an SI-generated (AI) character ("SI" = Super Intelligence, the word the NASA Space Apps rules use for AI tools). He is labelled "SI-generated (AI) character" on the site (chat header and button tooltip).
- **Orbi's answers:** his open answers come from an AI model, Llama 4 Scout on Cloudflare Workers AI. His short ready-made answers are written in `docs/js/orbi.js` and read from `docs/data/results.json`.

The same note is at the top of `docs/js/orbi.js`, `docs/css/orbi.css` and `docs/js/app.js`, and in the site's "About · AI use" box (link in the map credits).

## Team

Team **FAKERS**


## Acknowledgements and disclaimer

Data from NASA, ESA / Copernicus, JAXA, ECMWF and other agencies as credited above. This project was made for the NASA Space Apps Challenge 2026. It is **not affiliated with or endorsed by NASA**, and no NASA logo is used.

## License

Code released under the MIT License (see LICENSE). Libraries in docs/vendor/ keep their own licenses. Data from NASA, ESA and other providers under their own terms.
