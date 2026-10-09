#!/bin/bash
# For each file the port touches, compare the PPC64-mentioning CODE lines in
# our tree against the staged tree. A line present in ours and absent in the
# staged tree is a piece of the port that has not arrived -- including in
# files the edit table owns, whose rejects reconcile.py no longer shows.
#
# Comment-only lines are ignored. A forward-ported edit is often reworded
# (and must be, where the reasoning has changed), so comparing prose produces
# noise that hides the one line that matters. This found exactly one real gap
# that reconcile.py could not see: opcode_generator.rb had been marked wholly
# obsolete when only its isValidIndexForm change was.
PORT="${PORT:-/mnt/arch/home/jbettcher/Development/webkit-ppc64le}"
OUT="$1"
pat='PPC64|ppc64|POWER8|POWER9|isPPC64'
tot=0; miss=0
for p in /var/tmp/wk2gtk/split/*.patch; do
    rel=$(grep -m1 '^+++ b/' "$p" | sed 's|^+++ b/||')
    [ -f "$PORT/$rel" ] || continue
    [ -f "$OUT/$rel" ] || { echo "ABSENT  $rel"; continue; }
    strip="s/^[ \t]*//"
    nocomment='/^(\/\/|#[^a-zA-Z_]|\*|\/\*)/d'
    # COUNTS, not a set. A line the port has twice and the target has once is a
    # real gap that set comparison cannot see, and that is not hypothetical:
    # `elsif ARM64 or ARM64E or RISCV64 or PPC64` appears several times in
    # LowLevelInterpreter.asm, and functionPrologue's copy was missing while
    # preserveCallerPCAndCFR's was present. The interpreter then built no
    # frame and saved no link register on this target, and every call returned
    # to garbage -- with every gate reporting clean.
    a=$(grep -E "$pat" "$PORT/$rel" | sed "$strip" | sed -E "$nocomment" | sort | uniq -c | sed 's/^ *//')
    b=$(grep -E "$pat" "$OUT/$rel"  | sed "$strip" | sed -E "$nocomment" | sort | uniq -c | sed 's/^ *//')
    n=$(comm -23 <(printf '%s\n' "$a") <(printf '%s\n' "$b") | grep -c .)
    t=$(printf '%s\n' "$a" | grep -c .)
    tot=$((tot+t)); miss=$((miss+n))
    [ "$n" -gt 0 ] && printf '%4d/%-4d missing  %s\n' "$n" "$t" "${rel#Source/}"
done
echo
echo "ppc64-mentioning lines in the port: $tot ; not present in the staged tree: $miss"
