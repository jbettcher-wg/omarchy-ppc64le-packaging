# kicad-mcp — Omarchy ppc64le

[HackInvent/kicad-mcp](https://github.com/HackInvent/kicad-mcp) has two parts:

- a KiCad 10 IPC plugin with **Start/Stop MCP server** buttons in the PCB
  editor;
- the `kicad-mcp` CLI, for MCP clients that use stdio.

Both drive the open board through KiCad's official IPC API.

**Source.** It is not on PyPI and has no tags. The recipe pins commit
`ad60d6d`, which `pyproject.toml` calls 0.3.1.

## Layout

| Path | What |
|---|---|
| `/usr/lib/python3.*/site-packages/kicad_mcp` | the server, from the wheel |
| `/usr/bin/kicad-mcp` | `serve` / `status` / `stop` |
| `/usr/share/kicad/plugins/org.hackinvent.kicad-mcp/` | `plugin.json`, `start.py`, `stop.py`, `requirements.txt` |

**Plugin directory.** KiCad 10 scans that directory as its system plugin path.
Its log line is "Manager: scanning system path (%s) for plugins".

**No bundled copy of the server.** Upstream's installer and PCM archive put a
copy of `kicad_mcp` next to `start.py`. Here it is imported from
site-packages instead. KiCad creates each Python plugin's venv with
`--system-site-packages` (a string in `libkicommon`), so the plugin sees it.

**No downloads at runtime.** KiCad then runs `pip install -r requirements.txt`
in that venv. The system packages satisfy all three requirements:
`python-kicad-python` 0.7.1, `python-mcp` 1.30.0 and `uvicorn`. So nothing is
fetched from PyPI. `build()` checks this offline with `pip install --no-index
--dry-run` in such a venv.

## Patch

`kicad-mcp-protobuf7.patch`: protobuf 7 removed `FieldDescriptor.label`, which
was deprecated in favour of `is_repeated` / `is_required`.
`_validate_footprint_coordinates` used it, so against the system
`python-protobuf` 7.35.1 every footprint move failed with `AttributeError`.
That caused 12 failures in upstream's `tests/test_bridge.py`. The fix is one
line and is worth sending upstream.

## Dependencies added for this package

| Package | Version | Arch | Notes |
|---|---|---|---|
| `python-kicad-python` | 0.7.1 | any | wrappers regenerated for protobuf 7 (its README) |
| `python-pynng` | 0.9.0 | per-arch | AUR import, linked to the system nng instead of a bundled nng + mbedtls |
| `python-mcp` | 1.30.0 | any | held at 1.x; kicad-mcp pins `mcp<2` |
| `uvicorn` | 0.54.0 | any | |
| `python-httpx-sse` | 0.4.3 | any | |

## Checks in build()

bq builds with `--nocheck`, so the checks run in `build()`:

- upstream's pytest suite, with simulated editor and CLI against real kipy
  objects;
- `kicad-mcp --help`;
- the offline requirements check above.

The KiCad GUI path — the plugin buttons appearing and the server answering a
client — still needs a manual run.
