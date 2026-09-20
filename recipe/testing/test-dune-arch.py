#!/usr/bin/env python3
"""Test: dune binary architecture validation

Verifies dune binary is built for a recognized architecture.
Works cross-platform using Python's struct module for PE parsing on Windows.
"""

import os
import platform
import shutil
import struct
import subprocess
import sys

# Acceptable arch substrings (as they appear in `file` output / PE machine
# type labels, lower-cased for comparison) for each conda target_platform.
# An unrecognized target_platform has no entry here and must FAIL.
TARGET_ARCH_PATTERNS = {
    "linux-64": ("x86-64", "x86_64"),
    "win-64": ("x86-64", "x86_64"),
    "osx-64": ("x86_64", "x86-64"),
    "linux-aarch64": ("aarch64", "arm64"),
    "osx-arm64": ("aarch64", "arm64"),
    "linux-ppc64le": ("powerpc64le", "PowerPC", "ppc64"),
}

# Broader set used only to produce a human-readable label of whatever arch
# was actually detected, for diagnostics on mismatch.
KNOWN_ARCH_LABELS = [
    ("aarch64", "aarch64 (ARM 64-bit)"),
    ("arm aarch64", "aarch64 (ARM 64-bit)"),
    ("arm64", "arm64 (macOS ARM)"),
    ("x86-64", "x86_64 (AMD 64-bit)"),
    ("x86_64", "x86_64 (AMD 64-bit)"),
    ("powerpc64le", "ppc64le (POWER 64-bit)"),
    ("powerpc", "ppc64le (POWER 64-bit)"),
    ("ppc64", "ppc64le (POWER 64-bit)"),
]


def get_expected_arch_patterns(target_platform):
    """Return the acceptable arch substrings for a target_platform, or None
    if the target_platform is not recognized."""
    return TARGET_ARCH_PATTERNS.get(target_platform)


def detect_arch_label(arch_info):
    """Best-effort human-readable label for whatever arch is present."""
    for pattern, name in KNOWN_ARCH_LABELS:
        if pattern in arch_info:
            return name
    return "unrecognized"


def check_unix_arch(binary_path, target_platform):
    """Check architecture using file command on Unix and compare against
    the actual target_platform (no fixed allow-list shortcut)."""
    result = subprocess.run(
        ["file", binary_path],
        capture_output=True,
        text=True,
        check=False,
    )
    raw_output = result.stdout.strip()
    arch_info = result.stdout.lower()
    print(f"File info: {raw_output}")

    detected_label = detect_arch_label(arch_info)
    print(f"  Detected architecture: {detected_label}")

    expected_patterns = get_expected_arch_patterns(target_platform)
    if expected_patterns is None:
        print(f"[FAIL] Unrecognized target_platform: {target_platform}")
        return False

    if any(pattern.lower() in arch_info for pattern in expected_patterns):
        print(f"[OK] Architecture matches target_platform={target_platform}")
        return True

    print(f"[FAIL] Binary architecture does not match target_platform={target_platform}")
    print(f"  Expected one of: {expected_patterns}")
    print(f"  Detected architecture: {detected_label}")
    print(f"  file output: {raw_output}")
    return False


def check_windows_arch(binary_path, target_platform):
    """Check PE architecture on Windows and compare against the actual
    target_platform (no fixed allow-list shortcut)."""
    expected_patterns = get_expected_arch_patterns(target_platform)
    if expected_patterns is None:
        print(f"[FAIL] Unrecognized target_platform: {target_platform}")
        return False

    # Machine type -> (human label, arch substrings comparable to
    # TARGET_ARCH_PATTERNS). Empty tuple means "never matches any target".
    machine_archs = {
        0x8664: ("AMD64 (x86-64)", ("x86-64", "x86_64")),
        0x014C: ("i386 (x86)", ()),
        0xAA64: ("ARM64", ("aarch64", "arm64")),
    }

    try:
        with open(binary_path, "rb") as f:
            # Read DOS header
            dos_header = f.read(64)
            if dos_header[:2] != b"MZ":
                print("[FAIL] Not a valid DOS/PE file")
                return False

            # Get PE header offset from DOS header at 0x3C
            pe_offset = struct.unpack("<I", dos_header[0x3C:0x40])[0]

            # Read PE signature
            f.seek(pe_offset)
            pe_sig = f.read(4)
            if pe_sig != b"PE\x00\x00":
                print("[FAIL] Invalid PE signature")
                return False

            # Read machine type (2 bytes after PE signature)
            machine_type = struct.unpack("<H", f.read(2))[0]

            if machine_type not in machine_archs:
                print(f"[FAIL] Unknown machine type: 0x{machine_type:04X}")
                return False

            name, arch_patterns = machine_archs[machine_type]
            print(f"  Machine type: {name}")

            if machine_type == 0x014C:
                print("[FAIL] Expected 64-bit, got 32-bit x86")
                return False

            if any(pattern in arch_patterns for pattern in expected_patterns):
                print(f"[OK] Architecture matches target_platform={target_platform}")
                return True

            print(f"[FAIL] Binary architecture does not match target_platform={target_platform}")
            print(f"  Expected one of: {expected_patterns}")
            print(f"  Detected machine type: {name}")
            return False

    except Exception as e:
        print(f"[FAIL] Failed to read PE header: {e}")
        return False


def main():
    print("=== Dune Binary Architecture Tests ===")

    # target_platform is set by rattler-build (see recipe/building/build_functions.sh
    # for sibling helpers relying on it). Without it we cannot know what arch
    # the binary is supposed to be, so we must fail loudly rather than skip.
    target_platform = os.environ.get("target_platform", "")
    if not target_platform:
        print("[FAIL] target_platform environment variable is not set")
        print("  Cannot validate binary architecture without a target to compare against")
        return 1
    print(f"Target platform: {target_platform}")

    # Find dune binary
    dune_path = shutil.which("dune")
    if not dune_path:
        print("[FAIL] dune not found in PATH")
        return 1

    # shutil.which already resolves the PATHEXT suffix on Windows and only
    # returns a path that exists, so the name it hands back is used as-is.

    print(f"Binary: {dune_path}")

    if platform.system() == "Windows":
        success = check_windows_arch(dune_path, target_platform)
    else:
        success = check_unix_arch(dune_path, target_platform)

    if success:
        print("\n=== Architecture tests passed ===")
        return 0
    else:
        print("\n=== Architecture tests FAILED ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())
