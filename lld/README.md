# lld — Omarchy ppc64le

Arch POWER's `lld` 22.1.8-1 with one fix for ppc64le: TLS relaxation keeps the
destination register (`ppc64-tls-relax-keep-rt.patch`).

## The bug

LLD 22.1.8 relaxes general- and local-dynamic TLS sequences in executables.
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

Against the unpatched 22.1.8 all four segfault `[MEASURED]`.
