# M4 F3: isolated submission-linked write provenance

This is the first submission-provenance slice following the review of
`d8764c0cf0`. Resource-local revisions remain write intent. F2/F3 remain Open,
restricted eligibility remains blocked, and ordinary Memory::Write/UMA routing
remains inactive. This adds no physical latest-writer authority or ordinary shader
producer enrollment.

## Evidence recorded

`Scheduler::RecordCheckedWrite` accepts an externally qualified, retained resource
owner, its native identity, native byte offset/length and resource-local intent
revision. On the existing GPU owner, it records one worker command and immediately
calls `FlushChecked`. No intervening host flush can associate the command with a
later submission. The identity is the actual CheckedSubmission object, scoped to
its Scheduler owner, rather than a sortable integer or CurrentTick certificate.
The callback returns true only after recording its write commands, false only
when no write was emitted. Partial recording exceptions are Unknown and never
replayed. A submission identity is reserved before queue acceptance; its existence
does not itself mean Submitted.

| State | Evidence |
| --- | --- |
| Pending | Worker recording or actual queue submission is still pending. |
| Submitted | Actual checked queue submission returned success, but checked device completion is pending. |
| Skipped | Worker emitted no write; even a successfully completed empty submission cannot publish a content version. |
| Complete | Worker emitted the declared write and checked submit, timeline counter and zero-time host wait all succeeded. |
| Unknown | Recording, submission, counter/wait, owner lifetime or retirement is uncertain. Subsequent successful polling cannot recover the same event. |

Complete describes historical execution, not current resource validity, host
readback visibility or physical content authority. A later write can invalidate an
old resource/intent snapshot without erasing the earlier submission's history.
No revision or submission identities are ordered across allocations or queues.
Unknown retains the resources; physical admission/quarantine still belongs to the
existing backing range owner, and this API does not enroll producers in it.

## Bounded actual producer

`BufferCacheRuntime::ClearBufferChecked` is an explicit isolated staged fill.
It uses the same actual fill/barrier recorder as ordinary ClearBuffer, retains the
actual StagedBufferPin, and checks the pin again on the worker before recording.
An optional worker predicate supplies a supported no-emission path. The caller
captures the intent revision with the pin under the existing cache mutex; metadata
allocation and checked submission happen outside that lock. There is no ordinary
game call site and no per-draw flush policy change.

Ordinary Draw's existing worker command now returns whether it emitted a draw;
ordinary Scheduler::Record ignores that return value. Its actual failed-pipeline
guard is extracted into the fault fixture and observed with RecordCheckedWrite.
This tests the real guard body against fake pipeline/Vulkan dispatch, not a native
shader or a full storage-binding/draw integration. Ordinary draw/indirect/compute
provenance capture is still unimplemented and must not be inferred from that fixture.

Accepted evidence records and their real allocations are retained in the existing
Scheduler, bounded to 256 isolated records. They are disarmed only through the
renderer's existing successful-device-idle retirement boundary, after producer
joins. Retirement removes native identity/resource access and returns Unknown;
it cannot certify content. This is deliberately unsuitable for automatic ordinary
rendering enrollment until retirement/consumer integration is established.

## Validation boundary

The new hidden native `[f3-provenance]` case has its own CTest process, preserving
the existing per-process System lifetime restriction. It uses real ordinary cache
intent publication, staged resources, checked Vulkan fill/queue completion,
System/Kernel/process and device mappings. It checks skipped fill intent, distinct
submissions for the same dirty interval, old intent snapshot invalidation without
rewriting historical completion, a worker-pending later command, independent stale
replicas, remap before old-command completion, retained old bytes and rejection of
the old physical plan even after the replacement representation is warmed. A
completed old allocation is never associated with the new mapping. No physical
publisher exists in this slice.

The separate actual-body fault fixture checks the failed-pipeline Draw guard,
indexed draw emission, queue-accepted/device-pending distinction, submit/counter/
wait/partial-record/sealed-pin/owner failures, sticky Unknown and native payload
retention after cache/caller owners are dropped. Vulkan dispatch/device execution
and pipeline state in that fixture remain mocks. Existing mutation gates, native
alias adapter and original F2/F3 negative controls remain separate.

## Next gate

Before any physical latest-writer authority, capture immutable historical
GuestBackingEpoch/physical geometry and actual representation association at the
qualified producer boundary, carry the existing admitted footprint through
submission and validate it at publication. Ordinary skipped draw/dispatch and
multiple writable resources need actual producer integration, not bind-time
assumptions. Establish real queue/synchronization relationships, merge/GC and
mapping/frame-reuse exclusion before choosing between staged or backing sources.
