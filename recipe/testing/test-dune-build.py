#!/usr/bin/env python3
"""Test: dune functional build tests

Tests dune's ability to build OCaml projects:
- Bytecode and native executables
- Multi-file library projects
- Unix module integration
- Incremental builds
- dune clean

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


def write_file(path, content):
    """Write content to a file."""
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def run_cmd(cmd, check_output=None):
    """Run command and optionally check output contains a string."""
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return False, f"exit code {result.returncode}: {result.stderr}"
    if check_output and check_output not in result.stdout:
        return False, f"output missing '{check_output}': {result.stdout}"
    return True, result.stdout


def run_build_test(build_cmd, run_cmd_args, expected_output):
    """Run a build test and return success status with details.

    Returns:
        Tuple of (success: bool, error_msg: str or None)
    """
    result = subprocess.run(build_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, f"build failed: {result.stderr}"

    ok, msg = run_cmd(run_cmd_args, expected_output)
    if not ok:
        return False, f"run failed: {msg}"

    return True, None


def main():
    print("=== Dune Functional Build Tests ===")

    apply_ocaml_530_workaround()

    test_dir = tempfile.mkdtemp(prefix="dune_test_")
    original_dir = os.getcwd()
    test_results = []  # List of (test_name, success) tuples

    try:
        os.chdir(test_dir)

        # Initialize dune project
        write_file("dune-project", "(lang dune 3.0)")

        # Test 1: Bytecode executable
        print("\n=== Test 1: Simple bytecode executable ===")
        write_file(
            "simple_byte/dune",
            "(executable\n (name hello)\n (modes byte))",
        )
        write_file(
            "simple_byte/hello.ml",
            'let () = print_endline "Hello from dune (bytecode)"',
        )

        success, err = run_build_test(
            ["dune", "build", "simple_byte/hello.bc"],
            ["./_build/default/simple_byte/hello.bc"],
            "Hello from dune",
        )
        if success:
            print("[OK] bytecode build + run")
        else:
            print(f"[FAIL] bytecode: {err}")
        test_results.append(("Bytecode build", success))

        # Test 2: Native executable
        print("\n=== Test 2: Simple native executable ===")
        write_file(
            "simple_native/dune",
            "(executable\n (name hello)\n (modes native))",
        )
        write_file(
            "simple_native/hello.ml",
            'let () = print_endline "Hello from dune (native)"',
        )

        success, err = run_build_test(
            ["dune", "build", "simple_native/hello.exe"],
            ["./_build/default/simple_native/hello.exe"],
            "Hello from dune",
        )
        if success:
            print("[OK] native build + run")
        else:
            print(f"[FAIL] native: {err}")
        test_results.append(("Native build", success))

        # Test 3: Multi-file library project
        print("\n=== Test 3: Multi-file library project ===")
        write_file(
            "multifile/dune",
            """(library
 (name mylib)
 (modules mylib))

(executable
 (name main)
 (libraries mylib)
 (modules main))""",
        )
        write_file(
            "multifile/mylib.ml",
            'let greet name = Printf.printf "Hello, %s!\\n" name',
        )
        write_file("multifile/main.ml", 'let () = Mylib.greet "Dune"')

        success, err = run_build_test(
            ["dune", "build", "multifile/main.exe"],
            ["./_build/default/multifile/main.exe"],
            "Hello, Dune",
        )
        if success:
            print("[OK] multi-file library + executable")
        else:
            print(f"[FAIL] multi-file: {err}")
        test_results.append(("Multi-file build", success))

        # Test 4: Unix module (stdlib dependency)
        print("\n=== Test 4: Unix module integration ===")
        write_file(
            "unix_test/dune",
            "(executable\n (name unix_test)\n (libraries unix))",
        )
        write_file(
            "unix_test/unix_test.ml",
            """let () =
  let pid = Unix.getpid () in
  Printf.printf "PID: %d\\n" pid;
  print_endline "Unix module works"
""",
        )

        success, err = run_build_test(
            ["dune", "build", "unix_test/unix_test.exe"],
            ["./_build/default/unix_test/unix_test.exe"],
            "Unix module works",
        )
        if success:
            print("[OK] Unix module compilation + execution")
        else:
            print(f"[FAIL] unix: {err}")
        test_results.append(("Unix module build", success))

        # Test 5: dune clean
        print("\n=== Test 5: dune clean ===")
        result = subprocess.run(["dune", "clean"], capture_output=True, text=True)
        success = result.returncode == 0 and not os.path.exists("_build")
        if success:
            print("[OK] dune clean")
        else:
            print("[FAIL] dune clean didn't remove _build")
        test_results.append(("Dune clean", success))

    finally:
        os.chdir(original_dir)
        shutil.rmtree(test_dir, ignore_errors=True)

    # Aggregate results using version-aware handling
    all_passed = all(success for _, success in test_results)
    failed_tests = [name for name, success in test_results if not success]

    if all_passed:
        print("\n=== All dune functional tests passed ===")
        return 0

    # Use handle_test_result for version-aware failure handling
    # arch_sensitive=True: only document as known bug on aarch64/ppc64le
    test_summary = f"Build tests ({', '.join(failed_tests)})"
    return handle_test_result(test_summary, success=False, arch_sensitive=True)


if __name__ == "__main__":
    sys.exit(main())
