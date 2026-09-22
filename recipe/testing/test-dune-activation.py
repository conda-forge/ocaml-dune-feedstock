#!/usr/bin/env python3
"""Test: dune activation/deactivation OCAMLPATH handling

Verifies the shipped dune-activate.sh / dune-deactivate.sh scripts set and
restore OCAMLPATH correctly, including the build-mode case where both
PREFIX (host) and BUILD_PREFIX are set (issue #19): OCAMLPATH must then
start with "$PREFIX/lib/ocaml:$BUILD_PREFIX/lib/ocaml" so host OCaml
libraries are visible when ocaml-dune is a build dependency.
"""

import subprocess
import sys
from pathlib import Path

from test_utils import get_prefix

UNSET = "<unset>"


def get_scripts() -> tuple[Path, Path]:
    prefix = get_prefix()
    activate = prefix / "etc" / "conda" / "activate.d" / "dune-activate.sh"
    deactivate = prefix / "etc" / "conda" / "deactivate.d" / "dune-deactivate.sh"
    return activate, deactivate


def read_var(output: str, name: str) -> str:
    marker = f"{name}="
    for line in output.splitlines():
        if line.startswith(marker):
            return line[len(marker) :]
    return UNSET


def run_snippet(snippet: str, env: dict) -> str:
    full_env = dict(env)
    full_env.setdefault("PATH", "/usr/bin:/bin")
    result = subprocess.run(
        ["bash", "-c", snippet],
        env=full_env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"  bash exited {result.returncode}")
        print(f"  stderr: {result.stderr.strip()}")
    return result.stdout


def check_activation(name: str, env: dict, activate_script: Path, expected: str) -> bool:
    print(f"\n=== {name} ===")
    snippet = f'source "{activate_script}"\nprintf \'OCAMLPATH=%s\\n\' "${{OCAMLPATH-{UNSET}}}"'
    output = run_snippet(snippet, env)
    actual = read_var(output, "OCAMLPATH")
    if actual == expected:
        print(f"  OK: OCAMLPATH={actual}")
        return True
    print(f"  FAIL: expected OCAMLPATH={expected!r}, got {actual!r}")
    return False


def check_deactivation(name: str, env: dict, activate_script: Path, deactivate_script: Path, expected: str) -> bool:
    print(f"\n=== {name} ===")
    snippet = (
        f'source "{activate_script}"\n'
        f'source "{deactivate_script}"\n'
        f'printf \'OCAMLPATH=%s\\n\' "${{OCAMLPATH-{UNSET}}}"'
    )
    output = run_snippet(snippet, env)
    actual = read_var(output, "OCAMLPATH")
    if actual == expected:
        print(f"  OK: OCAMLPATH={actual}")
        return True
    print(f"  FAIL: expected OCAMLPATH={expected!r}, got {actual!r}")
    return False


def main() -> int:
    print("=== Dune Activation OCAMLPATH Tests ===")

    if sys.platform == "win32":
        print("SKIP: dune-activate.sh/dune-deactivate.sh are not shipped on Windows "
              "(only dune-activate.bat); skipping shell activation tests.")
        return 0

    activate_script, deactivate_script = get_scripts()

    missing = [str(p) for p in (activate_script, deactivate_script) if not p.is_file()]
    if missing:
        print("=== FAILED: shipped activation script(s) not found ===")
        for m in missing:
            print(f"  missing: {m}")
        return 1

    errors = 0

    # a) build mode: host + build prefix both on OCAMLPATH, host first
    ok = check_activation(
        "build mode: host prefix prepended before build prefix",
        {
            "PREFIX": "/tmp/dune-host",
            "BUILD_PREFIX": "/tmp/dune-build",
            "CONDA_PREFIX": "/tmp/dune-build",
            "CONDA_BUILD": "1",
        },
        activate_script,
        "/tmp/dune-host/lib/ocaml:/tmp/dune-build/lib/ocaml",
    )
    errors += 0 if ok else 1

    # b) user mode: single prefix
    ok = check_activation(
        "user mode: single CONDA_PREFIX on OCAMLPATH",
        {"CONDA_PREFIX": "/tmp/dune-env"},
        activate_script,
        "/tmp/dune-env/lib/ocaml",
    )
    errors += 0 if ok else 1

    # c) pre-existing value preserved
    ok = check_activation(
        "user mode: pre-existing OCAMLPATH preserved",
        {"CONDA_PREFIX": "/tmp/dune-env", "OCAMLPATH": "/opt/x"},
        activate_script,
        "/tmp/dune-env/lib/ocaml:/opt/x",
    )
    errors += 0 if ok else 1

    # d) deactivation restores pre-existing value
    ok = check_deactivation(
        "deactivation: restores pre-existing OCAMLPATH",
        {"CONDA_PREFIX": "/tmp/dune-env", "OCAMLPATH": "/opt/x"},
        activate_script,
        deactivate_script,
        "/opt/x",
    )
    errors += 0 if ok else 1

    # e) deactivation with no original value leaves OCAMLPATH unset
    ok = check_deactivation(
        "deactivation: no original value leaves OCAMLPATH unset",
        {"CONDA_PREFIX": "/tmp/dune-env"},
        activate_script,
        deactivate_script,
        UNSET,
    )
    errors += 0 if ok else 1

    if errors > 0:
        print(f"\n=== FAILED: {errors} error(s) ===")
        return 1

    print("\n=== Activation OCAMLPATH tests passed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
