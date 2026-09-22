#!/usr/bin/env python3
"""Diagnostic probe: why dune's cache init crashes on windows.

DIAGNOSTIC ONLY - this always exits 0 and can never fail the lane. Read
its output; do not gate on it.

test-dune-stubs.py died on the win lanes inside dune's cache init
(Code_error out of create_cache_directories) before compiling anything.
The recorded crash path was

    <tempdir>\\dune_stubs_xxx\\cstubs/dune/db

which decomposes as cwd + 'dune/db'. Dune's cache root should be
<xdg_cache_home>/dune/db, so the xdg cache dir apparently resolved to
EMPTY and the cache root became a RELATIVE path resolved against cwd.

Hypothesis, two preconditions BOTH required:
  1. HOME / XDG_CACHE_HOME unset, so the cache root lands in cwd.
  2. cwd holds a file literally named 'dune' (the stanza file), so mkdir_p
     is asked to create a directory through a regular file.

Precondition 2 is already established statically: test-dune-stubs.py is
the only test that chdirs into a directory containing a 'dune' file;
test-dune-build.py and test-dune-cmi.py keep their stanzas in subdirs and
build from the project root. This probe measures precondition 1, and
checks that the DUNE_CACHE=disabled workaround shipped in
test-dune-stubs.py actually works.

Arms:
  A flat layout,   inherited env          - reproduces the failure?
  B subdir layout, inherited env          - control for precondition 2
  C flat layout,   XDG_CACHE_HOME absolute - control for precondition 1
  D flat layout,   DUNE_CACHE=disabled    - does the shipped fix hold?
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile

from test_utils import write_file

BUILD_TIMEOUT = 300

DUNE_PROJECT = "(lang dune 3.0)"
DUNE_STANZA = """(executable
 (name main))"""
MAIN_ML = 'let () = print_endline "probe:ok"'

ENV_KEYS = (
    "HOME",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "XDG_CACHE_HOME",
    "DUNE_CACHE",
    "DUNE_CACHE_ROOT",
    "TEMP",
    "TMP",
)


def report_env():
    """Print the environment values that decide where dune puts its cache."""
    print("--- environment ---")
    for key in ENV_KEYS:
        print(f"  {key}={os.environ.get(key, '<unset>')}")
    print(f"  platform={platform.system()}")
    print(f"  gettempdir={tempfile.gettempdir()}")


def report_known_folders():
    """Ask Windows directly for the folders dune's xdg layer uses.

    dune's otherlibs/xdg/xdg_stubs.c calls SHGetKnownFolderPath for
    FOLDERID_InternetCache and maps any non-S_OK result to None.
    otherlibs/xdg/xdg.ml turns that None into "", and dune then resolves
    that empty string against the current directory, which is how the cache
    root ends up in the project. This reports what Windows actually returns
    so that step is observed rather than deduced.
    """
    if platform.system() != "Windows":
        print("  (not windows, skipped)")
        return

    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        def make_guid(d1, d2, d3, tail):
            return GUID(d1, d2, d3, (ctypes.c_ubyte * 8)(*tail))

        folders = [
            (
                "FOLDERID_InternetCache (dune's cache_dir default)",
                make_guid(
                    0x352481E8,
                    0x33BE,
                    0x4251,
                    [0xBA, 0x85, 0x60, 0x07, 0xCA, 0xED, 0xCF, 0x9D],
                ),
            ),
            (
                "FOLDERID_LocalAppData (dune's config/data default)",
                make_guid(
                    0xF1B32785,
                    0x6FBA,
                    0x4FCF,
                    [0x9D, 0x55, 0x7B, 0x8E, 0x7F, 0x15, 0x70, 0x91],
                ),
            ),
        ]

        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(GUID),
            wintypes.DWORD,
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long

        for label, folder_id in folders:
            ptr = ctypes.c_wchar_p()
            hr = shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_id), 0, None, ctypes.byref(ptr)
            )
            if hr == 0 and ptr.value:
                print(f"  {label}: S_OK {ptr.value}")
            else:
                print(f"  {label}: FAILED hr=0x{hr & 0xFFFFFFFF:08X}")
                print("    dune maps this to None, then to an empty string,")
                print("    then resolves it against the current directory.")
            if ptr:
                ole32.CoTaskMemFree(ptr)
    except Exception as exc:
        print(f"  known-folder probe could not run: {exc!r}")


def run_arm(label, layout, env_overrides):
    """Build a trivial dune project under one set of conditions.

    layout 'flat'   puts the dune stanza file in cwd (the stubs layout).
    layout 'subdir' puts it in a subdir and builds from the root (the
    build/cmi layout).

    Returns True if the build succeeded, False if it failed, None if the
    arm itself could not run.
    """
    print(f"\n--- arm {label} ({layout} layout, {env_overrides or 'inherited env'}) ---")

    env = os.environ.copy()
    cache_home = None
    for key, value in (env_overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value

    tmp = tempfile.mkdtemp(prefix="probe_dune_")
    original = os.getcwd()
    try:
        if env_overrides and env_overrides.get("XDG_CACHE_HOME") == "<absolute>":
            cache_home = tempfile.mkdtemp(prefix="probe_cache_")
            env["XDG_CACHE_HOME"] = cache_home
            print(f"  XDG_CACHE_HOME={cache_home}")

        if env_overrides and env_overrides.get("HOME") == "<absolute>":
            cache_home = tempfile.mkdtemp(prefix="probe_home_")
            env["HOME"] = cache_home
            print(f"  HOME={cache_home}")

        os.chdir(tmp)
        write_file("dune-project", DUNE_PROJECT)
        if layout == "flat":
            write_file("dune", DUNE_STANZA)
            write_file("main.ml", MAIN_ML)
            target = "main.exe"
        else:
            write_file("sub/dune", DUNE_STANZA)
            write_file("sub/main.ml", MAIN_ML)
            target = "sub/main.exe"

        print(f"  cwd={tmp}")
        print(f"  cwd holds a file named 'dune': {os.path.isfile('dune')}")

        result = subprocess.run(
            ["dune", "build", target],
            capture_output=True,
            text=True,
            env=env,
            timeout=BUILD_TIMEOUT,
        )
        ok = result.returncode == 0
        print(f"  exit={result.returncode} -> {'BUILD OK' if ok else 'BUILD FAILED'}")
        polluted = os.path.isdir(os.path.join("dune", "db"))
        print(f"  cache landed in cwd (a dune/db directory now exists here): {polluted}")
        if not ok:
            print("  stderr:")
            for line in result.stderr.splitlines():
                print(f"    {line}")
        return ok
    except Exception as e:
        print(f"  arm could not run: {e!r}")
        return None
    finally:
        os.chdir(original)
        shutil.rmtree(tmp, ignore_errors=True)
        if cache_home:
            shutil.rmtree(cache_home, ignore_errors=True)


def verdict(a, b, c, d):
    """Map the four arm outcomes onto the hypothesis."""
    print("\n--- verdict ---")

    if a is None:
        print("  INCONCLUSIVE: arm A could not run.")
        return

    if a:
        print("  REFUTED: arm A built fine, so the flat layout under the")
        print("  inherited env does not reproduce the crash. Dune's cache")
        print("  init is not the trigger - look elsewhere in the stubs test.")
        return

    print("  Arm A reproduced the failure.")

    if b:
        print("  Precondition 2 HOLDS: the same build from a subdir layout")
        print("  succeeded, so the 'dune' file in cwd is what collides.")
    elif b is False:
        print("  Precondition 2 DOES NOT HOLD: the subdir layout failed too,")
        print("  so the 'dune' file in cwd is not the discriminator.")

    if c:
        print("  Precondition 1 HOLDS: setting XDG_CACHE_HOME to an absolute")
        print("  path fixed it, so the empty xdg cache dir is what pushes the")
        print("  cache root into cwd.")
    elif c is False:
        print("  Precondition 1 DOES NOT HOLD: an absolute XDG_CACHE_HOME did")
        print("  not help, so the relative cache root is not the mechanism.")

    if d is False:
        print("  WARNING: DUNE_CACHE=disabled did NOT avoid the crash. The")
        print("  workaround shipped in test-dune-stubs.py is insufficient.")
    elif d:
        print("  DUNE_CACHE=disabled avoids it, confirming the shipped")
        print("  workaround in test-dune-stubs.py.")

    if b and c and d:
        print("  => Hypothesis CONFIRMED on both preconditions.")


def read_arm_e(e):
    """Arm E asks whether HOME is the lever at all.

    Measured on win_64 2026-09-19: it is not. An absolute HOME did not move
    the cache, so Xdg.cache_dir does not consult HOME on windows and only
    XDG_CACHE_HOME (arm C) relocates it. A patch teaching dune's HOME
    fallback about USERPROFILE was tried and dropped for this reason. The
    arm is kept so the result is re-measured rather than remembered.
    """
    print("\n--- arm E reading (is HOME the lever?) ---")
    if e is None:
        print("  INCONCLUSIVE: arm E could not run.")
    elif e:
        print("  HOME IS the lever on this platform. That CONTRADICTS the")
        print("  2026-09-19 win_64 measurement, where an absolute HOME")
        print("  changed nothing. Re-check before acting on it.")
    else:
        print("  HOME is NOT the lever, as measured before: Xdg does not")
        print("  consult HOME here, so a fix has to target how the cache dir")
        print("  is resolved, not how HOME is obtained.")


def main():
    print("=== Probe: dune cache init on this platform ===")
    print("(diagnostic only - always exits 0)")

    report_env()

    print("\n--- windows known folders (what dune's xdg asks for) ---")
    report_known_folders()

    a = run_arm("A", "flat", None)
    b = run_arm("B", "subdir", None)
    c = run_arm("C", "flat", {"XDG_CACHE_HOME": "<absolute>"})
    d = run_arm("D", "flat", {"DUNE_CACHE": "disabled"})
    e = run_arm("E", "flat", {"HOME": "<absolute>"})

    verdict(a, b, c, d)
    read_arm_e(e)

    print("\n=== probe complete (exit 0 regardless of findings) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
