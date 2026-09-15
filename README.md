# omarchy-ppc64le-packaging

Every build script the Omarchy ppc64le distribution builds from, in one tree.

One directory per pkgbase: the `PKGBUILD`, plus the patches, install hooks,
`.SRCINFO`, `.nvchecker.toml`, licence and keyring material it needs. This is
the source-controlled asset — build output is never committed.

`tools/bq.py` in [omarchy-ppc64le](https://github.com/jbettcher-wg/omarchy-ppc64le)
builds from **this tree and nothing else**. Arch's GitLab and the AUR are
import sources reached through `tools/fetch.sh`, which places a fetched recipe
in the right category *here*; they are not consulted at build time. That split
is the point: when three trees could each supply a recipe, versions drifted
silently between builders.

Point a builder at a clone with `OMARCHY_PACKAGING=/path/to/this/checkout`;
the default is `~/Development/omarchy-ppc64le-packaging`.

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
  struct punning. POWER9 is little-endian, which removes a whole class of bugs
  the historic big-endian ppc64 ports hit — do not assume old ppc64 patches
  apply unchanged.
- **Bump `pkgrel` before rebuilding something already published.** pacman
  compares versions, not contents.

## Licensing

Recipes and patches adapted from Arch Linux, Arch POWER or the AUR keep their
original licences; see each package directory (`LICENSE`, `REUSE.toml`, or the
patch header). Most of this tree is Arch POWER's work — their
`CONTRIBUTORS.txt` is kept at the top level. Our own recipes and patches are
MIT, as in the main repository.
