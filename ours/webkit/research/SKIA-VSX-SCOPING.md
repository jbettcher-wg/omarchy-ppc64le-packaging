# Skia `ppc64le` VSX CPU Raster Scoping & Prototype Benchmark Report

**Status:** 2026-11-21 · Companion to [`WEBKIT-ON-POWER.md`](./WEBKIT-ON-POWER.md) (Work Item #7)  
**Target host:** `omarchy-power9` (`Linux 7.3.5-64k #2 SMP PREEMPT Wed, 18 Nov 2026 02:19:31 +0000 ppc64le GNU/Linux`, IBM POWER9)  
**Toolchain & flags matched to WebKitGTK `2.54.3`:** `g++ (GCC) 16.2.1 20260810`, `-std=c++23 -O2 -ffp-contract=off -fstrict-aliasing -DSKIA_IMPLEMENTATION=1 -DSK_RELEASE -DSK_R32_SHIFT=16 -DSKCMS_HAS_MUSTTAIL=0 -DSKCMS_DISABLE_HSW -DSKCMS_DISABLE_SKX`  
**Staged patch (ready for next WebKit rebuild):** [`0003-skia-ppc64le-vsx-cpu-raster.patch`](./0003-skia-ppc64le-vsx-cpu-raster.patch) (`8` files, `+1017/-13`)

Every claim below is tagged `[MEASURED]`, `[CODE]`, `[DOC]`, or `[SPEC]`.

---

## Executive Summary

1. **Unmodified WebKitGTK `2.54.3` Skia CPU raster runs completely scalar on `ppc64le` (`[CODE]`, `[MEASURED]`):**
   - [`Source/ThirdParty/skia/include/private/SkFeatures.h`](../WEBKIT-ON-POWER.md) only checks `SK_CPU_X64_LEVEL`, `SK_ARM_HAS_NEON`, and `SK_CPU_LSX_LEVEL` / `LASX`.
   - As a result, `SkRasterPipeline_opts.h` falls into `#define SKRP_CPU_SCALAR` (`highp` stride = `1`, `lowp` stride = `1` with `start_pipeline_lowp = nullptr`), `SkSwizzler_opts.inc`, `SkBlitRow_opts.h`, and `SkBitmapProcState_opts.h` compile scalar byte/word loops, `SkVx.h` calls scalar `libm` `sqrtf` / `lrintf`, and `SkBlitMask_opts.h` hits a non-inlined `Sk4px` fallback (`[CODE]`, `[MEASURED]`).
   - By contrast, `modules/skcms/skcms_TransformBaseline.cc` and `src/opts/SkMemset_opts.h` already auto-vectorize cleanly via GNU vector extensions on GCC `-mcpu=power8` (`skcms_TransformBaseline.o`: `537 lxvd2x`, `397 xvmulsp`, `348 xvaddsp`, `0` scalar `libm` calls; `SkMemset_opts.o`: `22 stxvd2x`, `2 xxspltd`) and do not require patching (`[MEASURED]`, `[CODE]`).

2. **Self-contained POWER8-baseline (`ISA 2.07`) VSX prototype delivers 2.1x–13.4x speedups (`[MEASURED]`):**
   - Adding `SK_PPC_HAS_VSX` (guarded on little-endian `SK_CPU_PPC && SK_CPU_LENDIAN && __VSX__ && __POWER8_VECTOR__`) across `8` Skia headers under `Source/ThirdParty/skia/` switches `SkRasterPipeline` to **`highp` 4-wide / `lowp` 8-wide** (`SKRP_NARROW_STAGES = 0`) and adds native VSX kernels for `SkSwizzler`, `SkBlitRow`, `SkBlitMask`, `SkBitmapProcState`, and `SkVx`.
   - Across `27` differential oracle checks (`--verify ref_p8` against unmodified `base_p8`) on both `-mcpu=power8` and `-mcpu=power9`, **27/27 checks passed** (`25` with `maxdiff = 0` / `maxerr = 0`, and `2` reciprocal unpremul `rgbA_to_{RGBA,BGRA}` with `maxdiff = 1`), plus all `SkVx` edge checks (`NaN`, `lrint`, saturation, `strided_load4`) (`[MEASURED]`).
   - Static `objdump -M power8` vs `-M power9` audit shows **`0` ISA 3.0 leaks** and **`0` `vabsdu` binutils-blindspot instructions** across all `33` `.o` files and linked `runner_vsx_p8` (while the `-mcpu=power9` control triggers `6,265` ISA 3.0 delta hits) (`[MEASURED]`).
   - Why static-in-WebKit instead of an external library (`[CODE]`, `[DOC]`): `Source/ThirdParty/skia/CMakeLists.txt` builds `Skia` as an internal `STATIC` library directly linked into `libwebkitgtk`, with `SkGraphics::Init()` initializing `SkOpts::Init*()` inside WebProcess/UIProcess. Patching `Source/ThirdParty/skia/` applies identically to both `ours/webkit2gtk-4.1` and `ours/webkitgtk-6.0` on the next WebKit rebuild.

---

## Baseline Audit of WebKit `2.54.3` Skia (`[CODE]`, `[MEASURED]`)

| Component | Baseline Behavior on `ppc64le` (`-mcpu=power8`) | Finding |
|---|---|---|
| `SkFeatures.h` / `SkOpts_SetTarget.h` | No `SK_PPC_HAS_VSX` macro; `SK_OPTS_NS` defaults to scalar/portable | Missed VSX target namespace (`[CODE]`) |
| `SkRasterPipeline_opts.h` | Falls through to `#define SKRP_CPU_SCALAR` (`highp_stride=1`, `lowp=nullptr`) | All `SkRasterPipeline` stages execute 1 pixel at a time (`[MEASURED]`) |
| `SkSwizzler_opts.inc` | Falls into `portable` loops on all 12 swizzlers (`lwbrx`+`rotlwi`, `lbzu`) | Scalar byte/pixel unpacking (`[CODE]`) |
| `SkBlitRow_opts.h` | `blit_row_s32a_opaque` runs 1 px/iter scalar loop (`lwzu`, `mullw`) | `3.93 ns/px` p8 / `3.33 ns/px` p9 (`[MEASURED]`) |
| `SkBlitMask_opts.h` | Falls into generic `Sk4px::MapDstAlpha`; GCC at `-O2` fails to inline `approx_scale<16>` / lambda (`bl`, stack spills, `mtvsrdd`/`stxv` per 4 px) | `14.07 ns/px` opaque (`p8`), `17.78 ns/px` general (`p8`) (`[MEASURED]`, `[CODE]`) |
| `SkBitmapProcState_opts.h` | Scalar `filter_and_scale_by_alpha` SWAR (`0xFF00FF`) | `4.61 ns/px` p8 / `4.15 ns/px` p9 (`[MEASURED]`) |
| `SkVx.h` | Emits 4× `bl sqrtf` + NaN branches, 4× `bl lrintf`, manual overflow branches in `saturated_add`, scalar `any`/`all`/`strided_load4` | Scalar `libm` & spill overhead (`[CODE]`, `[MEASURED]`) |
| `skcms_TransformBaseline.cc` | Uses 4-wide GNU vector extensions (`N = 4`); GCC emits VSX (`lxvd2x`, `xvmulsp`, `xvaddsp`) | Already vectorized (~`61–66 ns/px` for sRGB→P3) (`[MEASURED]`) |
| `SkMemset_opts.h` | `SkVx` `16 / sizeof(T)` loop auto-vectorized by GCC (`stxvd2x`, `xxspltd`) | Already vectorized (`[MEASURED]`, `[CODE]`) |

---

## Prototype Architecture & Compiler Pitfalls Overcome (`[CODE]`, `[MEASURED]`)

1. **`<altivec.h>` `vec_perm` vs raw ISA `vperm` byte indexing on `ppc64le` (`[MEASURED]`, `[SPEC]`):**
   - Although raw Power ISA `vperm` indexes `b||a` in big-endian `15 - j` order, GCC's `<altivec.h>` `vec_perm(va, vb, vm)` on `ppc64le` emits `xxlnot` + swapped operands (`vperm b, a, ~m`) so `vm` uses **direct little-endian byte indices** (`0..15` selecting `va`, `16..31` selecting `vb`). Verified via probe and differential oracle across all `vec_perm` masks (`[MEASURED]`).
   - Always `#undef vector`, `#undef pixel`, and `#undef bool` immediately after `#include <altivec.h>`. Wrap macro arguments like `{0, 0, 0, 0}` into `const` variables before passing to `<altivec.h>` macros such as `vec_any_ne` / `vec_all_ne` (`[CODE]`).

2. **`lowp` `round_F_to_U16` and `__builtin_convertvector` on GCC `ppc64le` (`[MEASURED]`):**
   - Initial `lowp` gradients ran slower than `highp` (`17.81 ns/px` vs `9.37 ns/px` on p9) because:
     1. `lowp::round_F_to_U16` called `min(max(0, R), 1)` (emitting 32 `fcmpu` branches) instead of VSX `min_intr`/`max_intr` (`xvminsp`/`xvmaxsp`), and
     2. GCC lowered `__builtin_convertvector(Vec<8, float>, Vec<8, uint16_t>)` into 8 scalar `fctiwuz` + `mffprwz` + `mtvrd` + `vmrghh` cross-domain transfers (`[MEASURED]`).
   - Specializing `lowp::cast` for VSX (`split` + `vec_ctu`/`vec_cts`/`vec_ctf` + `vec_pack`/`vec_mergeh/l`), `lowp::mad`/`nmad` (`split` + `vec_madd`/`vec_nmsub`), and `round_F_to_U16` (`min_intr`/`max_intr`) eliminated all `fcmpu`/`fctiwuz`/`mffprwz` instructions (shrinking `vsx::lowp::evenly_spaced_2_stop_gradient` to `88` instructions, `0` branches) and cut `RP_lowp_grad_srcover` to **`8.08 ns/px` (`4.37x` vs baseline)** (`[MEASURED]`).

3. **2-pixel Y-first bilinear filter vs 1-pixel cross-domain stalls in `S32_alpha_D32_filter_DX` (`[MEASURED]`):**
   - A 1-pixel VSX port regressed (`4.15 -> 5.85 ns/px` on p9) because packing `(row0[x0], row1[x0])` and extracting one packed pixel crossed GPR ↔ VSR 5 times per pixel (`[MEASURED]`).
   - Batching 2 pixels in `uint64_t` GPR pairs (`mtvsrd` once per row pair, single `mfvrd` + 8-byte store for 2 output pixels) and applying constant scanline `wy`/`16-wy` weights first eliminated horizontal reductions and turned the regression into a **1.13x** speedup (`4.61 -> 4.09 ns/px` p8, `4.15 -> 3.67 ns/px` p9) (`[MEASURED]`).

4. **Dedicated VSX `SkBlitMask_opts.h` bypassing `Sk4px::MapDstAlpha` (`[MEASURED]`, `[CODE]`):**
   - Implementing `blit_mask_d32_a8_{black,opaque,general}` in `SkBlitMask_opts.h` (`8 px/iter` using strictly 8-byte `mask` loads via `memcpy`, `vec_xl`/`vec_xst` for `device`, `vec_perm` mask expansion, `vec_mladd` + `vec_sr(..., 8)`, and `vec_pack`) eliminated every out-of-line call and accelerated mask blitting **11.4x–13.4x** with `maxdiff = 0` (`[MEASURED]`).

---

## Head-to-Head Performance Benchmarks on Native POWER9 (`[MEASURED]`)

Buffer: `1920 × 256` (`491,520` pixels), median of `11` timed iterations after `3` warmups.  
Speedups for `RP_lowp_*` are reported against `base` `RP_highp_*` (because baseline `lowp` is disabled / `nullptr`).

| Benchmark | `base_p8` (ns/px) | `vsx_p8` (ns/px) | `p8` Speedup | `base_p9` (ns/px) | `vsx_p9` (ns/px) | `p9` Speedup |
|---|---:|---:|---:|---:|---:|---:|
| `RGBA_to_BGRA` | 0.400 | 0.171 | **2.34x** | 0.400 | 0.186 | **2.15x** |
| `RGBA_to_rgbA` | 2.400 | 1.155 | **2.08x** | 2.365 | 0.960 | **2.46x** |
| `RGBA_to_bgrA` | 2.403 | 1.154 | **2.08x** | 2.373 | 0.955 | **2.48x** |
| `rgbA_to_RGBA` | 8.936 | 3.515 | **2.54x** | 8.354 | 3.294 | **2.54x** |
| `gray_to_RGB1` | 0.834 | 0.222 | **3.76x** | 0.832 | 0.168 | **4.95x** |
| `grayA_to_RGBA` | 0.982 | 0.123 | **7.98x** | 0.968 | 0.122 | **7.93x** |
| `grayA_to_rgbA` | 1.754 | 0.389 | **4.51x** | 1.745 | 0.384 | **4.54x** |
| `RGB_to_BGR1` | 0.793 | 0.227 | **3.49x** | 0.775 | 0.236 | **3.28x** |
| `blit_row_s32a_opaque` | 3.931 | 1.098 | **3.58x** | 3.329 | 0.911 | **3.65x** |
| `blit_mask_d32_a8_black` | 10.620 | 0.902 | **11.77x** | 9.456 | 0.751 | **12.59x** |
| `blit_mask_d32_a8_opaque` | 14.069 | 1.234 | **11.40x** | 13.837 | 1.036 | **13.36x** |
| `blit_mask_d32_a8_general` | 17.779 | 1.404 | **12.66x** | 15.471 | 1.162 | **13.31x** |
| `S32_alpha_D32_filter_DX` | 4.605 | 4.087 | **1.13x** | 4.153 | 3.673 | **1.13x** |
| `RP_highp_srcover_8888` | 31.645 | 9.191 | **3.44x** | 30.424 | 8.265 | **3.68x** |
| `RP_lowp_srcover_8888` *(vs base highp)* | 31.645 | 3.458 | **9.15x** | 30.424 | 3.134 | **9.71x** |
| `RP_highp_grad_srcover` | 37.116 | 10.692 | **3.47x** | 35.332 | 9.562 | **3.70x** |
| `RP_lowp_grad_srcover` *(vs base highp)* | 37.116 | 10.188 | **3.64x** | 35.332 | 8.076 | **4.37x** |
| `RP_highp_bilerp_8888` | 72.935 | 28.380 | **2.57x** | 70.703 | 25.582 | **2.76x** |
| `RP_lowp_bilerp_8888` *(vs base highp)* | 72.935 | 21.048 | **3.47x** | 70.703 | 18.195 | **3.89x** |
| `skcms_srgb_to_p3_8888` *(baseline already VSX)* | 61.030 | 63.701 | 0.96x | 65.453 | 65.677 | 1.00x |

---

## Verification & ISA Compliance Summary (`[MEASURED]`)

- **Differential Oracle (`runner_vsx_p8 --verify ref_p8` and `runner_vsx_p9 --verify ref_p8`):**
  - `27/27` binary/float oracle suites **PASS** + `SkVx` edge checks **PASS** on both `-mcpu=power8` and `-mcpu=power9`.
  - Exact bit-identity (`maxdiff = 0` / `maxerr = 0`) on `25` suites (`RGBA_to_BGRA`, `RGBA_to_rgbA`, `RGBA_to_bgrA`, `inverted_CMYK_to_{RGB1,BGR1}`, `gray_to_RGB1`, `grayA_to_{RGBA,rgbA}`, `RGB_to_{RGB1,BGR1}`, `blit_row_s32a_opaque`, `S32_alpha_D32_filter_DX`, `blit_mask_d32_a8_{black,opaque,general}`, `rp_highp_{srcover_8888,grad,f32_roundtrip,u16x4_roundtrip,rg1616_roundtrip,bilerp_8888}`, `skcms_srgb_to_p3_8888`, and `lowp` `srcover`/`grad`/`bilerp` vs `highp`); `maxdiff = 1` on `rgbA_to_RGBA` and `rgbA_to_BGRA`.
- **POWER8 Baseline ISA 2.07 Audit (`objdump -d -M power8` vs `-M power9` + `\bvabsdu`):**
  - All `33` object files in `obj_vsx_p8/*.o`: **`isa30_delta = 0`**, **`vabsdu = 0`**.
  - Linked `runner_vsx_p8`: `total = 88454`, `p8_.long = 3594`, `p9_.long = 3594`, **`isa30_delta = 0`**, **`vabsdu = 0`**.
  - Positive control (`runner_vsx_p9` built identically except `-mcpu=power9`): `total = 84850`, `p8_.long = 9861`, `p9_.long = 3596`, **`isa30_delta = 6265`**.
  - Note: dynamic `qemu-ppc64le -cpu power8` execution was not run without a POWER8 `libc.so.6` sysroot (host runtime `libc.so.6` contains ISA 3.0 `extswsli`), so POWER8 baseline compliance is established by `-mcpu=power8` compilation plus the differential `objdump` ISA scan.
- **Clean Patch Dry-Run (`patch -p1 -F0 --dry-run`):**
  - [`0003-skia-ppc64le-vsx-cpu-raster.patch`](./0003-skia-ppc64le-vsx-cpu-raster.patch) applies cleanly with fuzz `0` against unmodified WebKit `2.54.3` files under `Source/ThirdParty/skia/` (`8` files, `+1017/-13`).

---

## Readiness for Next WebKit Rebuild

When ready to bundle into the next `webkit2gtk-4.1` and `webkitgtk-6.0` rebuild (without triggering an intermediate rebuild beforehand):
1. Copy `ours/webkit/research/0003-skia-ppc64le-vsx-cpu-raster.patch` alongside `0001-*` and `0002-*` in `ours/webkit2gtk-4.1/` and `ours/webkitgtk-6.0/`.
2. Add it to `source=()` and `sha256sums=()` (`updpkgsums`), apply with `patch -Np1 -i "$srcdir/0003-skia-ppc64le-vsx-cpu-raster.patch"` in `prepare()`, and bump `pkgrel`.
3. Note: [`WEBKIT-ON-POWER.md`](./WEBKIT-ON-POWER.md) (`Work Item #7`) and full WebKit end-to-end headless render verification (`WEBKIT_SKIA_ENABLE_CPU_RENDERING=1` pixel diff / Compositor frame timings) remain to be run once built into WebKit.
