#!/usr/bin/env python3
"""run-dart-tests.py OUTDIR LOGDIR JOBS NODUMP -- the engine's testing/dart
suite under flutter_tester, the way flutter/testing/run_tests.py runs it
(gather_dart_tests + gather_dart_smoke_test): each testing/dart/*_test.dart in
4 variants ({single, multi}-threaded x {Skia software, Impeller on
SwiftShader}), vm_service/*_test.dart with the VM service on, and the smoke
test, which must FAIL. Pass = exit 0 and no "[ERROR" in the output.

Environment as run_engine_executable(): cwd = the engine src root,
LD_LIBRARY_PATH = the out dir (its libvulkan.so.1), VK_DRIVER_FILES = the
out dir's SwiftShader ICD only (never the host GPU), FLUTTER_BUILD_DIRECTORY,
the nodump preload (no crash records), RLIMIT_CORE 0.
Adapted from the engine track's harness (/var/tmp/engine-sim/run-dart-tests.py,
work/engine/REPORT-NATIVE.md section 4). Prints one line per test and
"FAILED <name>" lines; exit 0 always (the recipe judges against its allowlist).
"""
import concurrent.futures, glob, os, re, resource, subprocess, sys, time

out, logdir, jobs, nodump = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
src = os.path.normpath(os.path.join(out, '..', '..', 'flutter'))
tdir = os.path.join(src, 'testing', 'dart')
os.makedirs(logdir, exist_ok=True)


def args_for(dart_file, multithreaded, impeller, vm_service=False, microtask=False):
    a = []
    if not vm_service:
        a.append('--disable-vm-service')
    a += ['--enable-impeller', '--enable-flutter-gpu'] if impeller else ['--no-enable-impeller']
    if multithreaded:
        a.insert(0, '--force-multithreading')
    if microtask:
        a.append('--profile-microtasks')
    a += re.findall('// FlutterTesterOptions=(.*)', open(dart_file).read())
    a += ['--use-test-fonts', f'--icu-data-file-path={out}/icudtl.dat',
          f'--flutter-assets-dir={out}/gen/flutter/lib/ui/assets', '--disable-asset-fonts',
          os.path.join(out, 'gen', os.path.basename(dart_file) + '.dill')]
    return a


tasks = []
for f in sorted(glob.glob(f'{tdir}/vm_service/*_test.dart')):
    b = os.path.basename(f)
    tasks.append((f'{b}[vm_service]', args_for(f, False, False, True, b == 'microtask_profiling_test.dart'), False))
for f in sorted(glob.glob(f'{tdir}/*_test.dart')):
    for mt in (False, True):
        for imp in (False, True):
            tasks.append((f"{os.path.basename(f)}[{'mt' if mt else 'st'},{'impeller' if imp else 'skia'}]",
                          args_for(f, mt, imp), False))
smoke = os.path.join(src, 'testing', 'smoke_test_failure', 'fail_test.dart')
for mt in (True, False):
    tasks.append((f"fail_test.dart[{'mt' if mt else 'st'},skia,EXPECT-FAILURE]", args_for(smoke, mt, False), True))


def run(t):
    name, a, expect_failure = t
    log = os.path.join(logdir, re.sub(r'[^A-Za-z0-9_.-]', '_', name) + '.log')
    s = time.time()
    env = dict(os.environ, LD_LIBRARY_PATH=out, FLUTTER_BUILD_DIRECTORY=out,
               VK_DRIVER_FILES=os.path.join(out, 'vk_swiftshader_icd.json'), LD_PRELOAD=nodump)
    p = subprocess.run(['timeout', '-k', '10', '1800', os.path.join(out, 'flutter_tester')] + a,
                       cwd=os.path.normpath(os.path.join(out, '..', '..')), env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = p.stdout.decode('utf-8', 'replace')
    open(log, 'w').write(text)
    ok = (p.returncode != 0) if expect_failure else (p.returncode == 0 and '[ERROR' not in text)
    return name, ok, p.returncode, time.time() - s


resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
res = []
with concurrent.futures.ThreadPoolExecutor(jobs) as ex:
    for r in ex.map(run, tasks):
        res.append(r)
        print(f"{'PASS' if r[1] else 'FAIL'} rc={r[2]:<4} {r[3]:7.1f}s {r[0]}", flush=True)
for r in res:
    if not r[1]:
        print(f'FAILED {r[0]}')
print(f'SUMMARY {sum(1 for r in res if r[1])}/{len(res)} passed')
