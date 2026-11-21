# `doxygen`

Arch's recipe (1.18.0-2, their LLVM 23 rebuild) with `powerpc64le` added and
no other change. It replaces Arch POWER's 1.16.1-3, which we never built.

## Why it is in the LLVM 23 wave

Arch POWER's doxygen links `libclang-cpp.so.22.1` and `libLLVM.so.22.1`
(`-Duse_libclang=ON`). bq stages it into the sysroot as a makedepend for many
recipes. Once clang-libs 23 is in the pool, that doxygen no longer runs.

## Building it under bq

`doxygen-docs` runs pdflatex three times over the manual
(`doc/CMakeLists.txt`), so the build needs a working TeX: ls-R databases,
formats and font maps. On a real system texlive's pacman hooks make those.
bq's sysroot never runs hooks, so bq does that work itself for any recipe that
depends on `texlive-*` (`texlive_hooks()` in `tools/bq.py`). The first attempt
built only the `pdflatex` format in `build()`. It failed, because kpathsea
found no file at all without ls-R.
