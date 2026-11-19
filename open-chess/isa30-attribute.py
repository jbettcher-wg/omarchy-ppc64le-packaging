#!/usr/bin/env python3
"""isa30-attribute.py -- attribute every ISA 3.0 (POWER9-only) instruction of
an unstripped ppc64le ELF to its function, and accept only libgcc's IFUNC'd
IEEE-128 hardware routines.

    isa30-attribute.py --libgcc <libgcc.a> [--installed <stripped copy>] <unstripped ELF>

Used by dart's build() in the baseline (POWER8) pool. The pool's own policy
(omarchy-ppc64le CLAUDE.local.md, the 2026-09-23 sweep) lists as benign "the
IFUNC'd float128 hardware objects from libgcc": a static -static-libgcc link
carries libgcc's *_hw IEEE-128 routines, which use ISA 3.0 instructions but
are only ever entered through an IFUNC resolver that picks the *_sw variant
on a CPU without IEEE-128 hardware. Everything else must be ISA 2.07.

Method (all of it must hold, or the exit status is 1):
  * objdump -D -z -j .text under -M power8 and -M power9, read in lockstep.
    -z keeps zero blocks, so every word of .text appears (without it objdump
    collapses runs of zeros and coverage drops to 80-97%); coverage must be
    >= 99% of .text/4. A word is ISA 3.0 when power8 shows `.long` and
    power9 decodes it; data in text is `.long` under both and cancels.
  * Each ISA 3.0 word is attributed to the function containing it (.symtab).
  * The allowlist is read from the libgcc.a the build linked: the text
    symbols defined by its _divkc3-hw.o, _mulkc3-hw.o, _powikf2-hw.o,
    float128-hw.o and float128-p10.o members. Every word must lie in one of
    them; a word anywhere else is a violation, named by function.
  * Each allowlisted function F that carries words must be reachable only
    through a resolver: F == D + "_hw" where D is an IFUNC symbol in the
    binary's .symtab, D is one of the IFUNCs libgcc's float128-ifunc.o
    defines, D_resolve exists, and the binary has IRELATIVE relocations.
    No branch outside the allowlisted functions may target F directly.
  * With --installed, the stripped copy's .text must be byte-identical to
    the unstripped one's, so the attribution holds for what is installed.

Prints per-function counts; the last line is "RESULT ok <total>" or
"RESULT FAIL <reason>".
"""
import argparse, hashlib, os, re, subprocess, sys, tempfile

MEMBERS = ('_divkc3-hw.o', '_mulkc3-hw.o', '_powikf2-hw.o', 'float128-hw.o', 'float128-p10.o')
HDR = re.compile(r'^([0-9a-f]+) <(.+)>:$')
INSN = re.compile(r'^\s*([0-9a-f]+):\s+(\S+)(.*)$')
TARGET = re.compile(r'<([^>+]+)(?:\+0x[0-9a-f]+)?>')


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout


def libgcc_sets(libgcc):
    """Allowlisted function names, and the IFUNC names float128-ifunc.o defines."""
    with tempfile.TemporaryDirectory() as td:
        names = run(['ar', 't', libgcc]).split()
        want = [m for m in MEMBERS if m in names] + (['float128-ifunc.o'] if 'float128-ifunc.o' in names else [])
        if want:
            run(['ar', 'x', os.path.abspath(libgcc)] + want, cwd=td)
        allowed, ifuncs = set(), set()
        for m in want:
            for line in run(['nm', '--defined-only', '-P', os.path.join(td, m)]).splitlines():
                parts = line.split()
                if len(parts) < 2:
                    continue
                name, typ = parts[0], parts[1]
                if m == 'float128-ifunc.o':
                    if typ == 'i':
                        ifuncs.add(name)
                elif typ in 'Tt':
                    allowed.add(name)
        return allowed, ifuncs, [m for m in MEMBERS if m not in names]


def text_info(elf):
    for line in run(['readelf', '-SW', elf]).splitlines():
        m = re.match(r'\s*\[\s*\d+\]\s+\.text\s+\S+\s+[0-9a-f]+\s+([0-9a-f]+)\s+([0-9a-f]+)', line)
        if m:
            return int(m.group(1), 16), int(m.group(2), 16)
    raise SystemExit('RESULT FAIL no .text in %s' % elf)


def text_sha(elf):
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, 't.bin')
        run(['objcopy', '-O', 'binary', '-j', '.text', elf, out])
        return hashlib.sha256(open(out, 'rb').read()).hexdigest()


SYMTYPES = ('NOTYPE', 'OBJECT', 'FUNC', 'SECTION', 'FILE', 'COMMON', 'TLS', 'IFUNC')


def symtab(elf):
    """name -> {(type, value)} for every .symtab symbol. STT_GNU_IFUNC (10) is
    printed as "IFUNC" or, when the ELF's OSABI is SYSV (lld's output here),
    as "<OS specific>: 10"; both become IFUNC. The Vis column may carry
    "[<localentry>: 8]", so the name is taken as the last field."""
    out = {}
    for line in run(['readelf', '-sW', elf]).splitlines():
        m = re.match(r'\s*\d+:\s+([0-9a-f]+)\s+\S+\s+(.*)$', line)
        if not m:
            continue
        rest = m.group(2)
        if rest.startswith('<OS specific>: 10'):
            typ = 'IFUNC'
        else:
            typ = rest.split()[0]
            if typ not in SYMTYPES:
                typ = 'OTHER'
        name = rest.split()[-1]
        out.setdefault(name, set()).add((typ, int(m.group(1), 16)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--libgcc', required=True)
    ap.add_argument('--installed')
    ap.add_argument('--min-coverage', type=float, default=0.99)
    ap.add_argument('elf')
    a = ap.parse_args()
    fail = []

    allowed, ifuncs, missing = libgcc_sets(a.libgcc)
    if missing:
        fail.append('libgcc.a lacks members %s' % ' '.join(missing))
    print('%s: allowlist %d functions from %s; %d float128 IFUNCs'
          % (os.path.basename(a.elf), len(allowed), ' '.join(MEMBERS), len(ifuncs)))

    if a.installed:
        s1, s2 = text_sha(a.elf), text_sha(a.installed)
        if s1 != s2:
            fail.append('.text of %s differs from %s' % (a.installed, a.elf))
        else:
            print('  .text identical to %s (sha256 %s)' % (a.installed, s1[:16]))

    _, size = text_info(a.elf)
    cmd = ['objdump', '-D', '-z', '-j', '.text', '--no-show-raw-insn', '-M']
    p8 = subprocess.Popen(cmd + ['power8', a.elf], stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
    p9 = subprocess.Popen(cmd + ['power9', a.elf], stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
    func, words, counts, outside, direct = None, 0, {}, {}, {}
    for l8, l9 in zip(p8.stdout, p9.stdout):
        h = HDR.match(l8)
        if h:
            func = h.group(2)
            continue
        m8, m9 = INSN.match(l8), INSN.match(l9)
        if not m8 or not m9:
            continue
        if m8.group(1) != m9.group(1):
            raise SystemExit('RESULT FAIL objdump streams diverged at %s / %s' % (m8.group(1), m9.group(1)))
        words += 1
        if m8.group(2) == '.long' and m9.group(2) != '.long':
            if func in allowed:
                counts[func] = counts.get(func, 0) + 1
            else:
                outside[func] = outside.get(func, 0) + 1
        mn = m9.group(2)
        if mn.startswith('b') and func not in allowed:
            t = TARGET.search(m9.group(3))
            if t and t.group(1) in allowed:
                direct.setdefault(t.group(1), set()).add(func)
    for p in (p8, p9):
        p.stdout.close()
        if p.wait():
            fail.append('objdump exited %d' % p.returncode)

    cov = words / (size / 4) if size else 0
    print('  .text %d bytes, %d words disassembled, coverage %.2f%%' % (size, words, 100 * cov))
    if cov < a.min_coverage:
        fail.append('coverage %.2f%% < %.0f%%' % (100 * cov, 100 * a.min_coverage))

    syms = symtab(a.elf)
    irel = sum(1 for l in run(['readelf', '-rW', a.elf]).splitlines() if 'IRELATIV' in l)
    for f in sorted(counts):
        d = f[:-3] if f.endswith('_hw') else None
        why = []
        if d is None:
            why.append('not a *_hw name')
        else:
            dt = {t for t, _ in syms.get(d, set())}
            if 'IFUNC' not in dt:
                why.append('dispatcher %s is not IFUNC (%s)' % (d, ','.join(sorted(dt)) or 'absent'))
            if d not in ifuncs:
                why.append("%s is not one of libgcc float128-ifunc.o's IFUNCs" % d)
            # On ELFv2 an IFUNC symbol's value is its resolver's address.
            iv = {v for t, v in syms.get(d, set()) if t == 'IFUNC'}
            rv = {v for t, v in syms.get(d + '_resolve', set()) if t == 'FUNC'}
            if not rv:
                why.append('no %s_resolve' % d)
            elif iv and not (iv & rv):
                why.append('IFUNC %s does not point at %s_resolve' % (d, d))
        if f in direct:
            why.append('branched to directly from %s' % ', '.join(sorted(direct[f])[:3]))
        print('  allowed %6d  %s%s' % (counts[f], f, ('   <- ' + '; '.join(why)) if why else
                                       '   (via IFUNC %s, resolver present)' % d))
        if why:
            fail.append('%s: %s' % (f, '; '.join(why)))
    if counts and irel == 0:
        fail.append('no IRELATIVE relocations: the IFUNCs are never resolved')
    for f in sorted(outside, key=lambda k: -outside[k])[:20]:
        print('  OUTSIDE %6d  %s' % (outside[f], f))
    if outside:
        fail.append('%d ISA 3.0 words outside the allowlist, in %d functions (first: %s)'
                    % (sum(outside.values()), len(outside), sorted(outside, key=lambda k: -outside[k])[0]))
    total = sum(counts.values())
    print('  IRELATIVE relocations: %d' % irel)
    if fail:
        print('RESULT FAIL ' + ' | '.join(fail))
        return 1
    print('RESULT ok %d' % total)
    return 0


if __name__ == '__main__':
    sys.exit(main())
