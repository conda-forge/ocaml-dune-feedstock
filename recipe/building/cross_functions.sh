# ==============================================================================
# CROSS-COMPILATION SETUP FUNCTIONS
# ==============================================================================

# Build bootstrap tool for cross-compilation
# The cross-compiler needs target libs (zstd, OCaml runtime) from PREFIX, not BUILD_PREFIX
build_native_bootstrap() {
  echo "=== Phase 2: Building bootstrap tool ==="

  # Cross-linker looks in BUILD_PREFIX by default, but target libs are in PREFIX
  # ocamlc uses OCAMLLIB to find runtime libs
  local target_lib="${PREFIX}/lib"
  local target_ocaml_lib="${PREFIX}/lib/ocaml"

  echo "  PREFIX: ${PREFIX}"
  echo "  Target lib: ${target_lib}"
  echo "  Target OCaml lib: ${target_ocaml_lib}"

  # Point OCAMLLIB to target OCaml runtime
  export OCAMLLIB="${target_ocaml_lib}"

  # Set LIBRARY_PATH so linker finds target libs
  # This works for both gcc (Linux) and clang (macOS)
  export LIBRARY_PATH="${target_ocaml_lib}:${target_lib}:${LIBRARY_PATH:-}"

  echo "  OCAMLLIB: ${OCAMLLIB}"
  echo "  LIBRARY_PATH: ${LIBRARY_PATH}"

  # Build bootstrap
  if is_macos; then
    ocamlc -verbose -output-complete-exe -intf-suffix .dummy -g \
      -cclib "${target_lib}/libzstd.dylib" \
      -cclib "-L${target_ocaml_lib}" \
      -cclib "-Wl,-rpath,${target_lib}" \
      -o ./_native_duneboot \
      -I boot -I +unix unix.cma boot/types.ml boot/libs.ml boot/duneboot.ml
  else
    ocamlc -output-complete-exe -intf-suffix .dummy -g \
      -cclib "-L${target_lib}" \
      -cclib "-L${target_ocaml_lib}" \
      -cclib "-Wl,-rpath,${target_lib}" \
      -o ./_native_duneboot \
      -I boot -I +unix unix.cma boot/types.ml boot/libs.ml boot/duneboot.ml
  fi
}

swap_ocaml_compilers() {
  echo "  Swapping OCaml compilers to cross-compilers..."
  pushd "${BUILD_PREFIX}/bin" > /dev/null
    for tool in ocamlc ocamldep ocamlopt ocamlobjinfo; do
      if [[ -f "${tool}" ]] || [[ -L "${tool}" ]]; then
        mv "${tool}" "${tool}.build"
        ln -sf "${CONDA_TOOLCHAIN_HOST}-${tool}" "${tool}"
      fi
      if [[ -f "${tool}.opt" ]] || [[ -L "${tool}.opt" ]]; then
        mv "${tool}.opt" "${tool}.opt.build"
        ln -sf "${CONDA_TOOLCHAIN_HOST}-${tool}.opt" "${tool}.opt"
      fi
    done
  popd > /dev/null
}

setup_cross_c_compilers() {
  echo "  Setting up C cross-compiler symlinks..."
  local target_cc="$(get_target_c_compiler)"

  pushd "${BUILD_PREFIX}/bin" > /dev/null
    for tool in gcc cc; do
      if [[ -f "${tool}" ]] || [[ -L "${tool}" ]]; then
        mv "${tool}" "${tool}.build" 2>/dev/null || true
      fi
      ln -sf "${target_cc}" "${tool}"
    done
  popd > /dev/null
}

configure_cross_environment() {
  echo "  Configuring cross-compilation environment variables..."
  export CONDA_OCAML_CC="$(get_target_c_compiler)"
  if is_macos; then
    export CONDA_OCAML_MKEXE="${CONDA_OCAML_CC}"
    export CONDA_OCAML_MKDLL="${CONDA_OCAML_CC} -dynamiclib"
  else
    export CONDA_OCAML_MKEXE="${CONDA_OCAML_CC} -Wl,-E -ldl"
    export CONDA_OCAML_MKDLL="${CONDA_OCAML_CC} -shared"
  fi
  export CONDA_OCAML_AR="${CONDA_TOOLCHAIN_HOST}-ar"
  export CONDA_OCAML_AS="${CONDA_TOOLCHAIN_HOST}-as"
  export CONDA_OCAML_LD="${CONDA_TOOLCHAIN_HOST}-ld"
  # export QEMU_LD_PREFIX="${BUILD_PREFIX}/${CONDA_TOOLCHAIN_HOST}/sysroot"

  local cross_ocaml_lib="${BUILD_PREFIX}/lib/ocaml-cross-compilers/${CONDA_TOOLCHAIN_HOST}/lib/ocaml"
  if [[ -d "${cross_ocaml_lib}" ]]; then
    export OCAMLLIB="${cross_ocaml_lib}"
    export LIBRARY_PATH="${cross_ocaml_lib}:${PREFIX}/lib:${LIBRARY_PATH:-}"
    export LDFLAGS="-L${cross_ocaml_lib} -L${PREFIX}/lib ${LDFLAGS:-}"
  fi
}

# ==============================================================================
# DUNE CROSS-COMPILATION BUILD FUNCTIONS
# ==============================================================================

# Cross-compile dune using native dune from BUILD_PREFIX (faster, preferred)
# Returns 0 on success, 1 on failure
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

  # Phase 1: Use native dune to build install artifacts
  # The dune-bootstrap profile expects _boot/dune.exe - use native dune as placeholder
  echo "=== Phase 1: Building install artifacts with native dune ==="
  mkdir -p _boot
  cp -v "${native_dune}" _boot/dune.exe || return 1
  if ! "${native_dune}" build @install -p dune --profile dune-bootstrap; then
    echo "ERROR: Failed to build install artifacts with native dune"
    return 1
  fi

  # Save the install artifacts (man pages, docs, emacs files, etc.)
  # Use -L to dereference symlinks (bin/dune is a symlink)
  echo "=== Saving install artifacts ==="
  cp -rL _build/install/default _build_install_native || return 1
  cp _build/default/dune.install _dune.install.saved || return 1

  # Phase 2: Build native bootstrap tool BEFORE swapping compilers
  # .duneboot.exe must run on build machine, so it needs native compiler
  if ! build_native_bootstrap; then
    echo "ERROR: Failed to build native bootstrap tool"
    return 1
  fi

  # Phase 3: Setup cross-compilation environment
  echo "=== Phase 3: Setting up cross-compilers ==="
  swap_ocaml_compilers
  setup_cross_c_compilers
  configure_cross_environment

  # Phase 4: Run native bootstrap tool to create cross-compiled dune.exe
  # The bootstrap runs on build machine (possibly via QEMU) but uses cross-compilers in PATH
  # It needs LD_LIBRARY_PATH to find target libs (zstd) at runtime
  echo "=== Phase 4: Running bootstrap with cross-compiler ==="
  rm -rf _boot _build
  if ! ./_native_duneboot; then
    echo "ERROR: Native bootstrap tool failed"
    return 1
  fi

  # Phase 5: Replace the binary in saved artifacts with cross-compiled version
  echo "=== Phase 5: Replacing binary with cross-compiled version ==="
  rm -f _build_install_native/bin/dune
  cp -v _boot/dune.exe _build_install_native/bin/dune || return 1
  file _build_install_native/bin/dune

  # Restore the install directory and dune.install for dune install to work
  mkdir -p _build/install _build/default
  mv _build_install_native _build/install/default || return 1
  mv _dune.install.saved _build/default/dune.install || return 1

  # Install using native dune
  echo "=== Installing with native dune ==="
  if ! "${native_dune}" install --prefix="${install_prefix}" dune; then
    echo "ERROR: Failed to install with native dune"
    return 1
  fi

  return 0
}

# Cross-compile dune using full bootstrap (slower, fallback when native dune unavailable)
# Returns 0 on success, 1 on failure
cross_compile_with_bootstrap() {
  local install_prefix="${1}"

  echo "=== Cross-compilation: Using full bootstrap (fallback) ==="

  # Phase 1: Build install artifacts with NATIVE compiler first
  # This generates man pages, docs, etc. that require running dune
  echo "=== Phase 1: Building install artifacts with native compiler ==="
  if ! make release; then
    echo "ERROR: Failed to build install artifacts"
    return 1
  fi

  # Save the install artifacts (man pages, docs, emacs files, etc.)
  echo "=== Saving install artifacts ==="
  cp -rL _build/install/default _build_install_native || return 1
  cp _build/default/dune.install _dune.install.saved || return 1

  # Phase 2: Build native bootstrap tool BEFORE swapping compilers
  if ! build_native_bootstrap; then
    echo "ERROR: Failed to build native bootstrap tool"
    return 1
  fi

  # Phase 3: Setup cross-compilation environment
  echo "=== Phase 3: Setting up cross-compilers ==="
  swap_ocaml_compilers
  setup_cross_c_compilers
  configure_cross_environment

  # Phase 4: Run native bootstrap tool to create cross-compiled dune.exe
  # It needs LD_LIBRARY_PATH to find target libs (zstd) at runtime
  echo "=== Phase 4: Running bootstrap with cross-compiler ==="
  rm -rf _boot _build
  if ! ./_native_duneboot; then
    echo "ERROR: Native bootstrap tool failed"
    return 1
  fi

  # Phase 5: Replace the binary in saved artifacts with cross-compiled version
  echo "=== Phase 5: Replacing binary with cross-compiled version ==="
  rm -f _build_install_native/bin/dune
  cp -v _boot/dune.exe _build_install_native/bin/dune || return 1
  file _build_install_native/bin/dune

  # Restore the install directory and dune.install for dune install to work
  mkdir -p _build/install _build/default
  mv _build_install_native _build/install/default || return 1
  mv _dune.install.saved _build/default/dune.install || return 1

  # Install manually from build artifacts
  echo "=== Installing from build artifacts ==="
  if ! install_dune_from_build_artifacts "${install_prefix}"; then
    echo "ERROR: Failed to install dune from build artifacts"
    return 1
  fi

  return 0
}
