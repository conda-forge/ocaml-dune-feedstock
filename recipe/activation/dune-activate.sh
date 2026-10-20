#!/bin/bash
# Dune activation script - configure dune for OCaml convention
# - OCAMLPATH: where dune searches for packages (lib/ocaml/<package>/META)

if [[ -n "${CONDA_PREFIX:-}" ]]; then
  # Save originals for deactivation
  export _CONDA_DUNE_OCAMLPATH_BACKUP="${OCAMLPATH:-}"

  # Set search path for package discovery. During conda build, dune runs
  # from the build environment (CONDA_PREFIX == BUILD_PREFIX), so host
  # libraries under PREFIX must be added explicitly and take precedence.
  if [[ -n "${PREFIX:-}" && -n "${BUILD_PREFIX:-}" ]]; then
    export OCAMLPATH="${PREFIX}/lib/ocaml:${BUILD_PREFIX}/lib/ocaml${OCAMLPATH:+:$OCAMLPATH}"
  else
    export OCAMLPATH="${CONDA_PREFIX}/lib/ocaml${OCAMLPATH:+:$OCAMLPATH}"
  fi
fi
