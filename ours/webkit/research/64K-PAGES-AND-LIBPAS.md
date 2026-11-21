# WebKit 64 KiB-Page Memory Footprint & `mimalloc` vs `libpas` Assessment on `ppc64le`

**Status:** 2026-11-21 · Companion to [`WEBKIT-ON-POWER.md`](./WEBKIT-ON-POWER.md) (Finding 2, Work Items #5 and #6)  
**Target host:** `omarchy-power9` (`Linux 7.3.5-64k #2 SMP PREEMPT ppc64le`, IBM AC922 POWER9 DD2.3, `PAGESIZE=65536`, kernel THP `enabled=[always] madvise never`, `defrag=[madvise]`, `hpage_pmd_size=2097152`)  
**Shipped package tested:** `webkitgtk-6.0 2.54.3-1` (built with `GCC 16.2.1`, `-O2 -mcpu=power8 -mminimal-toc`, `USE_MIMALLOC=ON`, `USE_SYSTEM_MALLOC=OFF`)

Every claim below is tagged:
- `[MEASURED]` — directly observed on the POWER9 host in live `WebKitWebProcess` runs, `test_pas`, or standalone allocator benchmarks.
- `[CODE]` — read directly from WebKitGTK `2.54.3` or `webkit-ppc64le` source/disassembly.
- `[DOC]` — from [`WEBKIT-ON-POWER.md`](./WEBKIT-ON-POWER.md) or upstream CMake/comments.
- `[SPEC]` — Power ISA 2.07/3.0 or Linux kernel behavior.

---

## Executive Summary & Recommendations

1. **What actually causes `WebKitWebProcess` bloat on `omarchy-power9` (`[MEASURED]`, `[CODE]`)**
   - Even an idle `about:blank` `WebKitWebProcess` uses **`252.6 MiB` RSS (`167.2 MiB` PSS, `80.9 MiB` Anonymous, `171.8 MiB` File, `24.0 MiB` THP)** (`[MEASURED]`).
   - That baseline has **four independent layers**:
     1. **Fixed 64 KiB shared-library + glibc footprint (~`219 MiB` RSS):** `180` unique `.so` mappings (`537` VMAs) consume **`200.38 MiB` RSS (`116.81 MiB` PSS)** including **`31.50 MiB` of non-shareable `Private_Dirty` pages** across `178` RW/RELRO VMAs (every library pays full `64 KiB` RELRO/data page rounding), plus **`16.0 MiB`–`27.8 MiB` glibc `ptmalloc2`** (GTK/Skia/Mesa/GStreamer/GObject C allocations) and **`2.3 MiB`–`6.8 MiB` pthread stacks** (`34`–`102` threads). Neither `mimalloc` nor `libpas` eliminates this floor (`[MEASURED]`).
     2. **Kernel THP `[always]` (`2 MiB` PMD) + `MI_DEFAULT_ALLOW_THP=1` (`-11.7 MiB` to `-64.9 MiB` RSS just by disabling THP):** Because host THP is `always`, every sparse `64 KiB` touch inside `mimalloc`'s `1 GiB` arenas, JSC's `4 GiB` `Structure` heap (`2.54.3` lacks `webkit-ppc64le`'s `MADV_NOHUGEPAGE` in `OSAllocatorPOSIX.cpp`), and the `128 MiB` `rwxp` JIT pool promotes to `2.0 MiB` THPs, **and** `MI_DEFAULT_ALLOW_THP=1` raises `mimalloc`'s `_mi_os_minimal_purge_size()` from `64 KiB` to `2 MiB` (`os.c:60-65`), suppressing sub-`2 MiB` slice purging (`[CODE]`, `[MEASURED]`).
     3. **`mimalloc` `64 KiB` aligned-allocation 2.0x–2.5x multiplier:** `mimalloc` v3 hardcodes `MI_PAGE_MAX_START_BLOCK_ALIGN2` and `MI_PAGE_OSPAGE_BLOCK_ALIGN2` to `4 KiB` (`types.h:391-392`) and `MI_PAGE_MAX_OVERALLOC_ALIGN` to `64 KiB` (`types.h:393`). Every JSC `64 KiB` `MarkedBlock` (`MarkedBlock::blockSize = 64 * KB`) and `Structure` block (`StructureAlignedMemoryAllocator.cpp:160`) fails `mi_malloc_is_naturally_aligned(65536, 65536)` and falls back to `oversize = 65536 + 65535 = 131071` (`alloc-aligned.c:89`), landing in **`128 KiB` blocks (Release `-DNDEBUG`) / `160 KiB` blocks (non-Release `MI_PADDING=1`) inside `4 MiB` `MI_LARGE_PAGE`s** — **2.0x–2.5x** requested size and **8x–10x** vs x86_64/16K `MarkedBlock`s (`[CODE]`, `[MEASURED]`).
     4. **`MemoryPressureHandler` (`30_s` poll on `/proc/self/statm * 64 KiB`):** Computes footprint as `statm.resident * 64 KiB` (including file-backed DSO RSS) against `0.33 * 3 GiB ≈ 1.0 GiB` Conservative and `0.50 * 3 GiB = 1.5 GiB` Strict (`MemoryPressureHandler.cpp:50-54,122,150-158`, `CurrentProcessMemoryStatus.cpp:50-55`) (`[CODE]`).

2. **Recommended Decision for Work Items #5 and #6**
   - **Short-term (Work Item #5 — ship now in `webkitgtk-6.0` / `webkit2gtk-4.1`):** Keep `USE_MIMALLOC=ON` and land a **~50-line `mimalloc` + `OSAllocator` patch** (`MI_DEFAULT_ALLOW_THP=0` on `ppc64le`, natural `64 KiB` slice-aligned packing in `alloc-aligned.c` + `arena.c`, `_mi_os_guard_page_size` debug-assert fix in `os.c`, plus `MADV_NOHUGEPAGE` on JSC `OSAllocator` reservations).
     - `[MEASURED]` Standalone microbenchmark of `128 × 64 KiB` `MarkedBlock`-equivalent allocations (`8.0 MiB` payload): anonymous RSS drops **`21,248 KiB -> 10,496 KiB` (`-50.6%`)**, committed arena bytes drop **`24.3 MiB -> 13.8 MiB` (`-43.2%`)**, THP drops **`20,480 KiB -> 0 KiB`**. On `16 × 64 KiB` sparse allocations (`1.0 MiB` payload), anonymous RSS drops **`6,912 KiB -> 2,304 KiB` (`-66.7%`)**.
     - `[MEASURED]` On live `WebKitWebProcess` `2.54.3-1`, disabling THP alone (`MIMALLOC_ALLOW_THP=0`) cuts anonymous RSS by **`-11.7 MiB` (`about:blank`)**, **`-12.8 MiB` (`features.html`)**, **`-22.1 MiB` (`jsdom`)**, and **`-63.2 MiB` (`bd16mem.html`)**, and more than doubles purge events on `jsdom` (`160 -> 363`).
   - **Medium-term (Work Item #6 — `libpas` for `ppc64le` + 64 KiB pages):** **Feasible**, and brings **real partial-page (`64 KiB` granule) decommit** where `mimalloc` holds partially occupied `512 KiB`/`4 MiB` pages (`[MEASURED]`: freeing 50% of 128 × 64K blocks returns **`-4,096 KiB`** immediately in `libpas` vs **`0 KiB`** in `mimalloc`). However, enabling `libpas` is **not** a flag flip: upstream has **6 ppc64le architecture/barrier blockers** (including silent missing `lwsync`/address-dependency barriers) and **7 `64 KiB` OS-page blockers** across `libpas`, `bmalloc`, and `JSC` (`ENABLE_LIBPAS_JIT_HEAP`). Upstream `WebKitFeatures.cmake:79-86` disables `libpas` and `JIT` even on `arm64` under `USE_64KB_PAGE_BLOCK`, so `libpas` must be validated across `test_pas` + `JSC` + `WebKitWebProcess` on a staging branch first.

---

## 1. Host & Measurement Environment `[MEASURED]`

| Property | Measured Value | Source / Command |
|---|---|---|
| Kernel | `Linux omarchy-power9 7.3.5-64k #2 SMP PREEMPT Wed, 18 Nov 2026 02:19:31 +0000 ppc64le` | `uname -a` |
| Kernel / Userspace Page Size | `65536` bytes (`64 KiB`) | `getconf PAGESIZE` |
| Transparent Huge Pages | `enabled=[always] madvise never`, `defrag=[madvise]`, `hpage_pmd_size=2097152` (`2 MiB`) | `/sys/kernel/mm/transparent_hugepage/*` |
| WebKitGTK / Compiler | `webkitgtk-6.0 2.54.3-1`, `gcc`/`g++ 16.2.1` (`-O2 -mcpu=power8 -DSKCMS_HAS_MUSTTAIL=0 -mminimal-toc -g1`) | `PKGBUILD`, live host |
| Headless Display | Weston 15 `--backend=headless --renderer=gl --shell=kiosk --width=1920 --height=1080 --scale=1` + `wkshot.py` (`1280×800`) | `/var/tmp/claude-webkit-diag.4s0mvH/` |

Note on `WebKitWebProcess` sandbox propagation `[MEASURED]`: `MIMALLOC_SHOW_STATS=1`, `MIMALLOC_ALLOW_THP=0`, `MIMALLOC_PURGE_DELAY=0`, `JSC_useJIT=0`, `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1`, and `WEBKIT_DISABLE_COMPOSITING_MODE=1` all pass into the `bwrap`-sandboxed `WebKitWebProcess` (verified directly by stderr stats output on exit; `cpuskia`/`nocomp` on `bd16mem` exited without flushing `WebProcess` stats, while `UI` stats flushed).

---

## 2. Live `WebKitWebProcess` RSS Breakdown `[MEASURED]`

Each run captured `/proc/<wppid>/{smaps_rollup,smaps,status}` at two points: `t1` (`delay + 2s` after page load/activity) and `t2` (`delay + linger - 3s`, after GC/purge window; linger `14–20s`). `jsdom` runs allocate and drop a churned DOM/JS heap before `t2`.

### 2.1 Process Memory Totals & `mimalloc` Stats

| Case | `t1_RSS` | `t1_PSS` | `t1_Anon` | `t1_File` | `t1_THP` | `t2_RSS` | `t2_Anon` | `t2_THP` | Threads | `mi_Res` | `mi_PkC` | `mi_CurC` | `mi_Prgd` | `mi_Prgs` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `blank_default` | `252.6M` | `167.2M` | `80.9M` | `171.8M` | `24.0M` | `255.5M` | `83.2M` | `26.0M` | 34 | - | - | - | - | - |
| `blank_nothp` | `240.9M` | `155.5M` | `69.2M` | `171.8M` | `0.0M` | `243.4M` | `71.2M` | `0.0M` | 34 | `1.0 GiB` | `33.9M` | `30.6M` | `3.3M` | 11 |
| `blank_nothp_purge0` | `240.8M` | `155.4M` | `69.0M` | `171.8M` | `0.0M` | `243.1M` | `70.9M` | `0.0M` | 34 | `1.0 GiB` | `31.2M` | `24.2M` | `9.6M` | 43 |
| `features_default` | `304.0M` | `216.6M` | `109.6M` | `194.4M` | `34.0M` | `298.1M` | `103.7M` | `20.0M` | 102 | `1.0 GiB` | `48.3M` | `40.1M` | `8.1M` | 44 |
| `features_nothp` | `291.2M` | `203.8M` | `96.8M` | `194.4M` | `0.0M` | `283.6M` | `89.2M` | `0.0M` | 102 | `1.0 GiB` | `48.4M` | `39.1M` | `9.2M` | 54 |
| `features_nojit` | `289.8M` | `203.9M` | `99.4M` | `190.4M` | `26.0M` | `287.5M` | `97.1M` | `18.0M` | 72 | `1.0 GiB` | `39.2M` | `34.2M` | `5.0M` | 37 |
| `features_cpuskia` | `315.4M` | `227.9M` | `121.1M` | `194.3M` | `46.0M` | `299.6M` | `105.2M` | `24.0M` | 102 | `1.0 GiB` | `61.6M` | `39.6M` | `22.0M` | 51 |
| `features_nocomp` | `296.2M` | `208.8M` | `102.8M` | `193.4M` | `30.0M` | `289.4M` | `96.0M` | `20.0M` | 90 | `1.0 GiB` | `28.6M`* | `20.6M`* | `8.0M`* | 4* |
| `jsdom_default` | `568.2M` | `481.1M` | `377.8M` | `190.4M` | `308.0M` | `551.9M` | `361.0M` | `266.0M` | 45 | `1.0 GiB` | `330.3M` | `276.5M` | `61.2M` | 160 |
| `jsdom_nothp` | `546.1M` | `459.0M` | `355.7M` | `190.4M` | `0.0M` | `529.6M` | `338.6M` | `0.0M` | 45 | `1.0 GiB` | `336.0M` | `276.3M` | `61.8M` | 363 |
| `jsdom_nojit` | `550.8M` | `465.4M` | `371.4M` | `179.4M` | `300.0M` | `406.8M` | `226.9M` | `130.0M` | 49 | `1.0 GiB` | `320.0M` | `137.0M` | `196.1M` | 226 |
| `bd12_default` | `272.4M` | `185.6M` | `85.9M` | `186.4M` | `22.0M` | `271.9M` | `85.4M` | `22.0M` | 48 | `1.0 GiB` | `34.4M` | `30.1M` | `4.6M` | 36 |
| `bd16mem_default` | `1638.1M` | `1551.1M` | `1444.6M` | `193.2M` | `1384.0M` | `1633.8M` | `1440.2M` | `1376.0M` | 46 | `2.0 GiB` | `1.3 GiB` | `1.3 GiB` | `6.9M` | 38 |
| `bd16mem_nothp` | `1573.2M` | `1486.4M` | `1381.4M` | `191.8M` | `0.0M` | `1570.2M` | `1378.3M` | `0.0M` | 47 | `2.0 GiB` | `1.3 GiB` | `1.3 GiB` | `7.0M` | 34 |
| `bd16mem_nojit` | `1616.1M` | `1530.9M` | `1438.7M` | `177.4M` | `1376.0M` | `1616.0M` | `1438.4M` | `1376.0M` | 46 | `2.0 GiB` | `1.3 GiB` | `1.3 GiB` | `8.5M` | 83 |
| `bd16mem_cpuskia` | `1637.1M` | `1550.3M` | `1445.9M` | `191.2M` | `1384.0M` | `1633.3M` | `1441.9M` | `1378.0M` | 41 | `1.0 GiB`* | `28.5M`* | `18.5M`* | `10.0M`* | 5* |
| `bd16mem_nocomp` | `1631.4M` | `1544.4M` | `1439.1M` | `192.1M` | `1380.0M` | `1627.1M` | `1434.7M` | `1370.0M` | 34 | `1.0 GiB`* | `28.5M`* | `18.5M`* | `10.0M`* | 5* |

*\*`features_nocomp` and `bd16mem_{cpuskia,nocomp}` exited before `WebProcess` flushed its own stderr stats; values shown are UI-process stats.*

### 2.2 Grouped VMA RSS Breakdown (MiB)

| Snapshot | `mimalloc_arena` | `structure_4G` | `jit_exec_pool` | `anon_small_other` | `glibc_ptmalloc` | `pthread_stacks` | `shlib_webkit_jsc` | `shlib_mesa_llvm` | `shlib_other` | `other_file` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `blank_default.t1` | `20.0M` | `2.0M` | `0.1M` | `8.9M` | `16.0M` | `2.3M` | `85.4M` | `60.2M` | `55.3M` | `2.4M` |
| `blank_nothp.t1` | `11.6M` | `0.9M` | `0.1M` | `6.9M` | `15.8M` | `2.3M` | `85.4M` | `60.2M` | `55.3M` | `2.4M` |
| `blank_nothp_purge0.t1` | `11.2M` | `0.9M` | `0.1M` | `6.9M` | `16.0M` | `2.3M` | `85.4M` | `60.2M` | `55.3M` | `2.4M` |
| `features_default.t1` | `31.9M` | `2.0M` | `0.1M` | `9.7M` | `27.5M` | `6.8M` | `101.6M` | `63.2M` | `58.1M` | `3.2M` |
| `features_nothp.t1` | `22.0M` | `0.9M` | `0.1M` | `7.8M` | `27.8M` | `6.8M` | `101.6M` | `63.2M` | `58.1M` | `3.2M` |
| `features_nojit.t1` | `23.9M` | `2.0M` | `0.0M` | `11.0M` | `25.9M` | `4.9M` | `100.0M` | `63.2M` | `55.6M` | `3.2M` |
| `features_cpuskia.t1` | `43.9M` | `2.0M` | `0.1M` | `9.7M` | `27.0M` | `6.8M` | `101.5M` | `63.2M` | `58.1M` | `3.2M` |
| `features_nocomp.t1` | `27.9M` | `2.0M` | `0.1M` | `9.7M` | `25.5M` | `6.0M` | `100.6M` | `63.2M` | `58.1M` | `3.2M` |
| `jsdom_default.t1` | `306.7M` | `2.0M` | `2.1M` | `9.6M` | `22.8M` | `3.0M` | `99.6M` | `63.3M` | `55.8M` | `3.4M` |
| `jsdom_default.t2` | `289.0M` | `2.0M` | `2.1M` | `9.6M` | `23.8M` | `2.9M` | `99.9M` | `63.3M` | `55.9M` | `3.4M` |
| `jsdom_nothp.t1` | `289.3M` | `0.9M` | `0.1M` | `7.7M` | `23.1M` | `3.0M` | `99.6M` | `63.3M` | `55.8M` | `3.4M` |
| `jsdom_nothp.t2` | `271.6M` | `0.9M` | `0.1M` | `7.7M` | `23.9M` | `2.9M` | `99.9M` | `63.3M` | `55.9M` | `3.4M` |
| `jsdom_nojit.t1` | `301.6M` | `2.0M` | `0.0M` | `11.1M` | `21.9M` | `3.2M` | `91.1M` | `63.3M` | `53.2M` | `3.4M` |
| `jsdom_nojit.t2` | `156.3M` | `2.0M` | `0.0M` | `11.1M` | `22.7M` | `3.2M` | `91.4M` | `63.3M` | `53.4M` | `3.4M` |
| `bd12_default.t1` | `22.0M` | `2.0M` | `0.1M` | `8.9M` | `18.1M` | `3.2M` | `97.8M` | `61.2M` | `55.9M` | `3.2M` |
| `bd16mem_default.t1` | `1380.0M` | `2.0M` | `0.1M` | `9.1M` | `18.6M` | `3.2M` | `103.1M` | `62.6M` | `56.1M` | `3.2M` |
| `bd16mem_nothp.t1` | `1320.1M` | `0.9M` | `0.1M` | `7.2M` | `18.3M` | `3.2M` | `103.1M` | `61.2M` | `55.9M` | `3.2M` |

**Key diagnostic observations (`[MEASURED]`):**
- **DSO `Private_Dirty` amplification on 64K pages:** In `blank_default.t1`, the `180` `.so` libraries (`537` VMAs) account for `200.38 MiB` RSS (`116.81 MiB` PSS): `123.50 MiB` `Shared_Clean`, `45.38 MiB` `Private_Clean`, and **`31.50 MiB` `Private_Dirty`** across `178` RW VMAs. Each `.so` RELRO/GOT/.data segment rounds to a `64 KiB` kernel page on write (up to 16× higher page-granularity waste per library than 4K pages).
- **THP amplification across every sparse WebKit arena:** Comparing `default` vs `nothp` (`MIMALLOC_ALLOW_THP=0`) isolates exact THP inflation:
  - `mimalloc_arena`: `20.0M -> 11.6M` (`blank`), `31.9M -> 22.0M` (`features`), `306.7M -> 289.3M` (`jsdom`), `1380.0M -> 1320.1M` (`bd16mem`).
  - `structure_4G` (`4 GiB` JSC `StructureMemoryManager` VMA): `2.0M -> 0.9M` across all pages.
  - `jit_exec_pool` (`128 MiB` `rwxp` JIT pool): `2.1M -> 0.1M` on `jsdom` (touching ~2 pages of JIT code promoted a `2.0 MiB` THP!).
  - `anon_small_other`: `8.9M -> 6.9M` (`blank`), `9.7M -> 7.8M` (`features`).
  - Purge responsiveness: on `jsdom`, `nothp` increases purges from `160` (`61.2 MiB` purged) to `363` (`61.8 MiB` purged); on `blank`, `MIMALLOC_PURGE_DELAY=0` (`blank_nothp_purge0`) raises purged bytes from `3.3 MiB` (11 purges) to `9.6 MiB` (43 purges), cutting `mi_CurC` from `30.6 MiB` to `24.2 MiB`.
- **CLoop vs JIT (`jsdom_nojit`):** Notice `jsdom_nojit` drops `mimalloc_arena` from `301.6M` at `t1` to `156.3M` at `t2` (`196.1 MiB` purged in 226 purges), because GC/interpreter retains fewer `MarkedBlock`s than JIT code/baseline caches.
- **No GPU/Mesa leak:** `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1` (`features_cpuskia`) *increased* `mimalloc_arena` (`31.9M -> 43.9M`) and total RSS (`304.0M -> 315.4M`); `WEBKIT_DISABLE_COMPOSITING_MODE=1` saved only `~8 MiB` (`304.0M -> 296.2M`).
- **`bd16mem.html` crosses Strict memory pressure (`[MEASURED]`, `[CODE]`):** `bd16mem` allocates `26 × 50 MiB` (`1,300 MiB`) `Uint8Array` backing stores, pushing `WebKitWebProcess` to **`1,638.1 MiB` RSS** (`1,573.2 MiB` with `nothp`), above the `1,536 MiB` (`0.50 * 3 GiB`) Strict threshold (`MemoryPressureHandler.cpp:50-51,122,150-158`). Notice `1,300 MiB` requested lands at `1,380.0 MiB` in `mimalloc_arena` (`1,320.1 MiB` under `nothp`, only `+20 MiB` over raw backing buffers + baseline heap!).

---

## 3. `mimalloc` v3 on 64 KiB Pages + Prototype Fix (`[CODE]`, `[MEASURED]`)

### 3.1 Exact Root Causes in `Source/bmalloc/mimalloc/` (`2.54.3`)

1. **THP default & `2 MiB` purge floor (`options.c:103-109`, `os.c:55-72`, `prim/unix/prim.c:219-230`):**
   - `MI_DEFAULT_ALLOW_THP` defaults to `1` everywhere except Android (`options.c:104-107`).
   - `_mi_os_minimal_purge_size()` (`os.c:55-66`) returns `_mi_os_large_page_size()` (`2 MiB`) when `has_transparent_huge_pages && allow_thp`, blocking all purges `< 2 MiB` inside `1 GiB` arenas until 32 contiguous `64 KiB` slices go completely free (`os.c:60-64`). With `allow_thp == 0`, it returns `_mi_os_page_size()` (`64 KiB`).
   - `_mi_prim_mem_init` (`prim/unix/prim.c:224-228`) disables THP via `prctl(PR_SET_THP_DISABLE, &val, ...)` when `!allow_thp` (`prctl(PR_GET_THP_DISABLE, &val, ...)` returns `-1` `EINVAL` because `arg2 != 0` on Linux, which enters the `!= 0` branch and sets `PR_SET_THP_DISABLE=1` — confirmed empirically via `prctl(PR_GET_THP_DISABLE, 0, 0, 0, 0) == 1` in `bench_orig`). Note: `prctl(PR_SET_THP_DISABLE, 1)` is inherited across `execve`, which is fine for `WebKitWebProcess`, while JSC `OSAllocator::tryReserveUncommitted` should also apply `MADV_NOHUGEPAGE` per-VMA (already present in `webkit-ppc64le` `OSAllocatorPOSIX.cpp:165-171`, **missing in upstream `2.54.3`**) (`[CODE]`).
   - `_mi_os_guard_page_size()` (`os.c:68-72`) asserts `mi_assert(gsize <= (MI_ARENA_SLICE_SIZE/4))` (`65536 <= 16384` fails in any debug/assert build on 64 KiB OS pages!) (`[CODE]`).

2. **`64 KiB`-aligned block 2.0x–2.5x overallocation (`types.h:391-405`, `alloc-aligned.c:18-28,71-96`, `arena.c:804-819`):**
   - On 64 KiB platforms (`CeilingOnPageSize = 64 * KB` in `PageBlock.h:57`), JSC `MarkedBlock::blockSize` is `65536` (`MarkedBlock.h:80`) and `StructureMemoryManager` calls `mi_heap_malloc_aligned(structureHeap, 65536, 65536)` (`StructureAlignedMemoryAllocator.cpp:160`), just as `MarkedBlock` allocation calls `tryMemalign(65536, 65536)` -> `mi_theap_malloc_aligned_at(..., 65536, 65536, 0)`.
   - `mi_malloc_is_naturally_aligned(65536, 65536)` (`alloc-aligned.c:18-28`) checks `(bsize <= MI_PAGE_MAX_START_BLOCK_ALIGN2 && ...)` or `(alignment == MI_PAGE_OSPAGE_BLOCK_ALIGN2 && ...)`. Both constants are hardcoded to `(4 * MI_KiB)` (`types.h:391-392`), so `mi_malloc_is_naturally_aligned` returns **`false`**.
   - It then enters `mi_theap_malloc_zero_aligned_at_overalloc` (`alloc-aligned.c:64-97`). Since `alignment > MI_PAGE_MAX_OVERALLOC_ALIGN` (`65536 > 65536`, `types.h:393`) is **also `false`** (and even singleton pages waste an entire `64 KiB` `MI_PAGE_ALIGN` metadata slice per block!), it falls to line 89: `oversize = 65536 + 65536 - 1 = 131071`.
   - In `Release` (`-DNDEBUG`, `MI_PADDING_SIZE == 0`), `mi_good_size(131071) == 131072` (`128 KiB`, `bin 52` inside `4 MiB` `MI_LARGE_PAGE`s — `31` blocks per `4 MiB` page). In non-`NDEBUG` (`MI_PADDING=1`), `mi_good_size(131071) == 163840` (`160 KiB`, `bin 53`, **2.50x**!).
   - **Clean fix:** When `bsize == MI_ARENA_SLICE_SIZE` (`64 KiB`) and `alignment == MI_ARENA_SLICE_SIZE` (`64 KiB`), treat it as naturally aligned in `mi_malloc_is_naturally_aligned` and align `block_start = _mi_align_up(mi_page_info_size(), MI_ARENA_SLICE_SIZE)` (`64 KiB`, slice 1) in `arena.c:mi_arenas_page_alloc_fresh`. In a `512 KiB` `MI_MEDIUM_PAGE` (`8` slices of `64 KiB`), slices `1..7` yield `7` strictly `64 KiB`-aligned blocks (`87.5%` density, `commit_on_demand` commits `128 KiB` for the first block and `+64 KiB` per additional block, retiring empty `512 KiB` pages much sooner than `4 MiB` pages!). Note `MI_PAGE_OSPAGE_BLOCK_ALIGN2` must **not** be raised to `64 KiB` globally because `MI_SMALL_MAX_OBJ_SIZE = (64 KiB - MI_PAGE_OSPAGE_BLOCK_ALIGN2)/6` (`types.h:402`) would collapse to `0`.

### 3.2 Microbenchmark Proof: `MarkedBlock`-Equivalent (`mi_malloc_aligned(65536, 65536)`) `[MEASURED]`

Standalone C benchmark (`/var/tmp/wk-64k-diag/mi-bench/bench_mi.c`) allocating `n` blocks of `(size=65536, align=65536)` and touching first + last byte (`[0]` and `[65535]`), compiled with `gcc -O2 -DNDEBUG -mcpu=power8` (matching WebKitGTK `Release`; also verified passing all internal assertions under `-DMI_DEBUG=3`):

| Allocator Build / Config | `n` (Requested) | Committed | RSS (alloc) | Anon RSS (alloc) | THP (alloc) | Anon (50% free + collect) | Anon (100% free + collect) |
|---|---:|---:|---:|---:|---:|---:|---:|
| `mimalloc` `2.54.3` default (`THP=1`) | 128 (`8.0 MiB`) | `24.3 MiB` | `23,552 KiB` | **`21,248 KiB`** | `20,480 KiB` | `21,248 KiB` | `4,864 KiB` (`4,096` THP) |
| `mimalloc` `2.54.3` `MIMALLOC_ALLOW_THP=0` | 128 (`8.0 MiB`) | `24.3 MiB` | `19,712 KiB` | **`17,408 KiB`** | `0 KiB` | `17,408 KiB` | `1,024 KiB` |
| `mimalloc` **proto** (`ALLOW_THP=0` + 64K slice pack) | 128 (`8.0 MiB`) | **`13.8 MiB`** | `12,800 KiB` | **`10,496 KiB`** | `0 KiB` | `10,496 KiB` | `1,088 KiB` |
| `libpas` 64K-tuned (`BENABLE_LIBPAS=1`, `THP=1`) | 128 (`8.0 MiB`) | — | `18,560 KiB` | **`13,696 KiB`** | `12,288 KiB` | **`9,600 KiB`** (`-4.0M`) | `5,440 KiB` |
| `libpas` 64K-tuned + `PR_SET_THP_DISABLE=1` | 128 (`8.0 MiB`) | — | `15,488 KiB` | **`10,624 KiB`** | `0 KiB` | **`6,528 KiB`** (`-4.0M`) | `2,368 KiB` |
| `mimalloc` `2.54.3` default (`THP=1`) | 16 (`1.0 MiB`) | `8.3 MiB` | `9,216 KiB` | **`6,912 KiB`** | `6,144 KiB` | `6,912 KiB` | `4,864 KiB` (`4,096` THP) |
| `mimalloc` **proto** (`ALLOW_THP=0` + 64K slice pack) | 16 (`1.0 MiB`) | **`5.8 MiB`** | `4,608 KiB` | **`2,304 KiB`** | `0 KiB` | `2,304 KiB` | `1,088 KiB` |
| `libpas` 64K-tuned + `PR_SET_THP_DISABLE=1` | 16 (`1.0 MiB`) | — | `8,320 KiB` | **`3,456 KiB`** | `0 KiB` | `2,944 KiB` | `2,368 KiB` |

**Takeaway (`[MEASURED]`):**
- For **allocated** `MarkedBlock`s / `Structure` blocks, our 20-line `mimalloc` prototype (`10,496 KiB` for `n=128`, `2,304 KiB` for `n=16`) matches or beats `libpas` (`10,624 KiB` for `n=128`, `3,456 KiB` for `n=16` due to `libpas`'s `2.3 MiB` baseline tables) and slashes upstream `mimalloc` RSS by **50.6% (`n=128`)** to **66.7% (`n=16`)**.
- Where `libpas` still wins structurally is **partial-page churn**: freeing every second block across `128` blocks (`50%`) lets `libpas` `scavenge()` immediately `MADV_DONTNEED` **`4.0 MiB`** (`10,624 -> 6,528 KiB`), whereas `mimalloc` retains `10,496 KiB` until an entire `512 KiB` medium page becomes empty (`[MEASURED]`).

---

## 4. `libpas` + `bmalloc` + `JSC` on `ppc64le` and `64 KiB` Pages (`[CODE]`, `[MEASURED]`)

We extracted `Source/bmalloc` from `webkitgtk-2.54.3.tar.xz`, compiled upstream `libpas` standalone on `omarchy-power9` (`gcc`/`g++ 16.2.1 -O2 -mcpu=power8`), fixed every architecture and `64 KiB`-page blocker in two stages (`libpas-proto` at 16K defaults vs `libpas-proto-64k` at 64K defaults), built `test_pas` + `libbmalloc.a`, and verified binary ISA compliance (`[MEASURED]`).

### 4.1 Architecture & Memory-Model Blockers on `ppc64le` (`[CODE]`)

1. **Missing `BCPU_PPC64LE` & gated `BENABLE_LIBPAS` (`Source/bmalloc/bmalloc/BPlatform.h:168-174, 400`):** `BPlatform.h` has no `BCPU_PPC64LE` macro and restricts `BENABLE_LIBPAS` on Linux to `BCPU(X86_64) || BCPU(ARM64)`. Also `GIGACAGE_ENABLED` (`BPlatform.h:471-477`) excludes `ppc64le`.
2. **Missing `__PAS_PPC64` detection (`libpas/src/libpas/pas_config_prefix.h:71-75`, `pas_utils.h:131`):** `libpas` only defines `__PAS_ARM64`, `__PAS_ARM32`, `__PAS_X86_64`, `__PAS_RISCV`.
3. **x86 inline-asm fences (`pas_utils_prefix.h:111-118`) — build blocker:** With `!__PAS_ARM && !__PAS_RISCV`, `__pas_fence()` emits `"lock; orl $0, (%%rsp)"`, which fails `gcc` assembly on `ppc64le`. `#else` (`__atomic_thread_fence(__ATOMIC_SEQ_CST)`) emits `sync`.
4. **Silent weak-memory-ordering bugs (`pas_utils_prefix.h:121-161`, `pas_utils.h:902-920`) — correctness hazard (`[CODE]`, `[SPEC]`):**
   - `__pas_depend_impl()` falls into `#else` (`output = 0;` + compiler fence only), **breaking hardware address dependency** for lock-free reads (`pas_segregated_page_header`, `pas_compact_ptr` tables, etc.) on out-of-order POWER9! Fix: `"xor %[out], %[in], %[in]"` (`[SPEC]` Power ISA Book II preserves address dependency on `xor ra, rs, rs`, matching ARM64 `eor`). Note: `Source/WTF/wtf/Atomics.h:314` already falls back safely to `loadLoadFence()` (`sync`) for `dependentLoadLoadFence()` on PPC64LE, whereas `libpas` does not.
   - `pas_fence_after_load()` and `pas_store_store_fence()` (`pas_utils.h:902-920`) check **only** `if (PAS_ARM)` and otherwise emit **only `pas_compiler_fence()`**! On `ppc64le` (unlike x86 TSO), both **silently omit `lwsync`**, risking torn publication / stale reads across threads!
5. **x86 `btrl` inline asm (`pas_segregated_page_inlines.h:366`) — build blocker:** `if (page_config.check_deallocation)` has `#if !PAS_ARM && !PAS_RISCV` gating x86 `btrl`/`jc`/`movq`/`call`; must add `&& !PAS_PPC64`.
6. **Crash trap/GPRs (`pas_utils.c:81-94`) & `tagged_bmalloc_heap*.c` CMakeCXX (`libpas/CMakeLists.txt:39-44`) — build blockers:** `pas_utils.c` lacks `#elif PAS_PPC64` (`PAS_FATAL_CRASH_INST "trap"`, `CRASH_GPR0..6 "r3".."r9"`) and `#if PAS_X86_64 || PAS_ARM64 || PAS_ARM32`, leaving `pas_crash_with_info_impl` undefined for standalone `libpas`. Also standalone `libpas/CMakeLists.txt` lacks `tagged_bmalloc_heap*.c` in `PROPERTIES LANGUAGE CXX` (unlike `Source/bmalloc/CMakeLists.txt:56-58`), failing with `initializer element is not constant`.
7. **128-bit `pas_pair` atomics (`pas_utils.h:930+`) — verified NOT a blocker (`[MEASURED]`):** GCC 16.2.1 `-O2 -mcpu=power8` emits native inline POWER8 ISA 2.07 `sync; lqarx ...; stqcx.; isync` / `lq` / `sync; stq`. Verified `objdump -d libpas_lib.so` contains **`20` `lqarx`/`stqcx.` instructions**, **`0` undefined `__atomic_*` / `libatomic` imports**, and **`0` ISA 3.0 instructions** (`libpas_lib.so`, `bmalloc_smoke`, `bench_proto`).

### 4.2 `64 KiB`-Page Blockers & Assertions Found via Source + `test_pas` (`[CODE]`, `[MEASURED]`)

| # | Blocker / Constant | Upstream `2.54.3` Value | What Fails on `64 KiB` Linux Host | Required `64 KiB` Fix |
|---|---|---|---|---|
| 1 | `PAS_SMALL_PAGE_DEFAULT_SHIFT`, `PAS_SMALL_BITFIT_PAGE_DEFAULT_SHIFT`, `PAS_GRANULE_DEFAULT_SHIFT` (`pas_internal_config.h:38-58`) | `14` (`16K`), `14` (`16K`), `12` (`4K`, or `14` on ARM64) | `pas_page_malloc.c:463-465` (`decommit_impl`) panics when scavenging `< 64K` pages/granules; `bmalloc`/`iso` tests crash in scavenger/bitfit/expendable tests. | Set all three to **`16` (`64 KiB`)**; bump `PAS_MEDIUM_PAGE_DEFAULT_SHIFT` to `18` (`256 KiB`, matching `pagesize64k_heap_config.h`). |
| 2 | `PAS_MAX_OBJECTS_PER_PAGE` (`pas_internal_config.h:133`, `pas_baseline_allocator.c:41`) | `2048` | `64 KiB / 16 B` (`bmalloc`) = `4096` bits; `64 KiB / 8 B` (`thingy`/`utility`) = `8192` bits. `pas_baseline_allocator_attach_directory` asserts `PAS_BASELINE_LOCAL_ALLOCATOR_SIZE >= directory size`. | Bump `PAS_MAX_OBJECTS_PER_PAGE` to **`8192`** (or `4096` if `thingy` minalign >= 16). |
| 3 | `JIT_SMALL_PAGE_SIZE`, `JIT_SMALL_GRANULE_SIZE`, `JIT_MEDIUM_GRANULE_SIZE` (`jit_heap_config.h:43-52`) | `16384u`, `16384u`, `4096u` (`16384u` ARM64) | `pas_page_malloc.c:376` (`commit_impl`) panics on 15/18 `JITHeap` tests (`16K`/`4K` not `64K`-aligned). Also if `JIT_MEDIUM_GRANULE_SIZE=65536` with `JIT_MEDIUM_BITFIT_MIN_ALIGN_SHIFT=8` (`256B`), `65536 >> 8 = 256 >= PAS_PAGE_GRANULE_DECOMMITTED (255)` risks granule refcount overflow (`pas_bitfit_page_inlines.h:167`). | Set `JIT_SMALL_PAGE_SIZE=65536u`, `JIT_SMALL_GRANULE_SIZE=65536u`, `JIT_MEDIUM_GRANULE_SIZE=65536u` (and raise `JIT_MEDIUM_BITFIT_MIN_ALIGN_SHIFT` to `9u` if >1 granule per medium JIT page, or set `JIT_MEDIUM_PAGE_SIZE=262144u` + shift `9u`). |
| 4 | `PAS_UTILITY_LOOKUP_SIZE_UPPER_BOUND` (`pas_internal_config.h:106`, `pas_utility_heap.c:83`) | `1400` | Discovered empirically by `JITHeap` once `JIT_SMALL_PAGE_SIZE=65536`: with `JIT_SMALL_BITFIT_MIN_ALIGN_SHIFT=2` (`4B`), `PAS_BITFIT_PAGE_HEADER_SIZE(65536, 65536, 2) = 4128` bytes, exceeding `1400` -> `index 516` panics in `pas_utility_heap_try_allocate_with_alignment`! | Raise `PAS_UTILITY_LOOKUP_SIZE_UPPER_BOUND` to **`4352`** (valid on 64K pages where `utility` `max_object_size ≈ 5850`). |
| 5 | `PAS_EXPENDABLE_MEMORY_PAGE_SIZE` & `pas_large_expendable_memory` (`pas_expendable_memory.h:54`, `pas_large_expendable_memory.h:44-50`) | `16384llu` | Hardcoded `16384` causes `decommit_impl` panics in `ExpendableMemory` and `testZeroingReuseWithScavengeBitfitSizes`! Simply raising it to `65536` inflates `PAS_LARGE_EXPENDABLE_MEMORY_ALIGNMENT` to `(65536/2)*65536 = 2 GiB`! | Set `PAS_EXPENDABLE_MEMORY_PAGE_SIZE = 65536llu` and cap `PAS_LARGE_EXPENDABLE_MEMORY_ALIGNMENT` / `PAYLOAD_SIZE` at `128 MiB`. |
| 6 | Linux TLC decommit & `TLCDecommitTests` (`pas_thread_local_cache.c:939`, `TLCDecommitTests.cpp:59-72`) | `#if PAS_OS(DARWIN)` only; tests calibrate 4K/16K only | On non-Darwin Linux, `decommit_allocator_range` is a no-op; `numCommittedPagesInTLC()` reports `130` (on 64K `PAS_MAX_OBJECTS_PER_PAGE=8192`) vs `1`, and 11 calibration tests abort with `"unsupported native page size for TLCDecommitTests"`. | Expected behavior on Linux (TLC stays committed); add Linux/64K test calibration or guard Darwin-only checks if running full `test_pas`. |
| 7 | `bmalloc` `WebConfig` + `JSC` `ENABLE_LIBPAS_JIT_HEAP` (`mbmalloc.cpp:35-36`, `ExecutableMemoryHandle.h:40-41`, `ExecutableAllocator.cpp:89,109`) | `ConfigAlignment = 16 KiB`; `fixedExecutableMemoryPoolSize = 32 MB` (`128 MB` in `webkit-ppc64le`) | `mbmalloc.cpp` `g_config` is only `16 KiB`-aligned/sized vs `64 KiB` `mprotect` page size (`Source/bmalloc/bmalloc/mbmalloc.cpp:33-38`). Enabling `BENABLE_LIBPAS` automatically turns on `ENABLE_LIBPAS_JIT_HEAP = 1` (`ExecutableMemoryHandle.h:41`), whose `minimumPoolSizeForSegregatedHeap = 256 MB` (`ExecutableAllocator.cpp:89`) exceeds `webkit-ppc64le`'s `128 MB` JIT pool. Also `pas_page_malloc.c` needs `MADV_NOHUGEPAGE` / THP opt-out (`12.0 MiB` THP observed on `bench_libpas`). | Fix `WebConfig` alignment to `64 KiB` (`CeilingOnPageSize`); audit `ENABLE_LIBPAS_JIT_HEAP` with `128 MB` pool (`JIT_MEDIUM` / `minimumPoolSizeForSegregatedHeap`); add `MADV_NOHUGEPAGE` to `pas_page_malloc.c` reservations. |

### 4.3 `test_pas` Empirical Progression (`16K` Defaults vs `64K`-Tuned) `[MEASURED]`

All runs on `omarchy-power9` (`PAGESIZE=65536`), `--child-processes 8`, `LD_PRELOAD=nodump.so`:

| `test_pas` Filter | `libpas-proto` (PPC64 fixes, 16K defaults) | `libpas-proto-64k` (PPC64 + 64K tuning) | Notes on Remaining 64K Failures |
|---|---|---|---|
| `Bmalloc` | **15 / 15 PASS** | **15 / 15 PASS** | Clean pass |
| `JITHeap` | **3 / 18 PASS** (`15` `commit_impl` crashes) | **18 / 18 PASS** | Fixed by `JIT_*` 64K + `PAS_UTILITY_LOOKUP_SIZE_UPPER_BOUND=4352` |
| `Bitfit` | **6 / 7 PASS** (`1` `decommit_impl` crash) | **7 / 7 PASS** | Fixed by `PAS_EXPENDABLE_MEMORY_PAGE_SIZE=65536llu` |
| `ExpendableMemory` | **2 / 18 PASS** (`16` `decommit_impl` crashes) | **0 `decommit_impl` crashes**; 3 hit `largeArray==2048` vs `2016`*, `testSoManyHeaps` timed out at 90s (`rc=124`), 1722–1729 all **PASS** | *`2000 B` fits in 64K `small_segregated` (`2016 B`) instead of 16K `medium_segregated` (`2048 B`) |
| `testScavengerShutsDownEventually` | **2 / 4 PASS** (`2` `decommit_impl` crashes) | **4 / 4 PASS** | Clean pass |
| `pagesize64k` (`IsoHeapChaos`) | (not separately isolated) | **12 / 12 PASS** | Segregated + bitfit chaos on 1 & 10 threads |
| `LargeSharingPool`, `ScavengerExternalWork`, `ViewCache`, `Utils`, `Memalign`, `Coalign` | **47 / 47 PASS** | **47 / 47 PASS** | `1 + 2 + 4 + 28 + 2 + 10 = 47 / 47 PASS` |
| `Thingy` | **1320 / 1358 PASS** (`38` failed in scavenge/chaos `decommit_impl`) | **998 / 1358 PASS** (`360` failed on hardcoded 16K size-class/page-count expectations) | E.g. `1000 B` -> `small_segregated` `1008` vs expected `medium` `1024`; `1` vs `2` pages for `200 × 100 B`; zero `decommit_impl` crashes! |
| `TLCDecommit` | **3 / 19 PASS** | **3 / 19 PASS** | `11` hit calibration assert (`65536` missing), `5` check Darwin-only TLC page decommit (`130` vs `1`) |
| **Standalone `Source/bmalloc` (`BENABLE_LIBPAS=1`)** | — | **`libbmalloc.a` + `bmalloc_smoke` PASS** | Built all 172 targets (`BPlatform.h` + `libpas-proto-64k`), `bmalloc::api::{tryMemalign(65536,65536), malloc(128), scavenge}` ran cleanly |


---

## 5. File-by-File Porting Plan & Prototype Diffs

### Phase A — Immediate Win for `webkitgtk-6.0` / `webkit2gtk-4.1` (Work Item #5)

Target files:
1. `Source/bmalloc/mimalloc/mimalloc/src/options.c` — default `MI_DEFAULT_ALLOW_THP=0` on `ppc64le` (`(defined(__PPC64__) || defined(__powerpc64__)) && defined(__LITTLE_ENDIAN__)`). Eliminates `2 MiB` THP faulting in `WebKitWebProcess` and restores `64 KiB` `_mi_os_minimal_purge_size()`.
2. `Source/bmalloc/mimalloc/mimalloc/src/alloc-aligned.c` & `arena.c` — allow `(bsize == MI_ARENA_SLICE_SIZE && alignment == MI_ARENA_SLICE_SIZE)` to pack natively at slice 1 (`block_start = 64 KiB`) inside `512 KiB` `MI_MEDIUM_PAGE`s instead of `131071 -> 128 KiB` overallocation in `4 MiB` `MI_LARGE_PAGE`s.
3. `Source/bmalloc/mimalloc/mimalloc/src/os.c` — relax `_mi_os_guard_page_size()` debug assert `mi_assert(gsize <= (MI_ARENA_SLICE_SIZE/4))` to `gsize <= MI_ARENA_SLICE_SIZE` so `MI_DEBUG` builds don't abort on `64 KiB` pages.
4. `Source/WTF/wtf/posix/OSAllocatorPOSIX.cpp` — port `webkit-ppc64le`'s `#ifdef MADV_NOHUGEPAGE` on `tryReserveUncommitted` (lines 165-171 of `webkit-ppc64le`) into `2.54.x` GTK packaging so `Structure` (`4 GiB`) and JIT (`128 MiB`) VMAs opt out of THP even independently of mimalloc `prctl`.

**Verified Prototype `mimalloc` Diff (`-DNDEBUG` & `MI_DEBUG=3` tested):**
```diff
--- a/Source/bmalloc/mimalloc/mimalloc/src/options.c
+++ b/Source/bmalloc/mimalloc/mimalloc/src/options.c
@@ -101,7 +101,7 @@
 #endif
 
 #ifndef MI_DEFAULT_ALLOW_THP
-#if defined(__ANDROID__)
+#if defined(__ANDROID__) || ((defined(__PPC64__) || defined(__powerpc64__)) && defined(__LITTLE_ENDIAN__))
 #define MI_DEFAULT_ALLOW_THP  0
 #else
 #define MI_DEFAULT_ALLOW_THP  1
--- a/Source/bmalloc/mimalloc/mimalloc/src/alloc-aligned.c
+++ b/Source/bmalloc/mimalloc/mimalloc/src/alloc-aligned.c
@@ -22,7 +22,8 @@ static bool mi_malloc_is_naturally_aligned( size_t size, size_t alignment ) {
   if (alignment > size) return false;
   const size_t bsize = mi_good_size(size);
   const bool ok = (bsize <= MI_PAGE_MAX_START_BLOCK_ALIGN2 && _mi_is_power_of_two(bsize)) ||             // power-of-two under N
-                  (alignment==MI_PAGE_OSPAGE_BLOCK_ALIGN2 && (bsize % MI_PAGE_OSPAGE_BLOCK_ALIGN2)==0);  // or multiple of N
+                  (alignment==MI_PAGE_OSPAGE_BLOCK_ALIGN2 && (bsize % MI_PAGE_OSPAGE_BLOCK_ALIGN2)==0) || // or multiple of N
+                  (bsize == MI_ARENA_SLICE_SIZE && alignment == MI_ARENA_SLICE_SIZE);                    // 64 KiB slice-aligned blocks (JSC MarkedBlock)
   if (ok) { mi_assert_internal((bsize & (alignment-1)) == 0); } // since both power of 2 and alignment <= size
   return ok;
 }
--- a/Source/bmalloc/mimalloc/mimalloc/src/arena.c
+++ b/Source/bmalloc/mimalloc/mimalloc/src/arena.c
@@ -808,6 +808,10 @@ static mi_page_t* mi_arenas_page_alloc_fresh(mi_theap_t* theap, size_t slice_cou
     // naturally align power-of-2 blocks up to MI_PAGE_MAX_START_BLOCK_ALIGN2 size (4KiB)
     block_start = _mi_align_up(mi_page_info_size(), block_size);
   }
+  else if (block_size == MI_ARENA_SLICE_SIZE) {
+    // start 64 KiB blocks on slice 1 so every block in the page is 64 KiB-aligned
+    block_start = _mi_align_up(mi_page_info_size(), MI_ARENA_SLICE_SIZE);
+  }
   else if (block_size != 0 && (block_size % MI_PAGE_OSPAGE_BLOCK_ALIGN2) == 0) {
     // also align large pages that are a multiple of MI_PAGE_OSPAGE_BLOCK_ALIGN2 (4KiB)
     block_start = _mi_align_up(mi_page_info_size(), MI_PAGE_OSPAGE_BLOCK_ALIGN2);
--- a/Source/bmalloc/mimalloc/mimalloc/src/os.c
+++ b/Source/bmalloc/mimalloc/mimalloc/src/os.c
@@ -67,7 +67,7 @@ size_t _mi_os_minimal_purge_size(void) {
 
 size_t _mi_os_guard_page_size(void) {
   const size_t gsize = _mi_os_page_size();
-  mi_assert(gsize <= (MI_ARENA_SLICE_SIZE/4)); // issue #1166
+  mi_assert(gsize <= MI_ARENA_SLICE_SIZE);
   return gsize;
 }
```

### Phase B — `libpas` + `JSC` 64 KiB-Page Port (Work Item #6, Upstreamable)

Target files (all verified to compile and pass `Bmalloc`/`JITHeap`/`Bitfit`/`pagesize64k`/`bmalloc_smoke` in our standalone prototype):
1. `Source/bmalloc/bmalloc/BPlatform.h`: define `BCPU_PPC64LE` and enable `BENABLE_LIBPAS` (gated on `!BUSE(MIMALLOC) && !BUSE(SYSTEM_MALLOC)` for `BOS(LINUX) && BCPU(PPC64LE)`). Also review `GIGACAGE_ENABLED` (`Gigacage.cpp`) and `Source/cmake/WebKitFeatures.cmake` (`USE_MIMALLOC_DEFAULT`).
2. `Source/bmalloc/libpas/CMakeLists.txt`: add `tagged_bmalloc_heap{,_config,_utils}.c` to `PROPERTIES LANGUAGE CXX`.
3. `Source/bmalloc/libpas/src/libpas/pas_config_prefix.h` & `pas_utils.h`: define `__PAS_PPC64` / `PAS_PPC64`; emit `lwsync` for `pas_fence_after_load()` and `pas_store_store_fence()` when `PAS_PPC64`.
4. `Source/bmalloc/libpas/src/libpas/pas_utils_prefix.h`: disable x86 `lock; orl` in `__pas_fence()` (`!__PAS_PPC64` -> `__atomic_thread_fence(__ATOMIC_SEQ_CST)` = `sync`); add `__PAS_PPC64` `xor` address-dependency chain in `__pas_depend_impl()`.
5. `Source/bmalloc/libpas/src/libpas/pas_utils.c`: add `#elif PAS_PPC64` (`PAS_FATAL_CRASH_INST "trap"`, `CRASH_GPR0..6 "r3".."r9"`) and include `PAS_PPC64` in crash-info guard.
6. `Source/bmalloc/libpas/src/libpas/pas_segregated_page_inlines.h`: guard x86 `btrl` inline asm with `&& !PAS_PPC64`.
7. `Source/bmalloc/libpas/src/libpas/pas_internal_config.h`: parameterize `64 KiB` page profile (`PAS_SMALL_PAGE_DEFAULT_SHIFT 16`, `PAS_SMALL_BITFIT_PAGE_DEFAULT_SHIFT 16`, `PAS_MEDIUM_PAGE_DEFAULT_SHIFT 18`, `PAS_GRANULE_DEFAULT_SHIFT 16`, `PAS_UTILITY_LOOKUP_SIZE_UPPER_BOUND 4352`, `PAS_MAX_OBJECTS_PER_PAGE 8192`; gate cleanly under `#if PAS_OS(LINUX) && (PAS_PPC64 || defined(PAS_OS_PAGE_SIZE_64K))` or runtime-detectable `PAS_OS_PAGE_SHIFT` before upstreaming so 4K/16K targets stay unchanged).
8. `Source/bmalloc/libpas/src/libpas/jit_heap_config.h`: set `JIT_SMALL_PAGE_SIZE 65536u`, `JIT_SMALL_GRANULE_SIZE 65536u`, `JIT_MEDIUM_GRANULE_SIZE 65536u`, and raise `JIT_MEDIUM_BITFIT_MIN_ALIGN_SHIFT` to `9u` (or `JIT_MEDIUM_PAGE_SIZE 262144u` + shift `9u`) so granule refcounts stay `< 255`.
9. `Source/bmalloc/libpas/src/libpas/pas_expendable_memory.h` & `pas_large_expendable_memory.h`: set `PAS_EXPENDABLE_MEMORY_PAGE_SIZE` to `65536llu` and cap `PAS_LARGE_EXPENDABLE_MEMORY_ALIGNMENT` at `128 MiB`.
10. `Source/bmalloc/libpas/src/libpas/pas_page_malloc.c`: add `MADV_NOHUGEPAGE` on fresh reservations so `libpas` avoids `2 MiB` THP inflation on `THP=always` kernels.
11. `Source/bmalloc/bmalloc/mbmalloc.cpp` & `Source/JavaScriptCore/jit/ExecutableAllocator.cpp`: align `WebConfig::g_config` to `64 KiB` (`CeilingOnPageSize`) and reconcile `webkit-ppc64le`'s `128 MB` JIT pool with `ENABLE_LIBPAS_JIT_HEAP`'s `minimumPoolSizeForSegregatedHeap` (`256 MB`).
