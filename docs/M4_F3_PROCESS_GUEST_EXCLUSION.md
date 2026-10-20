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

The captured epoch is explicitly identity only. It does not pin HostMemory
storage, freeze aliases or close a different Memory object. The retained process
prevents its normal slab finalization while this request lives; System, Kernel
and HostMemory must still be externally retained. This precursor cannot be
transferred to asynchronous GPU work. Unknown backend closure remains sealed;
the full resource-isolation registry for future asynchronous operations is still
required before such work can be admitted.

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

A separate native CTest runs an actual AArch64 store loop through real Dynarmic,
KProcess, KThread, PhysicalCore and ordinary guest heap backing on Linux x86-64.
It observes progress through process_vm_readv, requests the real halt, checks
backend return and stable bytes, rejects real re-entry while closed and checks
old cancellation against a new request. Native acceptance is pending. It does
not execute native ARM/NCE, close services/GPU or prove a complete alias census.
The thread is intentionally not dispatched as an ARM application by the scheduler;
the harness drives its real backend on a dedicated host thread.

## Next gates (still Open)

1. **Process guest exclusion.** Attach ordinary Memory CPU writes and mapping
   publication to a process/PageTable/backing cohort shared by every Memory
   context. Exclude host-service writes under that same owner boundary. A mutable
   pointer loan lasts through its final use, not just GetPointer. Raw escaped
   pointers and incomplete export/owner history must prevent admission.
2. **Whole-guest quiescence.** Combine the real execution acknowledgement with
   System suspension serialization and actual independent-producer close-and-join.
   Do not reuse today's unbounded suspension wait as a bounded certificate.
   Prove NCE separately or refuse it. Preserve prior pause state and lock order;
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
