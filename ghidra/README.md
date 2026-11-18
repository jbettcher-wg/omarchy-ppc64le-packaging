# `ghidra`

Arch's recipe, ported to ppc64le. Two changes carry the port.

## Gradle 9.9.1 is pinned as a source

Ghidra 12.2 needs JDK >= 25 and Gradle >= 9.1 (`Ghidra/application.properties`).
Arch POWER has no JDK 25, only 26, and its `gradle` is 8.14.2. Gradle 8.14.2
cannot run on JDK 26 and fails with `Unsupported class file major version 70`.
Gradle can run on JDK 26 from 9.4.0, so the official `gradle-9.9.1-bin.zip` is a
pinned source, and `build()` runs its `bin/gradle`. The system `gradle` is not
a makedepend.

Each call passes `--no-daemon`. A Gradle daemon outlives makepkg and keeps the
`/usr` of the sandbox that started it. The next build would reuse it, for
example the other pool's ghidra, and compile against the wrong pool's
toolchain.

Packaging Gradle 9 properly, as `java/gradle` built from source, is the
follow-up that would retire the zip.

## `ghidra-linux-ppc64le.patch`

Upstream knows only x86 and arm64. The patch adds `linux_ppc64le` in the places
below.

- **Build.** In `GPL/nativePlatforms.gradle`, add the platform entry and map
  `os.arch=ppc64le` to it. Without that mapping, `getCurrentPlatformName`
  throws `Unrecognized platform architecture`. Also add `targetPlatform` to
  each native component: decompile and sleigh, both GNU demanglers, lzfse, and
  gdis.
  - Gradle names the architecture `ppc64le`. `DefaultNativePlatform`
    passes `os.arch` through unchanged when it does not recognise the name, so
    the platform entry uses `arch: "ppc64le"`. The build log confirms it:
    `getCurrentPlatformName` prints `Arch: ppc64le` with no `(gradle: ...)`
    suffix, and that suffix appears only when the two names differ.
- **Only the current platform on ppc64le.** GCC on ppc64le accepts `-m64`,
  so Gradle's built-in Intel64 target configuration claims it can build
  `linux_x86_64` too. `buildGhidra`'s `assemble` then filled
  `os/linux_x86_64/` with ppc64le binaries. The patch adds a rule in
  `GPL/nativeBuildProperties.gradle` that sets `buildable = false` for every
  other platform when the host is `linux_ppc64le`. `_assert_dist` fails the
  build if any ELF appears in a foreign `os/` directory.
- **protoc.** `gradle/hasProtobuf.gradle` gave every non-x86 Linux the aarch64
  `protoc`. It now uses Maven Central's `linux-ppcle_64` build.
- **Runtime.** `Architecture`/`Platform` gain `POWERPC_64_LE` and
  `LINUX_PPC64LE`. Without them `Platform.CURRENT_PLATFORM` is `UNSUPPORTED` on
  ppc64le, and Ghidra cannot find `os/linux_ppc64le/decompile` or any other
  native.

## Baseline ISA

Gradle's native C/C++ build ignores `CFLAGS`, so the natives get the compiler's
default `-mcpu`. That default is POWER8 for the pool gcc in both lanes. When
`_power8_compat` is set, `build()` asserts that `gcc` and `g++` do not define
`_ARCH_PWR9`.

`_assert_dist` runs at the end of `build()`, because bq builds with
`--nocheck`. It checks that the distribution carries all five natives as
PowerPC64 ELF, that none of them was linked by LLD, and that the
SymbolicSummaryZ3 extension carries `libz3.so` and `libz3java.so`.

The Z3 libraries are copied from the build's own staged `z3`/`z3-java`, which
are ours (`packaging/z3`). Land z3 in a pool before building ghidra there.

## yajsw is pinned

Arch's recipe has `SKIP` for `yajsw-stable-13.18.zip`. A SourceForge download
here came back 229,376 bytes too long and failed every checksum. Gradle then
stopped at `Cannot expand ZIP` in `:GhidraServer:yajswDevUnpack`. The recipe
now pins the sha512 of the file that matches the sha256 Ghidra itself expects
(`50b34e98…` in `gradle/support/fetchDependencies.gradle`).
