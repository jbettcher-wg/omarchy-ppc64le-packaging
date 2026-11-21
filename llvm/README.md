# llvm — Omarchy ppc64le

Arch's monolithic LLVM 23.1.5 recipe (llvm, clang, lld, lldb, compiler-rt,
openmp, libclc, polly, bolt, libc++ and the wasi runtimes), pkgrel 1.1. It
replaced the 22.x split recipes (`clang/`, `lld/`, `compiler-rt/`, `openmp/`,
`libclc/`, `lldb/`), which were retired on 2026-11-21. Arch's `llvm22` compat
recipe sits beside this one as `llvm22/`.

## Deviations on powerpc64le

- **`ppc64-tls-relax-keep-rt.patch`**: LLD's PPC64 TLS relaxation keeps the
  destination register. It is carried over from `lld` 22.1.8-1.1, and 23.1.5
  still hard-codes r3. Details below.
- **`-DLLDB_ENABLE_TREESITTER=OFF -DLLDB_ENABLE_LUA=OFF`**: neither is in
  Arch's makedepends. Our sysroot carries the whole pool, so LLDB found the
  host's tree-sitter-cli and lua anyway, and tree-sitter-cli ran node at build
  time.
- **libclc against the LLVM just built**: `CMAKE_PREFIX_PATH` gets
  `$PWD/build` first and libclc gets `-DLLVM_DIR=$PWD/build/lib/cmake/llvm`.
  bq sets `CMAKE_PREFIX_PATH`, so libclc otherwise found the system LLVM 22's
  cmake files and compiled its bitcode with llvm-link 22.
- **`_llvm_bootstrap=1`** (environment only, off by default): leaves out
  libclc's spirv32/spirv64 targets and their spirv-mesa3d links. Those
  targets need an llvm-spirv of the same major version, and
  spirv-llvm-translator 23 needs LLVM 23 to build. So a major bump runs llvm
  with `_llvm_bootstrap=1`, then spirv-llvm-translator, then llvm again with
  bq's `--force` (bq reuses same-version files otherwise).

## The TLS relaxation bug

LLD 22.1.8 (and 23.1.5) relaxes general- and local-dynamic TLS sequences in executables.
The ELFv2 ABI's example sequence uses r3 throughout:

    addis r3, r2, x@got@tlsld@ha
    addi  r3, r3, x@got@tlsld@l
    bl    __tls_get_addr(x@tlsld)
    nop

LLD rewrites the `@l` insn as a fixed `addis r3,r13` for GD→LE and LD→LE, and
as `ld r3,…` for GD→IE. Whatever register the compiler actually used is lost.

GCC 16 does not always use r3. It can build the argument in, say, r9, spill
it, and move it into r3 just before the call. After LLD's rewrite, r9 is never
written: the `@ha` insn became a nop and the `@l` insn now writes r3. The copy
into r3 then overwrites the correct value with stale r9.

GNU ld keeps the register (`insn1 &= 0x1f << 21` in `bfd/elf64-ppc.c`). Its
source comment says the register "may be something other than the usual r3,
and moved to r3 before the call by intervening code".

**Found by:** blender 5.3.0-1, linked by this LLD, segfaulted at GUI startup
on both lanes (`blender/README.md`, "TLS relaxation").

## The patch

- `relaxTlsGdToLe`: emit `addis rT,r13` and keep rT.
- `relaxTlsLdToLe`: emit `addis rT,r13,0` and keep rT. It also adds the
  missing small-model `R_PPC64_GOT_TLSLD16` case
  ([llvm#240311](https://github.com/llvm/llvm-project/issues/240311)), which
  fell through to `llvm_unreachable`.
- `relaxTlsGdToIe`: emit `ld rT,…(rA)` and keep both rT and rA.

## The assertion

`build()` runs `ppc64-tls-relax-test.sh` against the `ld.lld` it just built,
because bq builds with `--nocheck` and `check()` never runs. The script links
four sequences and runs each one, expecting the thread-local's value, 42:

- LD→LE, address built in r9;
- GD→LE, address built in r9;
- GD→IE against a shared library, address built in r9;
- llvm#240311's small-model LD.

Against the unpatched 22.1.8 all four segfault `[MEASURED]`. The 23.1.5
builds in both lanes passed it on 2026-11-21.
