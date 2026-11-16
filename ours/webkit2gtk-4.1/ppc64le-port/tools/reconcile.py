#!/usr/bin/env python3
"""Decide which rejected hunks are actually still outstanding.

`patch` writes a .rej before the declarative edit table runs, and the table
resolves many of those same hunks by a different route (a different anchor,
upstream's own spelling, or not at all because upstream has since done it).
So a .rej file is not evidence of outstanding work on its own.

For each rejected hunk, this asks the only question that matters: are the lines
the hunk wanted to ADD present in the file now? If they all are, the hunk is
satisfied however it got there. If none are, it is outstanding. If some are, it
is partial and gets reported as such, because that is the state most likely to
be a half-finished merge.

  reconcile.py ROOT [--prune]      --prune deletes .rej files that are fully
                                   satisfied, leaving only real work behind
"""
import io, os, sys

def hunks(path):
    cur = None
    for line in io.open(path, encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        if line.startswith('@@'):
            if cur is not None:
                yield cur
            cur = []
            continue
        if cur is not None:
            cur.append(line)
    if cur is not None:
        yield cur

def managed():
    """Files the declarative edit table owns, and files deliberately dropped.

    A .rej under either is not outstanding work. The table's version of an edit
    is often deliberately NOT the patch's version -- it keeps an architecture
    upstream has since added to the same line -- so the patch's `+` line is
    absent by design and would otherwise be reported forever.
    """
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location('ed', os.path.join(here, 'edits.py'))
    ed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ed)
    return set(p for _k, p, _a, _p in ed.EDITS), dict(ed.OBSOLETE)


def main():
    root = sys.argv[1]
    prune = '--prune' in sys.argv
    owned, dropped = managed()
    sat = out = part = tab = drop = 0
    rows = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if not fn.endswith('.rej'):
                continue
            rej = os.path.join(dp, fn)
            tgt = rej[:-4]
            if not os.path.exists(tgt):
                rows.append(('MISSING', os.path.relpath(tgt, root), 0, 0)); continue
            lines = [l.rstrip() for l in
                     io.open(tgt, encoding='utf-8', errors='replace').read().split('\n')]
            fsat = fout = fpart = 0
            for h in hunks(rej):
                # The test is whether the hunk's POST-IMAGE -- its context and
                # added lines together, in order -- appears as a contiguous run.
                #
                # Asking only "are the added lines present somewhere in the
                # file" is not good enough, and that mistake cost a whole
                # debugging session: the PPC64 arm of functionPrologue reads
                # `elsif ARM64 or ARM64E or RISCV64 or PPC64`, which is also a
                # line in preserveCallerPCAndCFR. That other site WAS patched,
                # so the lenient test called the hunk satisfied while
                # functionPrologue silently emitted no prologue at all on this
                # target -- no saved link register, no frame -- and every call
                # in the interpreter returned to garbage.
                post = [l[1:].rstrip() for l in h
                        if l.startswith(('+', ' ')) and not l.startswith('+++')]
                post = [l for l in post if l.strip()]
                if not post:
                    fsat += 1; continue
                n = len(post)
                runs = [i for i in range(len(lines) - n + 1)
                        if [x for x in lines[i:i + n] if x.strip()] == post
                        or lines[i:i + n] == post]
                if runs:
                    fsat += 1; continue
                add = [l[1:].rstrip() for l in h if l.startswith('+')]
                add = [a for a in add if a.strip()]
                if not add:
                    fsat += 1; continue
                # fall back to reporting how much of the addition is anywhere,
                # purely to rank the review list
                have = set(lines)
                present = sum(1 for a in add if a in have)
                if present == 0:
                    fout += 1
                else:
                    fpart += 1
            rel = os.path.relpath(tgt, root)
            if rel in dropped:
                drop += fsat + fout + fpart
                if prune:
                    os.unlink(rej)
                continue
            if rel in owned:
                tab += fsat + fout + fpart
                if prune:
                    os.unlink(rej)
                continue
            sat += fsat; out += fout; part += fpart
            if fout or fpart:
                rows.append(('WORK', rel, fout, fpart))
            elif prune:
                os.unlink(rej)
    print('reconcile: %d satisfied, %d handled by the edit table, %d dropped '
          'as obsolete, %d outstanding, %d partial'
          % (sat, tab, drop, out, part))
    if dropped:
        print('\n   deliberately not carried forward:')
        for rel, why in sorted(dropped.items()):
            print('     %s' % rel.replace('Source/', ''))
            for chunk in (why[i:i + 66] for i in range(0, len(why), 66)):
                print('        %s' % chunk)
        print()
    for kind, rel, o, p in sorted(rows, key=lambda r: -(r[2] + r[3])):
        print('   %3d out %3d partial  %s' % (o, p, rel.replace('Source/', '')))
    return 0

if __name__ == '__main__':
    sys.exit(main())
