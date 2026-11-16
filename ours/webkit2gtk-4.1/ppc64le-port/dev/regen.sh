#!/bin/bash
# Regenerate the shipped inputs from a port checkout. Development only -- the
# recipe never runs this.
#
#   dev/regen.sh <port-checkout> <pre-port-base-commit>
#
# `patches/` and `newfiles/` come straight from the checkout; `airopcode.table`
# is DERIVED by diffing the base commit's AirOpcode.opcodes against the
# checkout's, so the table always describes the port rather than being typed
# by hand. The derivation is checked by round-trip: replaying the table onto
# the base must reproduce the checkout byte for byte.
set -eu
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PORT="$(cd "$1" && pwd)"
BASE="$2"
A=Source/JavaScriptCore/b3/air/AirOpcode.opcodes

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
git -C "$PORT" show "$BASE:$A" > "$tmp/base.opcodes"
python3 "$HERE/tools/airopcode.py" derive "$tmp/base.opcodes" "$PORT/$A" > "$HERE/airopcode.table"

cp "$tmp/base.opcodes" "$tmp/replay.opcodes"
python3 "$HERE/tools/airopcode.py" apply "$HERE/airopcode.table" "$tmp/replay.opcodes" >/dev/null
if cmp -s "$tmp/replay.opcodes" "$PORT/$A"; then
    echo "airopcode.table: $(wc -l < "$HERE/airopcode.table") ops, round-trip identical"
else
    echo "airopcode.table: ROUND-TRIP FAILED -- do not ship this" >&2; exit 1
fi
