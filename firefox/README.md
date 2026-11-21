# firefox — ppc64le packaging notes

Downstream of Arch's [firefox PKGBUILD](https://gitlab.archlinux.org/archlinux/packaging/packages/firefox)
(160.0.1-1), with runlevel5's PowerPC series and our SpiderMonkey JIT
performance patches on top.

## Patch stack (applied in `source=()` order)

| Patches | From | What |
|---|---|---|
| `0001` | Arch | install under the remoting name |
| `0002`–`0031` | [runlevel5/firefox-ppc64](https://github.com/runlevel5/firefox-ppc64) | the ppc64 JIT, VSX/AltiVec paths (Skia, libwebp, libyuv, jxl, swizzles, SWGL, text scanning, string search), NSS acceleration gated on the target baseline, the Linux sandbox on ppc64 |
| `0032`–`0034` | ours | the ppc64 JIT performance series: roughly 2x JavaScript on POWER8 |
| `0035` | ours | ppc64 JIT: patch OSI points with a single `bl` (fixes tab crashes with a garbage `cx->realm_` on POWER9) |
| `hotfix-*`, `sandbox-*`, `xlib-success` | T2 SDE | portability fixes |
| `power8-jxl-simd-no-power9-tier.diff` | ours | baseline pool only: drop jxl_simd's POWER9 tier (see POWER8 below) |

### Where 0002–0031 come from

runlevel5 rebases one `ppc64` branch onto each release and does not keep a
per-release branch. The `FIREFOX_*_RELEASE_PPC64` tags mark Mozilla's release
commits, not the series. The 160.0.1 series is the branch as pushed on
2026-11-17, head `108dab0153a3` = `FIREFOX_160_0_1_RELEASE` (`58fed86b1b68`)
+ 30 commits, found through the repository's push events. To refresh for a
later release, take the branch head that sits on that release's commit and
`git format-patch` the commits above it.

### 0032–0034: our JIT performance series

Measured by the POWER8 tester on 154: the load64 stanza as patchable
immediates (no `mflr`/`bcl` round trip per 64-bit constant), short forward
branches with veneers instead of 10-slot NOP padding (Ion code was 38-56%
NOPs), and codegen/call-path/bound-branch fixes. runlevel5 has not taken
them (only our `xsmindp` fix, which is now in their series). Each patch
carries a note on its rebase to 160. Three 160 changes needed real code, not
just conflict resolution:

- trap sites are `FaultingCodeRange`s, so all 28 use `flushPoolForTrapSite()`;
- 160 renumbered `JSValueType` (BigInt/String/Symbol above Object), so
  `branchTestPrimitive` is an equality test against the Object tag;
- the wasm trap-instruction summarizer is no longer debug-only in 160, and it
  did not know `lwax`, which 0034 emits for zero-offset `load32(BaseIndex)`:
  it is decoded as a Load32 now. Without that, wasm GC traps would be
  mishandled in release builds.

Verified with the SpiderMonkey jit-test suite on a debug shell of exactly this
tree: no failures and no timeouts, natively and with `MOZ_PPC64_FORCE_POWER8=1`.

### 0035: OSI points patched with a single `bl`

Ion invalidation patches each active frame's OSI point (`PatchWrite_NearCall`).
On ppc64 the patch was a 40-byte load64 + mtctr + bctrl stanza, and
`generateEpilogue()` flushes the constant pool right after the epilogue,
which is 24 bytes since 0034. That put the first pool entry inside the
patched window.

An invalidated frame still runs the code between its call's return and the
OSI point. After a generic cross-realm call that code restores the realm from
that first pool entry. So on POWER9 it stored the stanza's own `mtctr r16;
bctrl` (`0x4e8004217e0903a6`) in `cx->realm_`, and the tab crashed with
SIGSEGV `si_code` 3.

The patch is now one `bl` (`PatchWrite_NearCallSize()` = 4), as on arm and
arm64. Both callers call an epilogue in the same JitCode, and a pool dump
always starts with its guard branch, so the patch only ever lands on an
instruction.

The new jit-test `ion/invalidate-osi-pool-realm.js` segfaults the unpatched
opt shell 3/3. With 0035, the opt and debug shells pass it, both natively and
forced to POWER8. The full jit-test suite passes on the debug shell: 14514/0
natively, and PASSED ALL with `MOZ_PPC64_FORCE_POWER8=1`.

## Dropped since 154.0.1-4

- `hotfix-ppc-not-power8.diff`: it stripped NSS's VSX AES/GHASH/SHA paths
  on every ppc64le build. runlevel5's series gates NSS acceleration on the
  target baseline properly, so ppc64le gets hardware crypto again.
- Our `0010` VSX string search: superseded by runlevel5's (a POWER9 fast
  path under `_ARCH_PWR9`, `vbpermq` on POWER8).
- `0002-Bug-2053518` (Rust oe-linux targets): upstream in 160.
- `hotfix-bigendian-no-fading`, `hotfix-be-image-formats`: big-endian only,
  covered by runlevel5's big-endian rendering work.

## mozconfig (`powerpc64le` case)

- Bundled NSS (`--with-system-nss` is off): runlevel5's NSS acceleration
  lives in the bundled copy.
- `--disable-crashreporter`, `--with-wasi-sysroot=/usr/share/wasi-sysroot`.
- No PGO or LTO on POWER: only x86_64 takes Arch's three-stage PGO build.

## POWER8

The JIT emits POWER8 (ISA 2.07) code unless the CPU reports POWER9; set
`MOZ_PPC64_FORCE_POWER8=1` to exercise the POWER8 paths on POWER9 hardware
(also `_POWER9`, `_POWER10`, `_970`). Compiled C++ follows the pool's `-mcpu`.

Not everything follows `-mcpu`, though. `0016` (the jxl_simd VSX backend)
compiles a second copy of every JPEG XL kernel under
`#[target_feature(enable = "power9-altivec,power9-vector")]`, and dispatches to
it when `is_powerpc64_feature_detected!("power9-vector")` reports true. That
copy is runtime-gated, so it never runs on POWER8. Even so, it put 32,033
ISA 3.0 instructions into the baseline build's libxul (154.0.1-4 had 214).

The baseline pool ships no POWER9 code at all, so `prepare()` applies
`power8-jxl-simd-no-power9-tier.diff` when the POWER8 drop-in exports
`_power8=1`. The diff deletes the Power9 arm of `simd_function_body_vsx!`, so
no ISA 3.0 instance is ever generated. With it, the baseline package scans
170, and every one of those is a known artifact:

- libxul and libsoftokn3: quad-precision forms with `v31,v31,v31` /
  `cr7,vNN,127` operands, which are jump-table data;
- libmozsqlite3: the same;
- freebl: 6 mixed forms with impossible operands, which are constant tables.

The POWER9 pool keeps the tier. A distribution that builds a single generic
ppc64le package probably wants to keep it too.

## Build

Natively, through bq (POWER9 pool) or `tools/build-ppc64le.sh` (baseline).
Never inside the POWERarm aarch64 sleeve.
