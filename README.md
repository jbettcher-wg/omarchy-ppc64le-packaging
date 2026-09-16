# omarchy-ppc64le-packaging

Every build script the Omarchy ppc64le distribution builds from, in one tree.

One directory per pkgbase: the `PKGBUILD`, plus the patches, install hooks,
`.SRCINFO`, `.nvchecker.toml`, licence and keyring material it needs. This is
the source-controlled asset — build output is never committed.

## The two repositories

The distribution is two repositories.

| | |
|---|---|
| **this one** | every build script the distribution builds from — 4,562 pkgbases, 199 of them ours |
| [**omarchy-ppc64le**](https://github.com/jbettcher-wg/omarchy-ppc64le) | the installer and ISO, the build tooling, the repo databases, and the docs |

These recipes feed **two package pools**, both built from this one tree. A
build is named for what it runs on, not for what it was tuned for:

| pool | built | runs on | role |
|---|---|---|---|
| **`omarchy-ppc64le`** | POWER8-legal (ISA 2.07) | POWER8 → POWER11, every ppc64le machine | the baseline, and the default everywhere |
| `omarchy-power9` | `-mcpu=power9`, ISA 3.0 | POWER9 only | optimised opt-in, layered ahead of the baseline |

A recipe that pins an ISA of its own needs a toggle so both pools can be built
from it; `chromium`'s `_power8_compat` is the pattern.

`tools/bq.py` over there builds from **this tree and nothing else**. Arch's
GitLab and the AUR are import sources reached through its `tools/fetch.sh`,
which places a fetched recipe in the right category *here*; neither is
consulted at build time. That split is the point: when three trees could each
supply a recipe, versions drifted silently between builders.

A builder needs both, and locates this tree through `OMARCHY_PACKAGING`:

```sh
git clone git@github.com:jbettcher-wg/omarchy-ppc64le.git
git clone git@github.com:jbettcher-wg/omarchy-ppc64le-packaging.git
export OMARCHY_PACKAGING=$PWD/omarchy-ppc64le-packaging
```

Clone them side by side under `~/Development` and the variable is unnecessary —
that is the default the tools assume.

## Layout

The tree mirrors Arch POWER's, so the two stay comparable.

| Where | What |
|---|---|
| `<category>/<pkgbase>/` | a recipe Arch POWER nests under that category — `kf6/`, `kf5/`, `kde/`, `plasma/`, `qt6/`, `xorg/`, `python/`, `perl/`, `go/`, `dotnet/`, `kernels/`, `tde/` and the rest |
| `<pkgbase>/` | a recipe Arch POWER keeps at its top level, which is also where Arch's flat GitLab namespace maps |
| `ours/<pkgbase>/` | a recipe no upstream carries; this tree is its primary source |

Recipes are found **by pkgbase, recursively** — never by assuming
`<root>/<pkgbase>`, which would miss the 2,600-odd recipes that live one and
two levels down. **One pkgbase must resolve to exactly one directory**; two
directories claiming one is an error, never resolved by picking one.

Where it came from, what was excluded, and how the three inherited duplicate
pkgbases were resolved: [`PROVENANCE.md`](PROVENANCE.md).

## Conventions

- **Start from upstream.** For a package Arch or Arch POWER already ships, keep
  the diff against their recipe minimal, so rebasing onto a new upstream
  version stays cheap.
- **Record why.** Every patch gets a header comment saying what it fixes and
  whether it is a ppc64le portability fix (a candidate to send upstream) or a
  local workaround (not).
- **`arch=()`.** Many ports need no more than adding `powerpc64le`. Say so
  explicitly when that genuinely was the only change — it keeps the packages
  that needed real work visible.
- **Endianness and word size are the usual culprits.** x86 assumptions show up
  as hardcoded `x86_64` triplets, SSE intrinsics, `-m64`, and little-endian
  struct punning. POWER9 is bi-endian silicon; this distribution runs it in
  little-endian mode (`ppc64le`, ELFv2), which removes a whole class of bugs
  the historic big-endian ppc64 ports hit — do not assume old ppc64 patches
  apply unchanged, and do not assume a package that builds big-endian says
  anything about this target.
- **Bump `pkgrel` before rebuilding something already published.** pacman
  compares versions, not contents.

## Licensing

Recipes and patches adapted from Arch Linux, Arch POWER or the AUR keep their
original licences; see each package directory (`LICENSE`, `REUSE.toml`, or the
patch header). Most of this tree is Arch POWER's work — their
`CONTRIBUTORS.txt` is kept at the top level. Our own recipes and patches are
MIT, as in the main repository.
