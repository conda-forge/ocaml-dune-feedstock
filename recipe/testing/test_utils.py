#!/usr/bin/env python3
"""Shared test utilities for dune package tests."""

import os
import platform
from functools import lru_cache
from pathlib import Path


def get_prefix() -> Path:
    """Get the conda prefix path."""
    prefix = os.environ.get("PREFIX", os.environ.get("CONDA_PREFIX", ""))
    if not prefix:
        # Fallback for local testing
        return Path("/usr")
    return Path(prefix)


@lru_cache(maxsize=1)
def get_ocaml_build_version() -> tuple[int, int, int] | None:
    """Get OCaml version that was used during build.

    Reads from etc/conda/test-files/ocaml-build-version file written during build.

    Returns:
        Tuple of (major, minor, patch) version numbers.
        Returns None if the version file is missing or cannot be parsed.
        Callers must check for None explicitly rather than compare it as a
        tuple.
    """
    prefix = get_prefix()
    version_file = prefix / "etc" / "conda" / "test-files" / "ocaml-build-version"

    try:
        version_str = version_file.read_text().strip()
        parts = version_str.split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2].split("+")[0]))
    except (FileNotFoundError, IndexError, ValueError):
        print(f"WARNING: could not read/parse OCaml build version from {version_file}")
        return None


def get_ocaml_build_version_str() -> str:
    """Get OCaml build version as a string."""
    version = get_ocaml_build_version()
    if version is None:
        return "unknown"
    return f"{version[0]}.{version[1]}.{version[2]}"


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


def handle_test_result(test_name: str, success: bool) -> int:
    """Report a test result. Returns 0 on success, 1 on failure."""
    if success:
        print(f"\n=== {test_name} passed ===")
        return 0
    print(f"\n=== {test_name} FAILED ===")
    print(f"  Build OCaml version: {get_ocaml_build_version_str()}")
    print(f"  Target architecture: {get_target_arch()}")
    return 1
