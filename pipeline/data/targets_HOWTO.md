<!--
  targets_HOWTO.md — for teammate C.
  Fill in data/targets_TEMPLATE.csv, save it as data/targets.csv, check it, send it.
  Allowed values: a number | low / med / high | n/a.   Every value needs a source.
  Check:  python src/check_csv.py data/targets.csv   (must end with "OK")
-->

# How to fill in `targets.csv`

1. Copy `data/targets_TEMPLATE.csv` to `data/targets.csv`.
2. Fill in the **`value`** and **`source`** columns. Don't change `target`, `feature` or `unit`, and don't add or remove rows.
3. Run the check (from the `pipeline/` folder, with `.venv` active):
   ```bash
   python src/check_csv.py data/targets.csv
   ```
   Fix every `ERROR` until the last line says `OK`. Then send the file to D.

## Allowed values

| `value` | meaning | example |
|---|---|---|
| a number | in the unit given in the `unit` column | `-85`, `0.16` |
| `low` / `med` / `high` | no reliable number, only "compared to Earth". The pipeline uses Earth's 15th / 50th / 85th percentile | `high` |
| `n/a` | does not apply or unknown. That dimension is skipped for this target | `n/a` |

For the `name`, `body`, `lat` and `lon` rows:
- `name`: plain text, e.g. `Jezero Crater`.
- `body`: exactly `Mars` or `Moon`.
- `lat` and `lon`: numbers in degrees.

## Units (already filled in, don't change them)

| feature | unit | what it is |
|---|---|---|
| `lat`, `lon` | ° | site center, degrees (east positive, −180..180) |
| `temp_range` | °C | **MEAN** day–night range = mean day surface temperature − mean night surface temperature (NOT the yearly extreme range). A difference, so °C = K |
| `temp_min` | °C | **MEAN night** surface temperature (not the coldest night of the year), **°C, not Kelvin** (K − 273.15) |

Temperatures: Earth uses multi-year MEAN day and MEAN night land surface temperatures, so give the
same for both targets. Example, Jezero: mean day −19.03 °C, mean night −84.24 °C →
`temp_min` = −84.24, `temp_range` = −19.03 − (−84.24) = 65.21.
| `albedo` | none | 0–1 |
| `slope` | ° | mean slope in degrees (not %) |
| `roughness` | ° | standard deviation of slope, degrees |
| `mafic` | none | mafic (basaltic) mineral index, 0–1, or low/med/high |
| `aridity` | mm/yr | precipitation; Mars and Moon: `0` |
| `dust` | AOD | atmospheric dust optical depth (Mars only) |
| `sun_angle` | ° | maximum sun elevation above the horizon (Moon only) |

## Sources

**Every value needs a source:** a paper (authors, year, DOI), a PDS product ID, or a NASA page URL.
Put it in the `source` column of the same row. If you converted units, say so, e.g. `Smith 2020 doi:… (K→°C)`.
`check_csv.py` reports an error for any value with no source.
