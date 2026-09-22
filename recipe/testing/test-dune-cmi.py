#!/usr/bin/env python3
"""Test: dune interface consistency (CRC) tests

Tests that uses multiple stdlib modules to catch CRC mismatches
between compiled interfaces.
"""

import os
import shutil
import subprocess
import sys
import tempfile

from test_utils import handle_test_result


def main():
    print("=== Dune Interface Consistency Tests ===")

    test_dir = tempfile.mkdtemp(prefix="dune_cmi_")
    original_dir = os.getcwd()
    success = False

    try:
        os.chdir(test_dir)

        with open("dune-project", "w") as f:
            f.write("(lang dune 3.0)")

        # Create test that uses multiple stdlib modules
        os.makedirs("consistency", exist_ok=True)

        with open("consistency/dune", "w") as f:
            f.write(
                """(executable
 (name test_consistency)
 (libraries unix str))"""
            )

        with open("consistency/test_consistency.ml", "w") as f:
            f.write(
                """(* Uses multiple stdlib modules - CRC mismatch would fail here *)
let () =
  (* Unix module *)
  let _ = Unix.getpid () in
  (* Str module *)
  let re = Str.regexp "test" in
  let _ = Str.string_match re "test" 0 in
  (* Stdlib *)
  let _ = List.map (fun x -> x + 1) [1; 2; 3] in
  print_endline "Consistency check passed"
"""
            )

        # Build
        result = subprocess.run(
            ["dune", "build", "consistency/test_consistency.exe"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            # Run
            run_result = subprocess.run(
                ["./_build/default/consistency/test_consistency.exe"],
                capture_output=True,
                text=True,
            )
            if "Consistency check passed" in run_result.stdout:
                print("[OK] Multi-module CRC consistency")
                success = True
            else:
                print("[FAIL] Execution failed")
                print(f"  output: {run_result.stdout}")
        else:
            print("[FAIL] Build failed - possible CRC mismatch")
            print(f"  stderr: {result.stderr}")

    finally:
        os.chdir(original_dir)
        shutil.rmtree(test_dir, ignore_errors=True)

    return handle_test_result("CRC consistency tests", success)


if __name__ == "__main__":
    sys.exit(main())
