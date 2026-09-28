# chromium 153 on ppc64le: POWER8 / POWER9 build toggle

This is the 153 port. It lives in its own pkgbase (`chromium-153`) rather than
replacing `chromium/`, so the tested 151 recipe keeps shipping while this is
validated. bq derives pkgbase from the *directory name*
(`tools/closure.py:discover_recipes`) and refuses when two directories claim
one name, so the two coexist only because the directory and `pkgname` both say
`chromium-153`. Promotion is: `git mv chromium-153 chromium`, set
`pkgname=chromium`, bump pkgrel.

**Status: `prepare()` verified clean, nothing compiled yet.**
`makepkg --nobuild` exits 0 with `Sources are ready`; 38 Debian series patches
+ 3 local ppc64le patches + Arch's 20 apply with 55 hunks at offset, **0 fuzz,
0 FAILED, 0 `.rej`**. `gn gen` also succeeds against the pool's gn
(`Done. Made 31901 targets from 4976 files`). The compile itself is unproven.

## The toggle

`_power8_compat` produces both artifacts from one recipe instead of two
divergent forks. **The default in this tree is `0` (POWER9).**

```sh
makepkg -e                       # POWER9 / ISA 3.0 (default here)
_power8_compat=1 makepkg -e      # POWER8-legal
```

The policy: **source stays POWER8-compliant either way.** No POWER9-only
instruction is written into any source file. The difference is compiler flags
and which build-system feature gates get set — a POWER8 ISA floor with ISA 3.0
selected at build or runtime, the LuaJIT model.

## Which side is the well-trodden one — this inverted at 153

Both Debian and Fedora build ppc64le chromium at a **POWER8 baseline**: both
apply `third_party/0001-Force-baseline-POWER8-AltiVec-VSX-CPU-features-when-.patch`.
Fedora rawhide carries chromium 154 with `ExclusiveArch: x86_64 aarch64
ppc64le`, so ppc64le is a first-class build arch there, not a side port.

Nobody appears to ship a POWER9-baseline chromium. That means
`_power8_compat=1` is now the **upstream-identical** configuration, and our
default `_power8_compat=0` is the divergence. Scrutiny belongs on the POWER9
path, not on the Debian patches — those are load-bearing in two distributions'
production builds.

## Patch provenance: use the tag, not master

`chromium-ppc64le-patches-r4.tar.gz` is `debian/patches/ppc64le` at salsa tag
**`debian/153.0.8010.52-1`** — the exact upload Debian built on ppc64el. Refresh
from the tag matching `pkgver`, **never from master**: master tracks the next
release and does not apply. Verified — three patches from master (154-era) fail
against 153:

- `third_party/0002-regenerate-xnn-buildgn.patch` — hunks 2 and 6 FAILED
  (143k-line regenerated file; 154's xnnpack layout)
- `fixes/fix-rust-linking.patch` — hunk 2 FAILED (154 renamed
  `command`→`link_command` in both solink templates; 153's `solink_module` is
  still `command`)
- `third_party/0003-third_party-ffmpeg-Add-ppc64-generated-config.patch` —
  applies, but is 154's config

Reproducing the tarball:

```sh
curl -L "https://salsa.debian.org/chromium-team/chromium/-/archive/debian/153.0.8010.52-1/chromium-debian-153.0.8010.52-1.tar.gz?path=debian/patches/ppc64le"
# extract -> ppc64le-patches/, add debian-series = grep '^ppc64le/' series from the same tag
tar --sort=name --mtime='2026-09-18 00:00:00Z' --owner=0 --group=0 --numeric-owner \
    -cf - ppc64le-patches | gzip -n -9
```

Note r4's `debian-series` is pre-filtered to `ppc64le/` lines, unlike r1/r2
which carried Debian's entire series and relied on `prepare()` to filter.

## Our patches kept alongside Debian's

Debian now ships patches that look like duplicates of two we carry. They are
not — both were verified against the extracted 153 tree and both are kept:

- **`swiftshader-ppc-xcoff-baseclasses.patch` — kept; Debian's is a no-op
  here.** Debian's `third_party/0001-swiftshader-fix-build.patch` edits
  `third_party/swiftshader/third_party/llvm-16.0/BUILD.gn`. Stock 153
  `src/Reactor/BUILD.gn:310` hardcodes `llvm_dir = "../../third_party/llvm-10.0"`,
  so llvm-16.0 is never loaded — Debian reaches it only because their non-ppc
  series carries `debianization/swiftshader-use-llvm-16.patch`. llvm-10.0's
  `swiftshader_llvm_ppc` still lacks `MCAsmInfoXCOFF.cpp`. Debian's is skipped.
- **`chromium-151-dawn-cipd-add-ppc64le.patch` — kept; different failure.**
  Debian's `dawn-fix-ppc64le-detection.patch` reorders `__PPC__`/`__PPC64__` in
  `src/utils/platform.h`. Ours fixes `tools/python/cipd_deps.py`, which in stock
  153 still raises `ValueError('Unable to determine architecture')` on ppc64le
  and is called by `tools/generate-sources-gn.py` to locate go. Both apply.

## Deliberate skips

Recorded in a `_skip` array in `prepare()`, with the reason printed at apply time.

| Patch | Why |
|---|---|
| `third_party/0001-Force-baseline-POWER8-AltiVec-VSX-...` | POWER9 build; applied when `_power8_compat=1` |
| `third_party/0001-swiftshader-fix-build.patch` | stock builds swiftshader against llvm-10.0, not llvm-16.0 |
| `webrtc/Rtc_base-system-arch.h-PPC.patch` | **dead code.** Stock 153 `rtc_base/system/arch.h` already has an `#elif defined(__PPC__)` branch deriving 64-bit/endianness from `__PPC64__`/`__LITTLE_ENDIAN__` (both clang-defined, checked with `-dM`). Debian's hunk lands *inside* the `#if defined(__MIPSEL__)` block, unreachable on every arch, and `WEBRTC_ARCH_PPC_FAMILY` has zero users in `third_party/webrtc` |

## Patches that are required, contrary to appearances

- **`workarounds/HACK-debian-clang-disable-{base,pa}-musttail.patch` — required,
  and not Debian-specific.** Tested on Arch clang 22.1.8 / ppc64le:
  `[[clang::musttail]]` is a hard error — "external calls cannot be tail called
  on PPC", "indirect calls cannot be tail called on PPC" — at -O0 and -O2, with
  and without `-fPIC`, with and without `-mcpu=power9`.
  `allocator_shim_default_dispatch_to_partition_alloc.cc` has 20+
  `PA_MUSTTAIL return delegate->fn(...)` indirect calls, so the build fails
  without these. Fedora ships them too. Skia's `SK_HAS_MUSTTAIL` already
  excludes `SK_CPU_PPC` on its own.
- **`v8/0001-Enable-ppc64-pointer-compression.patch` — kept.** Sets only the
  `v8_enable_pointer_compression` default in `v8/gni/v8.gni`; touches no ISA
  flag. 153's `v8/BUILD.gn` asserts ppc64 is a supported shared-cage arch. The
  shipped 151 browser was built with this heap layout, so *removing* it would be
  the behavioural change. Debian and Fedora both ship it.

## Dropped upstream: v8 trap instructions

`v8/0002-Add-ppc64-trap-instructions.patch` was in r1/r2 and is gone from r4.
Not a regression — V8 absorbed it. Stock 153
`v8/src/base/immediate-crash.h:78` has `#elif V8_HOST_ARCH_PPC64` with AIX and
non-AIX trap encodings. Without either, the `#else` fallback is
`__builtin_trap()`, which still crashes correctly but with less precise reports.

## The POWER9 divergence, re-verified for 153

- **The awk hunk-strip on `baseline-isa-3-0.patch` is still correct and still
  necessary.** `v8/BUILD.gn:1752` reads
  `} else if (!v8_target_is_simulator) { cflags += [ "-mcpu=pwr9" ] }`. The
  `if (current_os == "linux") { "-mcpu=power8" ...` context that the patch's v8
  hunk edits exists *only* if Force-baseline inserted it, so with Force-baseline
  skipped the hunk has nothing to match. After patching, the ppc64 block holds
  only `-mcpu=power5+` (aix) and `-mcpu=pwr9`.
- **Nothing else depends on Force-baseline's hunks.** Only three series patches
  touch `v8/BUILD.gn` or `v8/gni`: Force-baseline, pointer-compression
  (different file), and baseline-isa-3-0 (hunk stripped). No other patch has
  `-mcpu=power8` in its context.
- **`baseline-isa-3-0` grew from 3 hunks to 7, and the skia layout moved.**
  `skia-vsx-instructions.patch` now writes `-mcpu=power8` at *three* sites —
  `skia/BUILD.gn` (new `skia_opts_vsx`), `third_party/skia/BUILD.gn`
  (`opts("vsx")`), and `third_party/skia/gn/skia/BUILD.gn` (`config("default")`)
  — and adds skia's `xvcvhpsp`/`xvcvsphp` half-float paths behind `#elif 0`.
  `baseline-isa-3-0` bumps all three to power9 and enables the half-float block.
  Both intrinsics were run on this POWER9 under clang `-mcpu=power9`: correct
  results, real `xvcvhpsp`/`xvcvsphp` emitted. The `_power8_compat=1` skia sed
  now covers `skia/BUILD.gn` as well — the 151 version missed it, which is how
  POWER8-legality came to depend on the build host's makepkg.conf.
- **POWER8 machinery confirmed gated off in the default build**, by inspecting
  the tree makepkg produced: no `-mcpu=power8` in any GN file except
  `build/config/aix`; Force-baseline skipped; loadpc not applied (reverse dry-run
  fails); skia sed not run; six `-mcpu=power9` sites present.

## gn: the git-gn step is gone

The 151 recipe built gn from a pinned commit because Arch POWER's gn was 0.2324.
Dropped: 153's `DEPS` pins gn `e8a8e093` (2026-08-13) and the pool's
`gn 0.2484.27a549cc` (2026-07-21) is a direct ancestor 33 commits behind — all
starlark, `gn edit` and test-framework work. `gn gen` with the pool gn succeeds
against the full `build()` flag set.

## Traps

- **`LC_ALL` must be set when running makepkg by hand over ssh.** ssh sessions
  have `LANG` unset, and 153 ships
  `third_party/vulkan-loader/src/tests/framework/icd/export_definitions/🌋.def`,
  so extraction dies with `bsdtar: Pathname can't be converted from UTF-8 to
  current locale`. bq exports `LANG`/`LC_ALL=C.UTF-8` (`tools/bq.py`), so builds
  through bq are unaffected.
- Arch generates its sha256sums with `_manual_clone=1`, so their `array[0]` is
  the `fetch-chromium-release` script's hash. We keep `_manual_clone=0` (the
  153 lite tarball exists, 1.7 GiB, sha
  `ed6fcbf913f12f97c619616b35fa8b56f6e61c53bdbf00cbb0e7ef839a39844a`, verified
  against Google's published `.hashes`) and keep Arch's value only inside the
  `_manual_clone` override.

## Unproven

Not compiled. Areas checked only statically: xnnpack ppc64 (all 274 `_ppc64`
targets and 982 source references exist in 153), the highway unbundle on
ppc64le (`build/linux/unbundle/highway.gn` present; system 1.4.0 matches
bundled 1.4.0), and Arch's crubit/iamf/typescript patches, which Arch has only
tested on x86.
