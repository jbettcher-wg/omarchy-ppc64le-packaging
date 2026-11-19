# `ghidra`

Arch's recipe, ported to ppc64le. One patch carries the port; the toolchain
is the same as x86's.

## The x86 toolchain: JDK 25 and the system Gradle

Ghidra 12.2 needs JDK >= 25 and Gradle >= 9.1 (`Ghidra/application.properties`).
Arch x86 builds it with `java-environment=25` and its `gradle` 9.9, and so do
we. Arch POWER has neither, so both are ours: `java/java25-openjdk` (booted from
JDK 26) and `java/gradle` 9.9.0. 12.2-1.1 had pinned `gradle-9.9.1-bin.zip` and
built on JDK 26 instead; 12.2-1.2 retired both.

`build()` checks that the `gradle` it runs is 9.1 or newer and runs on JDK 25,
and passes `--no-daemon` to every call. A Gradle daemon outlives makepkg and
keeps the `/usr` of the sandbox that started it. The next build would reuse it,
for example the other pool's ghidra, and compile against the wrong pool's
toolchain.

The package depends on `java-environment>=25`, as on x86, so Ghidra runs on the
system's default JDK. To run it on 25 while 26 is the default, set
`JAVA_HOME_OVERRIDE` in `/opt/ghidra/support/launch.properties`, or
`archlinux-java set java-25-openjdk`.

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

## Checksums

Every source is pinned, as in Arch's current recipe, including the
`ghidra-data` git tag. A SourceForge download of `yajsw-stable-13.18.zip` once
came back 229,376 bytes too long, and Gradle then stopped at `Cannot expand
ZIP` in `:GhidraServer:yajswDevUnpack`; the pinned sha512 is the file that
matches the sha256 Ghidra itself expects (`50b34e98…` in
`gradle/support/fetchDependencies.gradle`).
