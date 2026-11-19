# `linux-power9-7.2`

Linux 7.2.9 for POWER9, installed **beside** `linux-power9` (7.3) for people
who need **nova-core** (the Rust NVIDIA driver) on a Turing-or-newer card.

7.3's nova-core loads NVIDIA GSP firmware in a new `.tlv` format
(`nvidia/<chip>/gsp/gsp_bootloader.tlv`, `gsp.tlv`, ...), and no
linux-firmware release ships it yet: 20261019 has only the `.bin` firmware
(535 and 570). 7.2's nova-core loads those `.bin` files, so on 7.2 the GSP
starts and on 7.3 it does not.

This is the exact recipe `ours/linux-power9` built as 7.2.9-3 (packaging
`3d5aa41f`: squashfs zstd/lz4, the 11 POWER patches of that release), with
three changes:

- `pkgbase` is `linux-power9-7.2` / `linux-power9-7.2-64k`, so the kernel,
  its modules (`/usr/lib/modules/7.2.9[-64k]`), `/boot/vmlinuz-<pkgbase>` and
  the petitboot entry `omarchy-petitboot-entry` writes are its own;
- no `-api-headers` package: `linux-power9` ships those;
- `pkgrel` starts at 1.

Build and patch notes are `ours/linux-power9/README.md`'s, at 7.2.9.

**7.2 is end-of-life** (7.2.15, 2026-11-01, was its last release). This
package gets no security fixes. Remove it once linux-firmware ships the
`.tlv` firmware and 7.3's nova-core can start the GSP.

Install beside the 7.3 kernel, after `linux-power9` has moved to 7.3 (the two
cannot both own `/usr/lib/modules/7.2.9`):

    pacman -S linux-power9-7.2-64k linux-power9-7.2-64k-headers
