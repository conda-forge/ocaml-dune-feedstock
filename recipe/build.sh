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
  if [[ "${target_platform}" == "osx-arm64" ]]; then
    export CONDA_OCAML_AS="arm64-apple-darwin20.0.0-clang -c"
    export CONDA_OCAML_CC="arm64-apple-darwin20.0.0-clang"
    export CONDA_OCAML_MKDLL="arm64-apple-darwin20.0.0-clang -mmacosx-version-min=11.0 -shared -Wl,-headerpad_max_install_names -undefined dynamic_lookup"
    export CONDA_OCAML_MKEXE="arm64-apple-darwin20.0.0-clang -mmacosx-version-min=11.0 -Wl,-headerpad_max_install_names -Wl,-rpath,@executable_path/../lib"
  fi
  export DYLD_FALLBACK_LIBRARY_PATH="${PREFIX}/lib:${BUILD_PREFIX}/lib:${DYLD_FALLBACK_LIBRARY_PATH:-}"
fi

# Set install prefix
if is_non_unix; then
  # BUILD_PREFIX is Windows-form (D:\...). Interpolating it into a colon
  # separated PATH severs the drive letter, leaving entries like
  # \bld\...\build_env/Library/bin that resolve only by accident against the
  # current drive. make does its own PATH search for simple recipe lines and
  # does not resolve them at all. Convert to POSIX form before building PATH.
  if command -v cygpath >/dev/null 2>&1; then
    BUILD_PREFIX_POSIX="$(cygpath -u "${BUILD_PREFIX}")"
  else
    _bp="${BUILD_PREFIX//\\//}"
    BUILD_PREFIX_POSIX="/${_bp%%:*}${_bp#*:}"
  fi
  export DUNE_INSTALL_PREFIX="${PREFIX}/Library"
  export PATH="${BUILD_PREFIX_POSIX}/bin:${BUILD_PREFIX_POSIX}/Library/bin:${PATH}"
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
  export PATH="${BUILD_PREFIX_POSIX}/Library/mingw-w64/bin:${BUILD_PREFIX_POSIX}/Library/bin:${BUILD_PREFIX_POSIX}/bin:${PATH}"

  # A long PATH reaches cmd.exe children EMPTY rather than truncated, so every
  # command they try to resolve fails. Measured on this lane: at 7915 chars
  # `cmd /c "echo %PATH%"` printed nothing and even `where` was unresolvable; at
  # 5064 both work. The exact cutoff is somewhere between those two and is NOT
  # the 8191 figure often quoted for command lines. dune's Makefile runs `ocaml
  # boot/bootstrap.ml`, whose Sys.command reaches cmd.exe, so the bootstrap was
  # the only step that noticed. Dedupe, keeping the first occurrence of each
  # entry; PATH arrives with build_env six times over and the VS block twice.
  echo "win PATH length before dedupe: ${#PATH}"
  _dedup_path=""
  _seen_path=":"
  while IFS= read -r _entry; do
    [ -n "${_entry}" ] || continue
    case "${_seen_path}" in
      *":${_entry}:"*) continue ;;
    esac
    _seen_path="${_seen_path}${_entry}:"
    if [ -z "${_dedup_path}" ]; then
      _dedup_path="${_entry}"
    else
      _dedup_path="${_dedup_path}:${_entry}"
    fi
  done <<< "$(printf '%s' "${PATH}" | tr ':' '\n')"
  export PATH="${_dedup_path}"
  echo "win PATH length after dedupe: ${#PATH}"

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

  # Do NOT pass SHELL= here. The install recipe expands to
  # `dune.exe install --prefix D:\...\h_env/Library dune`, and running that
  # through bash strips the backslashes, so dune installs to a drive-relative
  # path under SRC_DIR and exits 0 having written nothing where we expect it.
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

# dune's own install manifest puts man pages under a top-level man/manN, but the
# package_contents test expects share/man/manN. Move them where they exist.
# Do NOT use `compgen -G` for the existence check: on win_64 MSYS bash it returns
# false even when the glob demonstrably matches, which stranded 38 man pages.
shopt -s nullglob
for _mansec in 1 5; do
  _man_pages=("${DUNE_INSTALL_PREFIX}/man/man${_mansec}"/*)
  if (( ${#_man_pages[@]} )); then
    mv "${_man_pages[@]}" "${DUNE_INSTALL_PREFIX}/share/man/man${_mansec}/"
  else
    echo "no man pages at ${DUNE_INSTALL_PREFIX}/man/man${_mansec}"
  fi
done
shopt -u nullglob

mkdir -p "${DUNE_INSTALL_PREFIX}/share/emacs/site-lisp/dune" || { echo "Cannot create site-lisp"; exit 1; }
shopt -s nullglob
_el_files=("${DUNE_INSTALL_PREFIX}"/share/emacs/site-lisp/*.el)
if (( ${#_el_files[@]} )); then
  mv "${_el_files[@]}" "${DUNE_INSTALL_PREFIX}/share/emacs/site-lisp/dune/"
fi
shopt -u nullglob

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
