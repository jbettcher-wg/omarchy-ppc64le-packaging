#!/usr/bin/env python3
"""Pin the aarch64 libraries superwhisper-bin carries for POWERarm.

Superwhisper's Linux build is x86_64 and aarch64 only. On ppc64le the aarch64
build runs under POWERarm, inside the per-user guest root POWERarm builds at
login (ArchLinuxARM-vk). That root holds a C runtime and a GPU stack, but not
GTK4 (the recording pill and tray icon), fontconfig or xkbcommon (the settings
window). The package carries those itself, so it works the same on every
machine no matter what else a user has installed into their guest.

This script works out exactly which Arch Linux ARM packages that takes. It
walks DT_NEEDED from the vendor's binaries, plus the libraries they dlopen,
maps each soname to its package with the repo .files databases, and stops at
the floor: packages that must come from the guest root and never from the
bundle. The floor is glibc and the gcc runtime (the guest's loader and C++ ABI)
and the libraries POWERarm overlays with thunks by path in /usr/lib, so a
bundled copy would bypass them (ThunksDB.json: GL, EGL, Vulkan, drm, wayland
client, ALSA, xshmfence).

It writes guest.manifest in the format of POWERarm's alarm_sysroot.py, so that
tool fetches and verifies the pins and publishes them to POWERarm's snapshot
(omappc64le.download/archrootfs) -- Arch Linux ARM keeps only the current
version of each package, so a pin is only reproducible once it is there. It
then rewrites the generated block in PKGBUILD.

Usage (see README.md, "Bumping"):
  guest-resolve.py --vendor superwhisper-omarchy-aarch64-<ver>.tar.zst
"""
import argparse, collections, email.utils, hashlib, io, os, re, subprocess, sys, tarfile
import tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MIRROR = "http://mirror.archlinuxarm.org/aarch64"
REPOS = ("core", "extra")
BASE_MANIFEST = "/usr/share/powerarm/rootfs/alarm-vk.manifest"

# Loaded at run time, so no DT_NEEDED names them. Each is checked to exist.
DLOPEN_ROOTS = (
    "libgtk4-layer-shell.so.0",  # superwhisper-indicator: the recording pill (gtk_layer_*)
    "libhunspell-1.7.so.0",      # superwhisper: spelling-based vocabulary correction
)
# Shipped in the vendor bundle itself.
VENDOR_SONAMES = ("libonnxruntime.so.1", "libsuperwhisper_muffle.so")
# Vendor objects that cannot run under POWERarm and are not installed on ppc64le:
# the fcitx5 addon is loaded by the host's native fcitx5.
VENDOR_SKIP = re.compile(r"/lib/fcitx5/")
# Never bundled. Each must be in the guest root (checked against BASE_MANIFEST).
FLOOR = (
    "glibc", "gcc-libs", "libgcc", "libstdc++", "libgomp", "libatomic",  # loader and C/C++ ABI
    "vulkan-icd-loader", "libglvnd", "mesa", "libdrm", "wayland",        # thunked or GPU-bound
    "libxshmfence", "alsa-lib",
)
FLOOR_OPTIONAL = {"alsa-lib"}    # thunked when present; nothing here needs it


def die(msg):
    sys.exit(f"guest-resolve: {msg}")


def fetch(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "guest-resolve"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest + ".part", "wb") as f:
        lm = r.headers.get("Last-Modified", "-")
        while chunk := r.read(1 << 20):
            f.write(chunk)
    os.replace(dest + ".part", dest)
    return lm


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def parse_db(path, repo, want_files):
    """{name: entry}; with want_files, entry['files'] lists usr/lib/*.so* paths."""
    fields = collections.defaultdict(dict)
    with tarfile.open(path, "r:*") as tf:
        for mem in tf:
            if not mem.isfile():
                continue
            d = mem.name.split("/")[0]
            key = None
            for line in tf.extractfile(mem).read().decode().split("\n"):
                if line.startswith("%") and line.endswith("%"):
                    key = line[1:-1]
                    fields[d].setdefault(key, [])
                elif line and key:
                    fields[d][key].append(line)
    out = {}
    for f in fields.values():
        if not f.get("NAME") or not f.get("SHA256SUM"):
            continue
        e = dict(name=f["NAME"][0], version=f["VERSION"][0], filename=f["FILENAME"][0],
                 sha256=f["SHA256SUM"][0], csize=int(f["CSIZE"][0]),
                 isize=int(f.get("ISIZE", ["0"])[0]), repo=repo)
        if want_files:
            e["files"] = [p for p in f.get("FILES", []) if re.match(r"usr/lib/[^/]+\.so", p)]
        out[e["name"]] = e
    return out


def elf_needed(path):
    r = subprocess.run(["readelf", "-dW", path], capture_output=True, text=True)
    return re.findall(r"\(NEEDED\)\s+Shared library: \[(.+?)\]", r.stdout)


def elf_glibc_max(path):
    r = subprocess.run(["readelf", "-VW", path], capture_output=True, text=True)
    vs = [tuple(map(int, v.split("."))) for v in re.findall(r"Name: GLIBC_(\d+\.\d+(?:\.\d+)?)", r.stdout)]
    return max(vs, default=(0,))


def is_elf(path):
    with open(path, "rb") as f:
        return f.read(4) == b"\x7fELF"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vendor", required=True, help="the vendor's aarch64 .tar.zst, or its extracted app/ dir")
    ap.add_argument("--cache", default=os.path.expanduser("~/.cache/powerarm/alarm-pkgs"),
                    help="package cache, shared with alarm_sysroot.py (default: %(default)s)")
    ap.add_argument("--base-manifest", default=BASE_MANIFEST)
    ap.add_argument("--manifest", default=os.path.join(HERE, "guest.manifest"))
    ap.add_argument("--pkgbuild", default=os.path.join(HERE, "PKGBUILD"))
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)

    # 1. The vendor's ELF objects and what they need.
    work = tempfile.mkdtemp(prefix="guest-resolve.")
    app = a.vendor
    if os.path.isfile(app):
        subprocess.run(["bsdtar", "-xf", app, "-C", work], check=True)
        hits = [os.path.join(r, "app") for r, ds, _ in os.walk(work) if "app" in ds]
        app = hits[0] if hits else die("no app/ directory in the vendor archive")
    roots = set(DLOPEN_ROOTS)
    for sub in ("bin", "lib"):
        for r, _, fs in os.walk(os.path.join(app, sub)):
            for f in fs:
                p = os.path.join(r, f)
                if VENDOR_SKIP.search(p) or os.path.islink(p) or not is_elf(p):
                    continue
                roots.update(elf_needed(p))
    roots -= set(VENDOR_SONAMES)

    # 2. Today's repo databases, and the soname -> package map.
    dbs = []
    byname = {}
    soname_pkg = {}
    for repo in REPOS:
        dbp = os.path.join(a.cache, f"{repo}.db")
        lm = fetch(f"{MIRROR}/{repo}/{repo}.db", dbp).replace(" ", "_")
        dbs.append((repo, sha256(dbp), lm))
        fp = os.path.join(a.cache, f"{repo}.files")
        fetch(f"{MIRROR}/{repo}/{repo}.files", fp)
        for name, e in parse_db(fp, repo, True).items():
            byname.setdefault(name, e)
            for p in e["files"]:
                soname_pkg.setdefault(os.path.basename(p), name)
    keyring = byname.get("archlinuxarm-keyring") or die("archlinuxarm-keyring not in the repos")

    # 3. The floor must be in the guest root this runs on.
    base_pkgs = {}
    with open(a.base_manifest) as f:
        for line in f:
            t = line.split()
            if t[:1] == ["pkg"]:
                base_pkgs[t[1]] = t[2]
    for p in FLOOR:
        if p not in base_pkgs and p not in FLOOR_OPTIONAL:
            die(f"floor package {p} is not in {a.base_manifest}")
    floor_sonames = {os.path.basename(f) for p in FLOOR if p in byname for f in byname[p]["files"]}
    base_glibc = tuple(map(int, re.match(r"(\d+)\.(\d+)", base_pkgs["glibc"]).groups()))

    # 4. Close over DT_NEEDED, one soname at a time: only the file behind each
    #    needed soname is taken and followed, never the rest of its package
    #    (gst-plugins-bad-libs ships thirty libraries; one may be needed).
    selected = {}
    members = collections.defaultdict(set)   # package -> usr/lib members to install
    queue = sorted(roots)
    seen = set()
    while queue:
        so = queue.pop(0)
        if so in seen:
            continue
        seen.add(so)
        if so in floor_sonames:
            continue
        name = soname_pkg.get(so) or die(f"no package provides {so}")
        if name in FLOOR:
            continue
        e = byname[name]
        path = os.path.join(a.cache, e["filename"])
        if not (os.path.exists(path) and sha256(path) == e["sha256"]):
            fetch(f"{MIRROR}/{e['repo']}/{e['filename']}", path)
            if sha256(path) != e["sha256"]:
                die(f"{e['filename']}: sha256 does not match the {e['repo']} database")
        if name not in selected:
            selected[name] = e
            print(f"  {name} {e['version']}  (for {so})")
        with tarfile.open(path, "r:*") as tf:
            mems = {m.name: m for m in tf.getmembers()}
            rel = f"usr/lib/{so}"
            while rel in mems and mems[rel].issym():      # libfoo.so.1 -> libfoo.so.1.2.3
                members[name].add(rel)
                rel = os.path.normpath(os.path.join(os.path.dirname(rel), mems[rel].linkname))
            if rel not in mems or not mems[rel].isfile():
                die(f"{name}: {so} does not resolve to a file in the package")
            members[name].add(rel)
            tmp = os.path.join(work, "obj")
            with open(tmp, "wb") as f:
                f.write(tf.extractfile(mems[rel]).read())
        g = elf_glibc_max(tmp)
        if g[:2] > base_glibc:
            die(f"{rel} in {name} needs GLIBC_{'.'.join(map(str, g))}, the guest root has {base_pkgs['glibc']}")
        queue.extend(n for n in elf_needed(tmp) if n not in seen)

    # 5. guest.manifest, in alarm_sysroot.py's format.
    def pl(k, d):
        return f"{k} {d['name']} {d['version']} {d['repo']} {d['filename']} {d['sha256']} {d['csize']} {d['isize']}"
    fpr = next((l.split()[1] for l in open(a.base_manifest) if l.startswith("keyring-fingerprint ")), None)
    lines = [
        "# superwhisper-bin: aarch64 libraries carried for POWERarm. Generated by guest-resolve.py;",
        "# do not edit. Fetch and publish with POWERarm's alarm_sysroot.py (see README.md).",
        "format 1", "arch aarch64", f"mirror {MIRROR}",
    ] + ([f"keyring-fingerprint {fpr}"] if fpr else []) + [
        f"db {r} {s} {lm}" for r, s, lm in dbs
    ] + [pl("keyring", keyring)] + [pl("pkg", selected[n]) for n in sorted(selected)]
    with open(a.manifest, "w") as f:
        f.write("\n".join(lines) + "\n")

    # 6. The generated block in PKGBUILD.
    block = ["# BEGIN guest-libs: generated by guest-resolve.py from guest.manifest; do not edit",
             "_guest_pkgs=("]
    block += [f"  '{selected[n]['repo']}/{selected[n]['filename']}'" for n in sorted(selected)]
    block += [")", "_guest_sha256=("]
    block += [f"  '{selected[n]['sha256']}'" for n in sorted(selected)]
    block += [")", "# The usr/lib members taken from each package, in the same order.", "_guest_libs=("]
    block += [f"  '{' '.join(sorted(os.path.basename(p) for p in members[n]))}'" for n in sorted(selected)]
    block += [")", "# END guest-libs"]
    src = open(a.pkgbuild).read()
    new, n = re.subn(r"# BEGIN guest-libs.*?# END guest-libs", "\n".join(block), src, flags=re.S)
    if n != 1:
        die("PKGBUILD has no '# BEGIN guest-libs' ... '# END guest-libs' block")
    with open(a.pkgbuild, "w") as f:
        f.write(new)
    csize = sum(e["csize"] for e in selected.values())
    nfiles = sum(len(v) for v in members.values())
    print(f"{len(selected)} packages, {csize/1e6:.1f} MB download, {nfiles} usr/lib members "
          f"installed; wrote {a.manifest} and the PKGBUILD block")


if __name__ == "__main__":
    main()
