#!/usr/bin/env python3
"""Find functions/macros that the port supports but the staged tree does not.

  scopecheck.py <port-checkout> <staged-tree> [patches-dir]

With a patches directory it looks only at the files the port's series touches,
which is what makes it precise; without one it walks the whole tree and will
also report files the port deliberately does not carry forward (test
harnesses, Bun-only code).

This exists because the other gates missed a fatal bug and this one finds it.

`reconcile.py` asked whether a rejected hunk's added lines were present in the
file; `ppc64check.sh` compared the SET of ppc64-mentioning lines. Both said
clean while `functionPrologue` in LowLevelInterpreter.asm had no PPC64 arm --
because the line it needed, `elsif ARM64 or ARM64E or RISCV64 or PPC64`, is
textually identical to one in `preserveCallerPCAndCFR`, which HAD been
patched. On this target an offlineasm if/elsif chain with no matching branch
emits NOTHING, so every interpreter function got no prologue and no epilogue:
no saved link register, no frame. Calls returned to address 0 or to bytes from
.rodata, and branches appeared to loop.

So the question here is per-SCOPE and ignores the exact text: for every
function or macro where the port has any ppc64 line at all, does the staged
tree's same scope have one too? That cannot be fooled by an identical line
somewhere else in the file, and it tolerates the adaptations a forward-port
must make (upstream adding an architecture to the same condition).
"""
import io, os, re, sys

PPC = re.compile(r'PPC64|ppc64')
ASM_SCOPE = re.compile(r'^\s*(?:macro\s+(\w+)|op\(\s*(\w+)|(\w+):|global\s+(\w+))')
CALLISH = re.compile(r'(\w+)\s*\(')
SKIP = ('if', 'for', 'while', 'return', 'else', 'switch', 'case', 'do')


def scopes(path, is_asm):
    """-> {scope_name: [ppc64 lines]} for one file."""
    found, scope = {}, '<file>'
    for raw in io.open(path, encoding='utf-8', errors='replace'):
        line = raw.rstrip()
        stripped = line.strip()
        if is_asm:
            m = ASM_SCOPE.match(line)
            if m and any(m.groups()):
                scope = next(g for g in m.groups() if g)
        elif line[:1].isalpha() and '(' in line and not stripped.startswith(SKIP):
            m = CALLISH.search(line)
            if m:
                scope = m.group(1)
        if not stripped or stripped.startswith(('#', '//', '*')):
            continue
        if PPC.search(stripped):
            found.setdefault(scope, []).append(stripped)
    return found


def ported_files(patches):
    """The set of repo-relative paths the patch series touches."""
    out = set()
    for fn in sorted(os.listdir(patches)):
        if not fn.endswith('.patch'):
            continue
        for line in io.open(os.path.join(patches, fn), encoding='utf-8',
                            errors='replace'):
            if line.startswith('+++ b/'):
                out.add(line[6:].strip())
                break
    return out


def obsolete():
    """Files the port deliberately does not carry forward (edits.py OBSOLETE)."""
    try:
        import importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location(
            'ed', os.path.join(here, 'edits.py'))
        ed = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ed)
        return set(ed.OBSOLETE)
    except Exception:
        return set()


def main():
    port, out = sys.argv[1], sys.argv[2]
    only = ported_files(sys.argv[3]) if len(sys.argv) > 3 else None
    dropped = obsolete()
    gaps = 0
    for dirpath, _dirs, files in os.walk(os.path.join(port, 'Source')):
        if '/.git' in dirpath:
            continue
        for fn in files:
            if not fn.endswith(('.asm', '.cpp', '.h', '.rb')):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, port)
            if only is not None and rel not in only:
                continue
            if rel in dropped:
                continue
            q = os.path.join(out, rel)
            if not os.path.exists(q):
                continue
            try:
                a = scopes(p, fn.endswith('.asm'))
                if not a:
                    continue
                b = scopes(q, fn.endswith('.asm'))
            except Exception:
                continue
            missing = [s for s in a if s not in b]
            if missing:
                print('   %s' % rel.replace('Source/', ''))
                for s in missing:
                    print('       scope %-38s has no ppc64 line in the staged tree'
                          % s[:38])
                    print('           ours: %s' % a[s][0][:78])
                gaps += len(missing)
    print('   scopes the port supports and the staged tree does not: %d' % gaps)
    return 1 if gaps else 0


if __name__ == '__main__':
    sys.exit(main())
