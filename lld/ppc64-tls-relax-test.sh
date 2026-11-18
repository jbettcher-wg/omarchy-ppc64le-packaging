#!/bin/bash
# ppc64-tls-relax-test.sh <dir with ld.lld> -- link four PPC64 TLS sequences
# with that ld.lld into executables, run them, and require each to return the
# thread-local's value, 42.  Each builds the __tls_get_addr argument the way a
# compiler may: in r9, copied to r3 before the call.  LLD 22.1.8 as released
# forces r3 in the relaxed insn, so r9 stays stale and these crash
# (ppc64-tls-relax-keep-rt.patch).  The last case is llvm#240311's small-model
# GOT_TLSLD16.
set -euo pipefail
lld_dir=$(realpath "$1")
w=$(mktemp -d)
trap 'rm -rf "$w"' EXIT
cd "$w"

prologue='
        .abiversion 2
        .text
        .globl main
        .type main,@function
main:
0:      addis 2,12,.TOC.-0b@ha
        addi 2,2,.TOC.-0b@l
        .localentry main,.-main
        mflr 0
        std 0,16(1)
        stdu 1,-32(1)'
epilogue='
        lwz 3,0(3)
        addi 1,1,32
        ld 0,16(1)
        mtlr 0
        blr
        .size main,.-main'
tdata='
        .section .tdata,"awT",@progbits
        .align 2'

cat >ld-le.s <<EOF
$prologue
        addis 9,2,x@got@tlsld@ha
        addi 9,9,x@got@tlsld@l
        mr 3,9
        bl __tls_get_addr(x@tlsld)
        nop
        addi 3,3,x@dtprel
$epilogue
$tdata
x:      .long 42
EOF

cat >gd-le.s <<EOF
$prologue
        addis 9,2,x@got@tlsgd@ha
        addi 9,9,x@got@tlsgd@l
        mr 3,9
        bl __tls_get_addr(x@tlsgd)
        nop
$epilogue
$tdata
        .globl x
x:      .long 42
EOF

cat >gd-ie.s <<EOF
$prologue
        addis 9,2,y@got@tlsgd@ha
        addi 9,9,y@got@tlsgd@l
        mr 3,9
        bl __tls_get_addr(y@tlsgd)
        nop
$epilogue
EOF

cat >libtls.s <<EOF
$tdata
        .globl y
        .type y,@object
        .size y,4
y:      .long 42
EOF

cat >ld-small.s <<EOF
$prologue
        addi 3,2,x@got@tlsld
        bl __tls_get_addr(x@tlsld)
        nop
        addi 3,3,x@dtprel
$epilogue
$tdata
x:      .long 42
EOF

link() { LD_LIBRARY_PATH="$lld_dir/../lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  gcc -B "$lld_dir/" -fuse-ld=lld "$@"; }

for s in *.s; do as -a64 -mpower8 "$s" -o "${s%.s}.o"; done
link -shared libtls.o -o libtls.so
link ld-le.o -o ld-le
link gd-le.o -o gd-le
link gd-ie.o -L. -ltls -Wl,-rpath,"$w" -o gd-ie
link ld-small.o -o ld-small

fail=0
for t in ld-le gd-le gd-ie ld-small; do
  rc=0; ./"$t" || rc=$?
  if [[ $rc == 42 ]]; then echo "ppc64 tls relax: $t ok"
  else echo "ppc64 tls relax: $t FAILED (exit $rc, want 42)"; fail=1
  fi
done
exit $fail
