import glob, re, numpy as np
t = []
for f in glob.glob("diviner_cache/box_*.npy"):
    n = int(re.search(r"_(\d+)\.npy", f).group(1))
    if n >= 73 or n <= 24:                       # night bins
        a = np.load(f); t.append(a[a[:, 0] >= 1.0, 0])
t = np.concatenate(t)
for p in (0, 0.01, 0.1, 1, 5, 50):
    print(f"percentile {p}: {np.percentile(t, p):.1f} K = {np.percentile(t, p) - 273.15:.1f} C")