# artcraft on ppc64le -- what was verified, and when

Baseline for deciding what changed on a future rebuild. Everything below was
measured on .24 (POWER9, AC922) on 2026-10-08.

**Pinned at** `3e5793b6934b51536606720e5d56bcfd1fe7cc2d`.

## Verified

| step | command | result |
|---|---|---|
| Rust workspace | `SQLX_OFFLINE=true cargo check --release -p artcraft` | clean, 48.5 s |
| BoringSSL | builds after patch 0001 | 0 errors |
| ring 0.17 | standalone probe, SHA-256 over a known input | correct, 17 s, unpatched |
| frontend deps | `npm ci --ignore-scripts` | 1772 packages, 19 s |
| esbuild | `require('esbuild')` | 0.21.5 loads, `@esbuild/linux-ppc64` 9.2 MB |
| frontend build | `vite build` in `frontend/apps/artcraft` | 58.8 s, full dist |

## NOT yet verified

- `cargo build --release` (only `cargo check` has run)
- the Tauri bundle step
- the app actually running

## The three things that will break first

1. **`Cargo.lock` moving `boring-sys2` off 5.0.0-alpha.13.** Patch 0001 anchors
   on the riscv32 branch in `deps/boringssl/src/include/openssl/base.h`. The
   recipe globs `boring-sys2-*`, so a version bump keeps building until that
   file changes, then `patch` fails and makepkg aborts -- loudly, which is
   right, but it needs a refreshed patch. Check first on any lockfile bump.

2. **A real nx dependency appearing.** Today nx is only a task runner and
   `vite build` substitutes for `npx nx run artcraft:build`. If the app starts
   relying on nx's project graph (generators, inferred targets, module
   federation), that substitution stops working and
   `@nx/nx-linux-ppc64-gnu` has to be built from nx's Rust/napi crate --
   upstream publishes ten platforms and none is ppc64.

3. **vite 8.** vite 6 keeps esbuild as a first-class dependency. vite 8 moved
   to rolldown and made lightningcss the default CSS minifier, and neither
   publishes a ppc64le binary -- that is exactly what blocked sunshine, where
   the fix was `cssMinify: false`.

## Not a problem, despite appearances

- **`@swc/core`** has no ppc64le binary and does not need one: nothing in the
  tree references it. All nine vite configs use `@vitejs/plugin-react`, and
  `@swc/core` arrives only via `@swc-node/register`, which is nx's config
  loader.
- **`--omit=optional` is wrong here.** The native modules are
  optionalDependencies and `@esbuild/linux-ppc64` is one of them, so omitting
  optionals drops the one native module that does exist for us.
- **No local AI.** Every model call is a remote API (fal, grok, midjourney,
  sora, worldlabs), so there is no ONNX, torch or GPU kernel to port.

## Webview

Tauri 2 uses webkit2gtk-4.1, which Arch POWER already ships. That build's JSC
measured **5165 ms** against V8's **1428 ms** on a 200M-iteration integer loop
(`jsc` from `/usr/lib/webkit2gtk-4.1/jsc`). `ours/webkit` carries a full
ppc64le JIT including the wasm tiers (IPInt/BBQ/OMG), and two of artcraft's
vite configs use `vite-plugin-wasm` -- so rebuilding webkitgtk against that
port is what would make this app feel right. Tracked separately.
