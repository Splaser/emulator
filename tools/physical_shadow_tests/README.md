# M1: observation-only physical shadow registration

Baseline: M0 `3c1aae0f0f`. This is a bounded **historical range observation**
window, not a live producer registry or Physical Coherency Coordinator. Enabling
it does not fix alias bugs, authorize dispatch, select a fallback, add data
versions, copy bytes, create/import backing, issue GPU commands or change dirty
tracking. Phase 2/3 imports, UMA, scatter and eight-frame retirement are unchanged.

## Enable and read

Default off on every platform: renderer advanced setting
`physical_coherency_shadow=true`. Restart the renderer/application after changing
it; it is latched at renderer construction. Set log filter to include
`Render_Vulkan:Info` temporarily. No Android UI control is introduced. The existing
configuration serialization handles this registered setting.

Logs appear after every 4096 observed draw/compute preparation attempts and at
normal renderer shutdown. An exception during configuration ends the measurement
scope as a preparation attempt; counts are **not successful/submitted/completed
dispatch counts**. Abrupt Android process termination may lose final statistics.
Counters are cumulative per renderer, not per guest arena/game across renderers.

Metrics:

| Counter | Meaning |
| --- | --- |
| `queries`, `query_ns` | Resolver attempts and elapsed time including lock contention/errors |
| `max_dispatch_queries`, `max_dispatch_query_ns` | Largest query count and aggregate resolver time in one preparation |
| `observer_ns`, `max_dispatch_observer_ns` | All Observe calls including lookup, provenance walk, validation and geometry comparison; excludes visitor iteration/logging |
| `validation_ns` | Cache validation plus fresh DAddr provenance capture time |
| `hits`, `cache_invalidations` | Valid cached stamp reuse versus stale stamp; invalidation rate = invalidations / (hits + invalidations) |
| `snapshot_invalidations` | Fresh resolve became invalid before paired-lock provenance capture; denominator is queries |
| `outside_dispatch_queries` | Texture producer marks outside observed draw/compute configuration (e.g. copy/clear) |
| coverage by `buffer/scratch/texel/texture` | Observation/write-intent counts; successful full-range registration; unregistered write intents; unresolved observations including reads |
| coverage `bytes/max_range/size_buckets` | Descriptor/event-weighted requested range distribution, including unresolved attempts; bucket edges are 64 B, 1 KiB, 16 KiB, 64 KiB, 256 KiB, 1 MiB, 16 MiB (upper bucket includes edge) |
| coverage `segments/split_observations` | Registered physical segment sum and multi-segment observation count; multi-segment includes chunk boundaries, not only noncontiguous mappings |
| `aliases`, `different_daddr`, `different_manager` | Repeated overlap encounters in bounded historical window; not unique aliases/conflicts or live resource counts |
| `holes`, `provenance_mismatches` | Failed/hole-containing physical resolution; cached resource DAddr inconsistent with current GPU translation |
| `budget_drops`, `comparison_drops`, `evictions`, `errors` | Sampling/coverage loss; these must accompany any interpretation of alias counts |

An entire range must resolve before registration. Hole-containing ranges are
unresolved even if some segments resolve. No partial producer registration.
Physical segment coordinates remain `(backing epoch, physical offset, length)`;
GPU VA and DAddr are provenance, never the physical key. Chunk index is derived
from physical offset, not a new identity. Generations only validate observations.

## Production call chains and coverage limits

Graphics: `RasterizerVulkan::PrepareDraw` -> pipeline Configure -> existing buffer
preparation/binds -> `ObservePhysicalBindings(false)` before draw recording.
Compute: DispatchCompute -> Configure -> `ObservePhysicalBindings(true)` before
direct/indirect dispatch recording. Visitor only reads prepared bindings/masks;
it never calls FindBuffer, GatherBuffer, ResolveScatter or synchronization APIs.

- Enabled graphics/compute uniforms and SSBOs: resolved GPU logical ranges.
- Gathered uniform/storage: whole prepared gather allocation including scatter
  padding. Classified as scratch unless existing allocation is directly shared.
  Shared allocation observations may repeat once per descriptor; not unique producers.
- Enabled image/texel buffer views: actual cached contiguous DAddr checked against
  the current resolved GPU footprint. Both share the texel coverage category.
- Ordinary texture producers: existing private `MarkModification(ImageBase&)`,
  reached from storage-image descriptors, render-target PrepareImage, and texture
  copy/conversion preparation. Observes the entire guest allocation bounding
  range, **not an exact subresource/layout write mask**. Repeated marks are intents,
  not evidence a GPU write executed or completed.
- Transform feedback: present bindings are counted as unresolved write intents
  because current binding metadata does not retain GPU VA. No guessed identity.

Texture identity uses the cached image's GPU VA only when its translation still
matches the image's actual contiguous DAddr extent. Sparse textures, image reuse
across channels, remaps or stale originating GPU VAs can be unresolved; the
observer does not invent a current address for these resources. Texture extent
overlap includes padding/mips/tiling and can overestimate actual write overlap.
GPU VA retained by descriptors does not by itself prove a cache resource's
contents are fresh. Identity registration never asserts that fact.

CPU/NCE/kernel raw pointer accesses, query cache producers, DMA/inline buffer
writes, upload staging and internal texture alias copies/scale operations that do
not pass MarkModification are **not instrumented**. They are explicit unregistered
producer categories, but cannot be numerically counted by these hooks. The
write-intent denominator covers only instrumented hooks; it is not a global
coverage percentage. Vertex/index/indirect read consumers are also not visited.
This stage cannot prove complete coherency coverage or absence of aliases.

## Snapshot, locking and lifetime

Use the existing 3.5A production `ResolvePhysicalRanges`. On a fresh result,
lock that snapshot's GPU page-table token, then device mapping token. Check both
generations and lifetime before walking pure GpuToCpuAddress into DAddr spans.
The physical result and DAddr provenance therefore existed together under one
matching stamp. Reject stale/odd generations; don't combine separate remap epochs.
On cache reuse validate the same paired tokens before using saved provenance.

Locks release before comparing geometry or returning. Remaps may occur afterward:
these are historical observations, not mapping-use leases/GPU execution admission.
Comparison intentionally includes historical mappings, even if no longer live;
different-DAddr witnesses are checked within overlapped physical page slices.
Different managers are distinguished by shared GPU mapping token identity, not VA.
Distinct backing epochs never alias. No page table/object pointer is retained.

Observer is GPU-thread confined and hooks execute with existing cache locks.
Final shutdown report acquires both cache locks, detaches the borrowed texture
diagnostic pointer, and the diagnostic member outlives cache destruction. It owns
only vectors and inert shared mapping/backing tokens, no guest arena/import leases.
Caught observation/logging exceptions only reduce telemetry coverage; they never
escape into GPU execution. No CPU read, scheduler wait or nested GPU callback.

## Bounded cost and validation

128 range entries; at most 64 MiB/query, 256 physical/DAddr spans per retained
entry, 4096 geometry/page comparisons per observation. Eviction is a ring, not a
live resource retirement decision. Cache lookup is O(128); compare cost is bounded
but can be significant when enabled. Resolver plus DAddr page walks are O(pages),
including every mapped segment. Cache hits still acquire both mapping locks.
Whole-address-space generations may invalidate otherwise unchanged ranges; M1
measures that cost before any per-range generation optimization. Resolve can
temporarily allocate more than 256 segments before this observer applies its cap.
No diagnostic objects are allocated when disabled; only optional/pointer branches
are added to the paths. No per-dispatch process-wide fd/VMA scanning or GPU stall.

```sh
python tools/physical_shadow_tests/run_tests.py --cxx g++
```

Tests use the production observer and extracted production binding visitor,
texture producer hook, GMMU/resolver/device snapshot functions. Tables/cache
objects are fixtures. They cover different-DAddr/manager physical aliases,
partial ranges, mixed buffer/scratch/texel/texture coverage, scatter padding,
whole-AS/device generation invalidation, mixed-snapshot rejection, stale texture
provenance, holes, bounds, OOM containment and fixed metadata capacity. They do
not execute Vulkan/NCE or constitute device cost/coverage measurements.

Available-platform validation: new suite passes Windows MinGW and Linux GCC;
Linux ASan/UBSan passes. All nine existing gather/scatter runners pass on both
platforms, including CPU-write, unmap preservation, GPU-stop and mixed binding
alias tests. Production resolver and M0 suites pass Linux (M0 also Windows).
Actual vk_rasterizer.cpp compiles on Linux with real manager/cache headers and
isolated logging/assert/platform shims; not a full Android link/build. Shimmed
logging does not validate runtime log output. No local Android full build.

Workflow APK and SMU/SMO diagnostic sampling are the next validation step. Record
all counters above and an off/on same-scene comparison before choosing M2 data
structures. In particular don't interpret import reuse or successfully registered
geometry as GPU/NCE concurrent access safety.
