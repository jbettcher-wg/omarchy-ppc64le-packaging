#!/usr/bin/env python3
"""verify-conversion.py <gen dir> <profile dir> <romaji> <expected>

Verification aid for fcitx5-mozc (see README.md); not part of the build.

Drives a running mozc_server over mozc's own IPC, the way client/client.cc
does: abstract socket "\\0tmp/.mozc.<key>.session" (the key comes from
<profile>/.session.ipc), one serialized commands.Input per connection, the
write side shut down, the Output read to EOF. It types <romaji> with the IME
on, converts with SPACE, commits with ENTER, and exits 0 only if the
committed text is <expected>.

mozc's own clients refuse a server whose /proc/<pid>/exe is not
/usr/lib/mozc/mozc_server, which under qemu-user it never is; this one makes
no such check, so the server may run under qemu-ppc64le -cpu power8.

<gen dir> holds Python bindings generated from the same mozc checkout:
  protoc -I src --python_out=<gen dir> src/protocol/*.proto src/ipc/ipc.proto
"""
import os, socket, sys, time
gen, profile, romaji, expected = sys.argv[1:5]
sys.path.insert(0, gen)
from protocol import commands_pb2 as C
from ipc import ipc_pb2

keyfile = os.path.join(profile, ".session.ipc")
for _ in range(600):
    if os.path.exists(keyfile) and os.path.getsize(keyfile) > 0:
        break
    time.sleep(0.5)
info = ipc_pb2.IPCPathInfo()
info.ParseFromString(open(keyfile, "rb").read())
print("server: pid %d product %s protocol %d" % (info.process_id, info.product_version, info.protocol_version))
addr = "\0tmp/.mozc.%s.session" % info.key

def call(**kw):
    inp = C.Input(**kw)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(120)
    s.connect(addr)
    s.sendall(inp.SerializeToString())
    s.shutdown(socket.SHUT_WR)
    buf = b""
    while True:
        d = s.recv(65536)
        if not d:
            break
        buf += d
    s.close()
    out = C.Output()
    out.ParseFromString(buf)
    return out

def preedit(o):
    return "".join(seg.value for seg in o.preedit.segment)

K = C.KeyEvent
sid = call(type=C.Input.CREATE_SESSION).id
call(type=C.Input.SEND_KEY, id=sid, key=K(special_key=K.ON))
for ch in romaji:
    o = call(type=C.Input.SEND_KEY, id=sid, key=K(key_code=ord(ch)))
print("typed  %-10s -> preedit %s" % (romaji, preedit(o)))
o = call(type=C.Input.SEND_KEY, id=sid, key=K(special_key=K.SPACE))
cands = [c.value for c in o.candidate_window.candidate][:5]
print("SPACE           -> preedit %s  candidates %s" % (preedit(o), cands))
o = call(type=C.Input.SEND_KEY, id=sid, key=K(special_key=K.ENTER))
print("ENTER           -> result %s" % o.result.value)
call(type=C.Input.DELETE_SESSION, id=sid)
ok = o.result.value == expected
print("PASS" if ok else "FAIL: expected %s" % expected)
sys.exit(0 if ok else 1)
