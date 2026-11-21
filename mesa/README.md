# `mesa`

Arch's recipe (1:26.3.1-2) with `powerpc64le` added. On x86_64 it builds
exactly what Arch builds; every change is behind `CARCH == powerpc64le`.
Rebased onto Arch on 2026-11-21 for the LLVM 23 wave. Until then the recipe was
Arch POWER's (big-endian patch, `-g1`, 32-bit and `espresso` arches, docs off),
which we no longer track.

## Deviations on powerpc64le

- **Drivers: the GPUs a POWER box can hold.** `gallium-drivers=all` and Arch's
  Vulkan list are rewritten in `build()` to
  - gallium: `r300,r600,radeonsi,crocus,i915,iris,nouveau,svga,virgl,llvmpipe,softpipe,zink`
  - vulkan: `amd,intel,intel_hasvk,swrast,virtio,nouveau,gfxstream`
  - rusticl: `radeonsi`

  Dropped: the SoC GPUs (asahi, freedreno, panfrost, v3d/vc4, etnaviv, lima,
  tegra, imagination/PowerVR), the NPUs (rocket, ethosu) and d3d12/dzn, which
  is D3D12 interop for WSL. `freedreno-kmds` goes to its default and
  `panfrost-virtio` off, since neither driver is built. Intel's integrated-only
  drivers (crocus, i915, intel_hasvk) are kept so the `vulkan-intel` split
  stays Arch's; they find no device on POWER.

  `_ppc64le_opt` replaces each value in place and **fails the build** if the
  value it expects is not there. So when Arch edits these options, the build
  stops instead of quietly building `all` on POWER.
- **Packages:** `vulkan-asahi`, `vulkan-broadcom`, `vulkan-dzn`,
  `vulkan-freedreno`, `vulkan-panfrost` and `vulkan-powervr` are dropped from
  `pkgname`, and `_pick` skips their files. The other 11 packages match Arch's.
- **`mesa-radv-vm-pad-host-page-size.patch`:** RADV reserves and maps the
  `VM_PAD_1PAGE` padding as 4096 bytes, but rounds every VA operation to the
  host page size. With 64 KiB pages the pad mapping overruns. Ours since
  26.2.2-3. It is still needed in 26.3.1, where it applies at offset 3. Not
  POWER-specific: any 64K-page kernel (arm64 too) hits it.
- **`mesa-gcc16-missing-includes.patch`:** adds `<cstddef>` to the intel
  compiler and `<limits>` to r600's sfn. GCC 16 no longer supplies them
  transitively. It is still needed in 26.3.1 and was refreshed to apply
  without fuzz. Not POWER-specific.

## Notes

- `-D power8` no longer exists in 26.3: meson detects POWER8 intrinsics on
  ppc64le by itself (`meson.build`, "POWER8 intrinsics") and defines
  `_ARCH_PWR8`. The old recipe passed it explicitly.
- `intel-rt` stays enabled as Arch has it. Since 26.x meson only requires a
  64-bit target; Arch POWER's recipe disabled it.
- `html-docs` / `mesa-docs` are back. Arch POWER now has
  `python-sphinx-hawkmoth` 0.22.
- New makedepend `venus-protocol` (1.1.3, `arch=any`). It was not packaged
  for ppc64le anywhere, so we import Arch's recipe beside this one.
- Arch's `directx-headers` makedepend stays as it is: Arch POWER builds it,
  and staging an unused header package costs nothing.
