# M4 process guest exclusion: implementation sequence

This is the active follow-up to the
[whole-guest feasibility decision](M4_F3_GUEST_EXCLUSION_FEASIBILITY_AUDIT.md).
The ownership boundary is KProcess, its PageTable and physical backing, including
other Memory contexts, CPU aliases and independent producers of that backing.
Per-Memory retirement and a private arena are not certificates for this boundary.

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

This closes initial PageTable/TLS construction only. Kernel service-process
creation (is_real=false), later metadata/interface/module setup, publication of
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

## Next gates (still Open)

1. **Process guest exclusion.** Attach ordinary Memory CPU writes and mapping
   publication to a process/PageTable/backing cohort shared by every Memory
   context. Exclude host-service writes under that same owner boundary. A mutable
   pointer loan lasts through its final use, not just GetPointer. Raw escaped
   pointers and incomplete export/owner history must prevent admission.
2. **Whole-guest quiescence.** Combine the real execution acknowledgement with
   System suspension serialization and actual independent-producer close-and-join.
   Do not reuse today's unbounded suspension wait as a bounded certificate.
   Prove NCE separately or refuse it. The pinned unchecked fast-link loop is also
   an open stop/completion blocker; a halt request alone does not bound its exit.
   Preserve prior pause state and lock order;
   no owner may be parked holding a lock needed by drainage/completion.
3. **Device/GPU owners and Unknown.** Close GPU workers, transfer/shader/image
   producers and mapping mutation, including queued-but-unsubmitted commands.
   Retain backing storage, frozen aliases and native ownership through the exact
   checked completion. Retire an Unknown operation only through explicit proven
   recovery/termination; a late old submission cannot release a newer isolation.
4. **Actual guest-backed admission witness.** One known ordinary memfd physical
   page, bounded complete aliases, one queue, no concurrent shader/image writers.
   Exercise a real Vulkan Copy with success/refusal/partial failure/remap/teardown/
   resource-retirement controls. Retain the original independent F2/F3 negatives.

No normal guest route or physical latest-writer authority is enabled. F2/F3
remain Open. Validation continues on Linux; Android is not requested.
