# `linux-power9-v100`

A kernel for exactly one machine shape: an IBM AC922 (8335-GTG/GTH/GTX,
POWER9 powernv) with Tesla V100 SXM2 modules on NVLink 2.0. It exists because
mainline removed the powernv NPU2/NVLink code in 5.13 and NVIDIA's ppc64le
driver stopped at the 535 branch, so nothing newer than RHEL 8's 4.18 can
drive these cards without the patches here.

| pkgbase | pkgver | splits | page size |
|---|---|---|---|
| `linux-power9-v100` | `7.2.9_v100` | `-headers` | 64K |

It installs next to `linux-power9` / `linux-power9-64k` (different pkgbase,
`uname -r` is `7.2.9-v100`). `linux-power9` stays the general kernel: amdgpu,
Nova/Nouveau, Rust. This one drops those and carries the NVLink restore
instead. The modules are a separate recipe, `ours/nvidia-power9-v100`.

64K pages only: that is what every AC922 + V100 stack was ever run on (RHEL),
it is what the port was debugged on, and the driver's ATS path shares the
process's radix page tables with the GPU.

## The patches

Applied in `source=()` order. The first group is `linux-power9`'s set, copied
unchanged; the `v100-` group is what makes the GPUs work.

| | what | disposition |
|---|---|---|
| `0001`-`0005`, `0007`, `0009` | Same files as `ours/linux-power9` (xHCI Promontory quirks, the three powerpc syscall/interrupt exit fixes, `max_pfn` vs ZONE_DEVICE, amdkfd NUMA). See that README. | as there |
| *(no `0006`)* | The `eeh_rmv_device()` self-deadlock fix is already in 7.2.9. | upstream |
| *(no `0008`)* | Rust enablement. Only wanted for Nova, which this kernel must not build. | not applicable |
| `v100-0001` | Restores `arch/powerpc/platforms/powernv/npu-dma.c` and its hooks: NPU2 PHB setup, the per-GPU OPAL NPU context armed at boot (`pnv_npu2_map_lpar_dev()`), and the `ibm,gpu`/`ibm,npu` device tree links. Forward port of what 5.12 had. | local; upstream removed it on purpose |
| `v100-0002` | Exports `opal_npu_map_lpar`, `opal_npu_init_context`, `opal_npu_destroy_context`, `opal_npu_spa_setup`/`clear_cache` for the module. | local |
| `v100-0003` | Restores `pnv_npu2_unmap_lpar_dev()`. | local |
| `v100-0004` | Adds `pnv_npu2_destroy_pasid()`. **Has no caller any more** (the driver patch that used it was wrong, see below); kept so the conftest probe and export stay stable. Drop on the next rebase. | local, dead |
| `v100-0005` | `__vma_start_write` back to `EXPORT_SYMBOL`. `nvidia.ko` reaches it through the inline `vm_flags_set()`; GPL-only makes the module unloadable. | local workaround |
| `v100-0006` | Do not let a module inherit the proprietary taint from a symbol's exporter. With it, `nvidia-uvm` (dual MIT/GPL) lost access to GPL-only symbols as soon as it used one symbol from `nvidia.ko`. | local workaround |
| `v100-0007` | `pbus_size_mem()`: reserve at least one alignment unit per large window. Without it the bridge window above the four 32 GB BARs came out one alignment short and **two of the four GPUs got no BAR1** ("nvtop sees a couple of devices"). | PCI sizing bug, probably upstreamable |
| `v100-0008` | `pnv_eeh_probe()`: skip NVLink NPU "devices" that have no PE. Without it any config-space scan (`lspci`, `nvtop` start) made EEH freeze and then *remove* the NPU links, taking NVLink down until reboot. | local, tied to `v100-0001` |
| `v100-0009` | `powernv-cpufreq`: turn boost (WOF / ultra-turbo) on by default. 7.2.9 registers the boost attribute off, capping an AC922 below its ultra-turbo frequency (3.8 GHz on the test box). **Not V100 specific**: `linux-power9` will hit the same thing when it moves past 7.2.6. Workaround without the patch: `echo 1 > /sys/devices/system/cpu/cpufreq/boost`. | regression, upstreamable |

## The config

`config` is `linux-power9`'s `config.64k` (7.2.6) taken through
`make olddefconfig` on 7.2.9, with:

- `CONFIG_LOCALVERSION="-v100"`
- `CONFIG_RUST`, `CONFIG_NOVA_CORE`, `CONFIG_DRM_NOVA`, `CONFIG_DRM_NOUVEAU`
  and everything under them **off**. Nothing in-tree may bind `10de:1db5`;
  `prepare()` fails the build if any of the three comes back.
- `CONFIG_DRM_AST=m` (was off). The AC922's only display is the BMC's AST2500.
- `CONFIG_GCC_PLUGINS` / `RANDSTRUCT` choices dropped out with Rust; one new
  7.2.9 symbol (`GROUP_SCHED_BANDWIDTH`) took its default.

The tracked file still carries the Red Hat toolchain strings
(`CC_VERSION_TEXT`, `LD_VERSION`) of the box it was generated on.
`olddefconfig` in `prepare()` rewrites them; they are not choices.

## What has and has not been tested

Tested, on an 8335-GTG with 4x V100-SXM2-32GB (2026-10-04):

- The **patch set** `v100-0001`..`0009`, as kernel `7.2.9-npu`: all four GPUs
  enumerate with NVLink up, CUDA across 2 and 4 GPUs, repeated
  start / kill / restart of GPU jobs with memory returning to 0 MiB,
  `lspci`/`nvtop` safe, ultra-turbo back, `nvidia-drm` loaded.
- **This recipe's sources**: the sixteen patches apply to pristine
  `linux-7.2.9.tar.xz` with no fuzz, and that tree with this `config`
  compiles clean (0 warnings, 508 modules) to release `7.2.9-v100`.

Not tested:

- **This config has never been booted.** `7.2.9-npu` ran on its own
  config (`/boot/config-7.2.9-npu` on the test box), not one derived from
  `config.64k`. The patches are the
  same; the option set around them is not.
- `makepkg` itself. The recipe was written on an AlmaLinux host without
  pacman; `prepare()`/`build()`/`package()` were checked by `bash -n` and by
  running the same commands by hand, not by a real package build.
- Anything on a Talos/Blackbird or any non-NVLink machine. It should behave
  like `linux-power9-64k` minus Nova there, but there is no reason to install it.

## Known issues

- GPUs report a 163 W power cap where 4.18 gave 220 W. Unexplained; may be
  OCC/firmware rather than kernel.
- Model load to the cards looked somewhat slower than on 4.18. Not measured.
