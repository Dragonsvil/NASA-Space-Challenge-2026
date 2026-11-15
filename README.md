# Planetary Analog Finder

**We scan all of Earth's barren land to find the best places to prepare for the Moon and Mars, and we show where each analogy works and where it breaks.**

Team **FAKERS** · NASA Space Apps Challenge 2026 

**Links:** [Live site](https://dragonsvil.github.io/NASA-Space-Challenge-2026) · [Presentation slides](https://drive.google.com/file/d/1xE9jdfPoWZHd45voK8GhebjFmcU7uMux/view?usp=sharing) 

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

We ranked sites that scientists already use as analogs, with a rule fixed before looking at the results and weights that were **not** tuned on them (table and limitations:  [`pipeline/README.md`](pipeline/README.md#validation)).

- Jezero Crater, rover navigation profile: 3 of the 4 rover analogs we could score rank in the top 7% of Earth's barren land: **Atacama (0.6%)**, **Mojave (2.7%)** and **Haughton Crater (6.6%)**. The fourth, University Valley, does not reach the top 10%; Kilauea is excluded because its tile is vegetated.
- Across all 10 known analogs and every profile they are mapped to, 3 reach the top 10% on at least one (Rio Tinto and Kilauea are excluded as vegetated). By our own success rule (more than half), the method does not pass overall, and for the Moon none of the 3 analogs on our list passes (2 could be scored; Kilauea’s tile is excluded as vegetated), so Moon results are not yet validated.
- **Honest failure:** polar analogs fail on Jezero's 65 °C day-night swing, which Earth's polar sites (1-2 °C) cannot reproduce. This is a real physical limit, and the tool shows it.


## Data sources

Earth values come from Google Earth Engine; target values come from published papers and planetary data products. Each target value and its source is in `pipeline/data/targets.csv` and listed in [`pipeline/README.md`](pipeline/README.md#target-values).

- **Copernicus DEM GLO-30**, ESA / European Commission (_Contains modified Copernicus data._): slope and roughness. Earth Engine ID `COPERNICUS/DEM/GLO30` (marked deprecated, superseded by `COPERNICUS/DEM/GLO30_2024_1`; it still worked and gave sensible results).
- **ASTER Global Emissivity Dataset v3 (100 m)**, NASA / METI / AIST / Japan Space Systems and the US/Japan ASTER Science Team, via NASA LP DAAC (Hulley et al. 2015, _GRL_ 42, 7966-7976): mafic index, formula from Ninomiya, Fu & Cudahy (2005), _Remote Sensing of Environment_ 99, 127-139.
- **MODIS** land surface temperature, albedo (MCD43), vegetation indices and land cover, NASA.
- **GPM IMERG**, NASA / JAXA, and **ERA5-Land**, ECMWF / Copernicus Climate Change Service: precipitation.
- **Mars and Moon targets:** LRO Diviner and LOLA, Mars Odyssey THEMIS, Mars Global Surveyor MOLA and TES, Lunar Prospector GRS (NASA Planetary Data System).
- **Natural Earth** country borders; **GeoNames** (via `reverse_geocoder`) for region names.
- **Google Earth Engine:** Gorelick et al. (2017), _Remote Sensing of Environment_ 202, 18-27.
- **Map imagery:** NASA GIBS and Esri. Satellite imagery in deep dives: NASA Worldview / Copernicus Sentinel-2 (credited where shown).
- **Orbi's AI:** Llama model on Cloudflare Workers AI.

## How it was built

```
Earth Engine data -> 0.25 degree grid of land tiles (A: climate, B: terrain and geology)
  -> merge into one table of Earth features, with cleaning rules
  -> filters: land, no vegetation (NDVI <= 0.3)
  -> per-dimension closeness score vs. each target (percentile of the gap, in real units)
  -> weighted total per mission profile -> global rank
  -> K-Means clustering -> hidden-gem candidates
  -> validation against known analogs
  -> static website (Leaflet map + Chart.js charts) with site cards and Orbi
```

The full method (filters, weights, completeness rules, hidden-gem criteria, data cleaning, target values) is documented in **[`pipeline/README.md`](pipeline/README.md)**.


## Repository layout
```
data               climate layers exports
data_gee_A/        climate layers .py files (temperature, albedo, NDVI, precipitation, land mask)
data_gee_B/        terrain and geology .py files (slope, roughness, mafic/quartz indices)
docs/              website folder
pipeline/          scoring, clustering, validation (see pipeline/README.md)
relay/             Cloudflare Worker for Orbi's AI answers
LICENSE            MIT license
README.md
grid_config.py     shared 0.25° grid definition (tile_id = row * 1440 + col, row 0 = north)
```

## How to reproduce

You need Python 3, a free (non-commercial) [Google Earth Engine](https://earthengine.google.com/) account with a Cloud project, and the packages `earthengine-api`, `pandas`, `numpy`, `scikit-learn`.

```bash
pip install earthengine-api geemap pandas numpy scikit-learn
earthengine authenticate
```

**1. Climate layers.** 

Set your Earth Engine project ID in the scripts, then copy `grid_config.py` into `data_gee_A/` :

```bash
cd data_gee_A
python a_export_climate.py land
python a_export_cliamte.py lst
python a_export_climate.py albedo
python a_export_ndvi_precip.py ndvi
python a_export_ndvi_precip.py precip
python a_merge_csv.py
python a_sanity_check.py
```
To check the status : 
```bash
python a_export_climate.py status
python a_export_ndvi_precip.py status
```

**2. Terrain and geology.** 

Copy `grid_config.py` and `land_tiles.csv` into `data_gee_B/`, set your Earth Engine project ID in `b_export_features.py` (`PROJECT`), then:

```bash
cd data_gee_B
python b_direct.py terrain test     # quick check on a small Atacama block
python b_direct.py terrain run      # whole world, about 15 minutes
python b_direct.py geology run      # whole world, about 1 hour
python B3_postprocess.py ./exports land_tiles.csv
```

`B3_postprocess.py` merges the two CSVs, keeps land tiles only, adds the max sun elevation, blanks impossible mineral values and writes `B_features.csv`. (`b_export_features.py` holds the Earth Engine image definitions that `b_direct.py` reuses; it can also export to Google Drive with `... run`, which is slower). Slope is computed at about 500 m scale (the scale of Mars MOLA data), then averaged per 0.25° tile.

**3. Scoring, clustering, validation.** 

From the `pipeline/` folder:

```bash
cd pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/run_all.py        # merge A + B, check inputs, score, cluster, validate, export
```

Inputs, outputs and options (such as testing on fake data) are described in [`pipeline/README.md`](pipeline/README.md#how-to-run).

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


## Main limits and next steps

The complete list is in  [`pipeline/README.md`](pipeline/README.md#known-limitations).

|Limit|Next step|
|---|---|
|Tiles are 0.25° (about 28 km), coarse next to a single crater or valley|Re-score the hidden gems and top sites at 30 m with the same method|
|Few known Moon analogs to validate against: 3 on our list, 2 could be scored, and none reaches the top 10% (best: Haughton Crater, top 17.6% for lunar rover operations); overall, only 3 of 10 known analogs reach the top 10%|Add more lunar analogs and polar field sites; Moon results are not yet validated|
|Dust not scored (no data); rock-type data missing for many tiles (ASTER gaps, for example over ice, including Iceland and Antarctica)|Add an aerosol dataset and a second mineralogy source|
|Earth cannot reproduce Moon/Mars gravity, atmosphere or radiation|Stated on every site card; the tool ranks what Earth can match|
|Profile weights were chosen by the team before seeing the results, not learned or tuned|Publish them and let users adjust them in a future version|

## Super Intelligence (SI) / AI use

Stated as the NASA Space Apps rules ask (SI-generated code acknowledged, SI-generated images labelled):

- **Code:** AI coding assistants helped write the website code (`docs/`) and the data scripts.
- **Artwork:** Orbi, the website's mascot, is an SI-generated (AI) character ("SI" = Super Intelligence, the word the NASA Space Apps rules use for AI tools). He is labelled "SI-generated (AI) character" on the site (chat header and button tooltip).
- **Orbi's answers:** his open answers come from an AI model, Llama 4 Scout on Cloudflare Workers AI. His short ready-made answers are written in `docs/js/orbi.js` and read from `docs/data/results.json`.

The same note is at the top of `docs/js/orbi.js`, `docs/css/orbi.css` and `docs/js/app.js`, and in the site's "About · AI use" box (link in the map credits).

## Team

Team **FAKERS** :
- Khawla EL HAMDI
- Malak BITANE
- Fatima-Zahra EL MAGANA
- Mohamed Reda ABDI
- Mohamed Amine MELLATI
- Ghassan MOUJIB


## Acknowledgements and disclaimer

Data from NASA, ESA / Copernicus, JAXA, ECMWF and other agencies as credited above. This project was made for the NASA Space Apps Challenge 2026. It is **not affiliated with or endorsed by NASA**, and no NASA logo is used.

## License

Code released under the MIT License (see LICENSE). Libraries in docs/vendor/ keep their own licenses. Data from NASA, ESA and other providers under their own terms.
