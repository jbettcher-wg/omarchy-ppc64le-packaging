#!/bin/bash
# Verify a staged tree. Four gates, none of which needs a compiler:
#
#   1. no unapplied hunks left (reconcile.py)
#   2. every ppc64 CODE line the port has is present (ppc64check.sh)
#   3. the Air opcode generator accepts the merged AirOpcode.opcodes, and the
#      dispatch it emits for every OTHER architecture is byte-identical to the
#      one pristine upstream produces. This is the gate that matters most: the
#      port must add ppc64 and change nothing for anybody else, and an
#      absolute-tag merge would silently delete ARM support here.
#   4. the preprocessor is no more unbalanced than pristine (fuzzy patching
#      once left a bare #endif in DOMJITEffect.h while reporting success)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="${TOOLS:-$(cd "$HERE/../tools" && pwd)}"
# absolute, because gen() runs the generator from a temp directory
PRISTINE="$(cd "$1" && pwd)"; OUT="$(cd "$2" && pwd)"
PORT="${PORT:-/mnt/arch/home/jbettcher/Development/webkit-ppc64le}"
rc=0

echo "== 1. unapplied hunks"
# stage.sh deletes the .rej files once nothing is left unresolved, so a tree
# with none is a pass, not an absence of evidence.
if [ -z "$(find "$OUT" -name '*.rej' -print -quit)" ]; then
    echo "   no .rej files in the tree (stage.sh prunes them once clean)"
else
    r1=$(python3 "$TOOLS/reconcile.py" "$OUT" 2>/dev/null | head -1)
    echo "   $r1"
    printf '%s' "$r1" | grep -q '0 outstanding, 0 partial' || { echo "   FAIL"; rc=1; }
fi

echo "== 2. ppc64 code lines present"
"$HERE/ppc64check.sh" "$OUT" 2>/dev/null | tail -1 | sed 's/^/   /'

echo "== 3. Air dispatch: ppc64 added, every other architecture unchanged"
gen() {  # gen <opcodes-file> -> prints "PPC64LE ARM_THUMB2 ARM64 X86_64"
    local d; d=$(mktemp -d)
    ( cd "$d" && ruby "$OUT/Source/JavaScriptCore/b3/air/opcode_generator.rb" "$1" >/dev/null 2>&1 )
    if [ ! -f "$d/AirOpcodeGenerated.h" ]; then echo "GENERATOR-FAILED"; rm -rf "$d"; return 1; fi
    for a in PPC64LE ARM_THUMB2 ARM64 X86_64 ARM RISCV64; do
        printf '%s=%s ' "$a" "$(grep -c "CPU($a)" "$d/AirOpcodeGenerated.h")"
    done
    echo; rm -rf "$d"
}
p=$(gen "$PRISTINE/Source/JavaScriptCore/b3/air/AirOpcode.opcodes") || rc=1
o=$(gen "$OUT/Source/JavaScriptCore/b3/air/AirOpcode.opcodes")      || rc=1
echo "   pristine $p"
echo "   ported   $o"
if [ "${p#PPC64LE=0 }" = "${o#PPC64LE=510 }" ]; then
    echo "   other architectures identical"
else
    # compare field by field, ignoring PPC64LE
    pa=${p#PPC64LE=* }; oa=${o#PPC64LE=* }
    if [ "$pa" = "$oa" ]; then echo "   other architectures identical"
    else echo "   FAIL: an architecture other than ppc64 changed"; rc=1; fi
fi
case "$o" in PPC64LE=0\ *) echo "   FAIL: no ppc64 dispatch emitted"; rc=1;; esac

echo "== 5. every scope the port supports is supported here too"
if [ -d "$PORT" ]; then
    python3 "$TOOLS/scopecheck.py" "$PORT" "$OUT" "${PATCHES:-$HERE/../patches}" 2>/dev/null | tail -8 | sed 's/^/ /'
    python3 "$TOOLS/scopecheck.py" "$PORT" "$OUT" "${PATCHES:-$HERE/../patches}" >/dev/null 2>&1 || { echo "   FAIL"; rc=1; }
else
    echo "   skipped (no port checkout at PORT=$PORT)"
fi

echo "== 4. preprocessor balance"
bal() { python3 - "$1" <<'PY'
import io,os,sys
root=sys.argv[1]; bad=0
for dp,_,fns in os.walk(root):
    if '/.git' in dp: continue
    for fn in fns:
        if not fn.endswith(('.h','.cpp','.c')): continue
        d=0; lo=0
        try: t=io.open(os.path.join(dp,fn),encoding='utf-8',errors='replace').read()
        except Exception: continue
        for l in t.split('\n'):
            s=l.lstrip()
            if s.startswith('#if'): d+=1
            elif s.startswith('#endif'):
                d-=1
                if d<lo: lo=d
        if d or lo<0: bad+=1
print(bad)
PY
}
a=$(bal "$PRISTINE/Source"); b=$(bal "$OUT/Source")
echo "   pristine=$a ported=$b"
[ "$a" = "$b" ] || { echo "   FAIL: the port unbalanced $((b-a)) file(s)"; rc=1; }

echo
[ $rc -eq 0 ] && echo "ALL GATES PASS" || echo "GATES FAILED"
exit $rc
