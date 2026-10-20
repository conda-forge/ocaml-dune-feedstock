@echo off
REM Dune activation script - configure dune for OCaml convention

if defined CONDA_PREFIX (
    REM Save originals for deactivation
    if defined OCAMLPATH (
        set "_CONDA_DUNE_OCAMLPATH_BACKUP=%OCAMLPATH%"
        set "OCAMLPATH=%CONDA_PREFIX%\Library\lib\ocaml;%OCAMLPATH%"
    ) else (
        set "_CONDA_DUNE_OCAMLPATH_BACKUP="
        set "OCAMLPATH=%CONDA_PREFIX%\Library\lib\ocaml"
    )
)
