# Planetary Analog Finder — data pipeline

Scores every 0.25° Earth land tile against Jezero Crater (Mars) and the lunar south pole,
clusters tiles to find "hidden gems", validates against known analogs, and writes
`out/results.json` for the website. Full method and the results.json contract: see `CLAUDE.md`.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Input files (`data/`)
| file                  | provided by | content                                    |
|-----------------------|-------------|--------------------------------------------|
| `earth_features.csv`  | A and B     | one row per land tile, physical units      |
| `targets.csv`         | C           | Jezero + lunar south pole values (long)    |
| `known_analogs.csv`   | C           | known Earth analog sites                   |

Until real data arrives, generate fake data:
```bash
python src/make_fake_data.py
```

**Before sending a file, check it:**
```bash
python src/check_csv.py data/earth_features.csv
```
It checks the column names, the `tile_id` format (tile center, e.g. `-24.125_-69.875`),
units (°C not Kelvin, albedo 0–1, slope 0–90°), and prints NaN % and min/max per column.
Exit code 0 = OK, 1 = errors to fix.

## Run
```bash
python src/run_all.py
```
