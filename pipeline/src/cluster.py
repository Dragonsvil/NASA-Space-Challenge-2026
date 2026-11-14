"""
cluster.py — K-Means clustering of Earth tiles and "hidden gems"
(see "Clustering and hidden gems" in CLAUDE.md).

    python src/cluster.py           (run src/score.py first)

1. Population: tiles that passed the vegetation filter and have a total for every target
   (same population as scoring), then the clustering filter: ndvi < 0.2 OR lst_min_night < -20 °C.
2. StandardScaler on Earth features only, K-Means for k = 8..12, keep the best silhouette.
3. "Analog clusters" = clusters that contain a known analog's tile (same tile as the website).
4. Hidden gem = tile in an analog cluster AND total in the top 5% for some target × profile
   AND more than 300 km from every known analog.
Neighbouring gem tiles are merged into regions for the slides.

Writes:
    out/clusters.csv      tile_id, cluster, hidden_gem, gem_region  (read by export_web.py)
    out/hidden_gems.csv   top 15 hidden-gem regions
"""

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from common import (DATA_DIR, OUT_DIR, count_tiles_scored, find_analog_tiles, grid_config,
                    haversine_km, load_csv)
from score import PROFILES

RANDOM_STATE = 42             # fixed: same clusters every run
K_VALUES = range(8, 13)       # k = 8..12
SILHOUETTE_SAMPLE = 10_000    # silhouette on a sample: the full score is too slow on 100k+ tiles
NDVI_MAX_CLUSTER = 0.2        # step 1: arid ...
COLD_NIGHT_C = -20            # ... or polar / high-altitude
TOP_SHARE = 0.05              # step 4: top 5%
MIN_DIST_KM = 300             # step 4: > 300 km from every known analog
N_REGIONS_OUT = 15            # rows in out/hidden_gems.csv

# Earth features used for clustering (raw CSV columns; max_sun_elev is left out because it
# is just a function of latitude)
FEATURES = ["lst_min_night", "lst_max_day", "lst_range", "albedo", "ndvi", "precip_mm",
            "slope_mean", "slope_std", "mafic_idx", "quartz_idx", "dust_aod"]


def choose_clusters(X):
    """Run K-Means for each k, print the silhouette, return (best k, labels)."""
    print("\nK-Means (silhouette: higher = better separated clusters):")
    best = None
    for k in K_VALUES:
        km = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(X)
        sil = silhouette_score(X, km.labels_, sample_size=min(SILHOUETTE_SAMPLE, len(X)),
                               random_state=RANDOM_STATE)
        print(f"  k = {k:>2}: silhouette {sil:.3f}")
        if best is None or sil > best[1]:
            best = (k, sil, km.labels_)
    print(f"Chosen k = {best[0]} (silhouette {best[1]:.3f})")
    return best[0], best[2]


def merge_neighbours(tile_ids):
    """
    Group tiles that touch (8 neighbours on the grid) into regions.
    Returns {tile_id: region number}. Uses grid_config: tile_id = row * N_COLS + col.
    """
    remaining = set(int(t) for t in tile_ids)
    region_of = {}
    region = 0
    while remaining:
        start = remaining.pop()
        stack = [start]
        region_of[start] = region
        while stack:                                   # flood fill
            t = stack.pop()
            row, col = divmod(t, grid_config.N_COLS)
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    c = (col + dc) % grid_config.N_COLS        # wraps around at ±180°
                    n = grid_config.tile_id(row + dr, c)
                    if n in remaining:
                        remaining.remove(n)
                        region_of[n] = region
                        stack.append(n)
        region += 1
    return region_of


def main():
    scores = load_csv(OUT_DIR / "scores.csv", "Run first: python src/score.py")
    analogs = load_csv(DATA_DIR / "known_analogs.csv", "It is provided by teammate C (known analogs).")
    targets_csv = load_csv(DATA_DIR / "targets.csv", "It is provided by teammate C (targets).")
    target_ids = list(dict.fromkeys(targets_csv["target"]))
    tiles_scored = count_tiles_scored(scores, target_ids, PROFILES)

    # --- 1. Population ------------------------------------------------------
    scored = scores[[f"total_{t}_rover" for t in target_ids]].notna().all(axis=1)
    arid_or_cold = (scores["ndvi"] < NDVI_MAX_CLUSTER) | (scores["lst_min_night"] < COLD_NIGHT_C)
    pop = scores[scored & arid_or_cold].copy()
    print(f"Clustering population: {len(pop):,} tiles "
          f"(scored: {scored.sum():,}, of which ndvi < {NDVI_MAX_CLUSTER} or "
          f"lst_min_night < {COLD_NIGHT_C} °C)")

    # --- 2. Scale + K-Means ---------------------------------------------------
    X = pop[FEATURES].copy()
    X["precip_mm"] = np.log1p(X["precip_mm"])        # rain is very skewed: compare on a log scale
    X = X.fillna(X.median())                          # K-Means can't handle NaN: use the median
    X = StandardScaler().fit_transform(X)
    k, labels = choose_clusters(X)
    pop["cluster"] = labels

    # --- 3. Analog clusters -----------------------------------------------------
    analog_tiles = find_analog_tiles(scores, analogs, target_ids)   # same tiles as the website
    print("\nKnown analogs by cluster:")
    analog_clusters = set()
    for name, tile in zip(analogs["name"], analog_tiles):
        if tile["row"] is None:
            print(f"  {name:<22} -> no cluster ({tile['note']})")
        elif tile["row"] not in pop.index:
            print(f"  {name:<22} -> no cluster (tile not arid/cold enough for clustering)")
        else:
            c = int(pop.loc[tile["row"], "cluster"])
            analog_clusters.add(c)
            print(f"  {name:<22} -> cluster {c}")
    sizes = pop["cluster"].value_counts().sort_index()
    print("Cluster sizes: " + ", ".join(
        f"{c}{'*' if c in analog_clusters else ''}: {n:,}" for c, n in sizes.items())
          + "   (* = analog cluster)")

    # --- 4. Hidden gems -----------------------------------------------------------
    in_analog_cluster = pop["cluster"].isin(analog_clusters)
    in_top = pd.Series(False, index=pop.index)
    for t in target_ids:
        for p in PROFILES:
            in_top |= pop[f"rank_{t}_{p}"] <= TOP_SHARE * tiles_scored[t]
    # distance to the nearest known analog (all of them, even the excluded ones)
    nearest_km = np.full(len(pop), np.inf)
    for _, a in analogs.iterrows():
        d = haversine_km(a["lat"], a["lon"], pop["lat"].to_numpy(), pop["lon"].to_numpy())
        nearest_km = np.minimum(nearest_km, d)
    far = nearest_km > MIN_DIST_KM
    pop["hidden_gem"] = in_analog_cluster & in_top & far
    gems = pop[pop["hidden_gem"]].copy()
    print(f"\nHidden gems: {len(gems):,} tiles "
          f"(in analog cluster: {in_analog_cluster.sum():,}, "
          f"+ top {100 * TOP_SHARE:.0f}%: {(in_analog_cluster & in_top).sum():,}, "
          f"+ > {MIN_DIST_KM} km from analogs: {len(gems):,})")

    # --- Gem regions: merge neighbouring tiles ---------------------------------------
    region_of = merge_neighbours(gems["tile_id"])
    gems["gem_region"] = gems["tile_id"].map(region_of)
    # best target × profile of each tile = smallest rank / tiles_scored
    best_cols = [(t, p) for t in target_ids for p in PROFILES]
    shares = np.column_stack([gems[f"rank_{t}_{p}"] / tiles_scored[t] for t, p in best_cols])
    best_i = shares.argmin(axis=1)
    gems["best"] = [f"{best_cols[i][0]} × {best_cols[i][1]}" for i in best_i]
    gems["best_top_pct"] = 100 * shares.min(axis=1)
    gems["best_total"] = [gems.iloc[j][f"total_{best_cols[i][0]}_{best_cols[i][1]}"]
                          for j, i in enumerate(best_i)]
    gems["best_rank"] = [gems.iloc[j][f"rank_{best_cols[i][0]}_{best_cols[i][1]}"]
                         for j, i in enumerate(best_i)]

    regions = []
    for r, g in gems.groupby("gem_region"):
        top = g.loc[g["best_top_pct"].idxmin()]          # the region's best tile
        regions.append({"gem_region": int(r), "n_tiles": len(g),
                        "lat": round(g["lat"].mean(), 3), "lon": round(g["lon"].mean(), 3),
                        "cluster": int(top["cluster"]), "best": top["best"],
                        "best_total": int(top["best_total"]), "best_rank": int(top["best_rank"]),
                        "best_top_pct": round(top["best_top_pct"], 2),
                        "best_tile_id": int(top["tile_id"])})
    regions = pd.DataFrame(regions)
    if len(regions):
        regions = regions.sort_values(["best_top_pct", "n_tiles"], ascending=[True, False])
        regions = regions.head(N_REGIONS_OUT).reset_index(drop=True)
        from export_web import region_names            # same naming as the website
        regions.insert(4, "region", region_names(regions["lat"].tolist(), regions["lon"].tolist()))

    # --- Save ---------------------------------------------------------------------
    OUT_DIR.mkdir(exist_ok=True)
    out = pop[["tile_id", "cluster", "hidden_gem"]].copy()
    out["gem_region"] = gems["gem_region"].reindex(out.index).astype("Int64")
    out.to_csv(OUT_DIR / "clusters.csv", index=False)
    regions.to_csv(OUT_DIR / "hidden_gems.csv", index=False)

    print(f"\nHidden-gem regions: {len(set(region_of.values())):,} "
          f"(neighbouring tiles merged); top {len(regions)}:")
    if len(regions):
        print(regions[["n_tiles", "lat", "lon", "region", "best", "best_total",
                       "best_rank", "best_top_pct"]].to_string(index=False))
    print("\nWrote out/clusters.csv and out/hidden_gems.csv")


if __name__ == "__main__":
    main()
