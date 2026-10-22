# M4 process guest exclusion: implementation sequence

This is the active follow-up to the
[whole-guest feasibility decision](M4_F3_GUEST_EXCLUSION_FEASIBILITY_AUDIT.md).
The ownership boundary is KProcess, its PageTable and physical backing, including
other Memory contexts, CPU aliases and independent producers of that backing.
Per-Memory retirement and a private arena are not certificates for this boundary.
The remaining roadmap has three phases, listed at the end. Lifecycle fixes and
the implementation slices below are prerequisites within those phases, not
additional M4 milestones. None currently authorizes ordinary Guest admission.

## Required state and resource order

| State | Required real evidence | Resources that remain owned |
| --- | --- | --- |
| Closing | Close all execution, ordinary CPU/API, mapping and host-service ingress | Process/PageTable/Memory, backing owner, pending producer jobs |
| Backends stopped | Actual backend return AND UnlockThread, all cores still closed | Same owners; this alone cannot authorize access |
| Services joined | Actual Audio/VIC/service/debugger/callback/raw-pointer users closed and joined | Same owners and their callback/loan state |
| Mappings frozen | Complete alias census and CPU/DAddr/GPU mapping mutation exclusion | Actual storage pins and every alias/mapping guard, not epoch identity alone |
| GPU drained | Queued and unsubmitted work accounted for; actual producer stop/completion and visibility | Native resources, queue/worker owners, retained pre-admission obligations |
| Exclusive | All previous constraints held continuously and content/copy checks satisfied | All owners transferred to the exact checked operation before enqueue |
| Unknown retained | Partial effects, uncertain completion, remap, retirement or missing owner | No automatic reopening or release based on an old completion |
| Released | Exact operation completed successfully and all release validations passed | Reopen admission last; restore the previously existing pause state |

There is no public API that marks Services joined or Exclusive from caller booleans.
A future provider must assemble actual owned closure/join/freeze capabilities.
The first backend-stop component below has no GPU adoption or success-admission API.

## Implemented first component: process-bound actual backend stop

KProcess::TryStopGuestExecution retains a real KScopedAutoObject reference to the
target process and captures its current Common::PageTable identity and backing
epoch. It closes all PhysicalCore execution domains before requesting any halt.
Its ProcessExecutionStop polls the actual cores under try-lock, requests an actual
nonblocking backend interrupt and only acknowledges BackendsStopped once every
entered backend has returned, including UnlockThread. Poll-budget exhaustion,
unsupported interrupt, stale owner or retired backing is sticky Unknown.

The stop now captures a RetainedBackingStorage from the actual HostMemory Impl,
along with the allocation epoch. The epoch remains identity only; the separate
opaque owner retains the real allocation/reservation and existing or subsequently
materialized lazy chunks. Capture exposes no pointer/FD, materializes no chunk
and does not freeze aliases or close a different Memory object. It is declared
before the process owners so allocation release follows process finalization.
System, Kernel and the HostMemory facade still need external lifetime protection
during capture/validation; retaining storage is not permission to race facade
move/destruction. This precursor cannot transfer to asynchronous GPU work.
Unknown backend closure remains sealed; a durable resource-isolation registry
is still required before such work can be admitted.

PhysicalCore's previous count spanned the entire RunThread function, including
Svc::Call. A SVC can yield its fiber after the backend has already exited, leaving
the old count indefinitely active. The count now covers backend initialization
and each actual RunThread/StepThread visit through context unlock, with no count
held across the later SVC/debugger callbacks. Those callbacks remain independent
writers; they are not silently reclassified as stopped.

Dynarmic 32/64 explicitly implement the nonblocking request with HaltExecution,
whose backend implementation publishes the halt reason atomically. Request
success is not return acknowledgement. NCE does not opt in: its current
SignalInterrupt locks thread parameters and can wait for a signal handshake.
An active unsupported backend therefore refuses this path rather than pretending
its stores have stopped. No new fault handler or page-fault parking is installed.

Cancellation reopens only this backend-only, no-GPU-effects request after complete
acknowledgement and owner validation. Each request owns its own closure objects;
an old or moved-from request cannot reopen a new operation. ProducerDrain's
moved-from Closure operations now safely refuse instead of dereferencing moved
state. This does not add a mechanism for cancelling an uncertain GPU operation.

For the sustained cohort wrapper, cancellation reserves the roster mutex before
reopening any domain and validates its retained snapshot revision under that same
reservation. Contention or intervening retirement refuses with all those gates
still closed. The reservation spans only stopped-state validation and atomic gate
operations; it spans no callbacks, owner destruction, or roster re-entry. This
removes the fallible late creation-release lock. CPU, initialization and cold
publication cancellation now share the ResumeBatch protocol below. Durable Unknown
resource ownership is still required before any effect-bearing adoption.

## Atomic managed-domain cancellation (phase-one prerequisite)

ProducerDrain::ResumeBatch collects actual owned closures, each already closed and
drained. It publishes permanent shared-gate membership while those local domains
remain closed, reopens local count words behind the closed shared gate, then opens
that gate with one final CAS. All CPU cores, initialization and cold publication
participate in one cohort cancellation batch; creation commits afterward under
its previously acquired, revision-validated roster reservation, with no further
fallible step. Backend-only cancellation batches the cores and initialization.

| Cancellation point | Producer entry | Seal/failure disposition |
| --- | --- | --- |
| Collect/validate | Every participating local closure remains closed | No reopening; quarantine owned closures |
| Publish membership | Shared gate closed; local words still closed | Failed publication CAS preserves local closure and seals the group |
| Reopen local words | Shared gate still closed | Even already reopened members remain unavailable |
| Final gate CAS | Entries can resume only after success | A preceding Seal prevents success and keeps the group closed |
| Successful cancellation | Normal managed entry resumes | A later Seal is a separate event, still propagated to the group |

The shared owner is assigned before the release CAS that first publishes Grouped
in the local word and is immutable afterward. Seal reads it only after acquiring
that bit. A Seal that wins before publication makes the publication CAS fail; the
batch then seals its gate before any local resume. For a participating member,
the local reopen CAS publishes the already-closed shared gate. A late successful
entry CAS acquires that publication and rechecks the shared gate before returning
an entry; refusal rolls the count back. This closes the delayed-entry/ABA window.

There is no raw coordinator pointer, atomic shared_ptr, callback, wait or retry in
the release protocol. A fixed-size batch holds at most sixteen borrowed closures
which must outlive it. First group formation allocates once, before any reopening;
allocation failure refuses. Ungrouped ordinary entry keeps its single CAS path;
grouped entry adds gate reads before and after that CAS. Member domains own the
shared gate directly, so dropping a failed batch cannot remove its protection.

Membership remains until domain destruction; subsequent cancellation reuses the
same gate and can extend it with previously ungrouped domains. Existing distinct
groups cannot be merged or detached. Seal/retirement of a joined member propagates
conservatively to the shared gate. A subset cancellation does not prove that other
members have drained, and the gate is not a whole-guest exclusion certificate.
Old released or moved-from closures cannot reopen or quarantine a new operation.

The stopped backend latch also revalidates initialization/core closures, so a
later Seal cannot remain hidden behind a previous BackendsStopped observation.
Standalone tests exercise normal and scheduled production bodies, with precise
mutants for early group opening, missing Seal propagation, destructive batch drop,
and omitted late-entry rollback. Actual cohort-body tests separately reject an
omitted publication member and the old sequential cancellation implementation.

This protocol covers no-effects cancellation only. Ordinary writes, cache/fault
PTE mutation, NCE, host-service/raw-pointer writers and GPU queues still require
their own closure/join/freeze facts. It adds no GPU adoption, checked completion
or durable backing/resource quarantine registry. Ordinary Guest admission remains
Unknown, and all three M4 phases remain unfinished.

## Evidence and limits

The actual-body Linux fixture covers Run and Step, a halt request followed by a
final simulated store, delayed UnlockThread, a still-active SVC writer after
backend acknowledgement, process reference retention, closed re-entry,
unsupported backend, contended core, exhausted budget, moved-from handle,
backing replacement and backend exception cleanup. It compiles the production
ProcessExecutionStop type and extracted factory/core/stop methods, with injected
backend and kernel collaborators. Three repeats and two assertion-specific mutants
are required. The SVC writer is a mandatory successful bypass counterexample:
GuestBackingAdmission remains Unknown even after BackendsStopped.

Native run `39427948982` compiled all production targets, but the original
unconditional B -8 store-loop failed to acknowledge and timed out during cleanup.
The pinned frontend uses LinkBlockFast here; its linked terminal has no halt check.
The operation correctly becomes Unknown instead of certifying backend exit, but
ordinary arbitrary-program stop capability is not established.

The original loop now remains an explicit native refusal witness in a separate
process: continued writes, sticky Unknown, refused cancellation/new execution,
and retained owners until OS termination. A checked TBNZ loop separately tests
successful actual Dynarmic/KProcess/KThread/PhysicalCore exit and stable backing.
The counter stays odd so that loop cannot exit naturally. No global optimization
change or forced in-process cleanup disguises the original counterexample.
Both native results passed in run 39432258674 at 51266b64ef, with all seven
CTest logs and exact-source artifact hashes independently recovered. That run
later failed a stale extraction fixture, so it is not full-workflow acceptance.
Replacement run 39518766603 at 89f034d20b passed build/CTest, repeated native
witnesses and HostMemory checks, then failed the shared resolver fixture's missing
ReserveRange adapter. Its exact-source artifact (12310269482) is independently
hash-verified, including all seven CTests and the stop positives/mutants. The
resolver and assertion-stub fixture corrections still require a full Linux run;
the cancelled interim run 39527273477 supplies no additional acceptance.
The corrected baseline at `9fdec2afa1` subsequently passed the complete Linux
workflow 39528346917. Artifact 12316026001 is independently verified: 170 source
hash entries in 15 manifests and all seven CTest markers, with the pinned
Dynarmic gitlink unchanged. This accepts the existing prerequisite and negative
controls only; subsequent running-owner changes require a new run.
Neither result closes services/GPU or proves a complete alias census; the harness drives the real backend on a dedicated
host thread, not as an ARM application dispatched by the scheduler.

## Running-owner retention follow-up

The stop requester is not necessarily the process executing on any PhysicalCore.
After all execution entries close, each core now captures its actual running
KProcess under the same try-locked context that issues the halt request. The
stop handle retains those strong references and their PageTable identities,
including when a backend refuses the nonblocking request. A late exit does not
discard them. Moving the handle transfers the references; the execution closures
are sealed before references are destroyed. An occupied output slot refuses
before interrupt effects so no unrelated last reference is dropped under m_guard.

| Observation | Retention and disposition |
| --- | --- |
| Core lock contended | No owner snapshot or halt; retry within the existing budget |
| Core idle | No running owner to retain; still wait for the closed execution count |
| Running owner captured | Open its real reference before invoking backend halt; retain requester separately |
| Unsupported or uncertain backend | Keep captured owners for the handle lifetime and leave closure Unknown |
| Backend and UnlockThread exit | Validate retained PageTable identities; still no guest admission |
| Known cancellation | Reopen only owned execution closures; retain references until handle destruction |

The actual-body fixture covers two different running processes plus a third
requester, pre-halt reference capture, delayed UnlockThread, move/release exactly
once, occupied-slot refusal and foreign-owner retention after unsupported stop
and late exit. A third assertion mutant removes the capture and must fail at
the pre-halt retention assertion. A new isolated native CTest requests from A
while real Dynarmic executes a checked store loop in B, then checks retained
ownership through exit and exact reference release. Linux run 39533283269 at
`d98272e36a` passed the complete workflow. Artifact 12317661714 was independently
verified against that exact source: 170 source hash entries across 15 manifests,
98 unique files and all eight CTests. The archive digest is
`9d5cfe1feb2ccd7f3b3d5119d68474d67c29cc519a21aca5eb14cab082eea65b`.
This accepts the running-owner prerequisite, not later storage/initialization work.

This is the running-backend cohort, not a complete process/backing owner roster.
KernelCore::GetProcessList is populated by the OS process wrapper and is not an
exhaustive allocation/publication census. Constructor/initialization, registration,
all Memory views, teardown and independent service ownership must be closed and
joined before a full cohort can be certified. No process-list mutex is held across
halt/drain: those locks can be needed by lifecycle work. A separate backing
storage owner now retains Impl; it does not retain native GPU resources or freeze
aliases, and the handle cannot transfer to async GPU work. Callers retain
System/Kernel/HostMemory and an uncertain handle; a future durable Unknown registry
is still required. Original unchecked-loop/NCE/service/raw-alias/GPU blockers remain.

## Actual backing storage retention follow-up

RetainedBackingStorage is privately constructed by HostMemory from its real Impl
and epoch. Unlike an epoch reference it keeps OS allocation/reservation resources
alive; unlike PinnedPhysicalMemory it exposes no byte range, pointer or FD. Capture
is a cold owner operation, not a signal/ordinary-write path, and never materializes
lazy chunks, enrolls ordinary mappings or enters a mapping mutation. A moved-from
HostMemory refuses capture before touching transferred state. Moving the token
leaves its old OwnerAlive false and Size zero.

KProcess acquires this owner before opening process references or closing cores.
A capture failure has no core-closure effects. ProcessExecutionStop holds the
storage before its process members in declaration order: execution closures seal,
captured processes release/finalize, then storage releases. Replacement or epoch
retirement makes Poll Unknown while the old allocation remains retained for the
handle lifetime. System/Kernel/facade protection and durable Unknown retirement
remain separate requirements; this cannot keep a destroyed GPU device usable.

The dedicated Linux suite links actual HostMemory and uses process_vm_readv to
probe lifetime without dereferencing a potentially freed address. It checks
facade/token moves, moved-from refusal, retirement, replacement isolation, final
unmap/FD release, lazy capture with zero chunk creation, a later materialized chunk,
and capture during a controlled mapping freeze without escape or reopening.
Three repeats pass. A fake-owner mutant retaining only an unrelated allocation
and the real epoch fails at the precise premature-storage-release witness.
The stop actual-body fixture separately checks failed capture before closure,
old allocation retention after replacement and storage surviving process Close.
Production/native syntax and the existing full HostMemory mapping-freeze controls
pass locally. The later combined source a09bf27bb4 passed Linux run 39540116589,
including this storage owner and initialization closure. Its independently
verified artifact 12320539901 contains 180 source hash entries, 103 unique files,
16 manifests and all eight CTests, with archive SHA256
`6267209c50becfca1166b8f15b3025fca0e7386157ed79f0bb61e45a3f3fb5a7`.

## Guest process initialization closure follow-up

KernelCore now owns a session-specific guest initialization domain, independent
of the OS wrapper process list. Both PageTable-building KProcess::Initialize
overloads enter before resource reservation or initial mapping. Their entry
outlives initial TLS creation, the initialized flag and all local rollback guards.
The public real-process common initializer also enters; the two outer initializers
call a private InitializeCommon under their existing entry, so a close cannot
cause a spurious nested refusal halfway through an admitted initialization.
Closed, contended or exhausted entry refuses with ResultBusy before effects.

ProcessExecutionStop closes this domain before closing core execution. Poll waits
for admitted initializers/rollback to exit before issuing backend halt requests.
Budget exhaustion seals both domains Unknown; a later initializer exit does not
reopen them. Known no-effects cancellation reopens initialization last. An occupied
initialization closure refuses the factory before any core closure. Kernel session
initialization creates a fresh domain; an old closure cannot reopen the new one.
No process-list, scheduler or PTE lock is held while polling.

The actual-body stop fixture tests a pending initializer with a running backend,
no early halt request, closed re-entry, successful release/cancellation, stale
cancellation, timeout followed by late exit and occupied-closure refusal without
core effects. A fourth assertion mutant bypasses initialization drainage and must
fail specifically at the early halt request. The native checked/unchecked stop
witnesses now call all three real-process Initialize overloads while closed and
require ResultBusy, no initialized publication and unchanged resource-limit
references. Checked witnesses also create and tear down a real mapped process
after known cancellation. Linux run 39540116589 at a09bf27bb4 passed the full
workflow; the exact-source artifact and eight CTest markers were independently verified.

The initial implementation closed PageTable/TLS construction only. Its later
cohort extension below also closes is_real=false initialization and cold setup.
Service callbacks, independent cache/GPU publication, publication of
an already initialized process, Run/ordinary mapping mutation, existing Memory
contexts, service callbacks and teardown remain independent obligations. In
particular, initialization drainage supplies neither an exhaustive retained owner
roster nor proof that all users of previously published backing have stopped.
All GuestBackingAdmission results remain Unknown.

## Lifecycle inventory prerequisite (implemented, not admission)

KernelCore now has a separate ProcessOwnerRoster. KProcess registers after its
constructor-owned Memory is ready and before any caller can initialize/publish
its initial PageTable. This includes kernel service processes and initialized
processes that never enter the OS wrapper list. Normal C++ destruction removes
the exact registration only after all PageTable/Memory/member destruction and
unregisters the object's kernel bookkeeping; slab
Destroy marks it retiring before inherited Finalize/Free. If Finalize throws,
the retiring record remains and future captures refuse without dereferencing it.
Completion uses a monotonic registration ID rather than an address, because
another process may reuse the slab slot before the old Destroy returns.

TryRetainProcessOwners captures actual KScopedAutoObject references using a new
checked TryOpen: a constructor with reference count zero or an owner whose final
Close already won cannot be adopted/resurrected. Snapshot capture/validation use
one mutex try-lock. Partial pins release after that lock, including when their
release invokes finalization. Snapshot moves transfer pins. Its revision becomes
stale on registration/retirement; stale validation does not release those pins.
Counter overflow poisons validation instead of permitting identity/revision reuse.
Cold reference opening/allocation is not a bounded stop or signal-handler API.

Kernel bookkeeping unregister has explicit ownership: a direct C++ destructor
unregisters only while its registration is still present. Slab Destroy consumes
that registration and leaves unregister to KAutoObject::Close. The production
slab Free does not invoke the C++ destructor, so the earlier implementation did
not double-unregister on that ordinary path; the guard clarifies responsibility
and prevents a consumed registration from taking it again in later C++ cleanup.
The lifecycle witness now compiles the actual inherited slab Destroy body, counts
unregister calls through actual Close/UnregisterWithKernel, checks direct C++
cleanup separately and rejects unconditional or omitted destructor unregister.
These two additional mutants bring the roster suite to six precise negatives.

The standalone Linux witness compiles the actual roster, scoped reference type,
KAutoObject Open/Close and extracted KProcess Destroy/destructor, with injected
slab/Finalize collaborators. Three repeats cover zero refs, real final-reference
retention, partial capture racing the caller's last Close, reentrant cleanup,
Finalize failure, lock contention, stale/moved snapshots and address reuse.
Four precise mutants omit pinning, ignore retiring owners, omit registration
revision and erase by reused address. Native checked/unchecked execution witnesses
also retain an actual unpublished KProcess/PageTable/Memory through termination
and final release, reject a zero-ref constructor, and reacquire the roster after
real finalization. Full native runtime acceptance for this component is pending.

The roster itself retains neither arbitrary Memory contexts nor GPU/device
resources. It does not freeze PageTables, close raw pointer loans, stop service
creation/callbacks or join a process whose failed initialization left effects.
ProcessExecutionStop does not yet adopt its snapshot: integrating a cohort needs
continuous initialization/publication closure and a defined response to new
service owners, plus ordinary writes and teardown exclusion. An IsCurrent check
alone cannot authorize an asynchronous operation; creation could follow it.
Keep the captured cohort owned through all future drains/Unknown isolation rather
than returning raw pointers or enumerating GetProcessList under a long-held lock.

## Sustained cohort and execution integration (phase one, in progress)

KProcess::TryStopProcessCohort now composes continuously owned capabilities:

1. Retain actual backing storage and the requester, refusing a requester without
   a real Guest PageTable. Close creation at the same mutex-protected point that
   registers every KProcess, including service processes. A constructor not yet
   registered must refuse and unwind; its kernel bookkeeping and popped slab slot
   are restored. Already registered zero-ref constructors are retried/refused,
   never omitted or resurrected.
2. Close all initialization, including is_real=false common service setup, and
   the shared cold publication domain. Wait for admitted entries to leave before
   closing CPU execution; an admitted loader must not be parked behind its own
   CPU-dependent completion. No scheduler/PTE/roster lock spans the drain.
3. Capture the real owner roster while creation remains closed. Keep every strong
   owner reference, then close actual PhysicalCore entry and issue actual backend
   halt requests. IsCurrent is an additional consistency check under those owned
   closures, not a substitute for keeping creation/publication closed.
4. Retain the closures and cohort through polling, move and uncertainty. Known
   cancellation reopens creation last. Unknown and late producer exit do not
   reopen acquired gates. Backing outlives closure destruction and all retained
   process finalization. This type has no asynchronous GPU adoption interface.

Every Memory constructor binds a shared kernel cold-publication domain, including
locally untracked Memory. BeginCold covers context bind, map, unmap, protect and
debug publication. Reset/move use a parent-only entry before their local join to
avoid acquiring a shared lifetime lock and then waiting on themselves. Local
controlled-arena enrollment remains separate. Run, metadata/module/interface
setup, the OS loader wrapper, process-list publication and application-process
publication also participate. Refusal precedes effects; the OS wrapper propagates
loading/running refusal rather than claiming success. Cold entry retries count
contention so normal concurrent mapping is not rejected spuriously. That retry
API is forbidden in a fault handler, backend entry or bounded stop poll.

Cache/fault-related RasterizerMarkRegionCached still uses its original independent
Begin path. It remains a required successful bypass control; this component
certifies neither all PTE publishers nor full alias/producer coverage. The NCE
fault path has no new wait or parking mechanism. Ordinary writes, raw pointers,
service callbacks, GPU resources and partial-initialization remnants remain
separate proof obligations. Manual destruction outside the intrusive owner
protocol is not authorized by a snapshot. BackendsStopped is a prerequisite only;
GuestBackingAdmission remains Unknown.

The Linux actual-body integration fixture retains idle/unpublished owners before
the halt callback, delays initialization and publication independently, proves
CPU entry is not closed during those drains, refuses creation and cold mapping,
and tests move, stale cancel, zero refs, timeout/late exit and a post-stop seal.
Four mutants move capture after halt, omit publication drainage, omit creation
closure or close an unrelated publication domain. The ninth native CTest uses
real KProcess/Memory/roster and a real checked Dynarmic store loop. It tests actual
constructor/slab rollback, mapping/reset/move/interface/module/OS publication
refusal and resumed mapped-process initialization after cancellation. Native
runtime acceptance for this integration is pending its exact-source Linux CI.

## Remaining roadmap: three phases

1. **Roster plus real execution drainage — in progress.** Finish the continuous
   creation/initialization/publication ownership boundary and scheduler/lifecycle
   protocol. The sustained cold-route integration above does not close independent
   cache/GPU PTE publishers or prove all arbitrary Memory views. Never promote a
   single IsCurrent observation to permission for subsequent asynchronous work.
2. **Close every independent producer — Open.** Ordinary scalar/bulk/atomic CPU
   writes; NCE native stores and unchecked Dynarmic fastmem; Audio/VIC/service
   callbacks; raw pointer loans, external mappings and aliases; queued/unsubmitted
   GPU transfers, shader/image writes and cache/DAddr/GPU mapping publication.
   Require real stop and close-and-join facts, preserve pause state, and avoid
   parking an owner while it holds a lock needed for completion. Unknown must
   keep backing, alias protection and native resources owned under an explicit
   durable isolation/retirement protocol; an old completion cannot release a new
   operation. No fine-grained page-fault parking is required for this first version.
3. **Real Guest-backed Admission — Open.** With real KProcess and ordinary Guest
   physical backing, drain all relevant producers, freeze mapping/permission
   publication and retain physical storage, PageTables and GPU owners. Execute one
   restricted real Vulkan Copy, wait for exact checked completion, then release
   safely or keep isolation/resources on Unknown. Cover success/refusal/partial
   failure/remap/teardown/retirement and preserve independent original F2/F3 negatives.

No normal guest route or physical latest-writer authority is enabled. F2/F3
remain Open. Validation continues on Linux; Android is not requested.
