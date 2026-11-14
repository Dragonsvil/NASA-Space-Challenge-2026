"""
validate.py — how well do the KNOWN analogs rank? (see "Validation" in CLAUDE.md)

    python src/validate.py          (run src/score.py first)

For each known analog: its tile (same tile as the website, common.find_analog_tiles),
its global rank for every target × profile, and its best one.
Success = most analogs in the top 10% of at least one target × profile.

Writes:
    out/validation.csv   one row per analog, all target × profile ranks
    out/validation.md    table for the slides
"""

from datetime import datetime, timezone

import pandas as pd

from common import DATA_DIR, OUT_DIR, count_tiles_scored, find_analog_tiles, load_csv
from score import PROFILES

TOP_PCT = 10        # "in the top 10%"


def main():
    scores = load_csv(OUT_DIR / "scores.csv", "Run first: python src/score.py")
    analogs = load_csv(DATA_DIR / "known_analogs.csv", "It is provided by teammate C (known analogs).")
    targets_csv = load_csv(DATA_DIR / "targets.csv", "It is provided by teammate C (targets).")

    target_ids = list(dict.fromkeys(targets_csv["target"]))      # unique, file order
    tiles_scored = count_tiles_scored(scores, target_ids, PROFILES)
    analog_tiles = find_analog_tiles(scores, analogs, target_ids)   # same tiles as export_web

    rows = []
    for (_, a), tile in zip(analogs.iterrows(), analog_tiles):
        row = {"analog": a["name"], "analog_for": a["analog_for"],
               "tile_id": None, "tile_note": tile["note"] or ""}
        best = None                                   # (top %, target, profile, rank)
        if tile["row"] is not None:
            t_row = scores.loc[tile["row"]]
            row["tile_id"] = int(t_row["tile_id"])
            for t in target_ids:
                for p in PROFILES:
                    rank = t_row[f"rank_{t}_{p}"]
                    top_pct = 100 * rank / tiles_scored[t]
                    row[f"total_{t}_{p}"] = int(t_row[f"total_{t}_{p}"])
                    row[f"rank_{t}_{p}"] = int(rank)
                    row[f"top_pct_{t}_{p}"] = round(top_pct, 1)
                    if best is None or top_pct < best[0]:
                        best = (top_pct, t, p, int(rank))
        if best:
            row.update({"best": f"{best[1]} × {best[2]}", "best_rank": best[3],
                        "best_tiles_scored": tiles_scored[best[1]],
                        "best_top_pct": round(best[0], 1),
                        "in_top_10pct": best[0] <= TOP_PCT})
        else:
            row.update({"best": "", "best_rank": None, "best_tiles_scored": None,
                        "best_top_pct": None, "in_top_10pct": False})
        rows.append(row)

    table = pd.DataFrame(rows)
    # Keep whole numbers as integers (pandas turns them into 514.0 when some analogs have none)
    int_cols = [c for c in table.columns
                if c.startswith(("total_", "rank_")) or c in ("tile_id", "best_rank", "best_tiles_scored")]
    table[int_cols] = table[int_cols].astype("Int64")
    OUT_DIR.mkdir(exist_ok=True)
    table.to_csv(OUT_DIR / "validation.csv", index=False)

    # --- Summary ---------------------------------------------------------
    n = len(table)
    n_top = int(table["in_top_10pct"].sum())
    n_excluded = int((table["best"] == "").sum())
    summary = (f"{n_top} of {n} known analogs in the top {TOP_PCT}% of at least one profile "
               f"({n_excluded} excluded: no valid tile)")
    success = n_top > n / 2

    # --- Markdown table for the slides -------------------------------------
    lines = [
        "# Validation: known analogs",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
        f"Tiles scored: " + ", ".join(f"{t} {c:,}" for t, c in tiles_scored.items()) + ".",
        "",
        "| Analog | Analog for | Best target × profile | Rank | Top % | In top 10%? |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in table.iterrows():
        if r["best"]:
            rank = f"{r['best_rank']:,} / {r['best_tiles_scored']:,}"
            top = f"{r['best_top_pct']:.1f}%"
            ok = "yes" if r["in_top_10pct"] else "no"
            best = r["best"] + (f" ({r['tile_note']})" if r["tile_note"] else "")
        else:
            rank, top, ok, best = "–", "–", f"– ({r['tile_note']})", "–"
        lines.append(f"| {r['analog']} | {r['analog_for']} | {best} | {rank} | {top} | {ok} |")
    lines += ["", f"**{summary}.** Success = more than half: **{'yes' if success else 'no'}**.", ""]
    (OUT_DIR / "validation.md").write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines[4:-3]))
    print(f"\nWrote out/validation.csv and out/validation.md")
    print(f"\n{summary}. Success (more than half): {'YES' if success else 'NO'}")


if __name__ == "__main__":
    main()
