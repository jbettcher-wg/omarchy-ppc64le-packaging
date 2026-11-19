#!/bin/bash
# dart-sdk-fetch.sh - populate a Dart SDK source tree's DEPS without gclient.
#
# Reads <sdk>/DEPS (gclient's Python-literal format), evaluates each entry's
# condition for a Linux host that has *no* CIPD platform (ppc64le), and
#   - git deps:  shallow-fetches the exact pinned commit into place
#                (git init; git fetch --depth 1 <url> <sha>; detached checkout),
#                keeping .git so nested repos can carry/export patches;
#   - cipd deps: skipped, except the ones named with --cipd, which are fetched
#                through the public CIPD pRPC API with curl (no cipd client;
#                only platform-independent packages, i.e. no ${platform}).
# Then optionally runs the gclient hooks the build needs.
#
# Precedent: Alpine testing/dart snapshots the tree with gclient
# (teapot-tools) and ships a tarball; this script replaces that step so a
# PKGBUILD can fetch in prepare() with only git, curl and python3. It also
# writes build/config/gclient_args.gni (which //BUILD.gn imports) and a
# manifest of exactly what was fetched to buildtools/dart-sdk-fetch.manifest.
# With a GitHub source tarball (no .git), build with
# `--gn-args dart_version_git_info=false` or tools/gn.py --no-git-version.
#
# Usage:
#   dart-sdk-fetch.sh [options] <sdk-dir>
# Options:
#   --jobs N            parallel git fetches (default 8)
#   --cipd PATH         also fetch the CIPD dep installed at PATH (relative to
#                       <sdk-dir>, e.g. third_party/devtools); repeatable
#   --list              print "kind<TAB>path<TAB>url-or-package<TAB>rev" for every
#                       selected dep and exit (for generating makepkg sources)
#   --hooks             run the build-relevant gclient hooks afterwards
#                       (generate_package_config.py needs tools/sdks/dart-sdk/bin/dart)
#   --var NAME=VALUE    override a DEPS var or condition input (e.g. host_cpu=x64)
#   --link-system-tools symlink buildtools/gn and buildtools/ninja/ninja to the
#                       gn and ninja on $PATH (the CIPD packages they replace
#                       have no ppc64 build); tools/gn.py and tools/build.py
#                       look for them there
#
# Exit status is non-zero if any selected dep failed to fetch. Re-running is
# idempotent: a dep whose checkout is already at the pinned rev is skipped.
#
# The tree itself (DEPS, runtime/, ...) must already exist: a git clone of
# https://dart.googlesource.com/sdk.git at the release tag, or the GitHub
# source tarball for the tag.
set -euo pipefail

exec python3 -I - "$@" <<'PYEOF'
import argparse, concurrent.futures, json, os, shutil, subprocess, sys, tempfile, urllib.request, zipfile

ap = argparse.ArgumentParser(prog='dart-sdk-fetch.sh')
ap.add_argument('sdk')
ap.add_argument('--jobs', type=int, default=8)
ap.add_argument('--cipd', action='append', default=[])
ap.add_argument('--list', action='store_true')
ap.add_argument('--hooks', action='store_true')
ap.add_argument('--var', action='append', default=[])
ap.add_argument('--link-system-tools', action='store_true')
args = ap.parse_args()

sdk = os.path.abspath(args.sdk)
deps_file = os.path.join(sdk, 'DEPS')
if not os.path.isfile(deps_file):
    sys.exit(f'error: {deps_file} not found')

# --- evaluate DEPS -----------------------------------------------------------
g = {}
g['Var'] = lambda name: g['vars'][name]
g['Str'] = str
with open(deps_file) as f:
    exec(compile(f.read(), deps_file, 'exec'), g)
dvars = dict(g['vars'])

# Condition inputs as gclient would set them on a Linux host. host_cpu is a
# value that matches no CIPD platform, so every "host_cpu == 'x64'/'arm64'"
# prebuilt (clang, reclient, d8, ...) is deselected.
cond_env = dict(dvars)
cond_env.update(host_os='linux', host_cpu='ppc64',
                checkout_linux=True, checkout_mac=False, checkout_win=False,
                checkout_android=False, checkout_fuchsia=False,
                checkout_ios=False, checkout_chromeos=False,
                linux='linux', mac='mac', win='win')
for kv in args.var:
    k, v = kv.split('=', 1)
    cond_env[k] = {'True': True, 'False': False}.get(v, v)

def selected(entry):
    cond = entry.get('condition') if isinstance(entry, dict) else None
    return True if not cond else bool(eval(cond, {'__builtins__': {}}, cond_env))

root_prefix = dvars.get('dart_root', 'sdk') + '/'
git_deps, cipd_deps = [], []
for path, entry in g['deps'].items():
    if not path.startswith(root_prefix):
        continue
    rel = path[len(root_prefix):].rstrip('/')
    if not selected(entry):
        continue
    if isinstance(entry, str) or 'url' in entry:
        url = entry if isinstance(entry, str) else entry['url']
        repo, rev = url.rsplit('@', 1)
        git_deps.append((rel, repo, rev))
    elif entry.get('dep_type') == 'cipd':
        for p in entry['packages']:
            cipd_deps.append((rel, p['package'], p['version']))

if args.list:
    for rel, repo, rev in git_deps:
        print(f'git\t{rel}\t{repo}\t{rev}')
    for rel, pkg, ver in cipd_deps:
        mark = 'cipd' if rel in args.cipd else 'cipd-skipped'
        print(f'{mark}\t{rel}\t{pkg}\t{ver}')
    sys.exit(0)

# --- git ---------------------------------------------------------------------
def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True).stdout

def fetch_git(rel, repo, rev):
    dest = os.path.join(sdk, rel)
    if os.path.isdir(os.path.join(dest, '.git')):
        try:
            if run(['git', 'rev-parse', 'HEAD'], cwd=dest).strip() == rev:
                return f'ok    {rel} (already at {rev[:12]})'
        except subprocess.CalledProcessError:
            pass
    os.makedirs(dest, exist_ok=True)
    if not os.path.isdir(os.path.join(dest, '.git')):
        run(['git', 'init', '-q'], cwd=dest)
    for attempt in range(3):
        try:
            run(['git', 'fetch', '-q', '--depth', '1', repo, rev], cwd=dest)
            break
        except subprocess.CalledProcessError as e:
            if attempt == 2:
                raise RuntimeError(f'{rel}: git fetch {repo} {rev} failed:\n{e.stdout}')
    run(['git', '-c', 'advice.detachedHead=false', 'checkout', '-q', '--force',
         'FETCH_HEAD'], cwd=dest)
    got = run(['git', 'rev-parse', 'HEAD'], cwd=dest).strip()
    if got != rev:
        raise RuntimeError(f'{rel}: HEAD {got} != pinned {rev}')
    return f'fetch {rel} @ {rev[:12]}'

# --- cipd (platform-independent packages only) -------------------------------
CIPD = 'https://chrome-infra-packages.appspot.com/prpc/cipd.Repository/'

def prpc(method, body):
    req = urllib.request.Request(CIPD + method, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        txt = r.read().decode()
    return json.loads(txt.split('\n', 1)[1] if txt.startswith(")]}'") else txt)

def fetch_cipd(rel, pkg, ver):
    if '${' in pkg:
        raise RuntimeError(f'{rel}: {pkg} is per-platform; there is no ppc64 build')
    dest = os.path.join(sdk, rel)
    inst = prpc('ResolveVersion', {'package': pkg, 'version': ver})['instance']
    stamp = os.path.join(dest, '.cipd-instance')
    if os.path.exists(stamp) and open(stamp).read().strip() == inst['hexDigest']:
        return f'ok    {rel} (cipd {pkg} already installed)'
    url = prpc('GetInstanceURL', {'package': pkg, 'instance': inst})['signedUrl']
    with tempfile.TemporaryDirectory() as td:
        zp = os.path.join(td, 'pkg.zip')
        subprocess.run(['curl', '-fsSL', '--retry', '3', '-o', zp, url], check=True)
        import hashlib
        h = hashlib.sha256(open(zp, 'rb').read()).hexdigest()
        if h != inst['hexDigest']:
            raise RuntimeError(f'{rel}: sha256 {h} != {inst["hexDigest"]}')
        # Extract over the directory: it may hold files tracked by the SDK
        # repo itself (third_party/devtools/README.md).
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(zp) as z:
            for m in z.infolist():
                if m.filename.startswith('.cipdpkg/'):
                    continue
                z.extract(m, dest)
                mode = (m.external_attr >> 16) & 0o777
                if mode:
                    os.chmod(os.path.join(dest, m.filename), mode)
    with open(stamp, 'w') as f:
        f.write(inst['hexDigest'] + '\n')
    return f'cipd  {rel} = {pkg} {ver} sha256:{inst["hexDigest"][:12]}'

# --- run -----------------------------------------------------------------------
jobs = [(fetch_git, d) for d in git_deps]
known_cipd = {rel: (rel, pkg, ver) for rel, pkg, ver in cipd_deps}
for rel in args.cipd:
    if rel not in known_cipd:
        sys.exit(f'error: --cipd {rel}: no selected CIPD dep at that path')
    jobs.append((fetch_cipd, known_cipd[rel]))

failed = 0
with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
    futs = {ex.submit(fn, *d): d for fn, d in jobs}
    for fut in concurrent.futures.as_completed(futs):
        try:
            print(fut.result(), flush=True)
        except Exception as e:
            failed += 1
            print(f'FAIL  {e}', file=sys.stderr, flush=True)

skipped = [d for d in cipd_deps if d[0] not in args.cipd]
print(f'{len(git_deps)} git deps, {len(args.cipd)} cipd fetched, '
      f'{len(skipped)} cipd skipped (prebuilt toolchains/SDKs/test data), '
      f'{failed} failed')

# Manifest of exactly what this tree contains.
# Written under buildtools/, which the SDK's .gitignore already ignores.
os.makedirs(os.path.join(sdk, 'buildtools'), exist_ok=True)
with open(os.path.join(sdk, 'buildtools', 'dart-sdk-fetch.manifest'), 'w') as f:
    for rel, repo, rev in sorted(git_deps):
        f.write(f'git\t{rel}\t{repo}\t{rev}\n')
    for rel, pkg, ver in sorted(cipd_deps):
        f.write(f'{"cipd" if rel in args.cipd else "cipd-skipped"}\t{rel}\t{pkg}\t{ver}\n')

if failed:
    sys.exit(1)

# gclient writes the DEPS vars named in gclient_gn_args into this file, and
# //BUILD.gn imports it.
gn_args_file = g.get('gclient_gn_args_file')
if gn_args_file and gn_args_file.startswith(root_prefix):
    path = os.path.join(sdk, gn_args_file[len(root_prefix):])
    with open(path, 'w') as f:
        f.write("# Generated from 'DEPS' by dart-sdk-fetch.sh\n")
        for name in g.get('gclient_gn_args', []):
            v = cond_env.get(name, dvars.get(name))
            f.write(f'{name} = ' + ('true' if v is True else 'false' if v is False
                                    else '"%s"' % v) + '\n')
    print(f'wrote {os.path.relpath(path, sdk)}')

if args.link_system_tools:
    for tool, link in (('gn', 'buildtools/gn'), ('ninja', 'buildtools/ninja/ninja')):
        target = shutil.which(tool)
        if not target:
            sys.exit(f'error: {tool} not found on PATH')
        link = os.path.join(sdk, link)
        os.makedirs(os.path.dirname(link), exist_ok=True)
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(target, link)
        print(f'link  {os.path.relpath(link, sdk)} -> {target}')

if args.hooks:
    # The subset of DEPS hooks a Linux build needs. Skipped: tools/buildtools/
    # update.py (depot_tools + x64 clang-format), win_toolchain, emscripten,
    # fuchsia. generate_package_config.py runs tools/sdks/dart-sdk/bin/dart.
    for hook in ('tools/generate_package_config.py',
                 'tools/generate_sdk_version_file.py',
                 'tools/generate_large_tests.py'):
        print(f'hook  {hook}', flush=True)
        subprocess.run([sys.executable, os.path.join(sdk, hook)], cwd=sdk, check=True)
PYEOF
