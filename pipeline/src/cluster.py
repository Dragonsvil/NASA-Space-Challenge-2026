"""
cluster.py — K-Means clustering of Earth tiles and "hidden gems"
(see "Clustering and hidden gems" in CLAUDE.md).

    python src/cluster.py           (run src/score.py first)

1. Population: tiles that passed the vegetation filter and have a total for every target
   (same population as scoring), then the clustering filter: ndvi < 0.2 OR lst_mean_night < -10 °C.
2. StandardScaler on Earth features only, K-Means for k = 8..12, keep the best silhouette.
3. Hidden gems, PER TARGET (jezero = Mars, lunar_south_pole = Moon). A tile is a candidate if:
   - it is in the top 10% for that target on its best profile, AND
   - its cluster contains a known analog for that body (analog_for contains "Mars" / "Moon"), AND
   - it is more than 300 km from every known analog.
   Then keep the best 15 per target, greedily, never two within 300 km of each other.

Writes:
    out/clusters.csv      tile_id, cluster, gem_<target> for each target  (read by export_web.py)
    out/hidden_gems.csv   the gems: one row per target × gem (at most 15 per target)
"""

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from common import (INPUT_DIR, OUT_DIR, count_tiles_scored, find_analog_tiles, haversine_km,
                    load_csv, region_names)
from score import PROFILES

RANDOM_STATE = 42             # fixed: same clusters every run
K_VALUES = range(8, 13)       # k = 8..12
SILHOUETTE_SAMPLE = 10_000    # silhouette on a sample: the full score is too slow on 100k+ tiles
NDVI_MAX_CLUSTER = 0.2        # step 1: arid ...
COLD_NIGHT_C = -10            # ... or polar / high-altitude (MEAN night temperature, like scoring)
TOP_SHARE = 0.10              # gem: top 10% for the target, on its best profile
MIN_DIST_KM = 300             # gem: > 300 km from every known analog, and from other gems
MAX_GEMS = 15                 # gems kept per target

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


def main():
    scores = load_csv(OUT_DIR / "scores.csv", "Run first: python src/score.py")
    analogs = load_csv(INPUT_DIR / "known_analogs.csv", "It is provided by teammate C (known analogs).")
    targets_csv = load_csv(INPUT_DIR / "targets.csv", "It is provided by teammate C (targets).")
    target_ids = list(dict.fromkeys(targets_csv["target"]))
    tiles_scored = count_tiles_scored(scores, target_ids, PROFILES)

    # --- 1. Population ------------------------------------------------------
    # scored for at least one target (a gem for a target also needs that target's rank)
    scored = scores[[f"total_{t}_rover" for t in target_ids]].notna().any(axis=1)
    arid_or_cold = (scores["ndvi"] < NDVI_MAX_CLUSTER) | (scores["lst_mean_night"] < COLD_NIGHT_C)
    pop = scores[scored & arid_or_cold].copy()
    print(f"Clustering population: {len(pop):,} tiles "
          f"(scored: {scored.sum():,}, of which ndvi < {NDVI_MAX_CLUSTER} or "
          f"lst_mean_night < {COLD_NIGHT_C} °C)")

    # --- 2. Scale + K-Means ---------------------------------------------------
    X = pop[FEATURES].copy()
    X["precip_mm"] = np.log1p(X["precip_mm"])        # rain is very skewed: compare on a log scale
    X = X.fillna(X.median())                          # K-Means can't handle NaN: use the median
    X = StandardScaler().fit_transform(X)
    k, labels = choose_clusters(X)
    pop["cluster"] = labels

    # --- 3. Clusters containing a known analog, per body ----------------------------
    analog_tiles = find_analog_tiles(scores, analogs, target_ids)   # same tiles as the website
    print("\nKnown analogs by cluster:")
    analog_cluster = {}                               # analog name -> cluster
    for (_, a), tile in zip(analogs.iterrows(), analog_tiles):
        if tile["row"] is None:
            print(f"  {a['name']:<22} -> no cluster ({tile['note']})")
        elif tile["row"] not in pop.index:
            print(f"  {a['name']:<22} -> no cluster (tile not arid/cold enough for clustering)")
        else:
            analog_cluster[a["name"]] = int(pop.loc[tile["row"], "cluster"])
            print(f"  {a['name']:<22} -> cluster {analog_cluster[a['name']]} ({a['analog_for']})")
    sizes = pop["cluster"].value_counts().sort_index()
    print("Cluster sizes: " + ", ".join(f"{c}: {n:,}" for c, n in sizes.items()))

    # distance from each tile to the nearest known analog (all of them, even excluded ones)
    nearest_analog_km = np.full(len(pop), np.inf)
    for _, a in analogs.iterrows():
        d = haversine_km(a["lat"], a["lon"], pop["lat"].to_numpy(), pop["lon"].to_numpy())
        nearest_analog_km = np.minimum(nearest_analog_km, d)
    pop["nearest_analog_km"] = nearest_analog_km

    # --- 4. Hidden gems per target ---------------------------------------------------
    gem_rows = []
    for t in target_ids:
        body = targets_csv.loc[(targets_csv["target"] == t) & (targets_csv["feature"] == "body"),
                               "value"].iloc[0]
        body_clusters = {c for name, c in analog_cluster.items()
                         if body in analogs.loc[analogs["name"] == name, "analog_for"].iloc[0]}

        # best profile of each tile for this target = smallest rank
        ranks = pop[[f"rank_{t}_{p}" for p in PROFILES]].astype(float)
        ranks = ranks[ranks.notna().all(axis=1)]          # tiles scored for this target
        best_col = ranks.idxmin(axis=1)
        best_rank = ranks.min(axis=1).reindex(pop.index)  # NaN for tiles not scored
        cand = pop[(best_rank <= TOP_SHARE * tiles_scored[t])
                   & pop["cluster"].isin(body_clusters)
                   & (pop["nearest_analog_km"] > MIN_DIST_KM)].copy()
        cand["best_profile"] = best_col[cand.index].str.replace(f"rank_{t}_", "", regex=False)
        cand["best_rank"] = best_rank[cand.index].astype(int)
        cand["best_total"] = [int(cand.at[i, f"total_{t}_{p}"]) for i, p in cand["best_profile"].items()]
        cand = cand.sort_values(["best_rank", "best_total"], ascending=[True, False])

        # Greedy: take the best candidate, skip anything within 300 km of a gem already taken
        chosen = []
        for i, row in cand.iterrows():
            if all(haversine_km(row["lat"], row["lon"], g["lat"], g["lon"]) > MIN_DIST_KM
                   for g in chosen):
                chosen.append(row)
                if len(chosen) == MAX_GEMS:
                    break
        print(f"\n{t} ({body}): analog clusters {sorted(body_clusters)}, "
              f"{len(cand):,} candidate tiles -> {len(chosen)} gems")
        pop[f"gem_{t}"] = pop.index.isin([g.name for g in chosen])
        for n, g in enumerate(chosen, start=1):
            gem_rows.append({"target": t, "gem": n, "tile_id": int(g["tile_id"]),
                             "lat": g["lat"], "lon": g["lon"], "cluster": int(g["cluster"]),
                             "best_profile": g["best_profile"], "best_total": g["best_total"],
                             "best_rank": g["best_rank"], "tiles_scored": tiles_scored[t],
                             "top_pct": round(100 * g["best_rank"] / tiles_scored[t], 2),
                             "nearest_analog_km": round(g["nearest_analog_km"])})

    gems = pd.DataFrame(gem_rows)
    if len(gems):
        gems.insert(5, "region", region_names(gems["lat"].tolist(), gems["lon"].tolist()))

    # --- Save ---------------------------------------------------------------------
    OUT_DIR.mkdir(exist_ok=True)
    pop[["tile_id", "cluster"] + [f"gem_{t}" for t in target_ids]].to_csv(
        OUT_DIR / "clusters.csv", index=False)
    gems.to_csv(OUT_DIR / "hidden_gems.csv", index=False)

    for t in target_ids:
        g = gems[gems["target"] == t] if len(gems) else gems
        print(f"\n=== Hidden gems for {t}: {len(g)}")
        if len(g):
            print(g[["gem", "lat", "lon", "region", "cluster", "best_profile", "best_total",
                     "best_rank", "top_pct", "nearest_analog_km"]].to_string(index=False))
    print("\nWrote out/clusters.csv and out/hidden_gems.csv")


if __name__ == "__main__":
    main()
