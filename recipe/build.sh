#!/usr/bin/env bash
set -euxo pipefail

# ==============================================================================
# DUNE BUILD SCRIPT (Standalone Recipe)
# ==============================================================================
# Build the Dune build system for OCaml using the upstream Makefile.
# Standalone version - source extracts to ${SRC_DIR} directly.
# ==============================================================================

source "${RECIPE_DIR}/building/build_functions.sh"

# ==============================================================================
# ENVIRONMENT SETUP
# ==============================================================================

cd "${SRC_DIR}"

# OCaml 5.4 Makefile.config includes $(LDFLAGS) in MKEXE/MKDLL.
# Strip -fuse-ld=lld from conda's LDFLAGS — OCaml uses its own linker
# (ld64 on macOS, ld on Linux, MSVC link.exe on Windows), not lld.
export LDFLAGS="${LDFLAGS:-}"
export LDFLAGS="${LDFLAGS//-fuse-ld=lld/}"

# Cross-compilation: Ensure linker finds target libs (PREFIX) before build libs (BUILD_PREFIX)
# LIBRARY_PATH affects clang/ld64 at link time (both macOS and Linux)
if is_cross_compile; then
  export LIBRARY_PATH="${PREFIX}/lib:${BUILD_PREFIX}/lib:${LIBRARY_PATH:-}"
fi

# macOS: Set runtime library path for zstd (runtime loading, not linking)
if is_macos; then
  export DYLD_FALLBACK_LIBRARY_PATH="${PREFIX}/lib:${BUILD_PREFIX}/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"
fi

# Set install prefix
if is_non_unix; then
  export DUNE_INSTALL_PREFIX="${_PREFIX_}/Library"
  export PATH="${BUILD_PREFIX}/bin:${BUILD_PREFIX}/Library/bin:${PATH}"
else
  export DUNE_INSTALL_PREFIX="${PREFIX}"
fi

# ==============================================================================
# BUILD
# ==============================================================================

echo "=== Cross-compilation detection ==="
echo "  CONDA_BUILD_CROSS_COMPILATION: ${CONDA_BUILD_CROSS_COMPILATION:-not set}"
echo "  is_cross_compile: $(is_cross_compile && echo 'true' || echo 'false')"

if is_cross_compile; then
  source "${RECIPE_DIR}/building/cross_functions.sh"

  echo "=== Cross-compilation build ==="
  cross_compile_with_native_dune "${DUNE_INSTALL_PREFIX}"

elif is_non_unix; then
  echo "=== non-unix build ==="
  export PATH="${BUILD_PREFIX}/Library/mingw-w64/bin:${BUILD_PREFIX}/Library/bin:${BUILD_PREFIX}/bin:${PATH}"

  # Hide MSYS2 coreutils 'link' so OCaml finds MSVC's 'link.exe' for linking
  # MSYS2's link creates hard links; MSVC's link.exe is the actual linker
  for _link_dir in "${BUILD_PREFIX}/usr/bin" "${BUILD_PREFIX}/bin" "${BUILD_PREFIX}/Library/usr/bin"; do
    if [[ -f "${_link_dir}/link" ]]; then
      echo "Hiding MSYS2 link at ${_link_dir}/link"
      mv "${_link_dir}/link" "${_link_dir}/link.msys2"
    fi
  done
  # Verify which link will be used
  echo "link resolves to: $(which link 2>/dev/null || echo 'not found')"

  # Fix Dune which.ml double-.exe bug on Windows
  # Dune blindly appends .exe without checking if already present
  if [[ -f "${RECIPE_DIR}/patches/xxxx-fix-dune-which-double-exe-on-windows.patch" ]]; then
    echo "Applying double-.exe fix patch..."
    patch -p1 < "${RECIPE_DIR}/patches/xxxx-fix-dune-which-double-exe-on-windows.patch"
  fi

  make release
  make PREFIX="${DUNE_INSTALL_PREFIX}" install
else
  echo "=== Native build ==="
  make release
  make PREFIX="${DUNE_INSTALL_PREFIX}" install
fi

# ==============================================================================
# INSTALL ACTIVATION SCRIPTS
# ==============================================================================

ACTIVATE_DIR="${PREFIX}/etc/conda/activate.d"
DEACTIVATE_DIR="${PREFIX}/etc/conda/deactivate.d"
mkdir -p "${ACTIVATE_DIR}" "${DEACTIVATE_DIR}"

if is_non_unix; then
  cp "${RECIPE_DIR}/activation/dune-activate.bat" "${ACTIVATE_DIR}/dune-activate.bat"
  cp "${RECIPE_DIR}/activation/dune-deactivate.bat" "${DEACTIVATE_DIR}/dune-deactivate.bat"
else
  cp "${RECIPE_DIR}/activation/dune-activate.sh" "${ACTIVATE_DIR}/dune-activate.sh"
  cp "${RECIPE_DIR}/activation/dune-deactivate.sh" "${DEACTIVATE_DIR}/dune-deactivate.sh"
fi

# ==============================================================================
# WRITE OCAML BUILD VERSION FOR TESTS
# ==============================================================================
# Tests need to know the OCaml version used during build to distinguish
# between known bugs (OCaml <= 5.3.0) and real failures (OCaml >= 5.4.0)

TEST_FILES_DIR="${PREFIX}/etc/conda/test-files"
mkdir -p "${TEST_FILES_DIR}"
OCAML_BUILD_VERSION=$(ocamlc -version)
echo "${OCAML_BUILD_VERSION}" > "${TEST_FILES_DIR}/ocaml-build-version"
echo "Wrote OCaml build version ${OCAML_BUILD_VERSION} to ${TEST_FILES_DIR}/ocaml-build-version"

# ==============================================================================
# FIX MAN PAGE AND EMACS LOCATIONS
# ==============================================================================

mkdir -p "${DUNE_INSTALL_PREFIX}"/share/man/man{1,5} || { echo "Cannot create MANDIR"; exit 1; }

mv "${DUNE_INSTALL_PREFIX}"/man/man1/* "${DUNE_INSTALL_PREFIX}/share/man/man1/"
mv "${DUNE_INSTALL_PREFIX}"/man/man5/* "${DUNE_INSTALL_PREFIX}/share/man/man5/"

mkdir -p "${DUNE_INSTALL_PREFIX}/share/emacs/site-lisp/dune" || { echo "Cannot create site-lisp"; exit 1; }
mv "${DUNE_INSTALL_PREFIX}"/share/emacs/site-lisp/*.el "${DUNE_INSTALL_PREFIX}/share/emacs/site-lisp/dune/" 2>/dev/null || true

# ==============================================================================
# VERIFY INSTALLATION
# ==============================================================================

if is_non_unix; then
  DUNE_BIN="${DUNE_INSTALL_PREFIX}/bin/dune.exe"
else
  DUNE_BIN="${DUNE_INSTALL_PREFIX}/bin/dune"
fi

if [[ -f "${DUNE_BIN}" ]]; then
  echo "=== Dune installed successfully ==="
  echo "Binary: ${DUNE_BIN}"
  if ! is_non_unix; then
    file "${DUNE_BIN}" || true
    # Strip binary on Linux to reduce size (macOS: breaks code signature)
    if is_linux; then
      echo "Stripping binary..."
      strip "${DUNE_BIN}" || true
    fi
  fi
else
  echo "ERROR: Dune binary not found at ${DUNE_BIN}"
  exit 1
fi

echo "=== Dune build complete ==="
