# WebKit on POWER: findings and work list

Status as of 2026-11-20. This is the starting point for whoever takes on the
WebKit work: what is wrong today, how it was established, and what to do next,
in priority order. Every finding is marked **verified** (reproduced or read off
a binary or core) or **inferred** (reasoned from source or timing). Nothing
inferred here has been confirmed.

## Before you start: coordination

The package-update waves (security set, toolchain, openssl 4, perl 5.44, llvm
23, ...) have priority over this work and share the same build host.

- **Do not start large builds yet.** That means webkit, jsc, bun,
  webkit2gtk-4.1, webkitgtk-6.0, epiphany or anything else over about
  16 threads. Coordinate with the session running the waves first.
- Investigation, patch writing, headless testing and upstream bug reports can
  all start now. Keep them at 16 threads or fewer.
- Leave `/var/tmp/omarchy-bq*` (the bq build lanes) alone. Never clean or
  kill anything under `~/Development/flutter-port` or `/var/tmp/dart-m1`,
  which belong to another team.
- Build and test natively over ssh to localhost (see the repo's agent notes),
  never inside the POWERarm aarch64 sleeve. Kill processes by PID, never by
  pattern. Do not run an Omarchy installer on the build host.
- Commit in this tree with explicit paths (`git commit -- <paths>`). Other
  workstreams keep uncommitted changes here.

## How our WebKit is put together

One ppc64le port feeds five recipes: `ours/webkit`, `ours/jsc`, `ours/bun`,
`ours/webkit2gtk-4.1` and `ours/webkitgtk-6.0`. The JIT port is
`ours/webkit/webkit-ppc64le-jit.patch`. The GTK recipes apply it in layers via
`ppc64le-port.tar.gz` / `stage.sh`, whose comments explain why.

The shipped browser engine is **webkitgtk-6.0 2.54.1-3** (Epiphany 51.1 uses
it). On powerpc64le the recipe differs from Arch in these ways:

| setting | why |
|---|---|
| `CC=gcc CXX=g++` | clang's integrated assembler accepts ISA 3.0 at `-mcpu=power8`; GNU as keeps the POWER8 floor honest |
| `USE_MIMALLOC=ON`, `USE_SYSTEM_MALLOC=OFF` | libpas is x86-64/arm64-only in `BPlatform.h`; mimalloc is what the other libpas-less 64-bit JIT target (RISC-V) uses |
| `-DSKCMS_HAS_MUSTTAIL=0 -mminimal-toc` | skcms' musttail is x86/arm only; TOC overflow in very large translation units |
| `-Wl,--no-keep-memory` | final link memory |
| `ENABLE_SPEECH_SYNTHESIS=OFF`, `USE_FLITE=OFF` | same as Arch |

There are no debug symbols for any of it in the pools. Crash frames have to be
named by hand from `.dynsym` plus disassembly.

## Findings

### 1. Skia compositor: exponential backdrop-filter repaint, then hang, then watchdog abort (highest impact)

**Not POWER-specific: it affects every architecture.**

**Symptom (verified):** on a Discord page the page froze, and closing it killed
the web process (SIGABRT on thread `WatchDogQueue`). The abort is
`crashAfter10Seconds()` in `WebProcess.cpp`: *"WebProcess didn't exit as
expected after the UI process connection was closed"*. So the crash is the
consequence of the hang, not a second bug.

**What the core showed (verified, read with gdb):**

- The main thread is in `RunLoop` → `MemoryPressureHandler::releaseMemory` →
  WebProcess memory handler → WebPage/LayerTreeHost →
  `ThreadedCompositor::releaseMemory` → `WorkQueueBase::dispatchSync` →
  `BinarySemaphore::waitUntil`. It is blocked on the compositor thread.
- The compositor thread is busy, not waiting, 496 frames deep in
  `SkiaCompositingLayer::recursivePaint` → `paintWithMaskAndBackdrop` →
  `paintSelfAndChildren`. These were identified from disassembly, since there
  are no symbols.
  - Reading the layer pointer out of each frame: 148 recursion levels cover
    only 76 distinct layers, one ancestor chain is re-entered 13 times, and
    the backdrop root's subtree is repainted 12 times, nested.

**Mechanism (from source, matching the reproduction):**

- 2.54 composites with Skia by default (`UseSkiaForComposition=true`).
- Painting layer X's backdrop repaints the backdrop root's subtree, stopping at
  X (`SkiaCompositingLayer::paintBackdrop`).
- WebKit bug [325626](https://bugs.webkit.org/show_bug.cgi?id=325626)
  ("backdrop-filter misses the backdrop-filter of earlier elements") was fixed
  in [`bab8a55628ba`](https://github.com/WebKit/WebKit/commit/bab8a55628ba)
  and backported to webkitglib/2.54 as `5aa9856275e9`. Since then, every
  earlier backdrop layer inside that repaint paints its own backdrop as well:
  the check changed from `!context.paintingBackdropForLayer` to `!= this`, and
  the 2.54.1 tarball carries the new form.
- Nothing is cached between nested passes, so element *k* costs 2^(k−1)
  subtree repaints and a frame costs 2^n − 1, each one a full-resolution blur.

**Reproduction (verified):** pages in `repro/`. Each `bdN.html` has N
`backdrop-filter: blur()` cards under an `opacity:.99` root with an animated
background. The `bdNmem.html` variants also allocate about 1.3 GB in JS to
trigger memory pressure. The runs used headless weston at 3840×2160 scale 2 on
the RX 7900 XTX, with the shipped webkitgtk-6.0 and the sandbox on.

| cards | compositor FPS (`WEBKIT_DRAW_FPS`) | compositor CPU |
|---|---|---|
| 2 | 60 | ~25% of a core |
| 4 | 29 | ~50% |
| 6 | 26 | 100% |
| 12 | 0 | 100% |

| cards, with memory pressure | main-thread stall per 30 s pressure check |
|---|---|
| 8 | none |
| 12 | ~2 s |
| 14 | 5 s, 10.4 s |
| 16 | permanent (no reply for over 50 s): the hang |

With `WEBKIT_USE_SKIA_FOR_COMPOSITION=0` and 16 cards under the same memory
load there were no stalls, the compositor used about 25% CPU, and the page
still rendered correctly.

**Open gap:** real Discord shows only 4 elements with `backdrop-filter` in
computed style. Which DOM produced 12 or more backdrop layers has not been
identified; pseudo-elements and the logged-in app are the candidates.

**Workaround (verified):** run Epiphany or any WebKitGTK app with
`WEBKIT_USE_SKIA_FOR_COMPOSITION=0`. The cost is that the older TextureMapper
path brings back the cosmetic 325626 bug.

**Fixes:**

1. **Upstream:** limit backdrop nesting in `SkiaCompositingLayer::paintBackdrop`
   to one level, as TextureMapper does with `!options.backdropLayer`, or cache
   each layer's filtered backdrop once per frame. File a bug with
   `repro/bd12.html` and `repro/bd16mem.html`. Check first whether 2.54.2 or
   later already addresses it.
2. **Upstream hardening:** `ThreadedCompositor::releaseMemory` should not
   `dispatchSync` from the main thread. Even the `Synchronous::No`
   memory-pressure path ends up waiting on the compositor.
3. **Locally**, until upstream moves: carry the fix as a patch in
   `ours/webkitgtk-6.0` and `ours/webkit2gtk-4.1`, gated on `bd16mem.html`
   rendering with no stall. Alternatively, default
   `WEBKIT_USE_SKIA_FOR_COMPOSITION=0` in the package, if the 325626
   regression is acceptable.

### 2. Large web processes keep the memory-pressure path firing (inferred)

Web processes on the build host are big: 1.0–1.1 GB for an idle Discord
homepage, 1.4 GB for a news site, and about 3.5 GB dumped from the crashed
process. That keeps WebKit's memory-pressure handling, with thresholds of 1 GB
and 1.5 GB over a 3 GB base, running every 30 s. Each run makes the
synchronous compositor call from finding 1, which turns a frozen picture into
a frozen, unresponsive page.

The likely causes are 64 KiB pages plus mimalloc instead of libpas. There is
no x86 comparison yet to prove it. **First step:** measure RSS for the same
pages on an x86 WebKitGTK 2.54.1, and on ppc64le with a 4K-page kernel if one
is available.

### 3. Instruction-set leaks in shared libraries (verified; this instance is fixed)

libjxl 0.12.0-1 in the POWER9 pool executed a POWER10 `pla` on POWER9. Any page
with a JPEG XL image SIGILLed the web process: WebKit advertises `image/jxl`,
and Cloudinary's `f_auto` serves it.

Cause: highway's PPC10 tier was reachable without dispatch. It is fixed by
highway 1.4.0-2.2 (`ppc64le-no-ppc10-target.patch`) and libjxl 0.12.0-1.1, both
published.

The class of bug remains for any library that compiles higher ISA tiers. The
release gate for anything WebKit loads is:

- the ISA 3.0 scan (`tools/isa30-pkgscan.sh`) for the baseline pool;
- the ISA 3.1 scan (`isa31-scan.sh` in the omarchy-ppc64le repo's local tools)
  for the POWER9 pool;
- a runtime check under `qemu-ppc64le -cpu power8` (or `power9`) that a
  same-level control must SIGILL. "It is behind runtime dispatch" is not proof.

Of the 198 libraries WebKitWebProcess and its GStreamer plugins load, libjxl
and libjxl_cms were the only ones carrying POWER10 code (plus libcrypto's
gated code).

### 4. Epiphany's web extension aborts when the portal is unreachable (crash verified, mechanism inferred)

`ephy_file_helpers_init()` calls `xdp_portal_new()`, which aborts the process
when the session bus cannot be reached. The crash was observed:
`libportal-CRITICAL: Failed to create XdpPortal instance: Could not connect:
Connection refused`, with
`DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/webkitgtk/bus`.

**Inferred mechanism:**

- WebKit 2.54.1 gives each launched process its own xdg-dbus-proxy
  (`ProcessLauncher.h: XDGDBusProxy m_dbusProxy`).
- The proxy exits when its sync fd closes on launcher invalidation
  (`AuxiliaryProcessProxy::shutDownProcess`).
- So a web process abandoned mid-launch can run Epiphany's init against a dead
  proxy.

Each such abort also costs a 5–18 GB core dump that takes 8–27 s to write.

**Fixes:**

- Patch Epiphany to use `xdp_portal_initable_new()` and carry on without a
  portal (the web extension does not need one), and report it upstream.
  Epiphany comes from Arch POWER today, so import it first (`tools/fetch.sh
  epiphany`).
- To confirm the mechanism, run `WEBKIT_ENABLE_DBUS_PROXY_LOGGING=1 epiphany`.

### 5. No debug symbols (verified)

Every crash costs disassembly work, so this is worth fixing early. Options:

- a `-debug` split package for webkitgtk-6.0 only. bq drops debug packages
  by default (`OPTIONS+=(!debug)`), so the recipe would need an override;
- debuginfod.

Mind the size: WebKit debug info is several GB.

### 6. Minor (unexplained or not WebKit)

- xdg-desktop-portal's Realtime portal logs *"PIDFD_GET_PID_NAMESPACE ioctl
  failed: Inappropriate ioctl for device"* for every sandboxed web process.
  - The ioctl works natively with POWER's encoding `0x2000ff05`, and returns
    ENOTTY with the x86 encoding `0xff05`.
  - But xdp 1.22.1 uses `_IO()`, so the constant is not the explanation.
    Cause unknown.
  - Effect: WebKit's realtime thread-priority requests fail.
- Content-filter lists over about 40 MB time out on download (about 17 s) at
  every Epiphany start. This is configuration, not WebKit.

## What the shipped build supports

Verified with `repro/features.html` and `JSC_dumpOptions=2` on webkitgtk-6.0
2.54.1-3.

| area | state |
|---|---|
| JavaScriptCore | LLInt, Baseline, DFG, FTL, RegExp JIT, DOMJIT, concurrent JIT: all on (7 FTL threads) |
| WebAssembly | IPInt, BBQ, OMG, SIMD, fast memory: all on; `add(40,2)` returns 42. Tier-up into BBQ/OMG not separately verified |
| Rendering | Skia GPU on radeonsi; DMA-BUF with AMD GFX11 DCC modifiers into GTK's Vulkan renderer; correct at scale 1 and 2 |
| Canvas / WebGL | accelerated 2D canvas, WebGL, WebGL2: work |
| Media | MSE, ManagedMediaSource, WebCodecs; H.264 (openh264), HEVC (libde265), VP8/VP9 (libvpx), AV1 (libaom), all in software |
| Missing (GTK-port defaults, not POWER gaps) | WebRTC (`RTCPeerConnection` undefined: no Discord voice, Meet or Teams), EME, WebAuthn and passkeys, WebGPU, WebXR, speech synthesis, PaymentRequest; WebExtensions are experimental-only in 2.54 |

Performance is deliberately out of scope for now. WebKit and Firefox are
measurably on par on POWER (about 20k Octane each) and both trail Chromium.

## Work list, in order

Each item ends with the check that counts as done.

1. **Backdrop recursion** (finding 1): file the upstream bug with the
   reproducers, then write and carry the patch.
   - **Done when** `bd16mem.html` shows no main-thread stall and `bd12.html`
     runs at 60 fps with the Skia compositor on.
2. **`releaseMemory` must not block the main thread** (finding 1, fix 2):
   upstream patch.
   - **Done when** `bd16mem.html` with the backdrop fix reverted still never
     stalls the main thread.
3. **Packaging wins, no engine work:**
   - Ship `gst-plugin-va` from our gstreamer recipe so radeonsi can decode
     video in hardware. **Done when** a 1080p AV1/VP9 test video decodes
     through VA, as shown by `GST_DEBUG` and CPU use. MediaCapabilities
     currently calls 1080p AV1 "smooth" on libaom, which POWER is unlikely to
     sustain.
   - Turn on WebRTC through the GStreamer backend in webkitgtk-6.0 and
     webkit2gtk-4.1. **Done when** `RTCPeerConnection` is defined and a
     loopback call connects.
   - Debug symbols (finding 5).
4. **Epiphany portal abort** (finding 4): import the recipe, apply the patch,
   send it upstream.
   - **Done when** no `xdp_portal_new` abort appears in a stress run of rapid
     tab open and close.
5. **Memory footprint** (finding 2): measure against x86 and against a 4K-page
   kernel, then decide between libpas for ppc64le and mimalloc tuning.
6. **libpas for ppc64le**, plus 64 KiB-page tuning in bmalloc and JSC. This is
   larger engine work, and it is upstreamable.
7. **A VSX path for Skia's CPU raster**: Skia has no POWER SIMD path today, so
   CPU raster is scalar (inferred from source).
8. **Upstream the ppc64le JSC port.** It is an out-of-tree layer today, shared
   by five recipes. Upstream will only keep it alive with a ppc64le build bot
   and CI. This is the biggest long-term lever.

**For the "own browser" question:** extensions, WebRTC, DRM and the compositor
all live inside WebKit, so a new browser shell would inherit every gap above.
The 2026-11-20 assessment recommends WebKit-level work plus Epiphany patches as
the first investment. The decision has not been made.

## Test harness (on the build host, not in this repo)

The diagnosis harness lives in `/var/tmp/claude-webkit-diag.4s0mvH/`:

- `tools/run-weston-probe.sh` and `tools/wkprobe.py` drive GTK4 + WebKitGTK
  against **headless weston** on the AMD GPU, so nothing appears on the
  desktop. `run-xvfb.sh` does the same under Xvfb.
- `wkshot.py` and `wkscroll.py` take compositor screenshots and scroll tests.
- `layers.py` and `layers2.py` read layer pointers out of the recursion frames
  of a core.
- `nodump.c` is an `LD_PRELOAD` that suppresses core dumps in test runs.
- weston was taken from the Arch POWER mirror (signature checked) and
  extracted under that directory, not installed.

Copy it somewhere durable before relying on it, because `/var/tmp` is not
backed up. Review it before committing any of it.

**Method that worked:**

- Bisect subsystems with one environment switch at a time, against a pixel
  diff of the default render: `WEBKIT_DISABLE_DMABUF_RENDERER`,
  `WEBKIT_DISABLE_COMPOSITING_MODE`, `WEBKIT_SKIA_ENABLE_CPU_RENDERING`,
  `LIBGL_ALWAYS_SOFTWARE`, `JSC_useJIT=0`, `GDK_BACKEND`.
- For a hang, take all-thread stacks read-only with
  `gdb -p <pid> -batch -ex "thread apply all bt"`.
- For a crash, use `coredumpctl` plus `.dynsym` and disassembly.
