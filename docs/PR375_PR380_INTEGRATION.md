# PR #375 / #380 integration roadmap

## Baseline and scope

- Integration branch: `codex/pr375-pr380-integration`.
- Start: PR #375 head `3de1870c78babbdb934c875268fb49b43e5d3458`.
- Upstream: PR #380 merge `57b1925f51f450759439603410333c85abf7becc`.
- Keep coherency, source snapshots, physical-shadow diagnostics and explicit GPU shutdown
  boundaries while incorporating upstream translation and synchronization changes.
- Keep the eight newer local F1/F2 commits, including candidate admission, out of this branch.
  Production F1/F2 are not solved by this integration.

## Ordered work

| Order | Module | Required result |
| --- | --- | --- |
| 1 | `host_translate_info.h` | Keep independent bindless and passthrough fields. |
| 2 | `maxwell_dma.cpp` | Keep upstream remap support and local M0 source snapshots. |
| 3 | `buffer_cache.h` | Combine submission ticks/barriers with `EndGuestCpuAccess`; preserve scatter readback. |
| 4 | `vk_rasterizer.cpp/.h` | Keep physical-shadow scope and deferred WAIT_FOR_IDLE. |
| 5 | `renderer_vulkan.cpp` | Keep drain/join ordering; scope `submit_mutex` away from worker joins. |
| 6 | `host_memory.cpp` | Reconcile lazy sparse fd publication and VMA merging with an explicit validation boundary. |

## High-risk module: HostMemory

HostMemory requires dedicated Linux/Android validation before claiming concurrent dma-buf
remapping safe. A successful Windows compile cannot establish that property.

Required invariants and checks:

- Discover lazy fd identity when a chunk is published, including out-of-order sparse slots and
  mixed exported/memfd fallback backing. Do not assume a fixed array or stop at the first hole.
- Distinguish the stable physical `backing_base` view from remapped guest virtual aliases.
  An allocation pin alone does not protect a borrowed virtual alias from remapping.
- Make layout/fd metadata lock ordering explicit. Do not perform GPU waits under these locks.
- Stop and join the mapping sampler before freeing its state, backing or file descriptors.
- Exercise concurrent Map/Unmap/Protect, merge pressure, borrowed pointer accesses, failure
  fallback and shutdown on an appropriate target. Until proved, do not enable background
  MAP_FIXED merging over active guest aliases in the lazy path.

## Other semantic gates

- Upstream replaces the old NCE null-wrapper recovery with Core::Memory instruction emulation.
  This differs from the separate host ARM64 register guards; document the adopted behavior and
  retain the host guards. NCE signal behavior requires target validation.
- `WriteBlockUnsafe` hole reporting is not a preservation transaction: do not interpret it as
  callback completion, immutable destination identity or complete physical publication.
- Preserve GPU emulation, recording, fencing, pipeline and presentation shutdown boundaries.
- Do not overwrite main, PR #375 or the F2 branch merely to clear GitHub conflicts.

## Acceptance evidence

Record compilation, focused regression results, source revisions and environment limitations
here after integration. A clean merge is only the first check; distinguish a real production
build from extracted-source tests and from Linux/Android/device execution.

Status: roadmap recorded before conflict resolution; integration and validation in progress.
