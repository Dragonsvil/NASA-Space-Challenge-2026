"""
Robust temperature values for the lunar south pole row set, computed from the cache that
diviner_temps.py already filled (diviner_cache/box_*.npy). Nothing is downloaded.

Why: the raw minimum (14.9 K) is a single noisy 240 m bin, below anything published.
So lst_min_night = 0.1st percentile of all night bins in the box, and
   lst_max_day   = 99.9th percentile of all day bins (same robustness on the hot side).
The raw min/max are kept in the source text so nothing is hidden.

Run from pipeline\\src:   python finalize_temps.py
"""
import glob, re, json
import numpy as np
import pandas as pd

CACHE = "diviner_cache"
CSV_IN = CSV_OUT = "targets_moon_south_pole.csv"
P_LOW, P_HIGH = 0.1, 99.9            # percentiles used for the robust min / max
K = 273.15
DAY = range(25, 73)                  # 06-18 h local time
files = glob.glob(f"{CACHE}/box_*.npy")
if not files:
    raise SystemExit("No cache files found: run diviner_temps.py first (from this folder).")

night, day, day_means, night_means = [], [], [], []
season_means = {}
for f in files:
    n = int(re.search(r"_(\d+)\.npy$", f).group(1))
    a = np.load(f)
    t = a[a[:, 0] >= 1.0, 0]
    if t.size == 0:
        continue
    (day if n in DAY else night).append(t)
    season = 'SUM' if '_SUM_' in f else 'WIN'
    season_means.setdefault((season, 'day' if n in DAY else 'night'), []).append(t.mean())
    (day_means if n in DAY else night_means).append(t.mean())

night, day = np.concatenate(night), np.concatenate(day)
res = {
    "files": len(files),
    "night_raw_min_C": round(night.min() - K, 1),
    "night_p%s_C" % P_LOW: round(np.percentile(night, P_LOW) - K, 1),
    "night_p1_C": round(np.percentile(night, 1) - K, 1),
    "day_raw_max_C": round(day.max() - K, 1),
    "day_p%s_C" % P_HIGH: round(np.percentile(day, P_HIGH) - K, 1),
    "day_p99_C": round(np.percentile(day, 99) - K, 1),
    "lst_range_C_mean_day_minus_mean_night": round(float(np.mean(day_means) - np.mean(night_means)), 1),
    "mean_day_C": round(float(np.mean(day_means)) - K, 1),
    "mean_night_C": round(float(np.mean(night_means)) - K, 1),
    **{f"mean_{k[1]}_{k[0]}_C": round(float(np.mean(v)) - K, 1) for k, v in sorted(season_means.items())},
    "spread_C_max_minus_min_robust": round(float(np.percentile(day, P_HIGH) - np.percentile(night, P_LOW)), 1),
}
print(json.dumps(res, indent=2))

df = pd.read_csv(CSV_IN, keep_default_na=False)
df["value"] = df["value"].astype(object)
base = ("LRO Diviner Polar Cumulative Products (diurnal, south pole), bolometric temperature, 240 m bins, "
        "28x28 km box centred on pole, summer+winter pooled, nadir obs. 5 Jul 2009 - 17 Feb 2019, "
        "every 8th 0.25 h local-time bin; computed with diviner_temps.py + finalize_temps.py")
rows = {
    "lst_min_night": (res["night_p%s_C" % P_LOW],
                      f"{base}; robust: {P_LOW}th percentile of night bins (raw minimum {res['night_raw_min_C']} C is a noise spike)"),
    "lst_max_day": (res["day_p%s_C" % P_HIGH],
                    f"{base}; robust: {P_HIGH}th percentile of day bins (raw maximum {res['day_raw_max_C']} C)"),
    "lst_range": (res["lst_range_C_mean_day_minus_mean_night"],
                  f"{base}; mean(day) - mean(night) over the box (small because the Sun stays near the horizon); "
                  f"max-min spread is {res['spread_C_max_minus_min_robust']} C"),
}
for feat, (val, src) in rows.items():
    m = (df.target == "moon_south_pole") & (df.feature == feat)
    df.loc[m, "value"] = val
    df.loc[m, "source"] = src
mean_src = (base + "; mean over all bins in the box, then mean over the local-time bins; summer+winter pooled "
            "(seasonal means are in diviner_temps json/printout); day = local time 06-18 h, night = 18-06 h, "
            "NOT the same as sunlit/unlit near the pole")
new_rows = [("moon_south_pole", "lst_mean_day", res["mean_day_C"], "degC", mean_src),
            ("moon_south_pole", "lst_mean_night", res["mean_night_C"], "degC", mean_src),
            ("moon_south_pole", "lst_mean_diff", res["lst_range_C_mean_day_minus_mean_night"], "degC", mean_src)]
df = df[~df.feature.isin([r[1] for r in new_rows])]          # no duplicates when re-run
df = pd.concat([df, pd.DataFrame(new_rows, columns=df.columns)], ignore_index=True)
df.to_csv(CSV_OUT, index=False)
print("updated", CSV_OUT)