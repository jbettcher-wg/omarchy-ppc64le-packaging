# Provenance

This tree is the single curated source of build scripts for Omarchy ppc64le.
It was assembled on **2026-09-15** from two places, and from then on it is the
only one: Arch POWER and Arch are sources we *import from*, not trees anything
reads at build time.

## What it was built from

**Base — the Arch POWER packaging repo**, `~/Development/repo/archpower` at
commit `a31c166b` (*update libuninameslist to 20260107-1*), taken from its
**working tree**, not from the commit. That distinction matters: the checkout
carried eleven uncommitted PKGBUILD edits and seven untracked fix files that
are deliberate local work, and all of them are included here —

| Edited | |
|---|---|
| `7zip`, `chromium`, `gcc`, `gstreamer`, `libmnl`, `librtas`, `mesa`, `openexr`, `pipewire`, `powerpc-utils`, `sdl2` | modified `PKGBUILD` (gcc's bootstrap change, 7zip's pkgrel, and the rest) |

| Added | |
|---|---|
| `clang/clang-disable-float128-diagnostics-for-device-compilation.patch` | |
| `gstreamer/0002-gst-libav-guard-V308-V408-V410-for-libavcodec-63.patch` | |
| `mesa/mesa-gcc16-missing-includes.patch` | |
| `openexr/openexr-cxx-math.patch` | |
| `pipewire/spa-json-core-cxx-math.patch` | |
| `sdl2/sdl2-pipewire-node-cast.patch` | |

**Overlay — our own recipes**, from `omarchy-ppc64le/packages/` (199 pkgbases),
laid over that base with **ours winning every collision**. All 49 pkgbases we
share with Arch POWER sat at the identical relative path in both trees, so the
overlay replaced files in place and created no second directory for any
pkgbase. 150 pkgbases were ours alone, 29 of them under `ours/`.

Git history was deliberately not preserved. A plain copy is what was wanted:
the point is one curated tree under one roof, not a merge of two histories.

## What was left out

Only build residue and things that are not packaging:

- makepkg working trees and downloaded sources — `src/`, `pkg/`, `chromium/gn/`,
  `gcc/gcc/`, source tarballs and their `.sig` files. These were *untracked* in
  the archpower checkout, so importing the tracked set excluded them by
  construction rather than by pattern matching.
- `ThirdParty/` — 121 files of vendored VTK third-party C++ source that reached
  Arch POWER's packaging repo through a `Merge branch 'upstream-xdmf3'`. It
  contains no `PKGBUILD` and no recipe references it.
- `chromium/PKGBUILD.bak-2203`, the one backup among the untracked local
  changes. It is a copy of a recipe, not a recipe, and the `*.bak*` rule in
  `.gitignore` covers it.
- `.github/` and Arch POWER's top-level `README.md`, which describe their
  repository rather than this one. Their `CONTRIBUTORS.txt` is kept, because
  most of this tree is their work.

`gn/` at the top level is **not** residue — it is the Chromium GN build tool's
own pkgbase, and is kept. Only `chromium/gn/`, a build directory, was dropped.

## Layout rule

The layout is Arch POWER's, because ours already mirrored it and keeping them
comparable is what makes "do they carry this, and is theirs newer?" answerable.

| Where | What |
|---|---|
| `<category>/<pkgbase>/` | a recipe Arch POWER nests under that category — `kf6/`, `kf5/`, `kde/`, `plasma/`, `qt6/`, `xorg/`, `python/`, `perl/`, `go/`, `dotnet/`, `kernels/`, `tde/` and the rest. Use the category they use. |
| `<pkgbase>/` | a recipe Arch POWER keeps at its top level, which is also where Arch's flat GitLab namespace maps. |
| `ours/<pkgbase>/` | a recipe nobody upstream carries: absent from both Arch POWER and Arch's GitLab, so this tree is its primary source. |

**One pkgbase resolves to exactly one directory.** Two directories claiming one
pkgbase is reported as an error and never resolved by picking one — that silent
pick is the failure this tree exists to remove.

## Duplicates inherited from Arch POWER, and how they were resolved

Arch POWER carried three pkgbases in two directories each. They are ours to
curate now, so each was decided on the merits and the loser deleted:

| pkgbase | kept | dropped | why |
|---|---|---|---|
| `gnome-common` | `gnome-common/` (3.18.0-**6.1**) | `gnome/gnome-common/` (3.18.0-6) | the top-level copy is Arch POWER's own rebuild — higher pkgrel, and it is the one carrying a `.SRCINFO`. |
| `malcontent` | `gnome/malcontent/` | `malcontent/` | both are 0.14.0-4, but only the `gnome/` copy carries the ppc64le fix: a `case "${CARCH}" in powerpc*) return 0` that skips a check which does not pass here. Identical versions, so nothing but the diff could decide it. |
| `linux-ps3` | `kernels/powerpc/linux-ps3/` (6.12.62-2) | `linux-ps3/` (6.0.10.arch1-2.1) | six kernel releases newer, carries the full 40-patch PS3 stack, and sits in the category where kernels belong. |

After this, discovery reports **zero** duplicate pkgbases.
