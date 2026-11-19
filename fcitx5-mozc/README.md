# `fcitx5-mozc`

Arch's recipe (imported with `tools/fetch.sh fcitx5-mozc`, commit `013f6824`),
ported to ppc64le. Arch builds it for x86_64 only, with bazelisk. Every
ppc64le change sits under `if [[ $CARCH == powerpc64le ]]`, in the
`*_powerpc64le` arrays, or in `_ppc64le_setup`, which returns at once
elsewhere. x86_64 still builds exactly as Arch does.

## What bazelisk downloads, and the ppc64le route for each

Arch's `_bazel_deps` is mozc's whole dependency closure, so bazel can build
offline from `--distdir` and a local mirror of the Bazel Central Registry. Three
of its entries are tools bazelisk would pick for the host, and Arch carries them
for x86_64 and aarch64 only. None of the three is shipped. What ships is
compiled from source by bazel: mozc itself, abseil and the protobuf runtime.

| build-time tool | where it comes from on ppc64le |
|---|---|
| bazel 9.0.2, the build driver | our `bazel` package, built from its dist zip (`packaging/bazel`) |
| python-build-standalone 3.11.14, the interpreter rules_python runs mozc's generator scripts with | the ppc64le build from the same release, added as `source_powerpc64le` |
| protoc 34.1 | built from source by bazel: `--@com_google_protobuf//bazel/flags:prefer_prebuilt_protoc=false` |

**protoc is built from source.** protobuf 34.1's `MODULE.bazel` registers
prebuilt protoc toolchains for nine platforms, `linux_ppcle_64` among them.
They apply while `//bazel/flags:prefer_prebuilt_protoc` is true, its default.
With the flag false, protobuf's other toolchain builds protoc from its own
sources in the exec configuration. In the build, no `prebuilt_protoc` repository
is created and no protoc zip is fetched, and `bazel-out/ppc-opt-exec/bin/external/protobuf+/protoc`
is a ppc64le ELF built there `[MEASURED]`. If the from-source route ever
breaks, the fallback is to add `protoc-${_protobuf_version}-linux-ppcle_64.zip`
to `_bazel_deps_powerpc64le` and drop the flag. `ppc64le-pins.py` prints that
zip's sha256 from protobuf's `tool_integrity.bzl` (`9160f133...` for 34.1).

**python-build-standalone needed a rules_python patch.** rules_python 1.9.0
declares its ppc64le interpreter `compatible_with "@platforms//cpu:ppc"`, but
the platforms module detects a ppc64le host as `@platforms//cpu:ppc64le`.
Without the patch every `py_binary` fails with `No matching toolchains found
for types: @@bazel_tools//tools/python:toolchain_type`.
`rules_python-ppc64le-cpu.patch` changes that one constraint, and the patch's
header has the details. `prepare()` applies it through a
`single_version_override` appended to mozc's `MODULE.bazel`, the same
mechanism mozc already uses to patch rules_cc, so the BCR's own patch for
rules_python 1.9.0 still applies underneath. The bug is still on rules_python
`main` (checked 2026-11-18); it is a portability fix worth sending upstream.

The aarch64 and x86_64 entries in `_bazel_deps` stay as Arch has them. On
ppc64le they are downloaded and never opened.

## The pins, and what checks them

The values that decide the ppc64le additions are variables at the top of the
PKGBUILD:

| variable | read from |
|---|---|
| `_bazel_version` | `USE_BAZEL_VERSION` in mozc's `src/.bazeliskrc` |
| `_protobuf_version` | the `protobuf` `bazel_dep` in mozc's `src/MODULE.bazel` |
| `_pbs_python` | `MINOR_MAPPING` in rules_python's `python/versions.bzl`, for the version its `MODULE.bazel` passes to `python.defaults()` (mozc does not override it) |
| `_pbs_release` | the release that version's entry in `versions.bzl` downloads from |

`ppc64le-pins.py` reads each of them from those files. `prepare()` runs it as
`--check` against makepkg's `$srcdir`, offline. It fails the build if any pin
disagrees, or if the ppc64le PBS tarball lacks the sha256 rules_python
expects, or if protobuf's `bazel/flags/BUILD` has lost
`prefer_prebuilt_protoc`. `prepare()` also requires the installed
`bazel --version` to equal `_bazel_version`.

The other script here, `verify-conversion.py`, is the IPC client the
verification below uses. It is not a build input.

## Other ppc64le changes

Like bazel's, these are about bq's build environment, not about POWER.

- **Nothing from the network.** `--downloader_config` points at a generated
  `ppc64le-offline.cfg` that rewrites every http(s) URL to
  `127.0.0.1:9/fcitx5-mozc-builds-offline/<original>`. Bazel looks a file up
  in `--distdir` by the rewritten URL's basename, which is unchanged, so
  everything in `source=()` is still found. Anything missing is refused at once
  (`Connection refused`, with the original URL in the path) instead of being
  fetched behind makepkg's back. Arch's chroot can download, so a gap in Arch's
  list would not show there. The rewriter leaves non-HTTP(S) URLs alone, so the
  `file://` patches of the local registry still apply. Two obvious alternatives
  fail:
  - `--repository_disable_download` refuses those `file://` patches too. The
    first try died on `bazel_features+` with `download is disabled`.
  - A `block *` config leaves bazel no URL at all. `DownloadManager` then
    throws `Cache miss and no url specified` before it looks in the distdir.
    Or, given a repository-cache hit, it hands back a file named `cacheprobe`,
    which `download_and_extract` cannot unpack.
- **`pkgver()` builds offline too.** Arch's `pkgver()` runs
  `bazel build base:mozc_version_txt` without `--distdir` or `--registry`,
  which would resolve every module from the network. On ppc64le it gets the
  same arguments as `build()`, and it fails if `mozc_version.txt` was not
  produced, where Arch's would silently print `...` as the version.
- **`JAVA_HOME`** is JDK 21. Our bazel has no embedded JDK, and its server runs
  on `JAVA_HOME` or the default `java`; see `bazel/README.md`. The JDK is
  staged through bazel's own `depends`.
- **`CC=/usr/bin/gcc`.** bazel caches its own actions, so cc_configure gets the
  compiler itself, not the ccache shim bq can put first in `PATH`.
- **`--output_user_root` in `$srcdir`,** **`--max_idle_secs=300`,** and a
  `bazel shutdown` at the end of `build()`, so no bazel server outlives the
  build with a stale view of bq's `/usr` overlay.
- **`-j`.** makepkg's `-jN` becomes `--jobs=N --local_resources=cpu=N`.

## POWER8 codegen

bazel compiles with its own autoconfigured toolchain. makepkg's flags reach it
only because Arch's `build()` passes `CFLAGS` as `--conlyopt`, `CXXFLAGS` as
`--cxxopt` and `LDFLAGS` as `--linkopt`. Those apply to the target
configuration, the code that ships. The exec configuration builds tools that
run during the build only (protoc, the dictionary generators); they get gcc's
default flags and are not packaged.

On ppc64le, `build()` also writes bazel's execution log
(`--execution_log_json_file`): every spawn bazel ran, with its argv. Then
`_ppc64le_assert_mcpu` fails the build unless every target-configuration
`CppCompile` in that log has makepkg's `-mcpu` as its last `-mcpu`. In the
baseline pool that is `-mcpu=power8` from the POWER8 drop-in. The log is about
260 MB and is deleted once the check passes. Two cheaper routes do not work
with bazel 9:
- `aquery --skyframe_state` after the build returns `{}`;
- the after-build dump (`--experimental_aquery_dump_after_build_format`)
  carries no command lines.

In the 3.35.6354.2-1.1 builds, 766 target compiles ran in each pool, all at
`-mcpu=power8` in the baseline and all at `-mcpu=power9` in POWER9, with 487
exec-configuration compiles not checked `[MEASURED]`. Checked against
`-mcpu=power8`, a POWER9 log fails all 766, so the check does discriminate.

## Upstreams

- **Arch's recipe** (`gitlab.archlinux.org/archlinux/packaging/packages/fcitx5-mozc`)
  is what this tracks: `_mozc_commit`, `_bcr_commit`, `_bazel_deps`, the
  checksums, `pkgver` and the build line come from there unchanged.
- **fcitx/flatpak-fcitx5's `mozc-deps.yaml`** is the maintained list Arch's
  `_bazel_deps` is taken from, as its comment says. At `_mozc_commit`
  `a74b6712` the two name the same 31 URLs, compared by diffing the sets.
  Neither lists anything for ppc64le: flatpak builds x86_64 and aarch64 only.
- **mozc** itself is `github.com/fcitx/mozc`, the fcitx fork, at `_mozc_commit`.

## Bump procedure

1. Fetch Arch's current recipe into a scratch directory and diff it against
   this one:

   ```sh
   git clone --depth 1 https://gitlab.archlinux.org/archlinux/packaging/packages/fcitx5-mozc.git /var/tmp/fcitx5-mozc-arch
   diff /var/tmp/fcitx5-mozc-arch/PKGBUILD ~/Development/omarchy-ppc64le-packaging/fcitx5-mozc/PKGBUILD
   ```

   Carry Arch's changes over: `_mozc_commit`, `_bcr_commit`, `_bazel_deps`,
   `sha512sums`, `pkgver`, and anything in the functions. Leave the
   `ppc64le:` parts. Reset `pkgrel` to Arch's pkgrel with `.1` appended.
   (`tools/fetch.sh fcitx5-mozc` would overwrite the recipe in place, and the
   ppc64le parts would then have to be restored from `git diff`.)
2. Print the ppc64le pins for the new commit and paste the four values over
   the old ones:

   ```sh
   cd ~/Development/omarchy-ppc64le-packaging/fcitx5-mozc
   python3 -I ppc64le-pins.py <new _mozc_commit>
   ```

   It reads `src/.bazeliskrc` and `src/MODULE.bazel` at that commit, then the
   rules_python and protobuf release tarballs those name. It prints the PBS
   tarball's sha256 from rules_python, and the prebuilt protoc's sha256 from
   protobuf's `tool_integrity.bzl` in case the from-source route ever fails.
3. If `_bazel_version` moved, bump `packaging/bazel` first and publish it in
   both pools (`bazel/README.md`). bq stages makedepends from the pools, and
   `prepare()` refuses a bazel other than `_bazel_version`.
4. Refresh the checksums natively, with a `SRCDEST` so the 31 sources do not
   land in the recipe directory:
   `SRCDEST=/var/tmp/omarchy-bq-kzstd/srcdest updpkgsums`. That also covers
   `sha512sums_powerpc64le`, including the entries for `ppc64le-pins.py` and the
   patch, which change whenever those files are edited.
5. Build both pools. Read bq's `-> packaging fcitx5-mozc <version>` line
   before letting it run. A recipe bq has built before needs `--rebuild`; one
   that failed needs `--retry-failed`. Each lane took about 8 minutes at
   `--make-jobs 84`, most of it staging the sysroot.

   ```sh
   cd ~/Development/omarchy-ppc64le
   ( export BQ_BUILDROOT=/var/tmp/omarchy-bq-ppc64le-kzstd BQ_STATE=/var/tmp/omarchy-bq-ppc64le-kzstd/state.json
     tools/build-ppc64le.sh plan fcitx5-mozc &&
     tools/build-ppc64le.sh build -j1 --make-jobs 84 --rebuild )          # baseline
   ( B=/var/tmp/omarchy-bq-kzstd; export BQ_STATE=$B/state.json
     python3 tools/bq.py --buildroot $B plan fcitx5-mozc -o $B/queue-mozc.json &&
     python3 tools/bq.py --buildroot $B build -q $B/queue-mozc.json -j1 --make-jobs 84 --rebuild )  # POWER9
   ```

6. Verify as below, publish locally, and sync to R2.

## Verification

All `[MEASURED]`, 2026-11-19, `fcitx5-mozc-3.35.6354.2-1.1` from both lanes
(baseline 18,659,741 bytes, POWER9 18,580,124), built against
`bazel-9.0.2-1.1`.

**In the build** (bq's log, both lanes): `ppc64le-pins` agreed with the
sources on all four pins. Bazel ran 2766 actions. In the baseline,
`_ppc64le_assert_mcpu` found 766 target C/C++ compiles, all with
`-mcpu=power8` as the last `-mcpu`; in POWER9, the same 766 at
`-mcpu=power9`. All ran in `linux-sandbox`, and 487 exec-configuration
compiles were not checked. No URL was refused, i.e. `build()` needed nothing
outside `source=()`. `elf-pathguard: clean (3 ELF ...)`.

**On the packages**, per pool. `$P` is the package, `$SYS` the bq sysroot of
the same pool, `$CPU` power8 for the baseline and power9 for POWER9:

```sh
zstd -tq $P                                          # ok, both
~/Development/omarchy-ppc64le/tools/isa30-pkgscan.sh $P
/var/tmp/isa30-where.sh <extracted ELF>
python3 -I /var/tmp/blender53-work/zeropage.py <extracted ELFs>
readelf -d <ELF>                                     # NEEDED
qemu-ppc64le -L $SYS -E LD_TRACE_LOADED_OBJECTS=1 $SYS/usr/lib/ld64.so.2 <ELF>
```

- **ISA 3.0, baseline:** 1, in `mozc_server`, against an ISA 2.07 control of
  6,893. It is an `xsiexpqp v31,v31,v31` right after
  `lwax`/`add`/`mtctr`/`bctr`, among `.long 0xffff....` offsets: a switch
  table, i.e. data. `mozc_tool` and `fcitx5-mozc.so` scan 0, with controls of
  3,239 and 3,856. Real ISA 3.0: none. POWER9: 21,562, as intended.
- **Zeroed pages:** none in either pool.
- **Links:** `fcitx5-mozc.so` NEEDs `libFcitx5Config.so.6`,
  `libFcitx5Core.so.7` and `libFcitx5Utils.so.2`, which the pool's `.files`
  db assigns to `fcitx5-5.1.23-1`. `mozc_tool` NEEDs `libQt6{Core,Gui,Widgets}.so.6`,
  from `qt6-base-6.11.2-4`. `mozc_server` NEEDs only libc, libm, libstdc++
  and libgcc_s. Nothing is unresolved in either pool's sysroot.

**At run time**, natively and under `qemu-ppc64le -cpu $CPU -L $SYS`, with a
throwaway `HOME` whose `.config` exists:

```sh
# Python bindings for mozc's protocol, from the mozc checkout at _mozc_commit
protoc -I src --python_out=$GEN src/protocol/*.proto src/ipc/ipc.proto
H=<scratch home>; mkdir -p $H/.config
qemu-ppc64le -cpu $CPU -L $SYS -E HOME=$H -E XDG_CONFIG_HOME=$H/.config usr/lib/mozc/mozc_server &
python3 -I verify-conversion.py $GEN $H/.config/mozc nihongo 日本語
qemu-ppc64le -cpu $CPU -L $SYS -E HOME=$H -E QT_QPA_PLATFORM=offscreen usr/lib/mozc/mozc_tool --mode=about_dialog
qemu-ppc64le -cpu $CPU -L $SYS $SYS/usr/bin/python3 -I -c 'import ctypes,sys; ctypes.CDLL(sys.argv[1])' usr/lib/fcitx5/fcitx5-mozc.so
```

- **`mozc_server` converts:** `nihongo` gives the preedit `にほんご`, SPACE
  gives `日本語`, and ENTER commits `日本語`. That holds natively and as a
  POWER8 (baseline) or POWER9 (POWER9 pool) under qemu, and the server is
  still alive afterwards.
- **`mozc_tool`** is still running its about dialog after 45 s on the
  offscreen platform (exit 124 from `timeout`), natively and under qemu.
- **`fcitx5-mozc.so`** loads with `dlopen()` natively and under qemu.
- **Control:** the POWER9 pool's `mozc_server` and `mozc_tool`, run the same
  way as a POWER8 over the baseline sysroot, die with SIGILL (exit 132). So
  the qemu model does reject ISA 3.0, and the baseline's passes mean
  something.

## Traps

- **Arch's `pkgver()` discards bazel's output** (`>/dev/null 2>&1`). When it
  fails, rerun its `bazel build ... base:mozc_version_txt` line by hand in
  `src/mozc/src`, with the `_ppc64le_setup` arguments, to see why. On ppc64le
  the recipe stops there rather than versioning the package `...`. Both the
  local-registry patch failure and the python toolchain failure first showed up
  there.
- **rules_go asks go.dev for its SDK list** (`go.dev/dl/?mode=json`) during
  the first analysis, i.e. inside `pkgver()`. The offline rewrite refuses it,
  rules_go logs a warning and carries on, and nothing in the build needs Go.
  mozc's `MODULE.bazel` names rules_go only to pin the version that protobuf
  pulls in transitively.
- **bq caches the recipe** in `<buildroot>/_meta/fcitx5-mozc/` at the first
  `plan` and never refreshes it. After editing, `rm -rf` that directory in
  both buildroots, then plan again.
- **The `-mcpu` check needs a full build.** The execution log holds only
  spawns that ran, so an incremental rebuild in a kept `$srcdir` (`makepkg -e`)
  checks only what it recompiled. bq always builds from a fresh `$srcdir`.
- **Testing `mozc_server` under qemu-user.** mozc's own clients
  (`client/client.cc`) check `/proc/<server pid>/exe` against
  `/usr/lib/mozc/mozc_server` and refuse a server that does not match. Under
  qemu-user that path is the qemu binary. `verify-conversion.py` therefore
  speaks mozc's IPC directly from Python, which needs no such check.
- **mozc creates its profile directory non-recursively.** `mozc_server` and
  `mozc_tool` exit 255 without a word if `$XDG_CONFIG_HOME` (or
  `$HOME/.config`) does not exist. Their `LOG()` output goes to files in that
  directory, not to stderr.
