# `blender`

Blender 5.3.0 for ppc64le with **Cycles on the CPU, Embree BVH traversal and
the OpenImageDenoise denoiser**. Arch POWER lacks all three. Its current
`blender 17:5.2.2-2` still has neither `embree` nor `openimagedenoise` in its
`depends` `[MEASURED]`, 2026-11-17, `pacman -Si base/blender`. The rest of
this paragraph is the original 5.1.0 finding: Arch POWER's
`blender 17:5.1.0-2` recipe (`~/Development/repo/archpower/blender`)
takes the `*)` branch of a `case "${CARCH}"` and passes
`-D WITH_CYCLES=OFF -D WITH_CYCLES_EMBREE=OFF -D WITH_CYCLES_OSL=OFF`, because
neither `embree` nor `openimagedenoise` existed for POWER. Verified on the
shipped package, not the recipe `[MEASURED]`: the extracted
`blender-17:5.1.0-2-powerpc64le.pkg.tar.zst` has no
`scripts/addons_core/cycles/` directory (12 core add-ons, Cycles not among
them) and its binary links neither `libembree4` nor `libOpenImageDenoise`.
So "before" is not "Cycles without acceleration"; it is **no Cycles at all**
-- EEVEE and Workbench only. That package also links `libavcodec.so.62`
while Arch POWER now ships ffmpeg 9 (`libavcodec.so.63`), so it does not
start on a current Arch POWER system either.

Recipe base: Arch's 5.3.0-1 PKGBUILD, with the deviations below rebased
onto it. Patches:

- Arch's four, unchanged: `blender-usd-26.11.patch` (Hydra),
  `blender-hiprt-3-sdk-headers.patch` and `blender-hiprt-3-log-level.patch`
  (HIPRT 3), and `blender-onetbb-af82c3ca2d0f.patch` (an upstream commit,
  fetched by URL). Hydra and HIPRT are off here, so the first three touch
  code that is never compiled. They are carried so the recipe tracks Arch's.
- Ours: `cycles-vsx.patch`, `oidn-ppc64le-supported.patch` and
  `cycles-power-cpu-name.patch`. Each patch header explains its hunks. The
  last one is cosmetic: Cycles read the CPU name from cpuinfo's `model name`,
  which POWER lacks, and listed "Unknown CPU". The Cycles device list now
  shows `IBM POWER9 (VSX)` `[MEASURED]`.
- Dropped in 5.3.0: `ffmpeg-9.patch`. 5.3's audaspace has its own
  `FFMPEG_SUPPORTED_CONFIG` branch for libavcodec >= 62, so the old patch
  would only have rewritten the dead `#else` branch. Also dropped:
  `blender-hip-update.patch`, a leftover never listed in `source=()`, which
  Arch's `blender-hiprt-3-sdk-headers.patch` supersedes.

## What is and is not accelerated

| | state | evidence |
|---|---|---|
| Cycles CPU device | **on** | `_cycles` module imports; `bpy.app.build_options.cycles == True`; BMW27 and Classroom render `[MEASURED]` |
| BVH build + ray traversal | **Embree 4.4.1, SSE4.2 kernels on VSX** (`packages/embree`) | `ldd`: `libembree4.so.4`; `_cycles.with_embree == True` `[MEASURED]` |
| Cycles shading/integrator kernel | **native VSX 4-wide kernel** via `cycles-vsx.patch` (see below); the SSE-through-compat-headers kernel and scalar are build-time alternatives | `_cycles.system_info()` -> `CPU device capabilities: VSX`; 2,194 fused vector multiply-adds and 895 control-vector permutes in the kernel object vs 6 and 10,675 for the compat kernel `[MEASURED]` |
| Denoiser | **OpenImageDenoise 2.4.1 CPU device** (`packages/openimagedenoise`) | `ldd`: `libOpenImageDenoise.so.2`; `_cycles.with_openimagedenoise == True` `[MEASURED]` |
| Open Shading Language | **on**, against `openshadinglanguage 1.15.7.0` from this repo (OIIO 3.2 build) | `_cycles.with_osl == True`; a CPU render with `shading_system = True` matches the SVM render (`idiff` PASS) `[MEASURED]` |
| Path guiding (Open PGL) | **off** -- `openpgl` is not packaged for ppc64le; it is Embree-based and portable, a later job | |
| USD / Hydra | **off** -- `usd` is not packaged for ppc64le | |
| OpenTimelineIO import/export | **off** -- new in 5.3.0, needs an unreleased OTIO; see Deviations | |
| GPU: HIP | **compiled in, dormant** -- see "GPU" below | `HIPEW initialization failed: Error opening HIP dynamic library` at startup; `_cycles.get_device_types()` reports HIP `[MEASURED]` |
| GPU: CUDA / OptiX / oneAPI | off; no such stack exists for POWER | |

## Deviations from Arch's recipe

- `arch=(powerpc64le)`, `epoch=17 pkgver=5.3.0 pkgrel=1`. That outranks
  Arch POWER's `5.2.2-2`.
- **Source is the release tarball** (`download.blender.org/source/`, md5
  matches upstream's `.md5sum`; sha512 in the PKGBUILD) instead of Arch's
  `git+https://...#tag=v5.3.0` plus `git lfs fetch`. Same tree, no
  `git`/`git-lfs`/`subversion` makedepends, no multi-GB clone. One
  consequence: `build_hash` reports `unknown`, which buildinfo.cmake handles
  for a tree without `.git`.
- From Arch's depends, dropped: `hiprt`, `intel-oneapi-*`,
  `level-zero-loader`, `openpgl`, `usd`. From its makedepends, dropped:
  `cuda`, `hip-runtime-amd`, `hiprt`, `intel-*`, `level-zero-headers`,
  `mold`, `git`, `git-lfs`, `subversion`. Also dropped: the OptiX headers
  source, the CUDA/HIP/oneAPI/OptiX cmake paths and the oneAPI AOT library
  move in `package()`. Everything 5.3.0 newly added that exists for POWER is
  kept: `fmt`, `python-cattrs` (an `any` package from Arch POWER),
  `spirv-headers`, and `-Wno-error=format-security`.
- `release/bin/blender-softwaregl` is no longer installed: 5.3.0 removed it
  upstream, and Arch's recipe dropped it too.
- `WITH_CYCLES=ON WITH_CYCLES_EMBREE=ON WITH_CYCLES_OSL=ON
  WITH_OPENIMAGEDENOISE=ON`, set explicitly, with `embree` and
  `openimagedenoise` in `depends`. Arch's recipe is x86_64-only and gets
  them by default. Arch POWER builds them OFF.
- `WITH_CYCLES_PATH_GUIDING=OFF WITH_USD=OFF WITH_HYDRA=OFF`: `openpgl`
  and `usd` are not packaged for POWER.
- `WITH_OPENTIMELINEIO=OFF`, new in 5.3.0. OTIO is optional and
  auto-detected. Arch's chroot has none, so Arch's package is built without
  it. bq stages the whole baseline pool, which includes `opentimelineio
  0.18.1` (for kdenlive), so cmake turned it on. 5.3's `source/blender/io/otio`
  is written against the unreleased OTIO main that its
  `build_environment/cmake/versions.cmake` pins (2026-09-09, which defines
  `OPENTIMELINEIO_VERSION_NS`), and against 0.18.1 it fails to compile
  `[MEASURED]`. Turning it on later needs an OTIO release with that
  namespace macro.
- `WITH_CYCLES_DEVICE_HIP=ON WITH_CYCLES_HIP_BINARIES=OFF
  WITH_CYCLES_DEVICE_HIPRT=OFF`, set explicitly; CUDA/OptiX/oneAPI off.
- `WITH_LINKER_MOLD=OFF`, `mold` dropped from makedepends: mold 2.x on this
  host cannot parse GCC 16's `libatomic_asneeded.so` linker script
  (`INPUT ( AS_NEEDED ( -latomic ) )` -> `library not found: AS_NEEDED`),
  and the very first link (`bin/datatoc`) fails `[MEASURED]`.
- `WITH_SYSTEM_GFLAGS=ON WITH_SYSTEM_GLOG=ON`, `gflags` and `google-glog`
  added to depends. Blender bundles gflags/glog for libmv but links Arch
  POWER's `ceres-solver`, which pulls the system `libglog.so.2` /
  `libgflags.so.2.2`. With both present the binary aborts before `main`
  does anything: `ERROR: flag 'logtostderr' was defined more than once (in
  files '/build/google-glog/src/glog-0.7.1/src/flags.cc' and
  'extern/glog/src/logging.cc')` `[MEASURED]`. One glog, the system's, fixes
  it. (Arch POWER's shipped binary carries no `extern/glog` strings at all,
  so their build resolved this differently; their recipe does not say how.)
- The manpage `LD_LIBRARY_PATH` sed and the `!lto` option are kept as in
  Arch's recipe.

## 5.3.0-1: build and verification

Built in the baseline lane (`tools/build-ppc64le.sh`, POWER8 drop-in),
packaging `edddd9c0`, against `openimageio 3.2.1.2-3` and
`openshadinglanguage 1.15.7.0-2.1` from the same pool. The link is LLD
22.1.8, which blender 5.3 selects by default when mold is off.

**The buildroot was on tmpfs (`/dev/shm`), not `/var/tmp`.** On .24
(kernel 7.2.9-64k, btrfs with `compress=zstd:3`), a clone or
`copy_file_range` of a file whose pages are still dirty can come back
missing a 64K page, which reads as zeros. makepkg's strip does exactly that
(`strip -o tmp; cat tmp > binary`; coreutils `cat` uses
`copy_file_range`). Two `/var/tmp` builds of OSL shipped a `liboslexec.so`
with an all-zero `.dynamic`, and that is what broke blender's link (lld:
`undefined reference ... @LLVM_22.1` from liboslexec). The same steps
outside bq reproduce it every time. `sync` before the copy, a read/write
copy, or a tmpfs build directory all avoid it `[MEASURED]`. The blender
package has no all-zero section windows outside the known-legitimate
classes, and every ELF's dynamic section is intact.

**Links** `[MEASURED]`: `libOpenImageIO.so.3.2`, `liboslexec.so.1.15`,
`libembree4.so.4`, `libOpenImageDenoise.so.2`, `libopenvdb.so.13.0`. There
is no RUNPATH. 5.1.0-5 linked `libopenvdb.so.12.1`, so it no longer starts
on a system with Arch POWER's openvdb 13. `libshaderc_shared.so.1` is NEEDED
but not in `depends=()`, the same as 5.1.0-5 and Arch's recipe.

**Runtime**, natively on .24 (POWER9), from the extracted package with
`BLENDER_SYSTEM_RESOURCES` pointing into it, `blender --background
--factory-startup --python-expr` `[MEASURED]`:

    bpy.app.version_string                 5.3.0
    bpy.app.build_options.cycles           True
    _cycles.system_info()                  CPU device capabilities: VSX
    _cycles.with_embree                    True
    _cycles.with_openimagedenoise          True
    _cycles.with_osl                       True
    _cycles.get_device_types()             (False, False, True, False, False, False)   # HIP
    default cube, Cycles CPU, 64x64, 8 spp, OIDN on -> PNG, 205 distinct colours, luminance 0.193..0.659
    same with shading_system = True (OSL)  -> PNG; idiff against the SVM render: PASS

**ISA 3.0 scan** (`tools/isa30-pkgscan.sh`, like for like): 5.1.0-5: 36,
5.3.0-1: 7. Every hit in both is a switch-table offset right after
`lwax`/`add`/`mtctr`/`bctr`, decoding as `xsiexpqp`/`xsnmsubqp`/`xsmulqp`/
`xssubqp` with `v31` operands. That is data, not code. Real ISA 3.0: none,
including the VSX Cycles kernel, which is linked into `usr/bin/blender`.

**Changed relative to 5.1.0-5:** `blender-softwaregl` is gone (removed
upstream). OpenTimelineIO, new in 5.3, is off. Everything in the table
above is unchanged, and the BMW27/Classroom parity and timing below were
not repeated.

## `cycles-vsx.patch` -- the Cycles kernel on VSX

Cycles has one 4-wide CPU kernel, written against SSE intrinsics and selected
by `__KERNEL_SSE__`..`__KERNEL_SSE42__` in `util/optimization.h`; ARM
compiles the same code through `sse2neon`. Nothing set those macros on
POWER, so every kernel was scalar. The patch adds two ways to have one,
chosen with `_cycles_vsx=` in the PKGBUILD (`CYCLES_PPC64LE_SIMD` in cmake):

| `_cycles_vsx` | what | marker |
|---|---|---|
| `native` (default) | the vector layer written on VSX: `float4`/`float3` hold a `__vector float`, `int4`/`int3` a `__vector int`, every operation is `vec_*` or a GCC vector-extension expression. No x86 intrinsic used or emulated -- no compat header is included, so any leftover `_mm_*` is a compile error | `__KERNEL_VSX__` |
| `sse` | the x86 SSE4.2 kernel unchanged, through GCC's `<xmmintrin.h>`..`<nmmintrin.h>` for powerpc64le (the Embree technique), plus a 15-line `_mm_dp_ps` they lack | `__KERNEL_SSE2VSX__` |
| `scalar` | no SIMD kernel | -- |

Both SIMD modes also define the `__KERNEL_SSE*__` macros: that is what the
kernel tests for "a 4-wide kernel exists" (`svm/noise.h`, `hash.h`,
`color.h`, `transform.h`), and those sites use only the `float4`/`int4` API.
`_cycles.system_info()` reports `VSX` or `SSE4.2 on VSX` accordingly.

### What the native layer does differently, and why (all `[MEASURED]` on the disassembly, GCC 16, `-mcpu=power9`)

- **Shuffles.** SSE encodes lane selection in an immediate; VSX has no such
  instruction, so the compat header loads a control vector and `xxperm`s for
  every shuffle. The native layer uses `__builtin_shuffle` with a constant
  mask, which lets GCC emit the single-op permute where one exists
  (`xxswapd`, `xxmrghd/ld`, `xxspltw`, `xxmrghw/lw`), and rotates with
  `vec_sld(a, a, 12|8)` (one `vsldoi`, no control vector) in every horizontal
  reduction. Kernel object: `xxperm`+`vperm` 10,675 -> 895.
- **FMA.** With Cycles' `-ffp-contract=on`, GCC does not fuse `a * b + c`
  written with vector operators (it fuses the scalar kernel's expressions,
  and it fuses under `-ffp-contract=fast`). `madd`/`msub` are `vec_madd`/
  `vec_msub`: fused vector ops 6 -> 2,194.
- **Registers.** Both the compat and the native kernel objects already use
  all 64 VSRs; spill traffic is the same within noise. The emulation tax was
  permutes and un-fused math, not register pressure.
- **Reductions.** `dot()` sums `(a0+a1)+(a2+a3)`, the scalar association;
  `float3` reductions zero the w lane with `vec_insert(0, a, 3)`
  (`xxspltib`+`xxinsertw`, ISA 3.0, no memory constant).
- **Conversions.** `make_int4(float4)` truncates (`vctsxs`) like the scalar
  `(int)` casts; SSE's `cvtps` rounds to nearest, a difference the x86
  kernel carries against its own scalar path. `float3 / float` multiplies by
  the reciprocal as the scalar code does.
- **Transforms.** `transform_point/direction` transpose the three rows with
  `vec_mergeh/mergel` + `xxmrghd/xxmrgld` (8 ops) and apply three `vec_madd`
  of `xxspltw`-splatted components, the shape of the SSE path.
- **Single instructions** for `neg`, `abs`, `sqrt`, `floor`, `ceil`,
  `trunc`, `select` (`xxsel`), compares (`xvcmp*sp`).
- **Two documented semantic differences** from the scalar definitions:
  `round()` is `vrfin`, ties to even (as SSE's `roundps`; scalar `roundf` is
  ties-away); `min/max` are `xvminsp/xvmaxsp`, which return the non-NaN
  operand (scalar `(a<b)?a:b` returns `b`). Both are listed by name in the
  probe.

Kernel object (`kernel/device/cpu/kernel.cpp`): 296,749 / 336,909 / 303,769
instructions scalar / sse / native; the full census is in the handbook,
`docs/cycles-native-vsx-kernel.md`.

**Rebased onto 5.3.0.** One new hunk: 5.3 added
`select(mask, dual3, dual3)` to `util/math_dual.h`, whose SSE branch uses
`_mm_blendv_ps` on `.m128`. That was a compile error in the native layer,
exactly as designed, so it gets a `vec_sel` branch shaped like `float3`'s
`select()`. The `transform.h` hunk needed only its context refreshed, after
upstream fixed a comment typo. The patch was regenerated against the 5.3.0
tarball and applies with no fuzz. All 174 Cycles objects compile at
`-mcpu=power8` `[MEASURED]`.

**At `-mcpu=power8`, the baseline pool's flags** `[MEASURED]`, 5.3.0
`cycles_kernel_cpu` `kernel.cpp.o`:

| | count |
|---|---:|
| ISA 3.0 instructions (`.long` under `-M power8` minus `-M power9`) | 0 |
| fused vector multiply-adds (`xvm{add,sub}{a,m}sp`) | 2,660 |
| `xxperm`+`vperm` | 5,259 |
| ISA 2.06/2.07 VSX loads/stores (`lxvd2x`/`lxvw4x`/`stxvd2x`/`stxvw4x`) | 12,629 |

The per-instruction notes above were taken at `-mcpu=power9`. On POWER8
the same builtins lower to ISA 2.07 sequences. `vec_insert`, for one, becomes
a `vperm` with a loaded control vector instead of `xxinsertw`, which is why
the permute count is higher here.

**Parity before timing.** Two levels `[MEASURED]`:

1. Operation level: the handbook's `probes/cycles_vsx_probe.cpp` compiles the
   real patched headers twice (scalar, native), dumps 8,967 operation results
   over identical inputs and compares: 8,276 bit-identical, 688 within an
   operand-scaled rounding tolerance (GCC contracts the *scalar* reference
   into FMAs; cancellation in transforms), 3 documented differences, 0
   mismatches. The same probe against the `sse` layer reports 217 deviations
   from the scalar definitions -- all of them x86-SSE semantics (rounding
   `make_int4`, dividing `float3/float`, `fast_rint`), not bugs.
2. Render level, below: BMW27 PSNR 59.0 dB and Classroom 48.9 dB against the
   scalar kernel, the same as the `sse` kernel scores.

The native kernel is what the package ships (`_cycles_vsx=native`).

## Parity, and the benchmark that is still outstanding

All of this section was measured on **5.1.0** (`-3`/`-4`) and was not
repeated for 5.3.0. The kernel layer is the same patch, plus one `select()`
overload. Everything below was run from bq's sysroot overlay (`bwrap --overlay-src /usr
--overlay-src <sysroot>/usr --ro-overlay /usr`) with the scenes from
<https://download.blender.org/demo/test/> -- `BMW27_2.blend.zip` ->
`bmw27/bmw27_cpu.blend` (1920x1080 at 50%, 1225 samples, no adaptive
sampling, no denoising, seed 0) and `classroom.zip` -> `classroom/classroom.blend`
(1920x1080 at 100%, 300 samples, seed 1). Nothing in the files was changed.
The three binaries come from one scratch tree with this recipe's cmake
options, differing in exactly one variable each:

| binary | Cycles kernel | BVH |
|---|---|---|
| `blender-A` | scalar (`_cycles_vsx=scalar`) | Embree |
| `blender-B` | SSE4.2 through the compat headers (`sse`) | Embree |
| `blender-C` | SSE4.2 through the compat headers | Cycles' own BVH2 (`WITH_CYCLES_EMBREE=OFF`) |
| `blender-N` | **native VSX** (`native`, what the package ships) | Embree |

Render command, for every binary and scene:

    blender -b <scene.blend> -E CYCLES -o out/<label>-#### -F PNG -f 1 -- --cycles-device CPU --cycles-print-stats

(`--cycles-print-stats` makes Cycles print its per-kernel CPU-time profile
at the end.) Images compared with OpenImageIO's `idiff` (default
thresholds; it reports mean/RMS error, PSNR, and the pixel count over 1e-6).

**Determinism control** `[MEASURED]`: the same binary rendering BMW27 twice
differs in 9-21 pixels of 518,400 (PSNR 97-98 dB) -- the renderer is
deterministic to thread-scheduling noise, so any A/B difference below is the
kernel, not the run.

**Sampling-noise floor** `[MEASURED]`: `blender-A` at seed 0 vs seed 1 on
BMW27: mean error 3.2e-3, PSNR 42.7 dB, 69.6% of pixels differ. That is what
"a different but equally correct render" looks like.

**Scalar vs SIMD kernels** `[MEASURED]`:

| scene | pair | mean error | PSNR | pixels over 1e-6 |
|---|---|---|---|---|
| BMW27 | A vs B (sse) | 6.5e-05 | 60.4 dB | 1.63% (max 0.082, one headlight pixel) |
| BMW27 | A vs N (native) | 7.3e-05 | 59.0 dB | 1.61% |
| BMW27 | B vs N | 6.2e-05 | 59.6 dB | 1.38% |
| Classroom | A vs B (sse) | 1.3e-03 | 48.9 dB | 37.2% |
| Classroom | A vs N (native) | 1.3e-03 | 48.9 dB | 37.2% |

BMW27: 18 dB below the sampling-noise floor, 98.4% of pixels bit-identical;
the amplified diff is scattered noise in the headlight highlights. Classroom
(300 spp, glossy chrome chair legs) shows more pixels touched, still at
rounding amplitude with no structure; its own seed-to-seed floor was not
measured (the run was stopped, see below). The differences are the same
kind x86 gets between its scalar and SSE kernels: `_mm_rcp_ps` is an
approximate reciprocal on both ISAs, and the compat headers' `vec_re`
returns different low bits than x86's `rcpps`.

**VSX kernel with and without Embree (B vs C)** `[MEASURED]`: BMW27 mean
error 1.0e-4, PSNR 54.3 dB, 1.71% of pixels -- two different BVH builders
with different traversal order agree to rounding.

**OIDN** `[MEASURED]`: BMW27 at 32 samples with `use_denoising=True,
denoiser='OPENIMAGEDENOISE'` logs `Loading denoising kernels`, no error, and
the denoised frame is 10.7 dB closer to the 1225-sample reference than the
noisy 32-sample frame (PSNR 39.3 dB vs 28.6 dB).

**Timing, shipped package, idle box** `[MEASURED]` 2026-09-11: the installed
`blender 17:5.1.0-4` (native VSX kernel, `CPU device capabilities: VSX`),
`bmw27_cpu.blend` unchanged, `-- --cycles-device CPU`, threads auto (176),
first run started at load 0.37, three back-to-back runs:

    Time: 01:13.30   01:13.10   01:13.63      (wall 74.3 / 74.1 / 74.6 s)

That is the headline number. The A/B/C/N comparison below is still open; it
would say how much of the 73 s the kernel choice is worth.

**Timing during the parity runs: discarded.** Every render above ran while two other package
queues (rocm-llvm, thunderbird) held the machine at load 84-490 on 176
threads; the wall-clock and per-kernel CPU times that came out were
discarded, not averaged. Cycles' own profile did show where the time goes
in shape -- `Intersect Closest` + `Intersect Shadow` (Embree) and `Shade
Surface` (the VSX-or-scalar kernel) are the two halves -- but no number from
those runs is reported here. To measure on an idle box:

    cd /var/tmp/blender-bq/bench          # blender-A / -B / -C and stageB/ are still there
    export BLENDER_SYSTEM_RESOURCES=/var/tmp/blender-bq/bench/stageB/usr/share/blender/5.1
    ../scratch/in-overlay.sh ./final.sh   # interleaved A,B,C x2 on BMW27 -> results-final.tsv + out/F-*.log
                                           # add blender-N (native) to the loop in final.sh for the four-way comparison

`final.sh` records wall time, Blender's own `Time:` line and the 1-minute
load before each run; the `Kernel statistics:` block in each log is the
per-kernel profile. Whether the VSX kernel is faster than the scalar one on
POWER9 is an open question: the SSE code gains 4-wide `xvmulsp`/`xvaddsp`
but also ~23k lane-shuffle instructions (`xxinsertw`, `vperm`, `xxsldwi`)
that x86 addressing forms get for free, and the scalar build already keeps
its float math in VSX registers (`xsmulsp`). If it turns out slower, the
recipe builds any of the three kernels with `_cycles_vsx=native|sse|scalar`
-- parity holds for all of them.

## GPU: HIP is compiled in and dormant

`WITH_CYCLES_DEVICE_HIP=ON` is set explicitly, not left to cmake. Blender
reaches HIP through `extern/hipew`, which `dlopen`s the runtime at startup
instead of linking it -- verified in the built binary, not the cmake
summary: `strings` shows `libamdhip64.so`, `libamdhip64.so.6`,
`libamdhip64.so.7`, `hiprtcCompileProgram`, `hiprtcLinkCreate`; startup logs
`HIPEW initialization failed: Error opening HIP dynamic library`; and
`_cycles.get_device_types()` returns `(cuda=False, optix=False, hip=True,
metal=False, oneapi=False, hiprt=False)` `[MEASURED]`.

`WITH_CYCLES_HIP_BINARIES=OFF`: no precompiled `gfx*` kernels (that needs
`hipcc` at build time). Cycles then compiles its GPU kernel at runtime, from
the kernel sources the package installs under
`/usr/share/blender/5.3/scripts/addons_core/cycles/source/`.

**To activate the GPU later, with no Blender rebuild**, the system needs:

1. `libamdhip64.so` (`.so.6` or `.so.7`) on the loader path or in
   `/opt/rocm/lib` -- `hip-runtime-amd`;
2. `hipcc` (and the ROCm LLVM behind it) for the runtime kernel compile --
   Cycles looks in `$HIP_PATH`/`/opt/rocm/bin`; `libhiprtc.so` for the
   in-process path;
3. a supported AMD GPU with the `amdgpu` kernel driver.

A ROCm/HIP port for ppc64le is being worked on separately; nothing here was
tested against it. Until it lands, Cycles lists CPU only. HIPRT (hardware
ray tracing) is off because it needs the HIP RT SDK at build time; enabling
it later is a rebuild.

## Not in this recipe

- `openpgl` (path guiding): portable (Embree + TBB), not packaged. Later.
- `usd`: not packaged for POWER.
- Arch's `check()` does not exist upstream either; bq runs `--nocheck`.
  Verification is the runtime probe above (`/var/tmp/blender-bq/bench/features.py`
  during the port; the commands are reproduced in "Measurements").
