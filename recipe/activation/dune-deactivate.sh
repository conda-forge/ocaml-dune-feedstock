#!/bin/bash
# Dune deactivation script - restore original OCAMLPATH

if [[ -n "${_CONDA_DUNE_OCAMLPATH_BACKUP:-}" ]]; then
  export OCAMLPATH="${_CONDA_DUNE_OCAMLPATH_BACKUP}"
else
  unset OCAMLPATH
fi
unset _CONDA_DUNE_OCAMLPATH_BACKUP
