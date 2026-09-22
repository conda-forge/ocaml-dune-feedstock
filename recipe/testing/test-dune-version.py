#!/usr/bin/env python3
"""Test: dune version and basic commands

Validates dune binary runs and basic command help works.
"""

import subprocess
import sys

from test_utils import handle_test_result


def run_cmd(cmd, description):
    """Run a command and return success status."""
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"[FAIL] {description}")
        print(f"  stderr: {result.stderr[:500]}")
        return False
    print(f"[OK] {description}")
    return True


def main():
    print("=== dune version and help tests ===")

    all_ok = True

    print("\n--- Test: dune --version ---")
    result = subprocess.run(
        ["dune", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        print(f"dune version: {result.stdout.strip()}")
        print("[OK] dune --version")
    else:
        print("[FAIL] dune --version")
        print(f"  stderr: {result.stderr}")
        all_ok = False

    print("\n--- Test: dune --help ---")
    all_ok &= run_cmd(["dune", "--help"], "dune --help")

    print("\n--- Test: dune build --help ---")
    all_ok &= run_cmd(["dune", "build", "--help"], "dune build --help")

    print("\n--- Test: dune clean --help ---")
    all_ok &= run_cmd(["dune", "clean", "--help"], "dune clean --help")

    # Report the result; no suppression.
    return handle_test_result("dune version tests", all_ok)


if __name__ == "__main__":
    sys.exit(main())
