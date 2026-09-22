#!/usr/bin/env python3
"""Shared test utilities for dune package tests."""

import os
import platform
import subprocess
from pathlib import Path


def get_prefix() -> Path:
    """Get the conda prefix path."""
    prefix = os.environ.get("PREFIX", os.environ.get("CONDA_PREFIX", ""))
    if not prefix:
        # Fallback for local testing
        return Path("/usr")
    return Path(prefix)


def get_target_arch() -> str:
    """Get the target architecture, handling cross-compilation.

    On CI runners, cross-compiled packages run under QEMU but platform.machine()
    returns the HOST arch (x86_64), not the TARGET arch (aarch64/ppc64le).

    Check conda's target_platform env var first, then fall back to platform.machine().
    """
    target_platform = os.environ.get("target_platform", "")
    if "aarch64" in target_platform:
        return "aarch64"
    if "ppc64le" in target_platform:
        return "ppc64le"
    if "arm64" in target_platform:
        return "arm64"
    return platform.machine().lower()


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


def handle_test_result(test_name: str, success: bool) -> int:
    """Report a test result. Returns 0 on success, 1 on failure."""
    if success:
        print(f"\n=== {test_name} passed ===")
        return 0
    print(f"\n=== {test_name} FAILED ===")
    print(f"  Target architecture: {get_target_arch()}")
    return 1
