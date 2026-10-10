#!/bin/bash
# Apply the ppc64le JavaScriptCore JIT port to a WebKit source tree, in place.
#
#   ppc64le-port/stage.sh <webkit-source-tree>
#
# Self-contained: everything it needs is in this directory. Nothing is fetched
# and no port checkout is required, so it runs inside a PKGBUILD prepare().
#
# The port is NOT one patch. A squashed diff against a tree this size rots on
# every WebKit release -- measured against 2.54.1, 108 of 766 hunks failed and
# most of them were still CORRECT, just moved. So it is four layers:
#
#   1. newfiles/   files only this port has. They share nothing, so they never
#                  conflict, and they are most of the port by volume.
#   2. airopcode.table
#                  AirOpcode.opcodes rebuilt from a table of operations keyed
#                  on DECLARATION TEXT rather than line numbers. Upstream
#                  retags that file constantly; the port's intent ("ppc64
#                  implements this form too") does not change. Tag edits are a
#                  SET DELTA, never an absolute string -- writing the absolute
#                  string would have deleted the `arm`/`armv7` tags from 28
#                  declarations and dropped 32-bit ARM support from this build
#                  with nothing failing to say so.
#   3. patches/    an ordinary series, applied at EXACT context. Never with
#                  fuzz: fuzz bought 47 more hunks against 2.54.1 and silently
#                  corrupted two files (a bare #endif in DOMJITEffect.h) while
#                  reporting success.
#   4. tools/edits.py
#                  the rest, as operations anchored to an exact line of source.
#                  Idempotent, every anchor must match exactly once, and a file
#                  whose anchors are in doubt is NOT written.
#
# Anything unresolved is printed and the script fails. On a new WebKit version
# that output is the review list; see dev/ for the tools that shrink it.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
TREE="$(cd "$1" && pwd)"

echo ":: ppc64le port -> $TREE"

echo ":: 1/4 new files"
( cd "$HERE/newfiles" && find . -type f -print0 ) |
    while IFS= read -r -d '' f; do
        install -Dm644 "$HERE/newfiles/$f" "$TREE/$f"
    done
echo "   $(find "$HERE/newfiles" -type f | wc -l) installed"

echo ":: 2/4 AirOpcode.opcodes"
python3 "$HERE/tools/airopcode.py" apply "$HERE/airopcode.table" \
    "$TREE/Source/JavaScriptCore/b3/air/AirOpcode.opcodes" | sed 's/^/   /'

echo ":: 3/4 patch series (exact context)"
tot=0; bad=0
for p in "$HERE"/patches/*.patch; do
    h=$(grep -c '^@@' "$p") || h=0
    out=$(cd "$TREE" && patch -p1 -F0 -s --no-backup-if-mismatch < "$p" 2>&1) || true
    n=$(printf '%s' "$out" | grep -oE '[0-9]+ out of [0-9]+ hunks? FAILED' |
        awk '{s+=$1} END{print s+0}')
    tot=$((tot + h)); bad=$((bad + n))
done
echo "   $((tot - bad))/$tot hunks applied, $bad left for the edit table"

echo ":: 4/4 anchored edits"
python3 "$HERE/tools/edits.py" > "$HERE/.port.table"
python3 "$HERE/tools/portedit.py" "$HERE/.port.table" "$TREE" | sed 's/^/   /'

echo ":: residue"
# Captured, not tee'd. `tee /dev/stderr` OPENS /dev/stderr rather than dup'ing
# it, so under a `>log 2>&1` redirect it gets its own file offset at 0 and
# overwrites the log from the top -- a successful run used to shred its own
# progress output -- and the `head -1` downstream SIGPIPE'd tee mid-write, so a
# FAILING run could lose the diagnostics this block exists to print. Under
# makepkg that log is the only record, so take the output once and print it all.
res="$(python3 "$HERE/tools/reconcile.py" "$TREE" --prune 2>&1)" || true
printf '%s\n' "$res" | sed 's/^/   /'
if printf '%s\n' "$res" | head -1 | grep -q '0 outstanding, 0 partial'; then
    find "$TREE" -name '*.rej' -delete 2>/dev/null || true
    find "$TREE" -name '*.orig' -delete 2>/dev/null || true
    echo ":: clean"
else
    echo ":: UNRESOLVED -- see the .rej files above" >&2
    exit 1
fi
