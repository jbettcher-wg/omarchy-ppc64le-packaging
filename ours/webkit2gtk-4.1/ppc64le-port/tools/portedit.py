#!/usr/bin/env python3
"""Declarative, idempotent source edits for the ppc64le port.

The port's edits to files it shares with every other target are overwhelmingly
of three shapes:

    add PPC64LE to an existing arch list
    add a `#elif CPU(PPC64LE)` arm to an existing arch fork
    insert a ppc64 block next to a named anchor

A textual diff expresses those as line offsets plus context, which is exactly
the part upstream churn invalidates -- against WebKitGTK 2.54.1, 85 of the
port's hunks failed, and almost all of them failed because a neighbouring
architecture had been added or renamed, not because the edit was wrong.

This replays them as operations anchored to an EXACT LINE OF SOURCE instead:

    REPLACE    file | old line      | new line
    REPLACE*N  file | old line      | new line   (exactly N sites, all replaced)
    AFTER      file | anchor line   | block to insert after it
    BEFORE     file | anchor line   | block to insert before it

`REPLACE*N` is for an edit that genuinely applies at several identical sites --
three in LowLevelInterpreter64.asm have byte-identical surroundings. The count
is declared so that a site appearing or disappearing upstream is reported
rather than silently half-applied.

Every operation is idempotent (an edit already present is a no-op, so the table
can be replayed over a half-ported tree) and every operation is verified: the
anchor must occur exactly once, or the operation is reported and NOTHING is
written for that file. An anchor that has become ambiguous is as much a review
item as one that has disappeared, because applying it to the wrong one of two
sites is the failure mode that builds clean and crashes at run time.

Usage:  portedit.py TABLE ROOT [--dry-run]
"""
import io, os, sys
from collections import OrderedDict

def dec(s):
    """Unescape one table field.

    A single left-to-right scan, not a sequence of replaces: a payload may
    contain a literal backslash (a C string's own \\n, say), which encodes to
    two backslashes, and replacing "\\n" first would find the escape inside it
    and turn it into a real newline. That silently corrupted the Capstone
    payload before this was a scanner.
    """
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]
            if n == 'n':
                out.append('\n'); i += 2; continue
            if n == 'p':
                out.append('|'); i += 2; continue
            if n == '\\':
                out.append('\\'); i += 2; continue
        out.append(c); i += 1
    return ''.join(out)

def find(lines, block):
    """Every index where `block` appears as a contiguous run of whole lines.

    Anchors are matched as blocks rather than single lines because a single
    line is often not unique -- `#else` never is -- while the two or three
    lines around it are.
    """
    if not block:
        return []
    n = len(block)
    return [i for i in range(len(lines) - n + 1) if lines[i:i + n] == block]


def load(tablep):
    ops = []
    for n, raw in enumerate(io.open(tablep, encoding='utf-8'), 1):
        raw = raw.rstrip('\n')
        if not raw.strip() or raw.lstrip().startswith('#'):
            continue
        f = [dec(x) for x in raw.split('|')]
        if len(f) != 4:
            sys.exit('%s:%d: expected 4 fields, got %d' % (tablep, n, len(f)))
        ops.append((n, f[0].strip(), f[1].strip(), f[2], f[3]))
    return ops

def main():
    tablep, root = sys.argv[1], sys.argv[2]
    dry = '--dry-run' in sys.argv
    ops = load(tablep)

    byfile = OrderedDict()
    for op in ops:
        byfile.setdefault(op[2], []).append(op)

    done = skipped = 0
    problems = []
    for rel, fops in byfile.items():
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            problems.append((fops[0][0], rel, 'file does not exist'))
            continue
        text = io.open(path, encoding='utf-8').read()
        nl = '\n'
        lines = text.split(nl)
        local = []
        fail = False
        for lineno, kind, _rel, anchor, payload in fops:
            a = anchor.split(nl)
            pay = payload.split(nl)
            # Idempotence: an edit already in the file is a no-op, so the table
            # can be replayed over a partly ported tree.
            if kind.startswith('REPLACE'):
                # A REPLACE payload often CONTAINS its anchor (adding a line
                # after an #include, widening an #if). So "payload present and
                # anchor absent" is not the test: the test is that every
                # remaining anchor match sits inside a payload match, which is
                # what an already-applied edit looks like.
                pm, am = find(lines, pay), find(lines, a)
                if pm and all(any(j <= i and i + len(a) <= j + len(pay)
                                  for j in pm) for i in am):
                    skipped += 1; continue
            elif find(lines, pay):
                skipped += 1; continue
            want = 1
            if kind.startswith('REPLACE*'):
                want = int(kind.split('*')[1])
                kind = 'REPLACE_N'
            hits = find(lines, a)
            if kind == 'REPLACE_N':
                if len(hits) != want:
                    problems.append((lineno, rel,
                                     'REPLACE*%d found %d sites: %r'
                                     % (want, len(hits), a[0][:60])))
                    fail = True; continue
                for i in reversed(hits):
                    lines[i:i + len(a)] = pay
                local.append(kind); continue
            if len(hits) != 1:
                problems.append((lineno, rel,
                                 '%s anchor %s: %r' %
                                 (kind,
                                  'ambiguous (%d matches)' % len(hits) if hits
                                  else 'not found',
                                  a[0][:66] + (' ...' if len(a) > 1 else ''))))
                fail = True; continue
            i = hits[0]
            if kind == 'REPLACE':
                lines[i:i + len(a)] = pay
            elif kind == 'AFTER':
                lines[i + len(a):i + len(a)] = pay
            elif kind == 'BEFORE':
                lines[i:i] = pay
            else:
                problems.append((lineno, rel, 'unknown operation %r' % kind))
                fail = True; continue
            local.append(kind)
        if local and not fail and not dry:
            io.open(path, 'w', encoding='utf-8').write(nl.join(lines))
        if fail and local:
            problems.append((fops[0][0], rel,
                             'NOT WRITTEN: %d other edits to this file held back'
                             % len(local)))
        done += len(local) if not fail else 0

    print('portedit: %d applied, %d already present, %d need review'
          % (done, skipped, len(problems)))
    for lineno, rel, why in problems:
        print('  table:%-4d %-52s %s' % (lineno, rel, why))
    return 1 if problems else 0

if __name__ == '__main__':
    sys.exit(main())
