#!/bin/bash
# Pack ppc64le-port/ into the tarball that the webkitgtk recipes consume as a
# source=() entry, and drop a copy beside every recipe that uses it.
#
# WHY A TARBALL AND NOT THE DIRECTORY: makepkg fetches source=() entries and
# strips a local one to its basename, so a recipe cannot name a path inside
# another recipe's directory. Reaching the directory through $startdir instead
# works for a plain makepkg but not for a clean-chroot build, which copies only
# the recipe directory. A tarball makes the port an explicit, checksummed input
# of each recipe rather than something ambient.
#
# The SAME tarball goes to every consumer, so the sha256 in their PKGBUILDs must
# be identical. That is the drift detector: if one recipe's checksum differs
# from another's, somebody packed a different port.
#
# Deterministic on purpose (sorted, fixed mtime/owner, gzip -n) so re-running it
# on an unchanged directory reproduces the same bytes and the same hash.
#   make-port-tarball.sh            pack, and update every consumer
#   make-port-tarball.sh --check     verify the committed tarballs are current
#
# --check is the guard for the one failure mode this design introduces: the
# directory is what you edit and the tarball is what makepkg consumes, so an
# edit without a repack ships stale port material. --check repacks to a temp
# file and compares, touching nothing. Run it before committing a port change.
set -euo pipefail
MODE="${1:-pack}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OURS="$(cd "$HERE/.." && pwd)"
SRC="$HERE/ppc64le-port"
[ -d "$SRC" ] || { echo "no such directory: $SRC" >&2; exit 1; }

# Consumers. Add a recipe here when it starts staging the port.
CONSUMERS=(webkit2gtk webkitgtk-6.0)

TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT
cp -a "$SRC" "$TMP/ppc64le-port"
# Build hygiene: never ship generated or editor leftovers.
find "$TMP/ppc64le-port" \( -name '.port.table' -o -name '*.pyc' -o -name '__pycache__' \
     -o -name '*.rej' -o -name '*.orig' -o -name '*~' \) -prune -exec rm -rf {} + 2>/dev/null || true

OUT="$TMP/ppc64le-port.tar.gz"
tar -C "$TMP" --sort=name --mtime='UTC 2020-01-01' --owner=0 --group=0 \
    --numeric-owner -cf - ppc64le-port | gzip -n -9 > "$OUT"
SHA="$(sha256sum "$OUT" | cut -d' ' -f1)"

if [ "$MODE" = "--check" ]; then
  rc=0
  for c in "${CONSUMERS[@]}"; do
    f="$OURS/$c/ppc64le-port.tar.gz"
    if [ ! -f "$f" ]; then
      echo "  MISSING  ours/$c/ppc64le-port.tar.gz"; rc=1
    elif cmp -s "$OUT" "$f"; then
      echo "  current  ours/$c"
    else
      echo "  STALE    ours/$c -- repack with $(basename "$0")"; rc=1
    fi
  done
  echo
  [ $rc -eq 0 ] && echo "all consumers current ($SHA)" || echo "ACTION NEEDED"
  exit $rc
fi

for c in "${CONSUMERS[@]}"; do
  if [ -d "$OURS/$c" ]; then
    cp "$OUT" "$OURS/$c/ppc64le-port.tar.gz"
    echo "  -> ours/$c/ppc64le-port.tar.gz"
  else
    echo "  (skipped: ours/$c does not exist yet)"
  fi
done
echo
echo "files:  $(find "$TMP/ppc64le-port" -type f | wc -l)"
echo "size:   $(stat -c%s "$OUT") bytes"
echo "sha256: $SHA"
echo
echo "Put that sha256 in every consumer's PKGBUILD. They must all match."
