@echo off
REM Dune deactivation script - restore original OCAMLPATH

if defined _CONDA_DUNE_OCAMLPATH_BACKUP (
    set "OCAMLPATH=%_CONDA_DUNE_OCAMLPATH_BACKUP%"
) else (
    set "OCAMLPATH="
)
set "_CONDA_DUNE_OCAMLPATH_BACKUP="
