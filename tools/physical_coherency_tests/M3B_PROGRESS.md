# M3B production integration progress

## Resumed baseline: 2026-10-15

The user authorized merging the validated #380 integration into personal main and the #375
branch, and continuing yesterday's M3B work there. Both remote branches were fast-forwarded to
`105779d2c4`. The author of #380 supplied its Android device evidence; the user declined an
additional local device run. That decision does not provide device evidence for new M3B changes.

The prior F2/M3B branch at `80c4f4d7f7` was merged as `3e5b3228c3`. Its CPU CopyBlock snapshot,
host callback acknowledgement and candidate/negative-control tests remain intact. The sole
test conflict retained the #380 logging stub and acknowledgement include. Windows tests passed:
CopyBlock, preservation acknowledgement (three repetitions), 24 candidate cases (three repetitions)
and unmap alias preservation. None is a passing production F2 fixed-code witness.

## First production boundary: DMA method continuation

`DmaPusher::SetMethodAdmission` supplies a nonblocking GPU-thread preflight before scalar, inline
or non-incrementing batch effects, including `ConsumeSink`. False copies the unexecuted words
and parks the channel without consuming the rejected method. Its decoder state and original
command position survive retry. A callback is installed before the first submission and cannot
be replaced under queued or executing work. No real admission adapter is installed yet.

Existing `Control::Scheduler::RetrySuspended` retries the saved method on its original GPU
thread. The existing ThreadManager suspended-channel polling keeps servicing queue callbacks
and other channels. An unready admission does not wait under the channel scheduler guard.
This is a decoder boundary, not permission to replay an effectful draw or an entire command list.

`run_dma_admission_tests.py` compiles the actual DMA class/header/implementation and actual
channel scheduler, with fixture engines, guest command reads, Puller dependencies and Core/GPU
shells. Windows positive cases cover prefix retirement, blocked same-channel tail, independent
channel progress, increasing/non-increasing/increase-once/inline commands, immutable callback
installation and semaphore continuation compatibility. A control bypassing admission must fail
because the blocked method executes. The extracted-source manifest records the real inputs.
No actual driver, real physical admission, transfer visibility or production mapping pin is tested.

## Physical backing views and immutable plans

`HostMemory::PinPhysicalRange` materializes a complete bounded physical extent and returns a
`PinnedPhysicalMemory` retaining the actual shared Impl and backing epoch. The immutable extent
uses `backing_base`, never a remappable virtual alias. A retired epoch rejects new obligations
elsewhere, while already accepted views keep storage allocated; `OwnerAlive` and storage lifetime
are deliberately distinct. Moves/replacement of the HostMemory object must be excluded during
resolution by its owner; this API does not make concurrent destruction of a borrowed object safe.
Invalid/empty/overflowing extents return no view, and materialization failure precedes exposure.

Windows GCC standalone execution of the actual HostMemory implementation passes alias remap,
cross-page extent, moved owner/view, epoch retirement, backing replacement and final release
checks using real OS mappings. Only logging/assert formatting and unused dynamic-library filename
formatting are stubbed. The same runner additionally checks real lazy cross-chunk creation and
FD cleanup on Linux. These Linux checks subsequently passed in run `38674435729`. No CPU lookup
epoch, device/GPU representation pin or physical admission is connected by this storage API.

The prepared `PhysicalAccessPlan::Build` composes existing resolver snapshots with these real
pins. It validates exact ordered coverage, holes, extent bounds and backing identity before
materialization, then rechecks the snapshot under GPU-then-device mapping locks. Pin acquisition
runs outside those locks. If a mapping generation changed, the plan is rejected; an accepted
plan retains its original physical targets rather than re-resolving after a remap. Plans contain
no mapping-use lock. Resource owners retire after temporary validation locks, including rejection.
Windows tests use fixture mapping stamps with real allocations and exercise stale/retired stamps,
backing mismatch, invalid coverage/hole/overflow and retained split views. Engine footprint and
CPU first-registration adapters remain separate from this allocation ownership boundary.

The post-pin validation checkpoint also permits a controlled mapping change after pin acquisition.
Its Windows test rejects that stale plan. A negative control validates only before acquiring pins
and must fail by accepting the remap race. Linux additionally rejects a malformed suffix before
materializing any cold chunk; these Linux checks passed in the next remote run below.

Run `38672294519` on `41c6ce4ac3` finished with the complete Linux production/regression job
successful, including actual DMA/scheduler positive/negative controls and 24 candidate cases
(three repetitions). Android's complete compile error list contained one strict Clang lambda
capture shadow in the rejoined acknowledgement helper. Renamed its capture without changing
ownership/cancellation semantics; this fix accompanies the new storage/plan slice.

Run `38674435729` at `a6bc459af014e9b34542dd95df932c70b6a3567c` succeeded in both jobs:
real Android arm64 production libraries and complete Linux production/unit/HostMemory/coherency/
lifecycle validation. The Linux physical-pin tests include lazy cross-chunk publication, FD
cleanup, malformed-plan rejection before cold publication and the post-pin race negative control.

## GPU resolver adapter

`MemoryManager::PinPhysicalRanges` now composes the actual GMMU snapshot resolver with
`DeviceMemoryManager::PinGuestPhysicalRange` and `PhysicalAccessPlan::BuildWithPins`. The
device provider checks the exact backing epoch before obtaining a real HostMemory pin; the plan
builder checks returned epoch identity, physical offset and length, then validates the mapping
snapshot after all pins. No remappable guest virtual pointer is retained in the result.

`run_gpu_plan_tests.py` first runs the real pin/plan suite, then compiles the actual GPU map/unmap,
translation, resolver and pin methods plus actual device snapshot/translation/pin methods against
real HostMemory allocations. GPU/device PTE storage, manager shells, rasterizer notifications
and submapped enumeration remain fixtures. Windows checks pass noncontiguous and partial ranges,
real GMMU big-page translation, holes/empty requests, GPU remap at the post-pin checkpoint, device
remap, and old physical storage surviving both manager/arena exits. Input hashes identify seams.
This adapter has no active engine/cache consumer or data-admission privilege. Run `38676646541`
at `d6c593e4dfce3ae88f25b0e6d5a187caf3c314bb` passed both real Android arm64 production compilation
and the complete Linux production/unit/HostMemory/coherency/lifecycle suite, including the new
actual GPU-plan resolver tests and the pin/plan positive/negative controls.

## Engine register projection

`EngineInterface::ProjectPendingRegisters` validates the whole pending sink against register
bounds and the execution mask, then applies ordered writes to a register-array copy. It never
calls CallMethod/ConsumeSink, mutates committed state or drains the pending queue. MaxwellDMA's
`ProjectPendingState` exposes this projection for future footprint calculation; it does not
authorize the launch or infer page kind, memory layout, semaphore or remap effects.

Windows `run_engine_projection_tests.py` compiles the actual DMA register layout, constructor,
CallMethod/CallMultiMethod/ConsumeSinkImpl and projection. Launch is a side-effect spy; System
and MemoryManager are shells. Last-write ordering, idempotence, unchanged committed registers,
retained sink, equivalence with later real sink consumption, and execution/out-of-bounds rejection
pass. Omitting the execution mask produces an explicit failing negative control. Run `38678613933`
at `0eaedb5eb2e3f8d7b0aaa94f90400493cd61cd77` passed Android arm64 production compilation and the
complete Linux production/regression job, including this projection test and its negative control.
No active engine admission callback is installed, and production F2 remains unresolved.

## Restricted single-line DMA description

`MaxwellDMA::DescribeSingleLineCopy` projects pending registers without consuming the sink and
accepts exactly one non-pipelined, virtual-addressed, single-line launch encoding. Additional
semaphore, interrupt, remap, physical-address, multiline, reduction and reserved bits are rejected.
Zero lengths, extents above 32 MiB, upper address bits beyond 40 bits and overflowing extents are
ineligible. The limit bounds future page-plan construction; it does not limit existing execution.

The description carries logical addresses/length and conservative 512-byte group coverage for
both plain copies and Launch's pitch/block-linear 16-byte block permutation. This coverage is
for synchronization only, never exact dirty publication. PageKind/layout eligibility, mapping
stability and GPU representation ownership still need separate proof. This API neither installs
an admission callback nor changes Launch behavior, and does not describe a whole NI batch.

Windows extraction tests compile the actual descriptor with the actual DMA register layout and
pure projection. Tests pass flag rejection, source/destination bounds, exact 40-bit endpoint,
32 MiB boundary, unchanged sink/Launch spy, and exhaustive offsets with cross-group permutation
coverage. Launch remains a spy, not real DMA or driver execution. The execution-mask negative
control still fails as required. Run `38680939033` at
`5a072182e71107de384a38249ca0ebf8b7791fba` passed both Android arm64 production compilation and
the complete Linux production/regression job, including descriptor/projection positive and
negative controls. F2 remains unresolved.

## Joint source/destination storage preparation

`MemoryManager::PinPhysicalCopyRanges` resolves both extents, requires matching GPU/device/
backing identities, builds real storage pins outside mapping locks, then revalidates BOTH
snapshots under one GPU-then-device lock pair after all pins. A mapping change after either
individual build rejects the entire pair. Accepted plans retain their original storage after
later remaps; no mapping-use lease is retained, and their future use still requires admission.

`MaxwellDMA::PrepareSingleLineStorage` composes the pure restricted description with this real
pair adapter for its conservative source/destination coverage. It does not consume the sink,
call Launch, preserve cache contents, acquire GPU representation ownership or authorize access.
The returned logical length is distinct from synchronization coverage. PageKind/layout
eligibility and exact publication remain unresolved; no execution callback is installed.

The Windows real GMMU/HostMemory runner checks paired split/alias coverage, empty/hole rejection,
GPU and device remaps after both individual pin builds, and old physical view retention. Removing
the final joint validation produces the explicit `stale paired mapping accepted` negative control.
The combined runner additionally compiles the actual DMA projection/description/storage adapter
against those real extracted GPU/device resolver methods and real OS allocations; Launch is
still a spy and PTE storage/manager shells are fixtures. The smaller engine test checks exact
coverage arguments, unsupported-encoding rejection before resolution, failure propagation and
unchanged sink/Launch count. This preparation is not an executable DMA plan or an F2 repair.
Run `38683254478` at `8a0914f6ec054115b422e02753fbd4932b407dbd` passed both Android arm64
production compilation and the full Linux production/regression job, including combined DMA
storage preparation and the joint-validation negative control. This does not close F2.

## Next focus: DMA admission activation prerequisites

The user's 2026-10-15 review narrows the next activation milestone to the restricted single-line
DMA path. These are blockers for **activating admission**, not automatic merge blockers for inert
or test-only infrastructure. Current production execution remains unchanged for every unproved
path; no broader DMA eligibility is implied by storage-plan success.

| Risk | Current assessment | Priority |
| --- | --- | --- |
| Joint source/destination snapshot validation | Reasonable point-in-time design; not execution permission | Low |
| Remap after plan return, before execution | Requires old-plan/mutator admission contract | High |
| Physical coverage differs from representation footprint | No production representation admission established | High |
| Direct JIT/NCE bypasses controlled access | Still explicitly excluded | High |
| F2 first-cache-registration race | Not repaired in production | High |
| Shutdown lifecycle | Existing lock-order fixes retained; new pin/cancellation lifetime still needs proof | Medium |

### Representation ownership audit and required evidence

At `8a0914f6ec`, the actual Vulkan `Buffer` owns staged storage (`vk::Buffer`, views) and an optional
`unique_ptr<DirectGuestMapping>` containing the imported VkBuffer, memory and guest backing.
`BufferCache::DeleteBuffer` unregisters the representation, moves it from `slot_buffers` into
`DelayedDestructionRing`, and erases its slot. `DelayedDestructionRing::Tick` clears a ring slot;
`Flush` clears every slot. `BufferCacheRuntime::CopyBuffer` records raw source/destination
VkBuffer handles and copy geometry. Neither a BufferId, a captured raw VkBuffer, nor the current
HostMemory pin establishes ownership of a parked DMA representation. The existing destruction
ring is not evidence for an arbitrarily long parked-plan lifetime. This is a gap in the new
activation proof, not a claim that existing submitted-work lifetime management is broken.

The next implementation must provide real source/destination payload ownership across cache
replacement/unregistration, slot reuse, queued recording, submit, checked device completion and
Partial/Unknown/exit cancellation. Resource identity, physical-to-representation footprint and
generation must be immutable. A parked plan cannot keep a cache mutex, mapping-use lease or
whole-owner reservation; a reference-counted wrapper alone does not prove footprint/visibility.
Unknown completion must not release resources as if an exact successful tick had been observed.

### Staged Vulkan payload retention slice

The next production slice moves the real staged `vk::Buffer`/VMA allocation into
`StagedBufferPayload`; `Buffer` retains its ordinary owner through a shared pointer. A bounded
`StagedBufferPin` independently holds that same payload and immutable buffer-relative offset/
length. Pin construction rejects empty, absent and out-of-bounds extents. Live payload identity
is independent of a cache slot id. Moving a cache Buffer into the existing destruction ring,
erasing/reusing its slot, or clearing the ring cannot destroy that allocation while a pin exists.
The final owner runs the existing actual `vk::Buffer::Release` exactly once.

Only non-direct buffers expose this pin; direct/imported representations remain ineligible.
Conversion to direct storage clears old views and releases the cache's staged owner, while an
existing staged pin keeps its original VkBuffer. No texel-view ownership is promised: this pin
is scoped to DMA's VkBuffer payload, not arbitrary shader/image views. Existing Buffer lookup,
execution, cache registration, delayed retirement and submission policy stay in place; there
is no DMA activation or new pin consumer yet.

Windows `run_representation_pin_tests.py` passes actual owning Buffer fields/pin/implicit moves,
actual SlotVector and DelayedDestructionRing, actual payload and actual Vulkan RAII/Release,
with fake creation/device services and a fake VMA destruction callback. It checks slot reuse,
Tick/Flush, replacement, copies/moves, bounds and exactly-once final resource release. A negative
control retaining only the raw payload identity fails explicitly at ring retirement. This is
resource-owner retention evidence with a fake driver, not device execution/completion evidence.
The real production importer extraction also passes its success/failure/FD-ownership tests.

**Lifecycle proof remains partial.** Device/VMA allocator domains must outlive every pin; this
slice does not establish shutdown sealing or retain those domains. Physical/representation
footprint matching, cache-content preservation, immutable submit ownership, checked completion/
Unknown handling and cancellation remain activation blockers. A shared resource owner alone
does not close those contracts. The original F2 gate still reports backing 77/cache 10 and exit 1.
Remote Android/Linux compilation and regression evidence for this slice is pending.

### Required creation-to-execution order

1. Purely classify one supported launch and project pending registers without consuming effects.
2. Resolve/pin both physical storage ranges and validate them jointly; establish immutable,
   matching representation ownership and footprints. No data-access authority exists yet.
3. Order mapping-mutator intent and the old-plan request in the same admission domain. A mutator
   winning before plan acceptance must reject/reprepare the unexecuted plan; after acceptance,
   execution must use the accepted pinned targets with the required preservation ordering.
   Re-resolving current VA inside the existing Launch is not execution of the old plan.
4. Atomically TryStart source-read and destination-write ranges as one request, including physical
   aliases/overlap. Never retain a granted source while parking for its destination. CPU first
   registration and controlled stores must share this ordering domain to close the F2 gap.
5. On conflict park the unexecuted single-line method in the actual channel scheduler and return
   the GPU worker; independent preservation/release work must run. Retry the retained immutable
   request without replaying earlier effects or silently granting admission to legacy Launch.
6. Execute only the proved representation path, publish exact successful write extents, and
   retain resources/reservations until the defined visibility/completion or cancellation outcome.

Required deterministic production-adapter tests cover mutator-before-accept, remap-after-return,
mutator-during-park, representation replacement/slot reuse while parked, same-allocation
source/destination overlap, other-channel CPU dependency progress, no effected-prefix replay,
and shutdown/Unknown while parked or submitted. Existing real DmaPusher/Control::Scheduler
boundary tests are a prerequisite, not proof that this physical adapter is active. Use actual
mapping mutator methods and independently released CPU stores; keep explicit negative controls.

Keep the original F2 `backing=77`, `cache=10` failure assertion and its failing `--require-fixed`
gate. New infrastructure, candidate or scheduler-boundary passes cannot close that witness.

## Remaining production adapters and acceptance gates

1. Physical backing plans and the GPU resolver adapter are implemented. Add representation pins
   and the controlled CPU resolution adapter. Resolution may not hold a mapping-use lease across a parked
   channel. Revalidation cannot silently redirect an already accepted old plan to a new mapping.
2. Derive supported engine footprints without effectful decode. Pending `method_sink` register
   writes must be projected by pure resolution or otherwise bounded safely; running ConsumeSink
   to discover the footprint would precede this boundary and invalidate its pre-effect contract.
   Unsupported macro/NI batches, image layouts and unbounded footprints remain ineligible.
3. Join initially uncached controlled CPU stores and first cache registration with the same
   linearizable epoch handshake. Acquire a stable view before a store and publish exact successful
   extents afterwards; failed CAS publishes nothing. CopyBlock stays outside the transaction.
4. Install range admission outside cache/PTE locks, compose old-plan preservation and mapping
   mutation in a consistent owner order, and reject conflicting inline reentry without self-wait.
5. Connect real transfer visibility, checked completion/failure acknowledgement, resource retention
   for Partial/Unknown and cancellation/sealing before manager/renderer destruction. Callback
   completion alone is not Vulkan completion; suspended external dependencies cannot retain
   broad data admission that blocks their required CPU producer.
6. Run protected-path F2 tests with independent CPU-store release and GPU-attempt rendezvous,
   retaining stale-byte assertions and old-code controls. Existing five F1/F2 witnesses still
   characterize the unprotected production path. Candidate passes are not fixed-code passes.

F1 native/NCE access, direct JIT fastmem, raw/kernel pointers, F3 and image/buffer authority are
still outside this controlled-path work. Do not activate a cache-local blocking mutex to bypass
the queue-cycle counterexamples in `M3B_F2_IMPLEMENTATION_REPORT.md`.
