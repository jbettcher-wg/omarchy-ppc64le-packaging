#!/bin/bash
# make-bootstrap-tarball.sh <dart-sdk dir> <power9|baseline> [<provenance note>]
#
# Turns a built native ppc64le Dart SDK (create_sdk's out/ReleasePPC64/dart-sdk,
# or /usr/lib/dart of a `dart` package) into the tarball dart-bootstrap ships
# for one pool, beside this script:
#   dart-bootstrap-<ver>-powerpc64le.tar.zst          power9 pool
#   dart-bootstrap-<ver>-power8-powerpc64le.tar.zst   baseline pool
# plus <tarball>.sha256 and <tarball>.provenance (what went in, measured).
#
# Refuses an SDK that is not a native linux_ppc64 Dart of that version, and
# normalises modes (u+rwX,go+rX,go-w: M5's SDK carried DevTools files 0600
# straight from the CIPD zip), and applies the same ISA rule as dart's
# build(): AOT snapshots are Dart codegen and must carry 0 ISA 3.0
# instructions in both pools; in the baseline pool a native ELF may carry
# only what dart's build() attributed to libgcc's IFUNC'd float128 routines
# (its .pkginfo, isa30-allowed-total), and nothing else. The tarball is
# reproducible (sorted, root-owned, fixed mtime, zstd), so the same SDK
# always gives the same sha256.
#
# Run natively (ssh -n -i ~/.ssh/id_claude_omarchy -o BatchMode=yes localhost):
# it executes the SDK and needs the host's ppc64le objdump.
set -euo pipefail
[[ $# -ge 2 ]] || { sed -n '2,17p' "$0"; exit 2; }
here=$(cd "$(dirname "$0")" && pwd)
sdk=$(cd "$1" && pwd)
pool=$2
note=${3:-}
[[ $(uname -m) == ppc64le ]] || { echo "run this natively, not in the POWERarm sleeve" >&2; exit 2; }
case $pool in
  power9)   suffix= ;;
  baseline) suffix=-power8 ;;
  *) echo "pool must be power9 or baseline" >&2; exit 2 ;;
esac

ver=$(< "$sdk/version")
[[ $ver =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "unexpected SDK version '$ver'" >&2; exit 1; }
for b in dart dartaotruntime; do
  file -b "$sdk/bin/$b" | grep -q '64-bit LSB .*PowerPC' \
    || { echo "$b is not a ppc64le ELF: $(file -b "$sdk/bin/$b" | cut -d, -f1-2)" >&2; exit 1; }
  v=$("$sdk/bin/$b" --version 2>&1)
  [[ $v == *"$ver (stable)"*'"linux_ppc64"'* ]] || { echo "$b reports: $v" >&2; exit 1; }
done
vstring=$("$sdk/bin/dart" --version 2>&1)

isa30() {
  local n8 n9
  n8=$(objdump -d --no-show-raw-insn -M power8 "$1" 2>/dev/null | grep -cP '^\s+[0-9a-f]+:\s+\.long\b' || true)
  n9=$(objdump -d --no-show-raw-insn -M power9 "$1" 2>/dev/null | grep -cP '^\s+[0-9a-f]+:\s+\.long\b' || true)
  echo $((n8 - n9))
}
export -f isa30
counts=$(cd "$sdk" && find . -type f -print0 \
  | xargs -0 -n1 -P 16 bash -c '[[ $(od -An -tx1 -N4 "$1") == " 7f 45 4c 46" ]] || exit 0
                                printf "%s %s\n" "$(isa30 "$1")" "${1#./}"' _ | sort -k2)
# Baseline pool: a native binary may carry ISA 3.0 only as libgcc's IFUNC'd
# IEEE-128 hardware routines, which dart's build() attributed per function
# on the unstripped binary and recorded in the SDK's .pkginfo as
# "isa30-allowed-total <path> <n>". The installed count must equal it.
recorded() { sed -n "s#^isa30-allowed-total $1 \([0-9]*\) .*#\1#p" "$sdk/.pkginfo" 2>/dev/null; }
bad=0
while read -r n f; do
  if (( n )) && [[ $f == bin/snapshots/* ]]; then
    echo "REFUSED: $n ISA 3.0 instructions in AOT snapshot $f" >&2; bad=1
  elif (( n )) && [[ $pool == baseline ]]; then
    if [[ $(recorded "$f") == "$n" ]]; then
      echo "baseline: $f carries $n ISA 3.0 instructions, all attributed to libgcc's IFUNC'd float128 routines by dart's build()"
    else
      echo "REFUSED: $n ISA 3.0 instructions in $f (baseline pool; recorded attribution: '$(recorded "$f")')" >&2; bad=1
    fi
  fi
done <<< "$counts"
(( ! bad )) || exit 1

name=dart-bootstrap-$ver$suffix-powerpc64le.tar.zst
out=$here/$name
# Fixed mtime: the 3.11.5 tag's commit time. The SDK's own revision/version
# files and .provenance say what it actually is.
epoch=1776238592
base=$(basename "$sdk")
tar -C "$(dirname "$sdk")" --sort=name --owner=0 --group=0 --numeric-owner --hard-dereference \
    --mtime="@$epoch" --mode='u+rwX,go+rX,go-w' --pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime \
    --transform "s,^$base\(/\|\$\),dart-sdk\1," -cf - "$base" \
  | zstd -q -19 -T0 -o "$out" -f
sum=$(sha256sum < "$out" | cut -d' ' -f1)
printf '%s  %s\n' "$sum" "$name" > "$out.sha256"

{
  printf 'tarball: %s\nsha256: %s\nsize: %s bytes\npool: %s\n' "$name" "$sum" "$(stat -c %s "$out")" "$pool"
  printf 'made: %s on %s (%s, kernel %s)\n' "$(date -u +%FT%TZ)" "$(hostname)" "$(uname -m)" "$(uname -r)"
  printf 'from: %s\n' "$sdk"
  printf 'version: %s\nrevision: %s\n' "$vstring" "$(< "$sdk/revision")"
  for b in bin/dart bin/dartvm bin/dartaotruntime bin/utils/gen_snapshot; do
    [[ -f $sdk/$b ]] && printf '%s sha256: %s\n' "$b" "$(sha256sum < "$sdk/$b" | cut -d' ' -f1)"
  done
  printf 'files: %s\n' "$(find "$sdk" -type f | wc -l)"
  [[ -n $note ]] && printf 'provenance: %s\n' "$note"
  echo '# ISA 3.0 instructions per ELF (objdump -M power8 vs -M power9):'
  sed 's/^/isa30 /' <<< "$counts"
} > "$out.provenance"

echo "wrote $out"
echo "  sha256 $sum"
echo "PKGBUILD: _tarball='$name' _tarsum='$sum'"
