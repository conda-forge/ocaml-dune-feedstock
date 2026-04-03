# ==============================================================================
# Build Helper Functions (Standalone Recipe Version)
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
