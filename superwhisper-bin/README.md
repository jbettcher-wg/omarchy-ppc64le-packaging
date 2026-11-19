# Superwhisper

Packages the vendor's signed portable x86_64 or aarch64 Linux archive under `/opt/superwhisper`, with a launcher, desktop entries, user service, fonts, icons and the fcitx5 text-commit addon. Local models are downloaded through Superwhisper's settings; they are not bundled in the package.

`sync-upstream` follows stable releases from `superultrainc/superwhisper-linux-releases` (`v1.0.0` and later); prereleases are ignored. The vendor version is kept in `_version`. The recipe verifies the archive's SHA256 and Minisign signature against the checked-in vendor release key. Packaging never runs the downloaded installer.

Omarchy's Setup → Defaults → Dictation → Superwhisper invokes `/usr/share/superwhisper/setup-user`, then configures its shortcuts and saves Superwhisper as the default backend. The package does not add Omarchy menu extensions and omits the portable installer’s menu-writing helper. User setup enables the packaged service, links the vendor's panel and agent skill, places a newly linked panel in the bar's tray section, and retires known portable-install wrappers and unit overrides with backups. Preferences, history and downloaded models are retained. Package updates come from OPR; the portable install's private update timer is disabled.

Omarchy loads the selected backend's generated `~/.config/superwhisper/shortcuts.lua` bridge itself, so no Superwhisper block is required in the user's Hyprland files. The bridge retains cancellation and correction-based vocabulary learning alongside Omarchy's shared dictation commands.

The launcher redirects the vendor’s generated Hyprland include to a private, unloaded file for both the daemon and CLI. User setup waits for daemon readiness. The portable updater is disabled and refused by the packaged launcher. The archive is verified before extraction, its version is checked, and the bundled panel uses explicit Omarchy palette references for Qt 6.12.

Fresh profiles start with Alt+Space toggle, no native hold, and Escape cancellation before the daemon starts, avoiding a conflict with Omarchy’s Right Alt binding. Existing preferences remain unchanged.

Panel discovery is asynchronous: user setup retries placement, leaves a pending marker if the shell is unavailable, and retries on the next setup without moving an already placed panel. Bundled component license notices are installed under `/usr/share/licenses/superwhisper-bin/`.

## ppc64le (Omarchy on POWER)

Everything above is upstream's. This section is ours, and so is everything in
the recipe that sits behind a `CARCH == powerpc64le` test or in a
`*_powerpc64le` array. x86_64 and aarch64 build exactly as upstream does.

Superwhisper is closed source and published for x86_64 and aarch64 only. POWER
installs the vendor's signed **aarch64** archive and runs it under POWERarm.
Every POWER install carries POWERarm, which builds each user's aarch64 guest
root (`ArchLinuxARM-vk`) at login. Verified on an AC922, 2026-11-18:

- the daemon, the transcription workers and the settings window run in the guest;
- Parakeet transcribes on the host GPU through the guest's RADV;
- recording uses the host's `pw-record`.

### What the recipe adds, and why

| piece | why |
|---|---|
| `source_powerpc64le` = the aarch64 archive | The same file and minisign signature as upstream's aarch64 build. |
| guest libraries (`guest.manifest`, the `guest-libs` block) | The vk guest root has a C runtime and a GPU stack, but not GTK4 (the recording pill and tray icon, `superwhisper-indicator`), fontconfig or xkbcommon (`superwhisper-settings`). Without GTK4 the daemon relaunches the indicator several times a second. The package carries these itself, in `/opt/superwhisper/powerarm/lib`, so it works whatever else a user's guest holds. Only the exact library files are taken, no data. |
| `superwhisper-powerarm` → `/usr/bin/superwhisper` | Exports `POWERARM_ROOTFS=ArchLinuxARM-vk` (the root this is tested in; a user's own default may be another), puts the native python3 first on `PATH` and the guest libraries on `LD_LIBRARY_PATH`, then runs upstream's launcher unchanged from `/opt/superwhisper/powerarm/superwhisper`. Native children such as `pw-record` and `wl-copy` are unaffected: the loader skips a library built for another machine. |
| `host-python3.c` | The helper scripts (media pause, the Omarchy indicator, deep links) run as `python3` from `PATH`. Under POWERarm that resolves through the guest first. A guest that holds its own python3 then runs them on an aarch64 interpreter, which cannot load the host's gi bindings, and media pause breaks. A native executable runs natively, so this shim hands the script to the host's Python. A symlink or `#!` script would be resolved back into the guest. |
| `superwhisper-powerarm.conf` (unit drop-in) | The service waits for `powerarm-rootfs.service`, which builds the guest root on a user's first login. |
| no fcitx5 addon | `lib/fcitx5/libsuperwhisper-fcitx5.so` is an aarch64 module for the host's native fcitx5, which cannot load it. Dictation is pasted instead, as it is without fcitx5. |

Not available under emulation: the fcitx5 direct commit (above), and **Muffle**
playback ducking. Muffle starts the host's native PipeWire with an aarch64
filter plugin. Use the **Pause** playback setting instead
(`superwhisper audio set defaultPlaybackBehavior '"pause"'`).

### The guest libraries are pinned twice

`guest-resolve.py` decides the set:

1. It walks `DT_NEEDED` from every vendor executable and library, plus the two
   libraries it loads with `dlopen` (`libgtk4-layer-shell.so.0` and
   `libhunspell-1.7.so.0`).
2. It maps each soname to its Arch Linux ARM package through the repo `.files`
   databases.
3. It follows only the file behind each soname, not the rest of its package.
4. It stops at the **floor**: packages the guest root provides and that must
   never be bundled.
   - glibc and the gcc runtime are the guest's loader and C++ ABI.
   - The GPU stack and POWERarm's thunked libraries (GL, EGL, Vulkan, drm,
     wayland-client, ALSA, xshmfence) are overlaid by path in `/usr/lib`.
     Bundled copies would bypass them.
5. It refuses a library that needs a newer glibc than the guest root's.

It writes two things from the same resolution:

- **`guest.manifest`**, in the format of POWERarm's
  `/usr/share/powerarm/rootfs/alarm_sysroot.py`, which fetches and verifies
  signatures, and publishes.
- **the `guest-libs` block in `PKGBUILD`**: package, sha256, and the members
  to take.

Arch Linux ARM mirrors keep only the current version of a package, so a pin
is reproducible only once its file is on POWERarm's snapshot,
`https://omappc64le.download/archrootfs/<repo>/<file>`. That is where
`source_powerpc64le` fetches from.

`build()` re-checks the closure against what it extracted, and fails if any
library the aarch64 build loads is in none of these: the vendor's `lib/`, the
guest libraries, or the floor. `prepare()` asserts that:

- `run.sh` still prepends its own `lib/` and runs `bin/superwhisper`;
- every vendor executable is aarch64.

### Bumping (a new vendor release, or a rebuild against newer guest libraries)

Run natively, on a POWER machine with `powerarm`, `minisign` and `rclone`
configured for the bucket:

```sh
cd superwhisper-bin
# 1. New vendor version: update pkgver/_version and the aarch64 sums as
#    upstream does. pkgrel stays above Omarchy's stable pkgrel. The
#    powerpc64le array repeats the aarch64 archive's two sums.
# 2. Re-resolve the guest libraries from today's repos:
./guest-resolve.py --vendor /path/to/superwhisper-omarchy-aarch64-<ver>.tar.zst
# 3. Fetch (verifies each package's signature) and publish the pins:
python3 /usr/share/powerarm/rootfs/alarm_sysroot.py fetch   --manifest guest.manifest
python3 /usr/share/powerarm/rootfs/alarm_sysroot.py publish --manifest guest.manifest --dry-run
python3 /usr/share/powerarm/rootfs/alarm_sysroot.py publish --manifest guest.manifest
# 4. Build in both pools, then verify as below.
```

If `build()` reports an uncovered library after a vendor bump, the release
needs something new. Rerun step 2. If the new library belongs in the floor (a
new thunk in POWERarm's `ThunksDB.json`), add it to `FLOOR` in
`guest-resolve.py` and to the `floor` regex in `_check_guest_closure`.

### Verifying a build

From the built package, with paths rewritten to the extracted tree, and run
against a fresh, empty guest overlay so nothing on the build machine hides a
gap:

- `superwhisper doctor` and `superwhisper status`. The daemon is ready, with
  `workers.asr.backend` `Vulkan0` once a model is downloaded.
- `superwhisper transcribe /opt/superwhisper/assets/self-check.wav` gives
  "Ask not what your country can do for you."
- A recording: `start`, speak, `stop`. The indicator pill shows, and the log
  has no `cannot open shared object file`.
- `superwhisper settings` opens the settings window.
