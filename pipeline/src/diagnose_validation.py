"""
diagnose_validation.py — WHY does each known analog rank where it does?
Run by hand (not part of run_all.py), after run_all.py:

    python src/diagnose_validation.py

For each known analog, on its best target × profile, one line per dimension:
target value, the analog tile's raw value, gap, dimension score, weight, and the points
that dimension costs the total:  weight × (100 − score) / total weight.
(total = 100 − sum of points lost, up to rounding.) The 2 most costly = "main drag".

Then: which dimension is the main drag most often. If one drags almost every analog,
the first suspect is its units or its target value (CLAUDE.md: units and target values
FIRST, weights last).

Also lists excluded analogs with the exact rule that excluded them.
Writes out/diagnosis.md (same content as the terminal).
"""

import json
from collections import Counter

import pandas as pd

from common import (RUN_INPUTS_FILE, ROOT, TARGETS_DIR, NEAR_TOWN_KM, OUT_DIR, count_tiles_scored, find_analog_tiles,
                    load_csv, tile_of)
from export_web import DIM_LABELS
from score import DIMENSIONS, MIN_WEIGHT_COVERAGE, NDVI_MAX, POLAR_LAT, PROFILES

N_DRAG = 2                  # main drags flagged per analog
ALMOST_ALL = 0.8            # "drags almost every analog" = main drag for >= 80% of them

# Open questions on C's REAL target values (data/targets.csv). Shown in out/diagnosis.md when the last
# run used the real targets. Remove an item once C has confirmed it.
TO_CONFIRM_WITH_C = [
    "**Jezero mafic = high**: citation (Science Advances, DOI 10.1126/sciadv.abo3399) not verified yet.",
    "**Jezero albedo = 0.15**: a single THEMIS/TES observation (I75667014), not a regional average, and TES "
    "albedo is not the same quantity as MODIS broadband albedo (what the Earth tiles use).",
    "**Lunar slope / roughness (15.35° / 9.91°)**: confirm the pixel scale the LOLA slope was computed at "
    "(source says LDEM 80 m/px resampled to 500 m, Horn 3x3). Slope depends strongly on pixel size; "
    "Jezero (MOLA, ~500 m) and the Earth tiles must use a comparable scale.",
]

lines = []                  # everything printed also goes to out/diagnosis.md


def say(text=""):
    print(text)
    lines.append(text)


def fmt(x, decimals=2):
    return "–" if x is None or pd.isna(x) else f"{x:.{decimals}f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# Excluded analogs: which rule, with the values
# ---------------------------------------------------------------------------

def exclusion_reason(analog, scores, target_dims, note):
    """Explain exactly why an analog has no scored tile."""
    tile_id, c_lat, c_lon = tile_of(analog["lat"], analog["lon"])
    own = scores.index[scores["tile_id"] == tile_id]
    if not len(own):
        return (f"own tile {tile_id} ({c_lat}, {c_lon}) is not in earth_features.csv "
                f"(A/B export has no data there) and no valid tile within 50 km. Note: {note}")
    t = scores.loc[own[0]]
    rule = t["scoring_filter"]
    if rule == "vegetated":
        return f"vegetation filter: NDVI {t['ndvi']:.2f} > {NDVI_MAX}"
    if rule == "no NDVI":
        return f"vegetation filter: NDVI missing and not polar (|lat| {abs(t['lat']):.2f} <= {POLAR_LAT})"
    if rule == "no DEM":
        return ("land mask: slope_mean missing (no DEM data), and no valid tile within 50 km")
    if rule == "off land":
        return (f"land mask: tile center ({t['lat']}, {t['lon']}) outside every country polygon "
                f"and no town within {NEAR_TOWN_KM} km; no valid tile within 50 km")
    # kept by the filters, so it failed the completeness rules for some target
    parts = []
    for target, dims in target_dims.items():
        if pd.notna(t[f"total_{target}_rover"]):
            continue
        has = {d: pd.notna(t[DIMENSIONS[d][0]]) for d in dims}
        missing = [d for d in dims if not has[d]]
        cov = []
        for p, w in PROFILES.items():
            tot = sum(w.get(d, 0) for d in dims)
            share = sum(w.get(d, 0) for d in dims if has[d]) / tot
            cov.append(f"{p} {share:.0%}")
        parts.append(f"completeness ({target}): missing {missing}; weight coverage "
                     f"{', '.join(cov)} (need >= {MIN_WEIGHT_COVERAGE:.0%} for every profile, "
                     f"and at most half the dims missing)")
    return "; ".join(parts) if parts else f"no valid total ({note})"


# ---------------------------------------------------------------------------

def main():
    scores = load_csv(OUT_DIR / "scores.csv", "Run first: python src/run_all.py")
    target_values = load_csv(OUT_DIR / "target_values.csv", "Run first: python src/run_all.py")
    # Same known_analogs.csv as the last run_all.py (data/ or data/fake/ with --test-targets)
    analogs_dir = TARGETS_DIR
    if RUN_INPUTS_FILE.exists():
        analogs_dir = ROOT / json.loads(RUN_INPUTS_FILE.read_text())["targets_dir"]
    print(f"Known analogs from {analogs_dir.relative_to(ROOT)}/ (same as the last run_all.py)")
    analogs = load_csv(analogs_dir / "known_analogs.csv", "It is provided by teammate C (known analogs).")

    tv = target_values[target_values["used"].notna()]
    target_ids = list(dict.fromkeys(tv["target"]))
    target_dims = {t: tv.loc[tv["target"] == t, "dim"].tolist() for t in target_ids}
    target_value = {(r["target"], r["dim"]): r["used"] for _, r in tv.iterrows()}
    tiles_scored = count_tiles_scored(scores, target_ids, PROFILES)
    analog_tiles = find_analog_tiles(scores, analogs, target_ids)   # same tiles as the website

    say("# Validation diagnosis")
    say()
    say("Points lost = weight × (100 − score) / total weight of the dims the tile has. "
        "Total ≈ 100 − Σ points lost.")

    drags = Counter()
    n_analysed = 0
    excluded = []
    for (_, a), tile in zip(analogs.iterrows(), analog_tiles):
        if tile["row"] is None:
            excluded.append((a, tile["note"]))
            continue
        n_analysed += 1
        t = scores.loc[tile["row"]]

        # best target × profile = smallest rank / tiles_scored
        best = min(((t[f"rank_{tg}_{p}"] / tiles_scored[tg], tg, p)
                    for tg in target_ids for p in PROFILES))
        share, tg, p = best
        weights = PROFILES[p]
        dims = target_dims[tg]
        present = [d for d in dims if pd.notna(t[DIMENSIONS[d][0]])]
        total_w = sum(weights.get(d, 0) for d in present)

        rows = []
        for d in dims:
            raw = t[DIMENSIONS[d][0]]
            w = weights.get(d, 0)
            if pd.isna(raw):
                rows.append((d, target_value[(tg, d)], None, None, None, w, 0.0, "missing"))
                continue
            score = t[f"score_{tg}_{d}"]
            lost = w * (100 - score) / total_w
            rows.append((d, target_value[(tg, d)], raw, abs(raw - target_value[(tg, d)]),
                         score, w, lost, ""))
        rows.sort(key=lambda r: -r[6])
        for i in range(min(N_DRAG, len(rows))):
            if rows[i][6] > 0:
                rows[i] = rows[i][:7] + ("MAIN DRAG",)
                drags[rows[i][0]] += 1

        say()
        tile_txt = f"tile {int(t['tile_id'])} ({t['lat']}, {t['lon']})"
        if tile["note"]:
            tile_txt += f", {tile['note']}"
        say(f"## {a['name']} ({a['analog_for']})")
        say(f"Best: **{tg} × {p}**, total {int(t[f'total_{tg}_{p}'])}, "
            f"rank {int(t[f'rank_{tg}_{p}']):,} / {tiles_scored[tg]:,} (top {100 * share:.1f}%). {tile_txt}")
        say()
        say("| dimension | unit | target | analog | gap | score | weight | points lost | |")
        say("|---|---|---|---|---|---|---|---|---|")
        for d, target, raw, gap, score, w, lost, flag in rows:
            say(f"| {d} | {DIM_LABELS[d][1]} | {fmt(target)} | {fmt(raw)} | {fmt(gap)} | "
                f"{fmt(score, 0)} | {w} | {lost:.1f} | {flag} |")
        say(f"Check: 100 − Σ points lost = {100 - sum(r[6] for r in rows):.1f} "
            f"(total {int(t[f'total_{tg}_{p}'])})")

    # --- Summary ---------------------------------------------------------------
    say()
    say("## Summary: main drag (top 2 per analog)")
    say()
    if drags:
        for d, n in drags.most_common():
            say(f"- {d}: main drag for {n} of {n_analysed} analysed analogs")
        dim, n = drags.most_common(1)[0]
        if n_analysed >= 3 and n >= ALMOST_ALL * n_analysed:
            say()
            say(f"**CHECK UNITS / TARGET VALUE for {dim} first** "
                f"(main drag for {n} of {n_analysed} analogs).")
    else:
        say("No analog could be analysed.")

    say()
    say(f"## Excluded analogs ({len(excluded)})")
    say()
    for a, note in excluded:
        say(f"- **{a['name']}** ({a['lat']}, {a['lon']}): {exclusion_reason(a, scores, target_dims, note)}")
    if not excluded:
        say("None.")

    if analogs_dir == ROOT / "data":          # real targets from C (not data/fake/)
        say()
        say("## Target values to confirm with C")
        say()
        for item in TO_CONFIRM_WITH_C:
            say(f"- {item}")

    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "diagnosis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nWrote out/diagnosis.md")


if __name__ == "__main__":
    main()
