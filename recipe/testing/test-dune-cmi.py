#!/usr/bin/env python3
"""Test: dune interface consistency (CRC) tests

Tests that uses multiple stdlib modules to catch CRC mismatches
between compiled interfaces.

OCaml 5.3.0 aarch64/ppc64le known bugs are documented but don't fail the build.
OCaml 5.4.0+ failures are treated as real errors.
"""

import os
import shutil
import subprocess
import sys
import tempfile

from test_utils import (
    get_ocaml_build_version_str,
    get_target_arch,
    handle_test_result,
)


def apply_ocaml_530_workaround():
    """Apply OCaml 5.3.0 aarch64/ppc64le GC workaround if needed."""
    ocaml_version = get_ocaml_build_version_str()
    arch = get_target_arch()

    print(f"OCaml version: {ocaml_version}")
    print(f"Architecture: {arch}")

    if ocaml_version.startswith("5.3.") and arch in ("aarch64", "ppc64le", "arm64"):
        print("Applying OCaml 5.3.0 GC workaround (s=16M)")
        os.environ["OCAMLRUNPARAM"] = "s=16M"

    print(f"OCAMLRUNPARAM: {os.environ.get('OCAMLRUNPARAM', '<default>')}")


def main():
    print("=== Dune Interface Consistency Tests ===")

    apply_ocaml_530_workaround()

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

    # Use handle_test_result for version-aware failure handling
    return handle_test_result("CRC consistency tests", success, arch_sensitive=True)


if __name__ == "__main__":
    sys.exit(main())
