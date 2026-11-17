#!/bin/bash
#
# Tests for omarchy-petitboot-entry, against a fixture root.
# Usage: test-omarchy-petitboot-entry.sh <path to omarchy-petitboot-entry>

set -euo pipefail

gen=$(realpath "$1")
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
fails=0
fail() { echo "FAIL: $*" >&2; fails=$((fails + 1)); }

fixture() { # name -> a root with linux-omarchy 7.2.9 installed and /boot populated
  local r=$work/$1
  mkdir -p "$r/boot" "$r/etc/kernel" "$r/etc/default" "$r/usr/lib/modules/7.2.9-omarchy"
  echo linux-omarchy >"$r/usr/lib/modules/7.2.9-omarchy/pkgbase"
  : >"$r/boot/vmlinuz-linux-omarchy"
  : >"$r/boot/initramfs-linux-omarchy.img"
  printf '%s\n' "$r"
}
run() { # root [args] -> stdout+stderr, sets rc
  local r=$1; shift
  rc=0
  out=$(OMARCHY_PETITBOOT_ROOT=$r OMARCHY_PETITBOOT_BOOT_UUID=1111-2222 bash "$gen" "$@" 2>&1) || rc=$?
}
cfg() { cat "$1/boot/grub/grub.cfg"; }

# A system whose boot is not set up yet gets nothing written, and no failure:
# the package's own hook runs while the root image is built.
r=$(fixture unset)
run "$r"
[[ $rc == 0 ]] || fail "no command line: exit $rc"
[[ ! -e $r/boot/grub/grub.cfg ]] || fail "no command line: wrote a grub.cfg"
echo 'zswap.enabled=0 rootflags=subvol=@ rw quiet' >"$r/etc/kernel/cmdline"
run "$r"
[[ $rc == 0 && ! -e $r/boot/grub/grub.cfg ]] || fail "a command line without root= wrote entries"

# The entry: the boot filesystem by UUID, paths relative to it, the command
# line as written, and the initramfs.
r=$(fixture basic)
echo 'root=UUID=aaaa rootflags=subvol=@ rw quiet splash' >"$r/etc/kernel/cmdline"
run "$r"
[[ $rc == 0 ]] || fail "basic: exit $rc: $out"
c=$(cfg "$r")
grep -qxF "    search --set=root --fs-uuid 1111-2222" <<<"$c" || fail "basic: no search for the boot UUID"
grep -qxF "    linux /vmlinuz-linux-omarchy root=UUID=aaaa rootflags=subvol=@ rw quiet splash" <<<"$c" || fail "basic: wrong linux line: $c"
grep -qxF "    initrd /initramfs-linux-omarchy.img" <<<"$c" || fail "basic: no initrd line"
grep -q '/boot/' <<<"$c" && fail "basic: a path names /boot, which petitboot resolves against /boot itself"
grep -qx 'set timeout=5' <<<"$c" || fail "basic: no GRUB timeout"
statements=$(sed -e 's/#.*//' -e 's/^[[:space:]]*//' "$r/boot/grub/grub.cfg" | awk 'NF { print $1 }' | sort -u |
  grep -vx -e set -e menuentry -e search -e linux -e initrd -e '}' || true)
[[ -z $statements ]] || fail "basic: statements outside petitboot's grammar: $statements"

# Idempotent, and what an owner wrote outside the block stays.
r=$(fixture keep)
echo 'root=UUID=aaaa rw' >"$r/etc/kernel/cmdline"
mkdir -p "$r/boot/grub"
printf 'menuentry "Hand written" {\n    linux /other\n}\n' >"$r/boot/grub/grub.cfg"
run "$r"; first=$(cfg "$r")
run "$r"; second=$(cfg "$r")
[[ $first == "$second" ]] || fail "keep: a second run changed the file"
grep -qF 'menuentry "Hand written"' <<<"$second" || fail "keep: the hand-written entry is gone"
[[ $(grep -c '^### BEGIN omarchy-petitboot-entry ###$' <<<"$second") == 1 ]] || fail "keep: not exactly one block"

# The block omp-install wrote is taken over, not left beside a new one.
r=$(fixture legacy)
echo 'root=UUID=aaaa rw' >"$r/etc/kernel/cmdline"
mkdir -p "$r/boot/grub"
printf 'set foo=1\n### BEGIN petitboot-entry ###\nmenuentry "old" {\n}\n### END petitboot-entry ###\ntail\n' >"$r/boot/grub/grub.cfg"
run "$r"
c=$(cfg "$r")
grep -qF 'petitboot-entry ###' <<<"$(grep -v omarchy-petitboot-entry <<<"$c")" && fail "legacy: the old markers remain"
grep -qF 'menuentry "old"' <<<"$c" && fail "legacy: the old entry remains"
[[ $(head -n1 <<<"$c") == 'set foo=1' && $(tail -n1 <<<"$c") == tail ]] || fail "legacy: lost what surrounded the block: $c"

# The default kernel goes first wherever it sorts.
r=$(fixture order)
echo 'root=UUID=aaaa rw' >"$r/etc/kernel/cmdline"
mkdir -p "$r/usr/lib/modules/7.2.9-omarchy-64k"
echo linux-omarchy-64k >"$r/usr/lib/modules/7.2.9-omarchy-64k/pkgbase"
: >"$r/boot/vmlinuz-linux-omarchy-64k"
echo 'DEFAULT_KERNEL=linux-omarchy-64k' >"$r/etc/default/omarchy-petitboot-entry"
run "$r"
[[ $(grep -m1 '^menuentry' "$r/boot/grub/grub.cfg") == "menuentry 'Omarchy (linux-omarchy-64k)' {" ]] || fail "order: the default kernel is not first"
[[ $(grep -c '^menuentry' "$r/boot/grub/grub.cfg") == 2 ]] || fail "order: not one entry per kernel"

# --check changes nothing.
r=$(fixture check)
echo 'root=UUID=aaaa rw' >"$r/etc/kernel/cmdline"
run "$r" --check
[[ $rc == 0 && ! -e $r/boot/grub/grub.cfg ]] || fail "check: wrote the file"
grep -qF "linux /vmlinuz-linux-omarchy root=UUID=aaaa rw" <<<"$out" || fail "check: did not print the block"

# No kernel in /boot is a failure, not an empty menu.
r=$(fixture none)
echo 'root=UUID=aaaa rw' >"$r/etc/kernel/cmdline"
rm "$r/boot/vmlinuz-linux-omarchy"
run "$r"
[[ $rc == 1 ]] || fail "none: exit $rc with no kernel"

if (( fails )); then
  echo "$fails failure(s)" >&2
  exit 1
fi
echo "omarchy-petitboot-entry: all tests passed"
