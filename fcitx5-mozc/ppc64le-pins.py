#!/usr/bin/env python3
"""The ppc64le pins in fcitx5-mozc's PKGBUILD, read from the sources that set them.

  ppc64le-pins.py <mozc commit>
      Fetch what that commit pins and print the PKGBUILD block for it.
  ppc64le-pins.py --check <srcdir> _bazel_version=X _protobuf_version=X ...
      prepare()'s assert: read the same files from makepkg's srcdir, offline,
      and fail on any pin that disagrees with them.

  _bazel_version     USE_BAZEL_VERSION in mozc's src/.bazeliskrc
  _protobuf_version  the protobuf bazel_dep in mozc's src/MODULE.bazel
  _pbs_python        rules_python's MINOR_MAPPING for its python.defaults()
  _pbs_release       the python-build-standalone release that version's entry
                     in rules_python's python/versions.bzl names
"""
import hashlib, os, re, sys, tarfile, urllib.request

PLATFORM = "ppc64le-unknown-linux-gnu"
RULES_PYTHON = "https://github.com/bazel-contrib/rules_python/releases/download/{0}/rules_python-{0}.tar.gz"
PROTOBUF = "https://github.com/protocolbuffers/protobuf/releases/download/v{0}/protobuf-{0}.bazel.tar.gz"
PBS = "https://github.com/astral-sh/python-build-standalone/releases/download/"


def need(m, what):
    if not m:
        sys.exit("ppc64le-pins: cannot find %s" % what)
    return m.group(1)


def member(tarball, path):
    """<path> from a release tarball, under its top directory if it has one."""
    with tarfile.open(tarball) as t:
        for m in t.getmembers():
            name = m.name[2:] if m.name.startswith("./") else m.name
            if name == path or (name.count("/") == path.count("/") + 1 and name.split("/", 1)[1] == path):
                return t.extractfile(m).read().decode()
    sys.exit("ppc64le-pins: %s has no %s" % (tarball, path))


def derive(mozc_file, tarball):
    """mozc_file(name) -> text of src/<name>; tarball(url) -> local path."""
    pins = {}
    pins["_bazel_version"] = need(re.search(r"^USE_BAZEL_VERSION=(\S+)", mozc_file(".bazeliskrc"), re.M),
                                  "USE_BAZEL_VERSION in .bazeliskrc")
    module = mozc_file("MODULE.bazel")
    dep = lambda n: need(re.search(r'bazel_dep\(\s*name = "%s",\s*version = "([^"]+)"' % n, module),
                         "bazel_dep %s in MODULE.bazel" % n)
    rp, pb = dep("rules_python"), dep("protobuf")
    pins["_protobuf_version"] = pb

    rp_tar = tarball(RULES_PYTHON.format(rp))
    minor = need(re.search(r'python\.defaults\(\s*python_version = "([^"]+)"', member(rp_tar, "MODULE.bazel")),
                 "python.defaults() in rules_python %s" % rp)
    versions = member(rp_tar, "python/versions.bzl")
    mapping = need(re.search(r"^MINOR_MAPPING = \{(.*?)\}", versions, re.M | re.S), "MINOR_MAPPING")
    full = need(re.search(r'"%s": "([^"]+)"' % re.escape(minor), mapping), "MINOR_MAPPING[%s]" % minor)
    entry = re.search(r'^    "%s": \{\s*"url": "([^"]+)",\s*"sha256": \{(.*?)\}' % re.escape(full), versions, re.M | re.S)
    url, shas = need(entry, "TOOL_VERSIONS[%s]" % full), entry.group(2)
    sha = need(re.search(r'"%s": "([0-9a-f]{64})"' % PLATFORM, shas), "%s for %s" % (PLATFORM, full))
    build = need(re.search(r'^INSTALL_ONLY = "([^"]+)"', versions, re.M), "INSTALL_ONLY")
    pins["_pbs_python"], pins["_pbs_release"] = full, url.split("/")[0]
    pbs_file = url.split("/")[-1].format(python_version=full, platform=PLATFORM, build=build)

    pb_tar = tarball(PROTOBUF.format(pb))
    if 'name = "prefer_prebuilt_protoc"' not in member(pb_tar, "bazel/flags/BUILD"):
        sys.exit("ppc64le-pins: protobuf %s has no prefer_prebuilt_protoc flag" % pb)
    protoc = "protoc-%s-linux-ppcle_64.zip" % pb
    protoc_sha = need(re.search(r'"%s": "([0-9a-f]{64})"' % re.escape(protoc),
                                member(pb_tar, "bazel/private/oss/toolchains/prebuilt/tool_integrity.bzl")),
                      "%s in protobuf's tool_integrity.bzl" % protoc)
    info = dict(rules_python=rp, pbs_file=pbs_file, pbs_sha256=sha, protoc=protoc, protoc_sha256=protoc_sha)
    return pins, info


def check(srcdir, given):
    pins, info = derive(lambda n: open(os.path.join(srcdir, "mozc/src", n)).read(),
                        lambda url: os.path.join(srcdir, url.rsplit("/", 1)[-1]))
    bad = ["%s=%s, but the sources say %s" % (k, given.get(k), v) for k, v in pins.items() if given.get(k) != v]
    with open(os.path.join(srcdir, info["pbs_file"]), "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != info["pbs_sha256"]:
            bad.append("%s does not have the sha256 rules_python %s expects" % (info["pbs_file"], info["rules_python"]))
    for b in bad:
        print("ppc64le-pins: " + b, file=sys.stderr)
    if bad:
        sys.exit(1)
    print("ppc64le-pins: " + " ".join("%s=%s" % kv for kv in pins.items()) + ", all agree with the sources")


def fetch(commit):
    tmp = os.path.join(os.environ.get("TMPDIR", "/var/tmp"), "ppc64le-pins.%d" % os.getpid())
    os.makedirs(tmp)

    def get(url):
        with urllib.request.urlopen(url) as r:
            return r.read()

    def mozc_file(name):
        return get("https://raw.githubusercontent.com/fcitx/mozc/%s/src/%s" % (commit, name)).decode()

    def tarball(url):
        path = os.path.join(tmp, url.rsplit("/", 1)[-1])
        with open(path, "wb") as f:
            f.write(get(url))
        return path

    pins, info = derive(mozc_file, tarball)
    print("# ppc64le pins for mozc %s (rules_python %s, protobuf %s)" % (commit, info["rules_python"], pins["_protobuf_version"]))
    for k, v in pins.items():
        print("%s=%s" % (k, v))
    print("# %s%s/%s\n#   sha256 %s (rules_python's versions.bzl); run updpkgsums for the sha512"
          % (PBS, pins["_pbs_release"], info["pbs_file"], info["pbs_sha256"]))
    print("# prebuilt protoc, if building it from source ever fails: %s\n#   sha256 %s (protobuf's tool_integrity.bzl)"
          % (info["protoc"], info["protoc_sha256"]))
    for f in os.listdir(tmp):
        os.unlink(os.path.join(tmp, f))
    os.rmdir(tmp)


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "--check":
        check(a[1], dict(x.split("=", 1) for x in a[2:]))
    elif len(a) == 1 and not a[0].startswith("-"):
        fetch(a[0])
    else:
        sys.exit(__doc__)
