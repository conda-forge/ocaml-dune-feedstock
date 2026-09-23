# ==============================================================================
# Build Helper Functions (Standalone Recipe Version)
# ==============================================================================

# ==============================================================================
# PLATFORM DETECTION
# ==============================================================================

is_macos() { [[ "${target_platform}" == "osx-"* ]]; }
is_linux() { [[ "${target_platform}" == "linux-"* ]]; }
is_non_unix() { [[ "${target_platform}" != "linux-"* ]] && [[ "${target_platform}" != "osx-"* ]]; }
is_cross_compile() { [[ "${build_platform}" != "${target_platform}" ]]; }

fail() { echo "ERROR: $*" >&2; exit 1; }
