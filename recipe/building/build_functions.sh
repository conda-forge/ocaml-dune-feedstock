# ==============================================================================
# Build Helper Functions (Standalone Recipe Version)
# ==============================================================================
# Simplified helper functions for standalone conda-forge recipes.
# ==============================================================================

# ==============================================================================
# PLATFORM DETECTION
# ==============================================================================

is_macos() { [[ "${target_platform}" == "osx-"* ]]; }
is_linux() { [[ "${target_platform}" == "linux-"* ]]; }
is_non_unix() { [[ "${target_platform}" != "linux-"* ]] && [[ "${target_platform}" != "osx-"* ]]; }
is_cross_compile() { [[ "${CONDA_BUILD_CROSS_COMPILATION:-}" == "1" ]]; }

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

warn() {
  echo "WARNING: $*" >&2
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

# Get compiler path based on type and toolchain
get_compiler() {
  local toolchain_prefix="${1:-}"

  local c_compiler
  if [[ -n "${toolchain_prefix}" ]]; then
    if [[ "${toolchain_prefix}" == *"apple-darwin"* ]]; then
      c_compiler="${toolchain_prefix}-clang"
    else
      c_compiler="${toolchain_prefix}-gcc"
    fi
  else
    if is_macos; then
      c_compiler="clang"
    else
      c_compiler="gcc"
    fi
  fi

  echo "${c_compiler}"
}

get_target_c_compiler() { get_compiler "${CONDA_TOOLCHAIN_HOST:-}"; }

# Clean up any previous cross-compilation build artifacts
clean_cross_build() {
  rm -rf _boot _build _build_install_native _native_duneboot _dune.install.saved
}

# ==============================================================================
# CROSS-COMPILATION SETUP FUNCTIONS
# ==============================================================================

# Manual installation from _build/install/default (for bootstrap flow)
install_dune_from_build_artifacts() {
  local install_prefix="${1}"
  local src="_build/install/default"

  echo "=== Manual installation from build artifacts ==="

  # bin
  install -Dm755 "${src}/bin/dune" "${install_prefix}/bin/dune"

  # lib
  mkdir -p "${install_prefix}/lib/dune"
  cp -v "${src}/lib/dune/"* "${install_prefix}/lib/dune/"

  # doc
  mkdir -p "${install_prefix}/doc/dune/odoc-pages"
  cp -v "${src}/doc/dune/"*.md "${install_prefix}/doc/dune/" 2>/dev/null || true
  cp -v "${src}/doc/dune/odoc-pages/"* "${install_prefix}/doc/dune/odoc-pages/" 2>/dev/null || true

  # man pages
  mkdir -p "${install_prefix}/man/man1" "${install_prefix}/man/man5"
  cp -v "${src}/man/man1/"* "${install_prefix}/man/man1/"
  cp -v "${src}/man/man5/"* "${install_prefix}/man/man5/"

  # emacs
  mkdir -p "${install_prefix}/share/emacs/site-lisp"
  cp -v "${src}/share/emacs/site-lisp/"*.el "${install_prefix}/share/emacs/site-lisp/"
}
