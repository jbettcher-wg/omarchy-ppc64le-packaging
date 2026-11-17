# `openimageio`

Arch's recipe (3.2.1.2-3), imported with `tools/fetch.sh openimageio`, plus
two ppc64le changes:

- `powerpc64le` added to `arch=()`;
- `-DUSE_FFMPEG=OFF -DUSE_OPENVDB=OFF -DUSE_PTEX=OFF -DUSE_OPENCV=OFF
  -DUSE_TBB=OFF`.

No source changes. Arch's `-3` is its libjxl 0.13 rebuild; ours builds
against whatever libjxl the pool ships (0.12 at the time of writing). The
pkgrel is kept as Arch's so the next import is a plain re-fetch.

## The `USE_*=OFF`

They are the optional libraries that Arch's clean chroot never has: the four
in the `TODO: Consider adding these deps` comment on `depends=()`, plus
onetbb. Arch's package links none of them. In Arch's x86_64
`openimageio-3.2.1.2-2`, `libOpenImageIO_Util.so` NEEDs only libstdc++,
libm, libgcc_s and libc `[MEASURED]`. bq builds over the host's `/usr`, and
OIIO links any optional library it finds. So 3.1.12.1-6 linked
`libopenvdb.so.12.1`, `libPtex.so.2.5`, `libavcodec.so.63` and `libtbb.so.12`
without declaring any of them `[MEASURED]`. A first 3.2.1.2 build with only
the TODO four off still linked `libtbb.so.12` into `libOpenImageIO_Util`. When Arch POWER's `openvdb` moved to 13.0
(2026-11-16), `ldd /usr/lib/libOpenImageIO.so.3.1` on the build host
reported `libopenvdb.so.12.1 => not found`. That broke blender 5.1.0-5, and
anything else that loads OIIO, on any system with the new openvdb.

Turning them off makes the package's links match its `depends=()` and
Arch's build, and makes the result the same whatever the build host has
installed. Nothing in the pool needs them: blender and OSL use OIIO for
image I/O and texturing, not for video, VDB or Ptex files.

## SIMD and POWER8

OIIO's `USE_SIMD` defaults to empty on anything that is not x86-64 or
arm64, so no `-m`/`-mcpu` flag is added and makepkg's `-mcpu=power8` alone
decides codegen. `simd.h` has no VSX path (it is SSE/AVX/NEON or scalar).
`OIIO_USE_HWY` (Highway) defaults OFF and is not set.

## Soname

3.2 moves the soname from `libOpenImageIO{,_Util}.so.3.1` to `.so.3.2`.
The consumers come from a byte sweep of both pools for the old soname, plus
the build host's installed files, which cover Arch POWER packages: `blender`
and `openshadinglanguage`. OSL is in neither pool and Arch POWER's build
links 3.1, so it is rebuilt here too (`openshadinglanguage/`).

## Verification

bq runs makepkg `--nocheck`, so OIIO's own test suite does not run.
