#!/usr/bin/env python3
"""Test: dune toolchain path tests (C stubs, ocamllex)

Exercises two toolchain paths that the other dune functional tests never
touch:
- C stubs: builds a library with (foreign_stubs (language c) ...), which
  invokes the C compiler and linker. This is the path where the win gcc
  and vs2022 ocaml variants genuinely differ.
- ocamllex: builds a lexer via (ocamllex ...), exercising the tool whose
  resolution historically broke on win_64.

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
        return False, (
            f"exit code {result.returncode}\n"
            f"  stdout: {result.stdout}\n"
            f"  stderr: {result.stderr}"
        )
    if check_output and check_output not in result.stdout:
        return False, (
            f"output missing '{check_output}'\n"
            f"  stdout: {result.stdout}\n"
            f"  stderr: {result.stderr}"
        )
    return True, result.stdout


def run_build_test(build_cmd, run_cmd_args, expected_output):
    """Run a build test and return success status with details.

    Returns:
        Tuple of (success: bool, error_msg: str or None)
    """
    result = subprocess.run(build_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return False, (
            f"build failed (exit {result.returncode})\n"
            f"  stdout: {result.stdout}\n"
            f"  stderr: {result.stderr}"
        )

    ok, msg = run_cmd(run_cmd_args, expected_output)
    if not ok:
        return False, f"run failed: {msg}"

    return True, None


def main():
    print("=== Dune Toolchain Path Tests (C stubs, ocamllex) ===")

    # dune's cache init can crash on windows before anything is compiled:
    # Code_error out of create_cache_directories, seen here on the runner's
    # 8.3 short-name TEMP path. The other dune tests build in the same kind
    # of tempdir without tripping it, so the trigger is not fully pinned
    # down. Each test below builds once in a throwaway tempdir, so the cache
    # buys nothing here either way.
    os.environ["DUNE_CACHE"] = "disabled"

    apply_ocaml_530_workaround()

    test_dir = tempfile.mkdtemp(prefix="dune_stubs_")
    original_dir = os.getcwd()
    test_results = []  # List of (test_name, success) tuples

    try:
        os.chdir(test_dir)

        # Test 1: C stubs - exercises the C compiler and linker path used by
        # dune's (foreign_stubs (language c) ...), where the win gcc and
        # vs2022 ocaml variants genuinely differ.
        print("\n=== Test 1: C stubs (foreign_stubs) ===")
        os.makedirs("cstubs", exist_ok=True)
        os.chdir("cstubs")

        write_file("dune-project", "(lang dune 3.0)")
        write_file(
            "dune",
            """(library
 (name withstubs)
 (modules withstubs)
 (foreign_stubs
  (language c)
  (names cstub)))

(executable
 (name main)
 (modules main)
 (libraries withstubs))""",
        )
        write_file(
            "cstub.c",
            """#include <caml/mlvalues.h>
#include <caml/memory.h>

CAMLprim value caml_stub_add(value a, value b)
{
  CAMLparam2(a, b);
  CAMLreturn(Val_int(Int_val(a) + Int_val(b)));
}
""",
        )
        write_file(
            "withstubs.ml",
            """external stub_add : int -> int -> int = "caml_stub_add"

let add a b = stub_add a b
""",
        )
        write_file(
            "main.ml",
            'let () = Printf.printf "stubs:%d\\n" (Withstubs.add 40 2)',
        )

        success, err = run_build_test(
            ["dune", "build", "main.exe"],
            ["./_build/default/main.exe"],
            "stubs:42",
        )
        if success:
            print("[OK] C stubs build + run")
        else:
            print(f"[FAIL] C stubs: {err}")
        test_results.append(("C stubs build", success))

        os.chdir(test_dir)

        # Test 2: ocamllex - exercises the ocamllex tool, whose resolution
        # historically broke on win_64.
        print("\n=== Test 2: ocamllex ===")
        os.makedirs("ocamllex_test", exist_ok=True)
        os.chdir("ocamllex_test")

        write_file("dune-project", "(lang dune 3.0)")
        write_file(
            "dune",
            """(ocamllex lexer)

(executable
 (name main)
 (modules main lexer))""",
        )
        write_file(
            "lexer.mll",
            """{
type token = INT of int | EOF
}

rule token = parse
  | [' ' '\\t']      { token lexbuf }
  | ['0'-'9']+ as n { INT (int_of_string n) }
  | eof             { EOF }
""",
        )
        write_file(
            "main.ml",
            """let () =
  let buf = Lexing.from_string "  7 " in
  match Lexer.token buf with
  | Lexer.INT n -> Printf.printf "lex:%d\\n" n
  | Lexer.EOF -> print_endline "lex:eof"
""",
        )

        success, err = run_build_test(
            ["dune", "build", "main.exe"],
            ["./_build/default/main.exe"],
            "lex:7",
        )
        if success:
            print("[OK] ocamllex build + run")
        else:
            print(f"[FAIL] ocamllex: {err}")
        test_results.append(("ocamllex build", success))

        os.chdir(test_dir)

    finally:
        os.chdir(original_dir)
        shutil.rmtree(test_dir, ignore_errors=True)

    # Aggregate results using version-aware handling
    all_passed = all(success for _, success in test_results)
    failed_tests = [name for name, success in test_results if not success]

    if all_passed:
        print("\n=== All dune toolchain path tests passed ===")
        return 0

    # Use handle_test_result for version-aware failure handling
    # arch_sensitive=True: only document as known bug on aarch64/ppc64le
    test_summary = f"Toolchain path tests ({', '.join(failed_tests)})"
    return handle_test_result(test_summary, success=False, arch_sensitive=True)


if __name__ == "__main__":
    sys.exit(main())
