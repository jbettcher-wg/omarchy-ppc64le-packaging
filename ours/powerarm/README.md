# `powerarm`

POWERarm, the AArch64 emulator for ppc64le, packaged: binaries in `/usr`, the
binfmt_misc handler registered correctly, and nothing else pretending to be
configured.

It is the compatibility layer this distribution leans on. A growing share of
desktop software ships an arm64 build and no ppc64le one — the Claude Code CLI
is a Bun single binary for x64/arm64 only, VS Code is arm64 Electron — and
POWERarm is how those run here. AArch64 rather than x86 on purpose: AArch64 is
weakly ordered like POWER, so guest fences lower only where the guest asked for
them, where x86's TSO costs a barrier on nearly every access. `fastppcx86`
covers x86 at that price. The two install side by side; they claim different
ELF machine types and their binfmt entries have different names.

The recipe builds `main` from
[`jbettcher-wg/POWERarm`](https://github.com/jbettcher-wg/POWERarm).

## What gets installed

| Where | What |
|---|---|
| `/usr/bin/POWERarm` | the loader/interpreter. This is the binfmt interpreter, and the path the registration names |
| `/usr/bin/POWERarmInterpreter` | symlink to `POWERarm` (upstream installs a second full copy; see below) |
| `/usr/bin/POWERarm{Server,Bash,Config,GetConfig,OfflineCompiler,pidof}` | the server, a bash under emulation, the Qt6 settings GUI, the config dumper, the AOT compiler, a guest-aware `pidof` |
| `/usr/bin/POWERarmRootFSFetcher` | inherited from FEX. **Do not use it** — see "Getting a rootfs" |
| `/usr/lib/libPOWERarmCore.so` + `/usr/include/FEXCore/` | the core as a shared library and its headers. Nothing in this package links them (the tools link FEXCore statically); they are there for anything that wants to embed the core |
| `/usr/lib/gdb/libPOWERarmGDBReader.so` | the GDB JIT reader, so gdb can name frames in generated code |
| `/usr/lib/binfmt.d/POWERarm-aarch64.conf` | the AArch64 ELF registration. The whole point of the package |
| `/usr/share/powerarm/Config.json` | system-wide defaults; the lowest config layer, overridden by `~/.config/powerarm/Config.json` |
| `/usr/share/powerarm/ThunksDB.json` | the thunk database. Inert here: this build has no thunks |
| `/usr/share/powerarm/rootfs/` | the rootfs builder — `build-alarm-sysroot.sh`, `alarm_sysroot.py`, the pin manifests, the OCI extractor, the native runner, and their README |
| `/usr/share/powerarm/check-binfmt-inode.sh` | asks a running guest process which emulator it is really in |
| `/usr/share/man/man1/POWERarm.1.gz`, `/usr/share/doc/powerarm/` | the man page; `README.md`, `ENV_REFERENCE.md`, `DEPENDENCIES.md` |

`thunkgen` is a build tool and the build system already declines to install it;
nothing was needed to keep it out. `POWERarmInterpreter` is a second,
byte-identical 3.9 MB copy of `POWERarm` as the build installs it, and
`package()` replaces it with a symlink — safe here precisely because the binfmt
entry names `/usr/bin/POWERarm` directly and nothing resolves the emulator
through the legacy name any more.

## binfmt_misc, and why an upgrade has to re-register

The registration is

```
:POWERarm-aarch64:M:0:\x7fELF\x02\x01...\xb7\x00:\xff\xff...\xff:/usr/bin/POWERarm:POCF
```

`POCF` — preserve argv[0], open the binary, credentials from the script, fix
binary. **`F` is the one that matters.** It makes the kernel open the
interpreter *at registration time* and hold that inode for the life of the
entry. It is what lets the registration keep working inside mount namespaces
and after a chroot, and it is also a trap with no visible edges:

* The entry keeps printing the path string it was registered with, and the
  kernel passes that same string as `argv[0]`. Neither
  `/proc/sys/fs/binfmt_misc/POWERarm-aarch64`, nor `ps`, nor the process's own
  argv shows which binary is executing.
* A package upgrade writes a **new inode** at `/usr/bin/POWERarm`. The old one
  is unlinked but still open, so it stays alive and keeps handling every
  aarch64 exec on the machine. Somebody upgrades to get a fix, does not get the
  fix, and has nothing to look at.

So `powerarm.install` restarts `systemd-binfmt.service` on `post_install`,
`post_upgrade` **and** `post_remove`. Two details that are easy to get wrong:

* `restart`, never `start`. The unit's `ExecStop` is
  `systemd-binfmt --unregister`, and only that teardown drops the pinned inode.
  A bare `ExecStart` finds an entry of that name already registered, takes
  `EEXIST` from the kernel, logs a warning, and leaves the stale one in place —
  the exact outcome this is meant to prevent.
* There is no ALPM hook for `usr/lib/binfmt.d` on Arch POWER. Nothing in
  `/usr/share/libalpm/hooks` matches it. The scriptlet is not redundant with a
  distro hook; it is the only thing doing this.

Guests that were already running keep the old emulator until they exit. That is
the pinned inode behaving as designed, not a bug; restart them to pick up the
new build.

To check rather than assume — and this is the only way to check, because the
registration lies by construction:

```sh
bash /usr/share/powerarm/check-binfmt-inode.sh
```

It starts a real aarch64 process through binfmt and reads the emulator's mapped
path out of `/proc/<pid>/maps`.

## Getting a rootfs

**The package does not ship one, and until you have one nothing useful runs.**

POWERarm resolves guest absolute paths inside an AArch64 root filesystem. With
no rootfs — or with a configured rootfs *name* that does not resolve — the
lookup falls back to `AT_FDCWD`, the host tree, without a word. The guest then
opens the host's ppc64le loader and dies confusingly. That silence is the
reason the post-install message exists and the reason this section is here.

Build one. No root needed:

```sh
/usr/share/powerarm/rootfs/build-alarm-sysroot.sh
```

It downloads pinned Arch Linux ARM packages, verifies every sha256 against the
manifest and every signature against the pinned Arch Linux ARM Build System key
(`68B3537F39A313B3E574D06777193F152BDBE6A6`, imported into a throwaway
`GNUPGHOME`), and extracts them with Python's `tarfile` rather than the host
`tar`, so the result does not depend on the machine. It prints a content hash
you can compare against another machine's.

What it needs, and what to line up before a fresh-machine test:

| | |
|---|---|
| network | `mirror.archlinuxarm.org` over HTTP |
| disk | ~120 MB downloaded into `~/.cache/powerarm/alarm-pkgs`, ~600 MB extracted into `~/.local/share/powerarm/RootFS/ArchLinuxARM-m2` |
| tools | `python` (stdlib only), `gpg` and `gpgv`, `zstd` |
| config | none. The shipped `/usr/share/powerarm/Config.json` already names `ArchLinuxARM-m2`, which is the script's default `--dest` |

The result is the M2 toolchain closure — 90 packages, GCC 16.1.1, binutils,
glibc, bash, coreutils and the usual shell tools — which is enough to run
programs and to build them. `alarm-vk.manifest` is the same plus Vulkan and
RADV; pass `--manifest`. A writable `<rootfs>-overlay` next to the base turns on
guest `pacman`; `/usr/share/powerarm/rootfs/README.md` has that procedure.

Every ELF in the tree is 64K-aligned, so one image serves both 4K and 64K page
hosts.

### Not `POWERarmRootFSFetcher`, and not `mkrootfs.sh`

`POWERarmRootFSFetcher` is installed because the build installs it, but it is
FEX's fetcher with the names swapped: it still downloads from
`rootfs.fex-emu.gg`, which serves **x86_64 and i386** images for FEX. Running it
gets you an Ubuntu x86_64 squashfs in `~/.local/share/powerarm/RootFS/`, and an
aarch64 guest pointed at that fails in ways that look like emulator bugs.

`packaging/rootfs/mkrootfs.sh` in the POWERarm tree is in the same state —
unmodified fastppcx86, building an x86_64 Arch rootfs from Arch's x86_64
bootstrap tarball — so this package does not install it. Fixing or retiring
both is upstream work in the POWERarm tree, not something a recipe should paper
over.

## If you also have a development install

The development workflow does not use this package. It is:

```sh
sh ~/Development/promote-powerarm-stable.sh      # build-powerarm -> ~/.local/opt/powerarm-stable
sudo sh ~/Development/register-powerarm-binfmt.sh
bash ~/Development/POWERarm/Scripts/powerarm/check-binfmt-inode.sh
```

`promote` exists *because* of the `F` flag: development rebuilds of
`build-powerarm` must not change the interpreter's inode, so the registration
points at a stable copy that only moves when you promote it — and a promote is
therefore always followed by a re-register. Exactly the same hazard this package
handles with a scriptlet, handled by hand.

The hand registration writes `/etc/binfmt.d/POWERarm-aarch64.conf`, **the same
filename** this package installs under `/usr/lib/binfmt.d`. That is not a clash
to fear; it is the drop-in mechanism working. `binfmt.d` is read with systemd's
usual precedence:

```
/etc  >  /run  >  /usr/local/lib  >  /usr/lib
```

and a file in `/etc` masks the same-named file in `/usr` **entirely**. So:

| You want | Do |
|---|---|
| the hand-promoted stable build to keep handling everything (the developer's default) | nothing. `/etc` already wins |
| the packaged emulator to take over | `sudo rm /etc/binfmt.d/POWERarm-aarch64.conf`, then `sudo systemctl restart systemd-binfmt.service` |
| neither — no aarch64 handler at all | `sudo ln -s /dev/null /etc/binfmt.d/POWERarm-aarch64.conf`, then restart the unit |

What you must not do is guess. With two emulators on the machine and an entry
that prints a path rather than the inode it opened, `check-binfmt-inode.sh` is
the only honest answer, and it is installed at
`/usr/share/powerarm/check-binfmt-inode.sh` for that reason.

Note also that `systemd-binfmt --unregister` clears *every* binfmt_misc entry
before `ExecStart` reinstates the ones that have files in a `binfmt.d`
directory. Anything registered by hand and not backed by a file — including a
`register-powerarm-binfmt.sh` run whose `/etc` file was later deleted —
disappears at the next restart of that unit and does not come back.

## Building

```sh
cd ours/powerarm
makepkg -s
```

Point it at a local checkout or another branch:

```sh
POWERARM_GIT_URL='file:///home/jbettcher/Development/POWERarm' \
POWERARM_GIT_BRANCH=powerarm makepkg -s
```

`main` is what ships; the local development branch is `powerarm` and tracks
`origin/main`.

On a shared machine, keep it polite — the build is a few thousand heavy C++
translation units:

```sh
taskset -c 0-15 nice -n 19 env MAKEFLAGS=-j8 makepkg -s
```

### What the recipe configures, and why

| Option | Value | Why |
|---|---|---|
| `CMAKE_INSTALL_PREFIX` | `/usr` | **at configure time, and it cannot be corrected later.** `Data/binfmts/CMakeLists.txt` installs to an absolute `${CMAKE_INSTALL_PREFIX}/lib/binfmt.d` — which `cmake --install --prefix` does not move — and bakes the interpreter path into the `.conf` with `configure_file()`. Configure with the wrong prefix and the package ships a binfmt entry naming `/usr/local/bin/POWERarm`, under `/usr/local/lib/binfmt.d`, where systemd will happily read it |
| `TUNE_CPU` | `none` | the upstream default is `native`, which appends `-march=native`. Built on the POWER9 AC922 that bakes ISA 3.0 into the emulator's own host code and the package SIGILLs on its first instruction on a POWER8 machine. `none` leaves the ISA floor to `/etc/makepkg.conf` (`-mcpu=power8 -mtune=power8`), which is the pool's baseline. This is about *host* code only: the JIT picks ISA 3.0 against ISA 2.07 sequences at run time from `CTX->HostFeatures.SupportsISA30`, so the code it emits for the guest adapts on its own (`POWERARM_HOSTFEATURES=disableisa30` forces the 2.07 paths) |
| `CMAKE_BUILD_TYPE` | `Release` | what the development build and every published measurement use |
| `CMAKE_C/CXX_COMPILER` | `clang`/`clang++` | GCC is rejected outright — `FATAL_ERROR` in `CMakeLists.txt:90` |
| `ENABLE_LTO` | `ON`, with `options=('!lto')` | the build drives LTO through `CMAKE_INTERPROCEDURAL_OPTIMIZATION`; makepkg's own `lto` would add a second, different `-flto` on top. One owner |
| `BUILD_TESTING` | `OFF` | no unit tests in a package; also why Catch2 and vixl are not fetched |
| `BUILD_THUNKS` | `OFF` | no host thunks yet. This is what keeps the dependency list short — see below |
| `BUILD_GUEST_THUNKS` | `OFF` | see below |
| `BUILD_FEXCONFIG` | `ON` | the Qt6 settings GUI |
| `ENABLE_JEMALLOC_GLIBC_ALLOC`, `ENABLE_FEX_ALLOCATOR` | `ON` | as in the validated build |
| `ENABLE_GDB_SYMBOLS` | `ON` | installs the JIT reader; needs `gdb` at build time for `jit-reader.h` |
| `OVERRIDE_VERSION` / `OVERRIDE_HASH` | from git | the commit hash is part of the JIT code-cache key, so it has to be accurate or a stale cache is served |

### Guest libraries are off, on purpose

`BUILD_GUEST_THUNKS=ON` would make the build depend on **the builder's home
directory**. `CMakeLists.txt` reads `~/.config/powerarm/Config.json` for a
`RootFS` name, requires an AArch64 rootfs with `gcc` and glibc headers, and then
compiles the guest library by running *that rootfs's gcc under the POWERarm it
has just built*. On a machine without a rootfs it prints a warning and turns
itself off — so the same recipe would produce two different packages depending
on who ran it, which is not a property a package may have.

The cost of leaving it off is `libVDSO-a64-guest.so`: without it no
`AT_SYSINFO_EHDR` is handed to the guest and guest libcs make real clock
syscalls instead of vDSO calls. Slower, correct. On a machine that has a rootfs,
opt in:

```sh
_guest_rootfs=~/.local/share/powerarm/RootFS/ArchLinuxARM-m2 makepkg -s
```

`package()` installs that library **by hand** rather than through the build's
own install rule, and that is not tidiness. The upstream rule is an
`install(CODE)` that re-runs `cmake --build --target install` inside
`build/Guest`, and that build drives the rootfs's `gcc` through the POWERarm
just built — which does not survive fakeroot's `LD_PRELOAD`. The
`execute_process()` carries no `RESULT_VARIABLE` and no
`COMMAND_ERROR_IS_FATAL`, so the failure is **silent**: makepkg prints
`-- Installing: guest-libs`, everything exits 0, and the package comes out
without the library while `build/Guest/libVDSO-a64-guest.so` sits on disk. That
was measured here, not guessed. The hand install uses the artefact `build()`
already produced and lets `install(1)` fail the build if it is missing.

Host thunks (`BUILD_THUNKS`) are a separate question and are off for a different
reason: they do not exist for the AArch64 guest yet. When they arrive, every
library behind an enabled thunk becomes a hard `depends` that namcap cannot
infer — `thunkgen` emits `fexldr_init_<lib>`, the target is reached with
`dlopen()`, nothing is `DT_NEEDED`, and a missing library makes the thunk fail
*silently* rather than fail. That list is currently absent from `depends`
because it would be a lie, not because it was forgotten.

## Validating

```sh
namcap PKGBUILD
namcap powerarm-*.pkg.tar.zst
pacman -Qlp powerarm-*.pkg.tar.zst
bsdtar -xOf powerarm-*.pkg.tar.zst .INSTALL | head -40
```

`check()` in the recipe is not a test suite — it makes one assertion, about the
single thing in this package that fails silently and invisibly: that the
generated binfmt entry names `/usr/bin/POWERarm` and still carries the `F` flag.

**Do not install this package on a machine whose aarch64 processes you are
currently using.** Installing it restarts `systemd-binfmt`, which unregisters
every existing entry — including a hand-made one pointing at a development
build — and re-registers from the `binfmt.d` files. On a workstation running
aarch64 VS Code, browsers or agent sessions through a hand-registered emulator,
that reaches straight into live processes' exec path. Test installs in a
container, a chroot, or a VM.
