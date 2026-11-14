"""
run_all.py — run the whole pipeline, in order, stopping at the first failure.

    python src/run_all.py

Steps:
    1. check_csv.py on the 3 input files (data/)
    2. score.py
    3. cluster.py    (writes out/clusters.csv + out/hidden_gems.csv)
    4. validate.py   (writes out/validation.csv + out/validation.md)
    5. export_web.py (writes out/results.json + ../docs/data/results.json)
    6. check_results.py
"""

import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
DATA = ROOT / "data"

# Input files and who provides them
INPUTS = [
    ("earth_features.csv", "teammates A and B (Earth Engine export)"),
    ("targets.csv",        "teammate C (target values)"),
    ("known_analogs.csv",  "teammate C (known analogs)"),
]

# (script, arguments, optional?)
STEPS = [("check_csv.py", [f"data/{name}"], False) for name, _ in INPUTS] + [
    ("score.py",         [], False),
    ("cluster.py",       [], False),
    ("validate.py",      [], False),
    ("export_web.py",    [], False),
    ("check_results.py", [], False),
]


def stop(message):
    print("\n" + "!" * 70)
    print(f"PIPELINE STOPPED: {message}")
    print("!" * 70)
    sys.exit(1)


def main():
    start = time.time()

    # Before anything else: are all inputs there?
    for name, provider in INPUTS:
        if not (DATA / name).exists():
            stop(f"data/{name} is missing. It is provided by {provider}.\n"
                 f"(For testing only: python src/make_fake_data.py)")

    for i, (script, args, optional) in enumerate(STEPS, start=1):
        label = " ".join([script] + args)
        if not (SRC / script).exists():
            if optional:
                print(f"\n[{i}/{len(STEPS)}] {script}: not written yet, skipped")
                continue
            stop(f"src/{script} does not exist.")

        print(f"\n{'=' * 70}\n[{i}/{len(STEPS)}] python src/{label}\n{'=' * 70}", flush=True)
        # Same Python as this script (the .venv one), run from the pipeline/ folder
        result = subprocess.run([sys.executable, str(SRC / script), *args], cwd=ROOT)
        if result.returncode != 0:
            hint = ""
            if script == "check_csv.py":
                provider = dict(INPUTS)[Path(args[0]).name]
                hint = f"\nFix the ERRORS listed above, or send them to {provider}."
            stop(f"step {i} failed: python src/{label} (exit code {result.returncode}).{hint}")

    print(f"\n{'=' * 70}\nPIPELINE OK in {time.time() - start:.0f} s. "
          f"Website file: ../docs/data/results.json\n{'=' * 70}")


if __name__ == "__main__":
    main()
