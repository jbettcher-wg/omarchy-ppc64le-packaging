# `nvidia-power9-v100`

NVIDIA 535.216.03 kernel modules (`nvidia`, `nvidia-uvm`, `nvidia-modeset`,
`nvidia-drm`, `nvidia-peermem`), prebuilt for `linux-power9-v100` and
installed to `/usr/lib/modules/<release>/extramodules/`.

Prebuilt rather than DKMS: the modules only work against the one kernel that
carries the NVLink patches, the three patches below are needed to build at
all on 7.x, and a DKMS build failing in a kernel transaction is exactly the
thing that should not happen on a box whose GPUs are its job.

- **Rebuild on every `linux-power9-v100` change** (bump `pkgrel`).
- Needs `nvidia-utils=535.216.03` — userspace and module versions must match
  or `nvidia-smi` refuses to talk to the driver. The top-level `nvidia-utils`
  recipe was bumped from 535.161.08 for this (and moved off the Debian
  tarball URL, which is gone, to NVIDIA's own `.run`).
- `provides=NVIDIA-MODULE`, conflicts with `nvidia-dkms`. `nvidia-dkms` from
  the `nvidia-utils` recipe ships **unpatched** source and will not build on
  `linux-power9-v100`.

## The patches

Against the `kernel/` directory of the pristine `.run`; each file's header has
the detail.

| | what |
|---|---|
| `0001` | `nvidia-uvm` ATS on POWER9 without the in-kernel NPU2 context API: enable UVM's own mmu_notifier, invalidate on `.release`, bounded ATSD wait, and hold the mm for coprocessor teardown. The last part fixes the oops in process exit that left GPU memory allocated after every killed job. |
| `0002` | Build system and core shims for Linux 7.x (lost `EXTRA_CFLAGS`, conftest dialect, renamed timer/irq helpers, `dma_map_ops.map_phys`). Not ppc64le specific. |
| `0003` | `nvidia-drm` against the 7.2 DRM API (`drm_atomic_commit` rename and friends). Not ppc64le specific. |

These are three consolidated diffs, pristine source to the working tree. The
development history (patches `0001`-`0014`, including one that was wrong and its
replacement) is in `~/Development/V100-POWER9-KERNEL/driver/` and
`FORWARD-7.x.md` there.

`modules-load.d` loads `nvidia-drm` (with `modeset=0`, the default) so
`/dev/dri/card*` and the render nodes exist. `nvidia-uvm` is loaded by
`nvidia-utils`.

## What has and has not been tested

- The patched source is the tree that ran on `7.2.9-npu` on 2026-10-04
  (4x V100, see `ours/linux-power9-v100/README.md`).
- From this recipe's inputs — pristine `.run` + the three patches — all five
  modules build against the `7.2.9-v100` tree with vermagic `7.2.9-v100`, and
  every conftest verdict is identical to the build that ran.
- **Not** tested: these exact binaries loaded. Two differences from what ran:
  the kernel config (see the kernel README), and the binary objects, which
  here come from NVIDIA's `.run` while the tested modules linked the objects
  from the RHEL 8 RPM packaging of the same version. Same release,
  different files.
- **Not** tested: building against the installed `-headers` package instead
  of a full kernel tree (conftest compiles a few hundred probes against it), and
  `makepkg` itself.
- `nvidia-drm` with patch `0003` as it is now (including the `FOP_UNSIGNED_OFFSET` fix) was swapped in on the
  running `7.2.9-npu` system on 2026-10-05 with CUDA jobs live: it loads on all four GPUs, `/dev/dri/renderD128`
  opens, and the `drm_open_helper` warning the first version caused is gone. That is the whole test: nothing
  has rendered through it.
- **Not** tested: `modeset=1` and any real display use of `nvidia-drm`.
