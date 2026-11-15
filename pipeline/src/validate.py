"""
validate.py — how well do the KNOWN analogs rank? (see "Validation" in CLAUDE.md)

    python src/validate.py          (run src/score.py first)

Method (fixed BEFORE looking at the results; scores are not changed by it):
  - Each known analog is evaluated ONLY on the target(s) of its body: analog_for "Mars" -> jezero,
    "Moon" -> lunar_south_pole ("Mars, Moon" -> both). Body of a target = `body` row of targets.csv.
  - ...and ONLY on the profile(s) its used_for text names, by keyword (PROFILE_KEYWORDS below).
    An analog can map to several profiles.
  - Success for an analog = top 10% on at least one of ITS mapped target × profiles.
  - Overall success = more than half of the analogs.
Tile of each analog = same tile as the website (common.find_analog_tiles).

Writes:
    out/validation.csv   one row per analog: mapping, rank and top % on each mapped target × profile
    out/validation.md    table for the slides (with a short "Method" paragraph)
"""

import re
from datetime import datetime, timezone

import pandas as pd

from common import TARGETS_DIR, OUT_DIR, count_tiles_scored, find_analog_tiles, load_csv, tile_of
from score import PROFILES

TOP_PCT = 10        # "in the top 10%"

# used_for keywords -> profile (regular expressions, case-insensitive, matched anywhere in the text).
# Decided BEFORE looking at the results: do not edit them to make an analog pass.
PROFILE_KEYWORDS = {
    "rover":   r"rover|mobility|field operations|instrument|drilling",
    "geology": r"geology|geolog|volcan|mineral|impact|biosignature|life-detection|life detection"
               r"|astrobiology|habitab",
    "polar":   r"polar|permafrost|ice|cold",
}


def target_bodies(targets_csv):
    """{target id: body} from the `body` rows of targets.csv (jezero -> Mars, lunar_south_pole -> Moon)."""
    rows = targets_csv[targets_csv["feature"] == "body"]
    return dict(zip(rows["target"], rows["value"]))


def analog_mapping(analog, body_of):
    """
    Which target × profiles a known analog is evaluated on.
    Returns (targets, profiles, keywords): keywords = {profile: [matched words]} (to print the evidence).
    """
    bodies = [b.strip() for b in str(analog["analog_for"]).split(",")]
    targets = [t for t, body in body_of.items() if body in bodies]
    used_for = str(analog["used_for"]).lower()
    keywords = {p: sorted(set(re.findall(rx, used_for))) for p, rx in PROFILE_KEYWORDS.items()}
    profiles = [p for p in PROFILES if keywords.get(p)]
    return targets, profiles, {p: keywords[p] for p in profiles}


def print_mapping(analogs, body_of):
    """Print the analog -> target × profile mapping (BEFORE any result). Returns the mapping list."""
    mapping = [analog_mapping(a, body_of) for _, a in analogs.iterrows()]
    print("Mapping (fixed before the results): analog_for -> targets, used_for keywords -> profiles\n")
    print(f"{'analog':<48} {'analog_for':<11} {'targets':<26} profiles (keywords)")
    for (_, a), (targets, profiles, kw) in zip(analogs.iterrows(), mapping):
        prof = "; ".join(f"{p} ({', '.join(kw[p])})" for p in profiles) or "NONE: not evaluated"
        print(f"{a['name'][:47]:<48} {a['analog_for']:<11} {', '.join(targets):<26} {prof}")
    print()
    return mapping


def shared_tile_notes(analogs, analog_tiles, scores):
    """
    Known analogs that land on the same 0.25° tile, either their own tile (coordinates) or the
    tile used for validation (after "nearest valid tile"). Returns one text line per shared tile.
    """
    own = {}
    used = {}
    for (_, a), tile in zip(analogs.iterrows(), analog_tiles):
        own.setdefault(int(tile_of(a["lat"], a["lon"])[0]), []).append(a["name"])
        if tile["row"] is not None:
            used.setdefault(int(scores.loc[tile["row"], "tile_id"]), []).append(a["name"])
    lines = []
    for tile_id, names in own.items():
        if len(names) > 1:
            lines.append(f"same tile {tile_id} (their coordinates): " + " / ".join(names))
    for tile_id, names in used.items():
        if len(names) > 1 and own.get(tile_id) != names:
            lines.append(f"same validation tile {tile_id} (nearest valid tile): " + " / ".join(names))
    return lines


def main():
    scores = load_csv(OUT_DIR / "scores.csv", "Run first: python src/score.py")
    analogs = load_csv(TARGETS_DIR / "known_analogs.csv", "It is provided by teammate C (known analogs).")
    targets_csv = load_csv(TARGETS_DIR / "targets.csv", "It is provided by teammate C (targets).")

    target_ids = list(dict.fromkeys(targets_csv["target"]))      # unique, file order
    body_of = target_bodies(targets_csv)
    tiles_scored = count_tiles_scored(scores, target_ids, PROFILES)

    mapping = print_mapping(analogs, body_of)                     # 1. mapping FIRST

    analog_tiles = find_analog_tiles(scores, analogs, target_ids)   # same tiles as export_web
    shared = shared_tile_notes(analogs, analog_tiles, scores)
    for line in shared:
        print(f"WARNING: {line}")

    rows = []
    for (_, a), tile, (targets, profiles, kw) in zip(analogs.iterrows(), analog_tiles, mapping):
        row = {"analog": a["name"], "analog_for": a["analog_for"], "used_for": a["used_for"],
               "targets": ", ".join(targets), "profiles": ", ".join(profiles),
               "tile_id": None, "tile_note": tile["note"] or "", "evaluated": "", "best": "",
               "best_rank": None, "best_tiles_scored": None, "best_top_pct": None, "in_top_10pct": False}
        for t in target_ids:
            row[f"in_top_10pct_{t}"] = False
        if tile["row"] is not None:
            t_row = scores.loc[tile["row"]]
            row["tile_id"] = int(t_row["tile_id"])
            evaluated = []
            best = None                                   # (top %, target, profile, rank)
            for t in targets:                             # ONLY its mapped target × profiles
                for p in profiles:
                    rank = t_row[f"rank_{t}_{p}"]
                    if pd.isna(rank):                     # unavailable profile (safety rule)
                        continue
                    top_pct = 100 * rank / tiles_scored[t]
                    row[f"rank_{t}_{p}"] = int(rank)
                    row[f"top_pct_{t}_{p}"] = round(top_pct, 1)
                    evaluated.append(f"{t} × {p}: {int(rank):,} / {tiles_scored[t]:,} ({top_pct:.1f}%)")
                    if top_pct <= TOP_PCT:
                        row[f"in_top_10pct_{t}"] = True
                    if best is None or top_pct < best[0]:
                        best = (top_pct, t, p, int(rank))
            row["evaluated"] = " | ".join(evaluated)
            if best:
                row.update({"best": f"{best[1]} × {best[2]}", "best_rank": best[3],
                            "best_tiles_scored": tiles_scored[best[1]],
                            "best_top_pct": round(best[0], 1), "in_top_10pct": best[0] <= TOP_PCT})
        rows.append(row)

    table = pd.DataFrame(rows)
    int_cols = [c for c in table.columns
                if c.startswith("rank_") or c in ("tile_id", "best_rank", "best_tiles_scored")]
    table[int_cols] = table[int_cols].astype("Int64")
    OUT_DIR.mkdir(exist_ok=True)
    table.to_csv(OUT_DIR / "validation.csv", index=False)

    # --- Summary ---------------------------------------------------------
    n = len(table)
    n_top = int(table["in_top_10pct"].sum())
    n_excluded = int((table["tile_id"].isna()).sum())
    summary = (f"{n_top} of {n} known analogs in the top {TOP_PCT}% on at least one of their mapped "
               f"target × profiles ({n_excluded} excluded: no valid tile)")
    success = n_top > n / 2
    per_target = []
    for t in target_ids:
        on_t = table["targets"].str.split(", ").apply(lambda ts: t in ts)
        with_tile = on_t & table["tile_id"].notna()
        per_target.append(f"{t} ({body_of.get(t)}): {int(table.loc[on_t, f'in_top_10pct_{t}'].sum())} of "
                          f"{int(on_t.sum())} {body_of.get(t)} analogs ({int(with_tile.sum())} with a valid tile)")

    # Per target × profile: analogs mapped to it, and how many are in the top 10% on that exact pair
    per_profile = []
    for t in target_ids:
        for p in PROFILES:
            mapped = table[table["targets"].str.split(", ").apply(lambda ts: t in ts)
                           & table["profiles"].str.split(", ").apply(lambda ps: p in ps)]
            if mapped.empty:
                continue
            col = f"top_pct_{t}_{p}"
            n_pass = int((mapped[col] <= TOP_PCT).sum()) if col in mapped else 0
            n_excl = int(mapped["tile_id"].isna().sum())
            per_profile.append(f"{t} × {p}: {n_pass} of {len(mapped)} mapped analogs pass"
                               + (f" ({n_excl} excluded)" if n_excl else ""))

    # --- Markdown for the slides -------------------------------------------
    rule = " · ".join(f"**{p}**: {rx.replace('|', ', ')}" for p, rx in PROFILE_KEYWORDS.items())
    lines = [
        "# Validation: known analogs",
        "",
        f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
        f"Tiles scored: " + ", ".join(f"{t} {c:,}" for t, c in tiles_scored.items()) + ".",
        "",
        "## Method",
        "",
        "Each known analog is evaluated only where it is a claimed analog, with a rule fixed before looking at "
        "the results. **Target** = its body (`analog_for`): Mars → jezero, Moon → lunar_south_pole. "
        "**Profiles** = the mission profiles its `used_for` text names, by keyword (an analog can map to several): "
        f"{rule}. An analog **succeeds** if its tile is in the top {TOP_PCT}% of all scored Earth tiles on at "
        "least one of its mapped target × profiles; the method succeeds if more than half of the analogs do. "
        "Analogs whose tile is excluded (e.g. vegetated) count as failures. The scores themselves are not "
        "changed by this rule, and the weights were not tuned on the analogs.",
        "",
        "## Results",
        "",
        "| Analog | Analog for | Used for | Mapped profiles | Rank and top % on each mapped target × profile | In top 10%? |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in table.iterrows():
        if pd.notna(r["tile_id"]):
            on_each = "<br>".join(e + (" ✓" if float(e.rsplit("(", 1)[1].rstrip("%)")) <= TOP_PCT else "")
                                  for e in r["evaluated"].split(" | ")) if r["evaluated"] else "–"
            if r["tile_note"]:
                on_each += f"<br>({r['tile_note']})"
            ok = "yes" if r["in_top_10pct"] else "no"
        else:
            on_each, ok = f"– ({r['tile_note']})", "no (excluded)"
        lines.append(f"| {r['analog']} | {r['analog_for']} | {r['used_for']} | {r['profiles'] or '–'} "
                     f"| {on_each} | {ok} |")
    lines += ["", f"**{summary}.** Success = more than half: **{'yes' if success else 'no'}**.", "",
              "Per target: " + "; ".join(per_target) + ".", "",
              "Per target × profile (analogs mapped to it, passing on that exact target × profile):", ""]
    lines += [f"- {line}" for line in per_profile] + [""]
    lines += [
        "## Limitations of this validation",
        "",
        "- The keyword mapping is mechanical: e.g. \"drilling\" maps University Valley to rover, "
        "\"ice-rock interactions\" maps Iceland to polar. It was fixed before the results and not edited afterwards.",
        "- Our dimensions do not measure ground ice or permafrost, which is what polar analogs (McMurdo, "
        "University Valley, Svalbard) are mostly used for.",
        "- Earth polar sites have a 1–2 °C mean day–night range (the Sun barely moves in their sky) vs 65 °C at "
        "Jezero, and mean nights no colder than about −35 °C vs −84 °C: they are cold, but not Jezero-like.",
        "",
    ]
    if shared:
        lines += ["**Analogs sharing a tile** (they are not independent checks of the method):", ""]
        lines += [f"- {line}" for line in shared] + [""]
    (OUT_DIR / "validation.md").write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines[lines.index("## Results") + 2:]))
    print(f"Wrote out/validation.csv and out/validation.md")
    print(f"\n{summary}. Success (more than half): {'YES' if success else 'NO'}")
    for line in per_target + per_profile:
        print(f"  {line}")


if __name__ == "__main__":
    main()
