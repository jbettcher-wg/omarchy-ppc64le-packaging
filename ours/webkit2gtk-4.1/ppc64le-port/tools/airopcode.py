#!/usr/bin/env python3
"""Semantic diff/apply for JavaScriptCore's AirOpcode.opcodes.

Why this exists instead of a patch
----------------------------------
AirOpcode.opcodes is the highest-churn file the ppc64le port touches. Upstream
adds operand forms and retags existing ones on nearly every release -- the AVX
work alone rewrote most of the file -- so a textual diff against it rots
immediately, while the port's actual intent ("ppc64 implements this form too")
does not change at all. Measured against WebKitGTK 2.54.1, 22 of the port's 71
hunks no longer applied, every one of them a tag edit that was still correct.

So the port's edits are stored as operations addressed by DECLARATION TEXT and
FORM TEXT, which upstream churn does not move, and replayed onto whatever
version is in front of us. Two properties matter:

  * Tag edits are a SET DELTA, not an absolute string. The port only ever adds
    `ppc64`. Writing the absolute string would silently revert upstream's own
    tag changes -- against 2.54.1 that would have deleted the `arm` and `armv7`
    tags from 28 declarations, dropping 32-bit ARM support from a build that
    still ships it, with nothing failing to say so.
  * An operation whose anchor is gone is REPORTED, never guessed. That report
    is the review list for a new release.

Fidelity is checked by round-trip: derive(base, ported) replayed onto base must
reproduce `ported` byte for byte.

  derive BASE PORTED > table      write the table
  apply  TABLE FILE               replay it onto FILE, in place
  roundtrip FILE                  reprint FILE through the parser (fidelity check)
"""
import io, os, re, sys, tempfile
from collections import OrderedDict

# A decl/form line is `[tag: ]body`, where tag is one or more arch words.
LINE = re.compile(r'^(?P<ind>[ \t]*)'
                  r'(?:(?P<tag>[A-Za-z0-9_][A-Za-z0-9_ ]*):(?P<gap>[ \t]+))?'
                  r'(?P<body>\S.*)$')


def classify(line):
    """-> (indent, tag, body, gap) for a decl/form line, else None.

    `gap` is the whitespace after the tag's colon, kept verbatim: one line in
    2.54.1 uses two spaces and normalising it would show up as a change we
    did not intend to make.
    """
    if not line.strip() or line.lstrip().startswith('#'):
        return None
    m = LINE.match(line)
    return (m.group('ind'), m.group('tag'), m.group('body'),
            m.group('gap') or ' ') if m else None


class Block:
    """One opcode: leading comments, the declaration, and its operand forms."""
    def __init__(self, tag, body, lead, gap=' '):
        self.tag, self.body, self.lead, self.gap = tag, body, lead, gap
        self.forms = []                 # [tag_or_None, body, lead_lines, gap]

    def addr(self):
        return self.body


def parse(path):
    """Split into (header, blocks, tail).

    Comments and blank lines are buffered and attached as the `lead` of the
    next decl/form line, which is what lets emit() reproduce the input exactly.
    """
    raw = io.open(path, encoding='utf-8').read().split('\n')
    blocks, header, lead, cur = [], [], [], None
    for line in raw:
        c = classify(line)
        if c is None:
            lead.append(line)
            continue
        ind, tag, body, gap = c
        if ind == '':
            if cur is None:
                header, lead = lead[:], []
            cur = Block(tag, body, lead[:], gap)
            blocks.append(cur)
            lead = []
        else:
            cur.forms.append([tag, body, lead[:], gap])
            lead = []
    return header, blocks, lead[:]


def emit(header, blocks, tail):
    out = list(header)
    for b in blocks:
        out.extend(b.lead)
        out.append(('%s:%s%s' % (b.tag, b.gap, b.body)) if b.tag else b.body)
        for tag, body, lead, gap in b.forms:
            out.extend(lead)
            out.append('    ' + (('%s:%s%s' % (tag, gap, body)) if tag else body))
    out.extend(tail)
    return '\n'.join(out)


def index(blocks):
    ix = OrderedDict()
    for b in blocks:
        ix.setdefault(b.addr(), []).append(b)
    return ix


def parse_str(s):
    fd, p = tempfile.mkstemp(suffix='.opcodes')
    os.close(fd)
    io.open(p, 'w', encoding='utf-8').write(s)
    try:
        return parse(p)
    finally:
        os.unlink(p)


def enc(s):
    return s.replace('\\', '\\\\').replace('\n', '\\n').replace('|', '\\p')


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


def words(tag):
    return tag.split() if tag and tag != '-' else []


def retag(current, base, exact, added, removed):
    """Produce the new tag for a line whose tag is `current`.

    Byte-exact when the line still carries the tag we forked from; otherwise
    the delta is merged into whatever upstream now has, and the caller is told
    so it can be reported.
    """
    cur, want = words(current), words(base)
    if cur == want:
        return (exact if exact != '-' else None), False
    out = [w for w in cur if w not in removed]
    for a in added:
        if a not in out:
            out.append(a)
    # keep the file's usual ascii ordering unless upstream's own line is unsorted
    if cur == sorted(cur):
        out = sorted(out)
    return ('%s' % ' '.join(out)) if out else None, True


def altname_kinds(body):
    """`Index, Tmp as x86Lea64` -> `Index, Tmp`; used to spot a pure rename."""
    return body.split(' as ')[0]


def derive(oldp, newp):
    _, ob, _ = parse(oldp)
    _, nb, _ = parse(newp)
    oix, nix = index(ob), index(nb)
    ops = []
    for addr, ns in nix.items():
        os_ = oix.get(addr)
        if not os_:
            continue                                    # new block; handled below
        for o, n in zip(os_, ns):
            ow, nw = set(words(o.tag)), set(words(n.tag))
            if ow != nw:
                ops.append(('DECLTAG', addr, o.tag or '-', n.tag or '-',
                            ','.join(sorted('+' + x for x in nw - ow) +
                                     sorted('-' + x for x in ow - nw))))
            ofm = [(fm[0] or '', fm[1]) for fm in o.forms]
            seen, used = {}, set()
            pend_add, pend_drop = [], []
            for t, bd in [(fm[0], fm[1]) for fm in n.forms]:
                k = seen.get(bd, 0); seen[bd] = k + 1
                cand = [i for i, (_ot, ob_) in enumerate(ofm) if ob_ == bd]
                if k < len(cand):
                    used.add(cand[k])
                    ot = ofm[cand[k]][0]
                    if set(words(ot)) != set(words(t)):
                        a, r = set(words(t)) - set(words(ot)), set(words(ot)) - set(words(t))
                        ops.append(('FORMTAG', addr, bd, str(k), ot or '-', t or '-',
                                    ','.join(sorted('+' + x for x in a) +
                                             sorted('-' + x for x in r))))
                else:
                    pend_add.append((t or '-', bd))
            for i, (ot, ob_) in enumerate(ofm):
                if i not in used:
                    pend_drop.append((ot or '-', ob_))
            # one form out, one in, same operand kinds -> the port renamed the
            # `as` alt-name. Express it as a rename so upstream's tag survives.
            ren = []
            for dt, db in list(pend_drop):
                for at, ab in list(pend_add):
                    if altname_kinds(db) == altname_kinds(ab) and db != ab:
                        a = set(words(at)) - set(words(dt))
                        r = set(words(dt)) - set(words(at))
                        ops.append(('RENAMEFORM', addr, db, ab, dt, at,
                                    ','.join(sorted('+' + x for x in a) +
                                             sorted('-' + x for x in r))))
                        pend_drop.remove((dt, db)); pend_add.remove((at, ab))
                        ren.append(db)
                        break
            for t, bd in pend_add:
                ops.append(('ADDFORM', addr, bd, t))
            for t, bd in pend_drop:
                ops.append(('DROPFORM', addr, bd, t))
            added = [l for l in n.lead if l.strip().startswith('#') and l not in o.lead]
            if added:
                ops.append(('COMMENT', addr, '\n'.join(added)))
            seen = {}
            for t, bd, lead in [(fm[0], fm[1], fm[2]) for fm in n.forms]:
                k = seen.get(bd, 0); seen[bd] = k + 1
                cand = [i for i, fm in enumerate(o.forms) if fm[1] == bd]
                olead = o.forms[cand[k]][2] if k < len(cand) else []
                add2 = [l for l in lead if l.strip().startswith('#') and l not in olead]
                if add2:
                    ops.append(('FORMCOMMENT', addr, bd, str(k), '\n'.join(add2)))
    oset = set(oix)
    for i, n in enumerate(nb):
        if n.addr() in oset:
            continue
        prev = next((nb[j].addr() for j in range(i - 1, -1, -1) if nb[j].addr() in oset), '-')
        ops.append(('ADDBLOCK', prev, emit([], [n], [])))
    return ops


def apply(tablep, target):
    header, blocks, tail = parse(target)
    ix = index(blocks)
    ok = adapted = 0
    problems, notes = [], []

    for raw in io.open(tablep, encoding='utf-8'):
        raw = raw.rstrip('\n')
        if not raw.strip() or raw.startswith('#'):
            continue
        f = [dec(x) for x in raw.split('|')]
        op = f[0]

        if op == 'ADDBLOCK':
            anchor, body = f[1], f[2]
            npre, nbs, _ = parse_str(body)
            if nbs and npre:
                nbs[0].lead = npre + nbs[0].lead    # parse() calls it the header
            if nbs and nbs[0].addr() in ix:
                # Upstream has since introduced this declaration itself --
                # 2.54.1 added `armv7: RotateLeft32 U:G:32, U:G:32, ZD:G:32`,
                # which the port had been adding as a ppc64-only block. MERGE
                # rather than skip: skipping looks like success and leaves the
                # declaration without the port's tag, so the target silently
                # loses the opcode. Found by comparing generated dispatch
                # counts against the port's own tree, not by anything failing.
                ex, nb0 = ix[nbs[0].addr()][0], nbs[0]
                add = [w for w in words(nb0.tag) if w not in words(ex.tag)]
                if add:
                    merged = words(ex.tag) + add
                    if words(ex.tag) == sorted(words(ex.tag)):
                        merged = sorted(merged)
                    ex.tag = ' '.join(merged)
                for ftag, fbody, flead, fgap in nb0.forms:
                    hit = [f for f in ex.forms if f[1] == fbody]
                    if not hit:
                        ex.forms.append([ftag, fbody, flead, fgap])
                        continue
                    fadd = [w for w in words(ftag) if w not in words(hit[0][0])]
                    if fadd:
                        cur = words(hit[0][0])
                        m = cur + fadd
                        if cur == sorted(cur):
                            m = sorted(m)
                        hit[0][0] = ' '.join(m) if m else None
                adapted += 1
                notes.append(('ADDBLOCK', nb0.addr(),
                              'merged into upstream declaration (%s)'
                              % (ex.tag or '-')))
                ok += 1; continue
            tgt = ix.get(anchor)
            if not tgt and anchor != '-':
                problems.append(('ADDBLOCK anchor missing', anchor)); continue
            at = blocks.index(tgt[-1]) + 1 if tgt else len(blocks)
            for k, nbk in enumerate(nbs):
                blocks.insert(at + k, nbk)
            ix = index(blocks); ok += 1; continue

        addr = f[1]
        tgt = ix.get(addr)
        if not tgt:
            problems.append((op + ': declaration gone', addr)); continue
        b = tgt[0]

        if op == 'DECLTAG':
            base, exact, delta = f[2], f[3], f[4]
            a = [x[1:] for x in delta.split(',') if x.startswith('+')]
            r = [x[1:] for x in delta.split(',') if x.startswith('-')]
            new, moved = retag(b.tag, base, exact, a, r)
            if moved:
                adapted += 1
                notes.append(('DECLTAG', addr, '%s -> %s' % (b.tag or '-', new or '-')))
            b.tag = new; ok += 1

        elif op in ('FORMTAG', 'FORMCOMMENT'):
            bd, k = f[2], int(f[3])
            cand = [i for i, fm in enumerate(b.forms) if fm[1] == bd]
            if k >= len(cand):
                problems.append((op + ': form gone', '%s :: %s' % (addr, bd))); continue
            i = cand[k]
            if op == 'FORMTAG':
                base, exact, delta = f[4], f[5], f[6]
                a = [x[1:] for x in delta.split(',') if x.startswith('+')]
                r = [x[1:] for x in delta.split(',') if x.startswith('-')]
                new, moved = retag(b.forms[i][0], base, exact, a, r)
                if moved:
                    adapted += 1
                    notes.append(('FORMTAG', '%s :: %s' % (addr, bd),
                                  '%s -> %s' % (b.forms[i][0] or '-', new or '-')))
                b.forms[i][0] = new
            else:
                body = f[4].split('\n')
                if not any(l in b.forms[i][2] for l in body):
                    b.forms[i][2] = b.forms[i][2] + body
            ok += 1

        elif op == 'RENAMEFORM':
            oldb, newb, base, exact, delta = f[2], f[3], f[4], f[5], f[6]
            hit = [i for i, fm in enumerate(b.forms) if fm[1] == newb]
            if hit:
                ok += 1; continue                   # already renamed
            hit = [i for i, fm in enumerate(b.forms) if fm[1] == oldb]
            if not hit:
                problems.append(('RENAMEFORM: neither spelling present',
                                 '%s :: %s' % (addr, oldb))); continue
            i = hit[0]
            a = [x[1:] for x in delta.split(',') if x.startswith('+')]
            r = [x[1:] for x in delta.split(',') if x.startswith('-')]
            new, moved = retag(b.forms[i][0], base, exact, a, r)
            if moved:
                adapted += 1
                notes.append(('RENAMEFORM', '%s :: %s' % (addr, oldb),
                              '%s -> %s' % (b.forms[i][0] or '-', new or '-')))
            b.forms[i][0] = new
            b.forms[i][1] = newb
            ok += 1

        elif op == 'ADDFORM':
            bd, want = f[2], f[3]
            if any(fm[1] == bd for fm in b.forms):
                ok += 1; continue
            b.forms.append([None if want == '-' else want, bd, [], ' '])
            ok += 1

        elif op == 'DROPFORM':
            bd, want = f[2], f[3]
            hit = [i for i, fm in enumerate(b.forms) if fm[1] == bd]
            if not hit:
                problems.append(('DROPFORM: form already gone',
                                 '%s :: %s' % (addr, bd))); continue
            del b.forms[hit[0]]
            ok += 1

        elif op == 'COMMENT':
            body = f[2].split('\n')
            if not any(l in b.lead for l in body):
                b.lead = b.lead + body
            ok += 1

        else:
            problems.append(('unknown operation', op))

    io.open(target, 'w', encoding='utf-8').write(emit(header, blocks, tail))
    return ok, adapted, problems, notes


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    mode = sys.argv[1]
    if mode == 'derive':
        for o in derive(sys.argv[2], sys.argv[3]):
            print('|'.join(enc(x) for x in o))
    elif mode == 'apply':
        ok, adapted, problems, notes = apply(sys.argv[2], sys.argv[3])
        print('applied %d  (%d merged into an upstream tag change)  unresolved %d'
              % (ok, adapted, len(problems)))
        if notes and os.environ.get('AIROPCODE_VERBOSE'):
            print('\n  merged into upstream tag changes:')
            for kind, where, how in notes:
                print('    %-11s %-44s %s' % (kind, where[:44], how))
        for why, what in problems:
            print('  NEEDS REVIEW  %-34s %s' % (why, what))
        sys.exit(1 if problems else 0)
    elif mode == 'roundtrip':
        h, b, t = parse(sys.argv[2])
        sys.stdout.write(emit(h, b, t))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
