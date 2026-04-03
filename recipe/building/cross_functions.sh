# ==============================================================================
# CROSS-COMPILATION FUNCTIONS
# ==============================================================================
# Cross-compile dune for a target architecture using:
#   - Native OCaml (BUILD_PREFIX) to build the bootstrap tool
#   - Cross-compiler OCaml wrappers (aarch64-conda-linux-gnu-ocamlc etc.)
#     which automatically set OCAMLLIB, CONDA_OCAML_CC, etc.
#   - Native dune (BUILD_PREFIX) to generate install artifacts
# ==============================================================================

# Determine cross-compiler prefix.
# Linux: CONDA_TOOLCHAIN_HOST set by GCC activation (e.g. aarch64-conda-linux-gnu)
# macOS: neither CONDA_TOOLCHAIN_HOST nor HOST is set; discover from installed
#        cross-compiler binary (e.g. arm64-apple-darwin20.0.0-ocamlc)
if [[ -n "${CONDA_TOOLCHAIN_HOST:-}" ]]; then
  CROSS_PREFIX="${CONDA_TOOLCHAIN_HOST}"
elif [[ -n "${HOST:-}" ]]; then
  CROSS_PREFIX="${HOST}"
else
  # Discover from cross-compiler OCaml binary in BUILD_PREFIX/bin
  # Native ocaml installs bare 'ocamlc'; cross-compiler installs '<prefix>-ocamlc'
  _cross_ocamlc=$(ls "${BUILD_PREFIX}/bin/"*-ocamlc 2>/dev/null | head -1)
  if [[ -n "${_cross_ocamlc}" ]]; then
    CROSS_PREFIX="$(basename "${_cross_ocamlc}" | sed 's/-ocamlc$//')"
    echo "  Discovered cross-compiler prefix: ${CROSS_PREFIX}"
  else
    fail "Cannot determine cross-compiler prefix — no CONDA_TOOLCHAIN_HOST, HOST, or *-ocamlc in BUILD_PREFIX/bin"
  fi
fi
echo "  CROSS_PREFIX: ${CROSS_PREFIX}"

# Build the native bootstrap tool (_native_duneboot)
# This runs on the build machine and orchestrates cross-compilation.
# Must be called BEFORE swap_ocaml_compilers (needs native ocamlc).
build_native_bootstrap() {
  echo "=== Building native bootstrap tool ==="

  local target_lib="${PREFIX}/lib"
  local target_ocaml_lib="${PREFIX}/lib/ocaml"

  # Bootstrap runs on build machine — use native OCaml stdlib
  export OCAMLLIB="${BUILD_PREFIX}/lib/ocaml"

  # Set LIBRARY_PATH so linker finds target libs (zstd, etc.)
  export LIBRARY_PATH="${target_ocaml_lib}:${target_lib}:${LIBRARY_PATH:-}"

  echo "  OCAMLLIB: ${OCAMLLIB}"
  echo "  LIBRARY_PATH: ${LIBRARY_PATH}"

  if is_macos; then
    ocamlc -verbose -output-complete-exe -intf-suffix .dummy -g \
      -cclib "${target_lib}/libzstd.dylib" \
      -cclib "-L${target_ocaml_lib}" \
      -cclib "-L${BUILD_PREFIX}/lib/ocaml" \
      -cclib "-Wl,-rpath,${target_lib}" \
      -o ./_native_duneboot \
      -I boot -I +unix unix.cma boot/types.ml boot/libs.ml boot/duneboot.ml
  else
    ocamlc -output-complete-exe -intf-suffix .dummy -g \
      -cclib "-L${target_lib}" \
      -cclib "-L${target_ocaml_lib}" \
      -cclib "-L${BUILD_PREFIX}/lib/ocaml" \
      -cclib "-Wl,-rpath,${target_lib}" \
      -o ./_native_duneboot \
      -I boot -I +unix unix.cma boot/types.ml boot/libs.ml boot/duneboot.ml
  fi
}

# Redirect bare ocamlc/ocamlopt names to cross-compiler wrappers.
# Needed because _native_duneboot calls these tools by bare name.
# The cross-compiler wrappers (e.g. aarch64-conda-linux-gnu-ocamlc.opt)
# automatically set OCAMLLIB, CONDA_OCAML_CC, etc. — no manual env setup needed.
swap_ocaml_compilers() {
  echo "  Swapping OCaml compilers to cross-compilers..."
  pushd "${BUILD_PREFIX}/bin" > /dev/null
    for tool in ocamlc ocamldep ocamlopt ocamlobjinfo; do
      if [[ -f "${tool}" ]] || [[ -L "${tool}" ]]; then
        mv "${tool}" "${tool}.build"
        ln -sf "${CROSS_PREFIX}-${tool}" "${tool}"
      fi
      if [[ -f "${tool}.opt" ]] || [[ -L "${tool}.opt" ]]; then
        mv "${tool}.opt" "${tool}.opt.build"
        ln -sf "${CROSS_PREFIX}-${tool}.opt" "${tool}.opt"
      fi
    done
  popd > /dev/null
}

# ==============================================================================
# MAIN CROSS-COMPILATION FUNCTION
# ==============================================================================

cross_compile_with_native_dune() {
  local native_dune="${BUILD_PREFIX}/bin/dune"
  local install_prefix="${1}"

  echo "=== Cross-compilation: Using native dune from BUILD_PREFIX ==="

  if [[ ! -x "${native_dune}" ]]; then
    echo "ERROR: Native dune not found at ${native_dune}"
    return 1
  fi
  echo "  Native dune: ${native_dune}"
  "${native_dune}" --version

  # Verify cross-compiler exists before doing anything destructive
  local cross_ocamlc="${BUILD_PREFIX}/bin/${CROSS_PREFIX}-ocamlc"
  if [[ ! -f "${cross_ocamlc}" ]] && [[ ! -L "${cross_ocamlc}" ]]; then
    echo "ERROR: Cross-compiler OCaml not found at ${cross_ocamlc}"
    echo "  Add ocaml-cross-compilers or ocaml_\${target_platform} to build dependencies"
    return 1
  fi
  echo "  Cross-compiler: ${cross_ocamlc}"

  # Phase 1: Build install artifacts (man pages, docs, .install file) with native dune
  echo "=== Phase 1: Building install artifacts with native dune ==="
  mkdir -p _boot
  cp -v "${native_dune}" _boot/dune.exe || return 1
  if ! "${native_dune}" build @install -p dune --profile dune-bootstrap; then
    echo "ERROR: Failed to build install artifacts with native dune"
    return 1
  fi

  # Save install artifacts before cross-compile clobbers _build
  echo "=== Saving install artifacts ==="
  cp -rL _build/install/default _build_install_native || return 1
  cp _build/default/dune.install _dune.install.saved || return 1

  # Phase 2: Build native bootstrap tool (must run BEFORE compiler swap)
  if ! build_native_bootstrap; then
    echo "ERROR: Failed to build native bootstrap tool"
    return 1
  fi

  # Phase 3: Swap bare compiler names to cross-compiler wrappers
  # The wrappers handle OCAMLLIB, CONDA_OCAML_CC, etc. automatically
  echo "=== Phase 3: Setting up cross-compilers ==="
  swap_ocaml_compilers

  # Phase 4: Run bootstrap with cross-compiler to produce target dune.exe
  echo "=== Phase 4: Running bootstrap with cross-compiler ==="
  rm -rf _boot _build
  if ! ./_native_duneboot; then
    echo "ERROR: Native bootstrap tool failed"
    return 1
  fi

  # Phase 5: Splice cross-compiled binary into saved artifacts and install
  echo "=== Phase 5: Installing cross-compiled dune ==="
  rm -f _build_install_native/bin/dune
  cp -v _boot/dune.exe _build_install_native/bin/dune || return 1
  file _build_install_native/bin/dune

  mkdir -p _build/install _build/default
  mv _build_install_native _build/install/default || return 1
  mv _dune.install.saved _build/default/dune.install || return 1

  if ! "${native_dune}" install --prefix="${install_prefix}" dune; then
    echo "ERROR: Failed to install with native dune"
    return 1
  fi

  return 0
}
