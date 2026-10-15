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
Run `38692337709` at `cc324dff81303649e9385c2dd271424be3604c31` passed Android arm64 production
compilation and the full Linux production/regression job, including staged payload ownership
and raw-identity negative controls. This is not a full device-domain lifetime proof or F2 repair.

### Shutdown seal (after cc324dff81)

Each runtime now prepares a monotonic `StagedBufferPinDomain` shared by its staged payloads.
`RasterizerVulkan::Shutdown` seals that domain after taking exclusive producer exclusion and
before releasing the shutdown guard for pipeline/fence/recording drains. Runtime destruction
seals it again as a fallback. Seal performs no wait and releases no Vulkan resources. New pin
acquisitions observing the seal reject; existing pins stop exposing a usable VkBuffer through
Handle/IsUsable while retaining their payload until the final owner releases it. A creation
racing seal may finish with an unusable pin if its acquisition check preceded seal.

Windows tests pass the actual runtime seal method and payload domain, rejection after repeated
seal, handle invalidation without early VMA destruction, and exactly-once final release. A
missing-seal negative control explicitly accepts a post-shutdown pin and fails. Actual extracted
renderer shutdown orchestration also passes its producer-exclusion/order assertion and existing
recording, presentation, fence, turbo and completion-worker drain tests. Importer tests still pass.

This is cancellation of future handle lookup, **not a complete device-domain lifetime proof**.
Previously extracted handles and submitted commands are not revoked. No outstanding resource
may outlive the real Device/VMA allocator; this slice does not enforce final-pin drainage or
connect parked-plan cancellation/Unknown completion to that boundary. It deliberately does not
force-free old payloads at seal or reinterpret callback return/unchecked WaitIdle as completion.
There is still no active DMA admission consumer and the original F2 failure remains open.
The cc324dff81 native run finished successfully before this slice was submitted. Run
`38694742732` at `be4eb320115a9d4699d198270de8d3cc60b12344` passed both Android arm64 production
compilation and complete Linux production/regressions, including seal/ownership negative controls
and actual renderer shutdown/drain tests. The remaining activation gaps above are unchanged.

### Existing-cache physical correspondence

`BufferCache::PinExistingDmaRepresentation` now exposes a pure, existing-buffer-only preparation
query for pin-capable backends. The caller retains the cache mutex and device/backing/renderer
owners on the GPU/cache thread. It rejects empty/out-of-range requests, missing/null/stale cache
ids, partial buffer coverage, inconsistent cache-page ids, active scatter and any pending gather
scatter. It never invokes FindBuffer, creates/merges buffers, synchronizes contents, resolves
scatter, publishes dirty state or issues GPU work. Direct/imported pins remain rejected by the
actual Vulkan Buffer pin API; unsupported backend pin types are not instantiated.

The pure `MatchesDevicePhysicalPlanLocked` compares EVERY relevant device page with the ordered
physical spans retained in the supplied plan, including exact backing epoch identity and range
bounds. Empty/moved-from plans cannot pass. After this device snapshot check, the query obtains
the actual buffer-relative Vulkan resource pin outside the mapping lock, then checks the device
epoch/generation again. A remap during resource acquisition rejects the query. Cache locking
and mapping locks are not retained in the returned resource pin. An old GVA plan is compared
against its original physical targets, not redirected by a later GVA retranslation.

`run_cache_representation_tests.py` composes the preceding suites' hash-checked generated actual
GMMU/device/HostMemory and Vulkan Buffer/payload/RAII inputs with the actual cache lookup/pin
method and page-id checks. Cache/PTE table storage, registration, VMA/device services and the
post-resource-pin rendezvous remain fixtures. Windows checks pass split-page physical matching,
changed interior PTEs, different backing epochs, resource-acquisition remap, old GVA targets,
missing/stale/reused cache slots, partial coverage, pending-scatter refusal, moved-from rejection,
and domain seal. Removing the physical comparison explicitly accepts mismatched storage; removing
the final generation check explicitly accepts the post-pin remap. Both negative controls fail
as required. The workflow runs this suite after both input generators; stale source hashes reject.

**This proves current address correspondence, not historical registration/content authority.**
It does not prove the buffer was populated from this physical allocation, join first-registration
epochs with CPU stores, preserve old contents across a mutator, establish layout eligibility,
atomically admit source/destination, execute the pinned resource path, or drain the final pin at
shutdown. The supplied physical plan and returned representation pin must remain paired by a
future adapter with those contracts. No production admission consumer is installed, all ordinary
DMA execution remains unchanged, and the original F2 gate still fails with backing 77/cache 10.
Run `38698088610` at `f1cd4d870169ad865820ad1e9c31353626ec9f2e` passed both Android arm64
production compilation and the full Linux production/regression job, including correspondence
and post-resource-pin remap positive/negative controls. The content/registration gap remains open.

### Backing-owned range ordering groundwork

The next slice gives each real `GuestBackingEpoch` one `PhysicalRangeAdmission` metadata domain.
Arena retirement seals that domain before marking the epoch dead. Ordinary CPU/GPU access does
not enqueue requests yet, so this does not change existing access eligibility or close F2.
The domain is shared by the actual allocation identity, not a cache slot, VA or test dispatcher.

Ready logical segments enqueue bounded immutable read/write intervals and retained resources
outside cache/PTE locks. `TryStart` grants ALL intervals atomically or parks with NONE granted.
Earlier conflicting pending requests order later ones; shared readers and disjoint scopes can
proceed. Inline conflicts are rejected through an explicit execution-scope chain, including an
outer same-domain scope hidden beneath a different nested domain. Tickets retain domain identity
to avoid stale-owner ABA. There are no worker threads, queue pumps, GPU waits or owner-wide leases.
Only ready segments may enqueue: pending requests must not conceal unresolved external dependencies.
Preparation/capacity/seal failure is never authorization to fall through to an unguarded access.

`EnqueuePhysicalCopyAdmission` prepares a real physical-copy bundle on its exact backing domain:
source segments read, destination segments write, with actual source/destination storage and the
supplied GPU representation owners retained together. It rejects empty/moved/mixed-backing plans,
dead epochs, missing representation ownership and unsupported fragmentation (64 intervals maximum).
The metadata queue is bounded to 256 requests. It does not certify representation contents or
match that opaque owner to its physical footprint; the real adapter must supply that proof.

Pending requests can cancel; seal cancels them without releasing resource owners under the
metadata mutex. Running/Unknown obligations retain resources. Unknown conservatively quarantines
the request's physical footprint, including readers, while permitting disjoint work. No recovery
API pretends to supply device quiescence: Unknown cannot be completed/cancelled by this slice,
and its unresolved resources intentionally remain retained. `Complete` is an explicit caller
obligation after real completion/visibility or proof of no effects, not a Vulkan completion signal.

Windows `run_physical_admission_tests.py` composes the actual domain, actual physical-copy builder,
HostMemory and preceding GMMU/cache/Vulkan-owner fixture inputs. It passes atomic source/destination
parking, opposite-copy concurrent TryStart, ordered readers/writers, real storage bytes with an
independently released CPU producer, aliases, nested reentry, foreign identities, bounds/capacity,
resource-destructor reentry after unlock, arena retirement and Unknown quarantine. CPU store,
registration and memcpy executor participation in this suite remain fixtures, not Memory::Write,
BufferCache first-registration or a live scheduler adapter. Bypassing pending-writer order and
bypassing conflict checks each produce explicit failing negative controls. Cross-platform actual
HostMemory/GPU-plan regressions also pass. The additional chunk-backing runner requires Linux;
its Windows attempt cannot compile Linux mmap headers, so its evidence awaits the remote Linux job.

**No activation:** initially uncached Memory::Write/WriteBlock/CAS still do not join this domain;
first-cache-registration/upload also does not join. CPU lookup can still bypass notification after
cached marking. Before activation, implement stable controlled CPU resolution, preservation-before-
store and exact successful-store publication, registration epoch/content provenance, mapping-mutator
ordering, real scheduler park/resume and checked completion/Unknown/final-pin drainage. The original
F2 correctness gate still reports backing 77/cache 10 and exits 1. Native evidence for this new
range-ordering slice is pending.

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

## Prepared physical-page writer and registration boundary (inert)

Native run [38700231751](https://github.com/Splaser/emulator/actions/runs/38700231751)
passed Android production and the complete Linux production/regression jobs for `80bf2b85f3`.
The completed PR380 integration branch was subsequently deleted locally and remotely after
checking ancestry; development now continues on `codex/issue-372-fixes`, synchronized with main.

`HostMemory::PreparePhysicalCpuPage` now prepares a real pinned physical page and its canonical
`GuestBackingEpoch::pages` gate. Different GPU/device virtual aliases of the same backing page
obtain the same gate; different physical pages or backing epochs do not. Cold preparation uses
a bounded registry (65,536 pages); it can allocate. Prepared scalar stores do not query that
registry, allocate a range ticket, copy a shared owner, or acquire cache/PTE locks.

The prepared physical interface executes actual bounded memcpy or aligned unsigned CAS and
publishes cumulative exact modified-byte bits and a release sequence AFTER a successful store,
before releasing its page-local writer count. Failed CAS publishes nothing. Closing or tracked
pages return `NeedSlow` without storing; no fallback is authorized. This is not CPU-VA resolution,
a cache dirty-bit consumer, or support for cross-page stores, u128 CAS or registered-page writes.
Concurrent conflicting CPU operations still need their normal language/memory-access contract;
the writer count orders registration, not overlapping scalar writes against each other.

First-registration preparation enqueues its whole-page write intent before atomically closing
fast writer entry. Nonblocking `TryStart` reports `Draining` until already entered writers have
published and exited, then attempts the backing range ticket. The returned registration retains
actual storage and the supplied representation owner. `PublishTracked` changes only gate state;
it neither certifies an upload nor completes the ticket. `CompleteWithExternalEvidence` still
requires the caller's real visibility/completion or no-effect proof. Destruction cancels pending
work or marks running work Unknown; cancellation never silently reopens the gate.

Windows `run_page_writer_tests.py` composes actual HostMemory, GPU/device translation, existing
cache representation lookup and Vulkan payload owners (creation/PTE/cache storage remain fixtures).
It checks aliases, a deterministically paused real store versus registration, exact byte publication,
failed/successful CAS, bounds, retirement and fail-closed cancellation. An independent releaser
unblocks the writer. 2,000 prepared byte stores perform zero measured hot allocations and do not
advance range-domain enqueue progress. Negative controls explicitly fail for ignoring writer drain
(49) and publishing before the store (50). This is bounded correctness evidence, not a performance
benchmark or normal Memory::Write/BufferCache::Register production routing.

**Activation remains blocked.** Normal CPU VA stores and actual first cache creation/upload do
not call these adapters. Preservation, stable CPU resolution, cache-content provenance, registered
slow writes and DMA participation must join this SAME handshake before use. Range admission alone
does not exclude these fast writers. Unknown retains resources intentionally; a trusted quiescence/
recovery owner and final-pin drainage before device/VMA destruction remain required. Destroying
the admission object is not recovery. The original F2 gate was rechecked and still reports
`expected=77 observed=10 backing=77`, with `require-fixed` exit 1. No DMA activation or eligibility
expansion is included in this slice.

### Publication consumption and failed registration activation gates

The user's next implementation priority is the controlled CPU VA store adapter; DMA admission
must remain disabled. Its required chain is `Memory::Write -> stable VA/physical resolution ->
page writer qualification -> actual store -> exact publication`. Preparation must occur cold
and hot accesses must reuse an owned stable page view, with explicit invalidation on CPU mapping,
address-space and backing changes. Calling `PreparePhysicalCpuPage` for each scalar access is
not an acceptable implementation. Writer qualification must precede first cache registration
even for an initially uncached page; cached-PTE checks alone cannot provide that ordering.

Current source audit: `GetPointerImpl` returns a nonzero PTE pointer without the rasterizer
callback; `MapPages` writes the atomic tagged pointer and plain `backing_addr` separately.
Thus pointer/tag sampling or a generation retry around unsynchronized `backing_addr` does not
yet provide a legal stable physical snapshot. Map/unmap, debug/cached tag changes, table resize,
current-process switch and destruction must be included in the prepared-view lifetime audit.
The existing `Write` scalar/cross-page branches, `WriteExclusive`/128, `WriteBlockImpl`,
`HandleRasterizerWrite` device-alias fanout/OnCPUWrite/dirty collection and uncached behavior
must retain their semantics until their individual controlled counterparts are proved. The
physical memcpy tests are not evidence for replacing those ordinary paths.

`Published()` is cumulative observation, not a consumable dirty queue. There is no clear or
incremental acknowledgement API. The current snapshot requires fast entry closed and writers
drained. A future consumer or tracked-writer extension must prove concurrent snapshot/sequence
validation and incremental acknowledgement without dropping writes during cleanup; it may not
clear the observed bitmap and assume it owns those modifications.

`PublishTracked()` means only that fast entry remains disabled. It is not registration-ready,
content-valid or upload-success state. The future adapter must separately track representation
validity and real upload visibility/completion. After uncertain/partial upload failure it must
mark Unknown and retain the ticket/resources, preventing dependent CPU/GPU access. A certified
no-effect failure may release its reservation only while the failed/uninitialized representation
remains inaccessible; such release never turns Tracked into valid content. Callback return,
Tracked state and a readable cumulative bitmap are insufficient completion evidence. These
failure transitions and their deterministic negative controls remain activation prerequisites.

## Remaining production adapters and acceptance gates

### Explicit prepared CPU Write execution (not ordinary-path activation)

`ecf9bb31e8` adds an explicit prepared-view overload of actual `Memory::Impl::Write`,
exposed through result-returning `WritePrepared8/16/32/64`. Ordinary Write wrappers and their
original body remain unchanged. Cold preparation captures a Memory-owned active-context epoch;
actual `SetCurrentPageTable` advances it even when switching away and back to the same table.
The view retains immutable mapping/physical/context fields. A prepared write checks caller
context identity, canonical 48-bit VA/page bounds, then takes nonblocking shared context/PTE
try-locks, validates the epochs/tag, enters the physical page writer, performs the actual store
and publishes before releasing that writer and the short execution guards. No callbacks,
suspension, registry lookup, physical pin creation or shared-owner copy occurs in this hot call.

Busy, stale, retired, wrong-context/cross-page, tracked/closing and cached/debug targets refuse
with a result and no effects; there is no fallback to legacy memcpy. In particular cached/debug
rejection does NOT replace preservation/device-alias/OnCPUWrite handling. This API is an inert
explicit entry with no ordinary caller installed, not a repair of the normal CPU path. Two
shared try-locks and byte publication are correctness groundwork, not a throughput claim.

The actual extracted prepared Write, SetCurrentPageTable, cold factory and actual page/physical
implementations pass Windows tests for context switch away/back, top-bit VA masking, wrong-page
and cross-page refusal, remap/tag invalidation, Busy under a mapping mutator and shared physical
alias gates. An independently released actual prepared writer races first-registration gate
closure: registration reports Draining until its exact store publication, and a later alias
writer refuses. Resource ownership supplied to this registration is a fixture, not a real
BufferCache upload. 2,000 prepared Memory writes perform zero measured hot allocations and no
range enqueue. Removing hot active-context validation fails explicitly (54); missing cold
post-pin validation remains control 51. The full Memory::Write -> real BufferCache first
registration/preservation/cached-slow-path integration is STILL REQUIRED. DMA remains disabled.

Native run 38708541040 passed both jobs for its parent `06408b9ce5`. New native
[38711873776](https://github.com/Splaser/emulator/actions/runs/38711873776) verifies
`ecf9bb31e8`; its result is pending at this handoff. The next stage is **M3B - Controlled First
Registration Integration**, whose scope, real source edges, whole-coarse-range coverage,
completion/Unknown gates and home-machine commands are saved in
[`docs/M3B_CONTROLLED_FIRST_REGISTRATION_HANDOFF.md`](../../docs/M3B_CONTROLLED_FIRST_REGISTRATION_HANDOFF.md).
That controlled BufferCache end-to-end stage is not implemented yet; none of the prepared
Write passes closes the original backing77/cache10 failure.

### CPU VA cold-resolution dependency

Native [38704560296](https://github.com/Splaser/emulator/actions/runs/38704560296) passed both
Android production and the complete Linux production/regressions for `0ed92c3efd`, including
the real page writer suite. This does not close F2 or activate any new ordinary access path.

`PageTable::SnapshotMapping` now samples the tag and plain backing address together under a
short shared metadata guard. The actual `Memory::Impl::MapPages` and debug/cached tag mutators
take the corresponding exclusive guard; `Resize` invalidates snapshots under that same guard.
The domain generation invalidates prior snapshots conservatively for the entire table. Owner
retirement marks retained tokens dead even when their domain remains owned by old snapshots.
Existing raw/JIT/page-table readers are not converted into this snapshot protocol.

Actual `Memory::PrepareControlledCpuPage` takes this cold snapshot, drops the PTE guard, prepares
the real HostMemory physical page, then rechecks the table and mapping generation. The returned
view pairs the mapping token with owned physical storage and canonical page gate. It performs
no CPU store, callbacks, registration or data admission. Callers must keep the process/PageTable/
HostMemory alive and use the memory-owner thread. The token does not own the process or detect
an address-space switch away and back; future hot access needs an explicit active-context
qualification and bounded mapping-use protocol. `IsCurrent` alone is not execution permission.
Table-wide invalidation is correctness groundwork, not a hot-path performance claim. No physical
pin, shared view creation or registry lookup has been inserted into scalar `Memory::Write`.

Windows `run_cpu_mapping_tests.py` uses the actual PageTable implementation/VirtualBuffer and
HostMemory plus extracted actual Memory cold-preparation and MapPages bodies. System/device
collaborators, logging/formatting and controlled rendezvous remain fixtures. It checks same-page
physical aliases, remap during cold preparation, tag/unmap/resize/destruction invalidation and
mutator exclusion of snapshot reads between field writes. Removing the post-pin validation
accepts the remap and fails explicitly (51). Candidate and unsafe-insertion tests retain their
fixture PTEs and original failure semantics; their new metadata guards do not certify production
CPU writes. Next work must connect reusable views and full writer qualification to actual
Memory::Write and real first registration, preserving OnCPUWrite/device alias checks and all
unconverted paths. DMA admission stays disabled.

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
