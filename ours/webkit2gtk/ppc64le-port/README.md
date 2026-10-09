# ppc64le JavaScriptCore JIT port for WebKitGTK

Applied by `stage.sh <webkit-source-tree>`, which the recipe calls from
`prepare()`. Self-contained: no network, no port checkout.

Without this, ppc64le WebKitGTK is a **CLoop** build — the interpreter only,
no JIT at any tier. The `webkit2gtk-4.1 2.50.4-1` package currently installed
on ppc64le is such a build: `libjavascriptcoregtk-4.1.so` contains zero ppc64
JIT symbols. With it, the target has LLInt, Baseline, DFG, FTL (so B3 and
Air), YARR, and all three WebAssembly tiers (IPInt, BBQ, OMG).

## Why this is not one patch

A squashed diff against a tree this size rots on every WebKit release.
Measured against 2.54.1: **108 of 766 hunks failed, and most were still
correct** — a neighbouring architecture had been added to the same line, or
the file had moved under them. So the port is four layers, each one checkable
on its own:

| | what | why it survives a version bump |
|---|---|---|
| 1 | `newfiles/` | files only this port has; they share nothing |
| 2 | `airopcode.table` | `AirOpcode.opcodes` rebuilt from operations keyed on **declaration text**, not line numbers |
| 3 | `patches/` | an ordinary series, at **exact context only** |
| 4 | `tools/edits.py` | the rest, anchored to an exact line of source |

Two rules earn their keep:

**Tag edits are a set delta, never an absolute string.** The port only ever
adds `ppc64`. Writing the absolute tag would have deleted the `arm` and
`armv7` tags from 28 declarations in 2.54.1 and dropped 32-bit ARM support
from this build, with nothing failing to say so.

**No fuzz, ever.** `patch -F2` applied 47 more hunks than `-F0` against 2.54.1
and silently corrupted two files while reporting success — a bare `#endif`
with no `#if` in `DOMJITEffect.h`, and the same in `FTLLowerDFGToB3.cpp`.

**An anchor in doubt is not applied.** `portedit.py` requires every anchor to
match exactly once and writes nothing to a file whose anchors are ambiguous or
missing; applying an edit to the wrong one of two sites is the failure mode
that builds clean and crashes at run time.

## Bumping to a new WebKit version

```sh
dev/regen.sh <port-checkout> <pre-port-base-commit>   # refresh the inputs
stage.sh <new-tree>                                    # apply; it fails loudly
dev/verify.sh <pristine-tree> <new-tree>               # four gates, no compiler
```

`stage.sh` prints what it could not resolve; that output is the review list.
Edit `tools/edits.py` — never the generated table — and when upstream has
since done something itself, **delete the entry and record why in
`OBSOLETE`**, so the port keeps shrinking. 2.54.1 absorbed three of them:
`isValidIndexForm`'s opcode threading, `DOMJITEffect`'s DFG coupling, and the
whole `ENABLE(YARR_JIT_REGEXP_TEST_INLINE)` split.

`dev/verify.sh`'s third gate is the one that matters most: it runs the Air
opcode generator over the merged opcodes file and checks that the dispatch
emitted for **every other architecture** is byte-identical to what pristine
upstream produces, while ppc64 goes from nothing to 510 sites.

## Things this needed that are not the port's own

- **`USE_MIMALLOC=ON`** (set by the recipe). `bmalloc`'s libpas is enabled only
  for x86-64 and arm64 on Linux and nothing else is selected by default, so a
  bare configure dies on *"libpas, mimalloc, or system malloc needs to be
  specified"*. mimalloc is vendored in `Source/bmalloc/mimalloc`, and is what
  RISC-V — the other 64-bit JIT target without libpas — defaults to.
- **An upstream compile fix**, carried in `edits.py` and marked as such:
  `AirArg.h`'s `isValidFPImm64Form` declares `u64` only inside its
  `CPU(ARM64)`/`CPU(X86_64)` arms and then uses it unconditionally, so 2.54.1
  does not compile on any third architecture. Delete that entry once upstream
  fixes it.

## The gate that matters most

`dev/scopecheck.py` asks, for every function or macro where the port has a
ppc64 line at all, whether the staged tree's **same scope** has one too.

It exists because the other gates missed a fatal bug and this one finds it.
`functionPrologue` in `LowLevelInterpreter.asm` reached a build with no PPC64
arm. On this target an offlineasm `if`/`elsif` chain with no matching branch
emits **nothing**, so every interpreter function got no prologue and no
epilogue — no saved link register, no frame. Calls returned to address 0 or to
bytes out of `.rodata`, and branches appeared to loop.

Two gates had called that clean:

- `reconcile.py` asked whether a rejected hunk's added lines were present
  *anywhere in the file*. The line needed here,
  `elsif ARM64 or ARM64E or RISCV64 or PPC64`, is textually identical to one in
  `preserveCallerPCAndCFR` — which *had* been patched. Now it tests the hunk's
  post-image as a contiguous run instead.
- `ppc64check.sh` compared the *set* of ppc64 lines, so a line the port has
  twice and the target has once looked fine. It compares counts now.

The same class of miss also left `copyCalleeSavesToBuffer`,
`restoreCalleeSavesFromBuffer` and `AssemblyHelpers::checkWasmStackOverflow`'s
definition guard unpatched. Three gates, three different blind spots, one bug
shape: **a condition that silently matches nothing.** When adding a gate, ask
what it would say about that.
