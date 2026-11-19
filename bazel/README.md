# `bazel`

Arch's recipe (`extra/bazel`, built from the release's dist zip with
`./compile.sh`), held at **9.0.2**, the release fcitx5-mozc pins, rather than
Arch's newest (9.3.2 when this was written). Until 9.0.2 this directory held
Arch POWER's 8.1.0 recipe unchanged.

Every ppc64le change sits under `if [[ $CARCH == powerpc64le ]]` (or in
`_ppc64le_setup`, which returns at once elsewhere), so the recipe still builds
x86_64 exactly as Arch does.

## Why 9.0.2, and who else depends on that

mozc's `src/.bazeliskrc` says `USE_BAZEL_VERSION=9.0.2`. On x86_64 bazelisk
downloads that release; there is no ppc64le download, so we build it.
`fcitx5-mozc`'s `prepare()` fails if its `_bazel_version`, the installed
`bazel --version` and `.bazeliskrc` disagree. A mozc bump that moves the pin
is therefore a bazel bump first.

## What the ppc64le changes are for

All of them are about bq's build environment, not about POWER. Arch builds in
a clean chroot whose only JDK is 21 and which may download freely; bq builds
over the host's `/usr`, with the host's default JDK and the user's `$HOME`.

- **`depends+=(jdk21-openjdk)`.** bq's `stage-deps` strips version
  constraints, so Arch's `java-environment=21` is satisfied by whatever JDK
  the host has. The bootstrap refuses anything older than 21 (`JDK version
  (...) is lower than 21, please set $JAVA_HOME`). Naming the package gets it
  staged. It sits in `depends`, not `makedepends`, so anything that
  makedepends on bazel (fcitx5-mozc) gets the same JDK staged with it.
- **`JAVA_HOME=/usr/lib/jvm/java-21-openjdk`** in `build()`.
  `scripts/bootstrap/buildenv.sh` otherwise takes it from
  `readlink -f $(which javac)`, which is the host's default JDK, not the staged
  one.
- **`-j`.** Bazel ignores `MAKEFLAGS` and takes every core. `build()` carries
  makepkg's `-jN` over as `--jobs=N --local_resources=cpu=N` in
  `EXTRA_BAZEL_ARGS`.
- **Completions without a second bazel build.** Arch runs
  `./output/bazel build scripts:bazel-complete.bash scripts:bazel.fish`.
  Both genrules take `//src:bazel` as a tool, the variant with an embedded
  JDK. The dist's `.bazelrc` sets `--java_runtime_version=remotejdk_25`, so
  that build downloads a JDK and runs it, and it fetches bazel's whole
  dependency graph from the network, because nothing points it at the dist's
  `derived/repository_cache`. On ppc64le, `build()` runs the two genrules' own
  commands from `scripts/BUILD` against the bazel it just bootstrapped:
  `output/bazel --batch help completion bash`, and
  `scripts/generate_fish_completion.py --bazel=output/bazel`, with the dist's
  vendored absl on `PYTHONPATH`. The output lands in `bazel-bin/scripts/`,
  where `package()` expects it. Arch POWER's 8.1.0 had commented the bash
  completion out and shipped neither.
- **`--output_user_root` beside `$srcdir`.** Otherwise the completion step and
  `bazel shutdown` extract an install base into `~/.cache/bazel`. Beside, not
  in: see the first trap.
- **The `bazel-9.x-linux-*` symlink.** `scripts/packages/bazel.sh`, installed
  as `/usr/bin/bazel`, looks for `bazel-<version>-linux-$(uname -m)`. Arch
  names the link after `$CARCH`, which matches `uname -m` on x86_64. On
  ppc64le `uname -m` says `ppc64le` and `CARCH` says `powerpc64le`, so the
  link is named `bazel-9.x-linux-ppc64le`.
- **Asserts in `build()`,** because bq runs makepkg with `--nocheck`:
  `output/bazel --version` is `bazel $pkgver`, its server reports
  `Build label: $pkgver`, and both completions are non-empty.

## Running it

`bazel-real` is the dist build, which has no embedded JDK. Its server runs on
`$JAVA_HOME`, or else on the default `java`. That is Arch's behaviour too.
On a host whose default JDK is older than 21 (`archlinux-java status`), set
`JAVA_HOME=/usr/lib/jvm/java-21-openjdk`, or make 21 or newer the default.

## Bump procedure

1. Read the new release from mozc: `USE_BAZEL_VERSION` in `src/.bazeliskrc`
   at fcitx5-mozc's `_mozc_commit`. `fcitx5-mozc/ppc64le-pins.py <commit>`
   prints it.
2. Compare with Arch's current recipe for anything new to carry:
   `git clone --depth 1 https://gitlab.archlinux.org/archlinux/packaging/packages/bazel.git`
   into a scratch directory under `/var/tmp`, and diff it against this one.
3. Set `pkgver`, reset `pkgrel` to `1.1`, and refresh the checksum natively:
   `SRCDEST=/var/tmp/omarchy-bq-kzstd/srcdest updpkgsums`. Check the signature
   by hand, since bq builds with `--skippgpcheck`:
   `gpg --homedir <scratch> --import keys/pgp/*.asc` and then
   `gpg --homedir <scratch> --verify bazel-<ver>-dist.zip.sig bazel-<ver>-dist.zip`.
4. Build both pools. bq skips a pkgbase it has built before (state `ok`)
   until it is given `--rebuild`:

   ```sh
   cd ~/Development/omarchy-ppc64le
   BQ_BUILDROOT=/var/tmp/omarchy-bq-ppc64le-kzstd BQ_STATE=/var/tmp/omarchy-bq-ppc64le-kzstd/state.json \
     tools/build-ppc64le.sh plan bazel
   BQ_BUILDROOT=/var/tmp/omarchy-bq-ppc64le-kzstd BQ_STATE=/var/tmp/omarchy-bq-ppc64le-kzstd/state.json \
     tools/build-ppc64le.sh build -j1 --make-jobs 84 --rebuild
   B=/var/tmp/omarchy-bq-kzstd
   BQ_STATE=$B/state.json python3 tools/bq.py --buildroot $B plan bazel -o $B/queue-bazel.json
   BQ_STATE=$B/state.json python3 tools/bq.py --buildroot $B build -q $B/queue-bazel.json -j1 --make-jobs 84 --rebuild
   ```

   Read bq's `-> packaging bazel <version>` line before letting it run.
5. Verify as below, publish both pools, then build fcitx5-mozc against it.

## Codegen

`compile.sh` builds bazel's C++ (the client, the JNI library, the sandbox and
process tools) with bazel's own autoconfigured toolchain, and makepkg's
`CFLAGS` never reach it. GCC's default `-mcpu` decides, so both pools get
the same code: the two packages scan identically, ISA 3.0 and control counts
alike, and that code is POWER8-legal.

## Verification

All `[MEASURED]`, 2026-11-18, `bazel-9.0.2-1.1` from both lanes (baseline
39,577,618 bytes, POWER9 39,576,780).

- **Package.** `zstd -t` clean; `elf-pathguard: clean`. `~/.cache/bazel`
  did not exist before either build or after it.
- **ISA 3.0.** `tools/isa30-pkgscan.sh` reports 9 in each pool, all in
  `usr/bin/bazel-real`, against 24,227 ISA 2.07 instructions in the same
  binary as the control. `/var/tmp/isa30-where.sh` places 8 `xscpsgnqp
  v31,v31,v31` in `grpc_core::Server::AddData` and 1 `xsiexpqp v31,v31,v30` in
  `grpc_core::HuffDecoder<...>::Run`. Each sits right after
  `lwax`/`add`/`mtctr`/`bctr`, among `.long` offsets: switch tables, i.e. data.
  Real ISA 3.0: none.
- **The native code inside `bazel-real`,** which `isa30-pkgscan` cannot see:
  `bazel-real` is an ELF with a zip appended, and `unzip` extracts its install
  base (322 files). `daemonize`, `linux-sandbox`, `process-wrapper`,
  `libcpu_profiler.so`, `zipper`, `aggregate-ddi` and `generate-modmap` scan
  0. So do `libunix_jni.so` and `libzstd-jni.so` inside `A-server.jar`
  (controls 547 and 3,068).
- **Zeroed pages** (`/var/tmp/blender53-work/zeropage.py` over every ELF
  above): none.
- **Runs.** `bazel-real --version` prints `bazel 9.0.2` natively, under
  `qemu-ppc64le -cpu power8 -L <baseline sysroot>` for the baseline package,
  and under `-cpu power9 -L <POWER9 sysroot>` for the POWER9 one.
  `--batch version` on JDK 21 reports `Build label: 9.0.2`. The same command
  with `JAVA_HOME` pointing at a shim that runs JDK 21's `java` under
  `qemu-ppc64le -cpu power8` also reports `Build label: 9.0.2`, in 66 s. That
  run had bazel's own client start its server, with `libunix_jni.so` loaded,
  inside a POWER8 model.
- **The wrapper.** In a workspace whose `.bazelversion` says `9.x`,
  `/usr/bin/bazel --version` runs `bazel-real` through
  `bazel-9.x-linux-ppc64le`. `9.0.2` also resolves, by `bazel-real`'s own
  version. `8.6.0` gets the wrapper's `requires Bazel 8.6.0 ... wasn't found`.
  The package carries bash, fish and zsh completions (556 KB, 1.9 MB, 10 KB).
- **Default JDK too old.** Without `JAVA_HOME` on a host whose default is 17:
  `Error: LinkageError occurred while loading main class
  com.google.devtools.build.lib.bazel.Bazel`.
- **End to end.** fcitx5-mozc 3.35.6354.2-1.1 builds with this bazel in both
  pools: 2766 actions each, offline, in `linux-sandbox` inside bq's bwrap.

## Traps

- **`$srcdir` is bazel's own workspace.** The first 9.0.2 build put
  `--output_user_root` under `$srcdir` and the version assert failed with
  `The repo contents cache [...] is inside the main repo [...]`. The root
  now sits beside `$srcdir`. fcitx5-mozc's can stay in its `$srcdir`,
  because its workspace is `$srcdir/mozc/src`.
- **A harmless ERROR in the bootstrap.** After `Build completed
  successfully`, compile.sh prints
  `ERROR: ... no such target '@@bazel_tools//tools:host_platform'`. That is
  `get_bazel_bin_path`, i.e. `bazel info bazel-bin || echo bazel-bin`,
  falling back as designed. `Build successful! Binary is here: ...` follows,
  and the build carries on.
- **bq caches the recipe.** bq materialises the PKGBUILD into
  `<buildroot>/_meta/bazel/` at the first `plan` and never refreshes it. After
  editing the recipe, `rm -rf <buildroot>/_meta/bazel` in both buildroots, then
  plan again.
- **Two JDKs get staged.** `stage-deps` resolves the bare `java-environment`
  to the first provider in our pool, `jdk25-openjdk`, and stages
  `jdk21-openjdk` from Arch POWER for the named dependency. `JAVA_HOME`
  decides which one runs, so the extra one does no harm.
