"""
run_all.py — run the whole pipeline, in order, stopping at the first failure.

    python src/run_all.py

    python src/run_all.py --no-merge     (skip step 0 and use the FAKE inputs in data/fake/,
                                          made by make_fake_data.py: for testing)
    python src/run_all.py --test-targets (REAL Earth data, FAKE targets + known analogs from data/fake/
                                          while C hasn't delivered; "FAKE" sources = warning, and
                                          results.json is NOT copied to ../docs/data/)

Steps:
    0. merge_inputs.py: data/raw/ files from A and B -> data/earth_features.csv
    1. check_csv.py on the 3 input files (data/, or data/fake/: see the flags above)
    2. score.py
    3. cluster.py    (writes out/clusters.csv + out/hidden_gems.csv)
    4. validate.py   (writes out/validation.csv + out/validation.md)
    5. export_web.py (writes out/results.json + ../docs/data/results.json)
    6. check_results.py
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent

FAKE = "--no-merge" in sys.argv            # everything fake (data/fake/), no merge
TEST_TARGETS = "--test-targets" in sys.argv  # real Earth data, fake targets/analogs, no website copy
if FAKE:
    os.environ["PIPELINE_FAKE"] = "1"            # read by common.py in every step
if TEST_TARGETS:
    os.environ["PIPELINE_TEST_TARGETS"] = "1"
EARTH_REL = "data/fake" if FAKE else "data"
TARGETS_REL = "data/fake" if (FAKE or TEST_TARGETS) else "data"

# Input files: (name, folder, who provides them)
INPUTS = [
    ("earth_features.csv", EARTH_REL,   "teammates A and B (Earth Engine export, via merge_inputs.py)"),
    ("targets.csv",        TARGETS_REL, "teammate C (target values)"),
    ("known_analogs.csv",  TARGETS_REL, "teammate C (known analogs)"),
]

# (script, arguments, optional?)
STEPS = [("check_csv.py", [f"{folder}/{name}"], False) for name, folder, _ in INPUTS] + [
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

    # Step 0: build data/earth_features.csv from A's and B's raw files
    if FAKE:
        print("\n[0] merge_inputs.py skipped (--no-merge): using the FAKE inputs in data/fake/")
    else:
        print(f"\n{'=' * 70}\n[0] python src/merge_inputs.py\n{'=' * 70}", flush=True)
        result = subprocess.run([sys.executable, str(SRC / "merge_inputs.py")], cwd=ROOT)
        if result.returncode != 0:
            stop("step 0 failed: python src/merge_inputs.py (see the message above).\n"
                 "To test with the fake inputs in data/fake/: python src/run_all.py --no-merge")

    # Before anything else: are all inputs there?
    for name, folder, provider in INPUTS:
        if not (ROOT / folder / name).exists():
            stop(f"{folder}/{name} is missing. It is provided by {provider}.\n"
                 f"(For testing only: python src/make_fake_data.py)")
    print(f"\nInputs: earth_features from {EARTH_REL}/, targets + known_analogs from {TARGETS_REL}/")
    if TEST_TARGETS:
        print("--test-targets: FAKE targets. results.json will NOT be copied to ../docs/data/.")
    # Remember which inputs this run used (diagnose_validation.py, run by hand later, reads it)
    (ROOT / "out").mkdir(exist_ok=True)
    (ROOT / "out" / "run_inputs.json").write_text(json.dumps(
        {"earth_dir": EARTH_REL, "targets_dir": TARGETS_REL, "test_targets": TEST_TARGETS}))

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
                provider = {name: who for name, _, who in INPUTS}[Path(args[0]).name]
                hint = f"\nFix the ERRORS listed above, or send them to {provider}."
            stop(f"step {i} failed: python src/{label} (exit code {result.returncode}).{hint}")

    web = ("NOT copied to ../docs/data/ (--test-targets)" if TEST_TARGETS
           else "Website file: ../docs/data/results.json")
    print(f"\n{'=' * 70}\nPIPELINE OK in {time.time() - start:.0f} s. {web}\n{'=' * 70}")


if __name__ == "__main__":
    main()
