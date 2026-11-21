# `libfyaml`

Arch's recipe (0.9.6-3, the switch to CMake) with `powerpc64le` added. It
replaces Arch POWER's 0.9.6-2, whose `hotfix-arch32.patch` only matters on
32-bit targets.

## Why it is in the LLVM 23 wave

Our 0.9.6-2 linked `libclang.so.22.1` and `libLLVM.so.22.1` but declared
only `glibc`. Autotools found libclang in bq's whole-pool sysroot and built
the reflection support. With CMake, `ENABLE_LIBCLANG` defaults to OFF, so
0.9.6-3 links neither, as Arch's does.

## Deviation

- `-DSPHINX_EXECUTABLE=SPHINX_EXECUTABLE-NOTFOUND`: there is no docs
  option. CMake builds man pages whenever it finds `sphinx-build`, and the
  pool sysroot has one. The man pages then need the `linuxdoc` extension,
  which nobody packages, and `cmake --install` failed. Arch's chroot has no
  sphinx, so this gives Arch's output.
