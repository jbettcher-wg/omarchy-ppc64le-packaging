#!/usr/bin/env python3
"""isa30-text-scan.py [--min-coverage F] ELF... -- ISA 3.0 (POWER9-only)
instructions over the WHOLE .text of AOT ELFs (Dart snapshots, libapp.so),
which must have none in either pool: Dart codegen is ISA 2.07.

A stripped AOT ELF's only symbols are the _kDart*SnapshotInstructions
OBJECTs, so plain `objdump -d` hex-dumps most of it instead of decoding it
(work/packaging NOTES item 17: a release libapp.so was ~25% decoded). So:
  * `objdump -D -z -j .text` under -M power8 and -M power9, read in lockstep:
    every word of .text, -z keeping zero runs; a word is ISA 3.0 when power8
    shows `.long` and power9 decodes it (data in text is .long under both);
  * coverage = decoded words / (.text size / 4), must be >= --min-coverage;
  * control: a copy with a POWER9-only `modsd r3,r4,r5` written over the
    word in the middle of .text must count exactly one more, or the scan
    proves nothing about this file.
Prints one line per file plus the control; exit 1 on any ISA 3.0 word, low
coverage or a control that does not fire. Run natively (host objdump).
"""
import os, re, shutil, struct, subprocess, sys, tempfile

INSN = re.compile(r'^\s*([0-9a-f]+):\s+(\S+)')
MODSD = (31 << 26) | (3 << 21) | (4 << 16) | (5 << 11) | (777 << 1)  # modsd r3,r4,r5 (ISA 3.0)


def text_section(path):
    out = subprocess.run(['readelf', '-SW', path], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        m = re.search(r'\]\s+\.text\s+\S+\s+[0-9a-f]+\s+([0-9a-f]+)\s+([0-9a-f]+)', line)
        if m:
            return int(m.group(1), 16), int(m.group(2), 16)
    raise SystemExit('%s: no .text' % path)


def scan(path):
    cmd = ['objdump', '-D', '-z', '-j', '.text', '--no-show-raw-insn', '-M']
    p8 = subprocess.Popen(cmd + ['power8', path], stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
    p9 = subprocess.Popen(cmd + ['power9', path], stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
    words = isa30 = 0
    for l8, l9 in zip(p8.stdout, p9.stdout):
        m8, m9 = INSN.match(l8), INSN.match(l9)
        if not m8 or not m9:
            continue
        words += 1
        if m8.group(2) == '.long' and m9.group(2) != '.long':
            isa30 += 1
    for p in (p8, p9):
        p.stdout.close()
        if p.wait():
            raise SystemExit('%s: objdump exited %d' % (path, p.returncode))
    return words, isa30


def main():
    args = sys.argv[1:]
    mincov = 0.99
    if args[:1] == ['--min-coverage']:
        mincov, args = float(args[1]), args[2:]
    bad = 0
    for path in args:
        off, size = text_section(path)
        words, n = scan(path)
        cov = words / (size / 4) if size else 0
        print('%s: .text %d words, decoded %d (coverage %.2f%%), ISA 3.0: %d'
              % (path, size // 4, words, 100 * cov, n))
        if n:
            print('  FAIL: %d ISA 3.0 instructions in an AOT ELF' % n); bad = 1
        if cov < mincov:
            print('  FAIL: coverage below %.0f%%' % (100 * mincov)); bad = 1
        td = tempfile.mkdtemp(prefix='isa30ctl.', dir=os.environ.get('TMPDIR', '/var/tmp'))
        try:
            q = os.path.join(td, 'ctl')
            shutil.copy(path, q)
            pos = off + (size // 2) // 4 * 4
            with open(q, 'r+b') as f:
                f.seek(pos)
                f.write(struct.pack('<I', MODSD))
            _, n2 = scan(q)
        finally:
            shutil.rmtree(td)
        fired = n2 == n + 1
        print('  control: modsd mid-.text (file offset 0x%x): %d -> %d, %s'
              % (pos, n, n2, 'fires' if fired else 'DID NOT FIRE'))
        if not fired:
            bad = 1
    print('RESULT %s' % ('FAIL' if bad else 'ok'))
    return bad


if __name__ == '__main__':
    sys.exit(main())
