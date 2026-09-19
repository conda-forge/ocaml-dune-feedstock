#!/usr/bin/env python3
"""Aggregate runner for the dune functional test suite.

A conda `tests: - script: |` block with multiple lines does not fail fast:
the block's exit status is only the LAST command's, so a failure in an
earlier line is swallowed and the lane is reported as a success anyway
(observed on PR #22, where three tests printed [FAIL] on
win_64_c_compilergcc and the job still concluded success). To avoid that,
every test below is run through this single aggregating process, which
runs all of them, collects each one's exit code, and exits non-zero if
ANY test failed.

Probes listed in PROBE_ORDER run first and are diagnostic only: their exit
codes are ignored and can never fail the suite.
"""

import os
import subprocess
import sys

TEST_ORDER = [
    "test-dune-version.py",
    "test-dune-arch.py",
    "test-dune-config.py",
    "test-dune-build.py",
    "test-dune-cmi.py",
    "test-dune-stubs.py",
    "test-dune-activation.py",
]

PROBE_ORDER = [
    "probe-dune-cache.py",
]


def run_tests() -> int:
    """Run each test in TEST_ORDER and return 0 if all passed, else 1."""
    here = os.path.dirname(os.path.abspath(__file__))
    results = []

    for name in PROBE_ORDER:
        print(f"=== running probe {name} ===")
        path = os.path.join(here, name)
        if os.path.isfile(path):
            subprocess.run([sys.executable, path])
        else:
            print(f"[WARN] probe {name} not found at {path}")

    for name in TEST_ORDER:
        print(f"=== running {name} ===")
        path = os.path.join(here, name)

        if not os.path.isfile(path):
            print(f"[FAIL] {name}: test file not found at {path}")
            results.append((name, 1))
            continue

        completed = subprocess.run([sys.executable, path])
        results.append((name, completed.returncode))

    print()
    print("=== summary ===")
    failed = []
    for name, code in results:
        status = "PASS" if code == 0 else "FAIL"
        print(f"{status} {name} (exit {code})")
        if code != 0:
            failed.append(name)

    if failed:
        print()
        print("FAILED: " + ", ".join(failed))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(run_tests())
