# M4-F3 current-content qualification

This slice separates immutable callback-end ancestry from a cancellable current
snapshot check. It does not publish a physical latest writer, import prior
submission roots, or synchronize replicas. F2 and F3 remain Open.

## Contract

`CompletedTransferContent`, `TransferContentForMapping`, `PlannedContent` and
`HistoricalOrigins` retain their existing historical meanings. A new
`CurrentTransferContent(transfer, memory)` requires checked completion, real
intra-batch dependency evidence, strict immutable physical mapping identity,
live native ownership and cache membership, and an uncancelled snapshot.

The boolean cancellation state has no ordering meaning. It cannot compare two
resources, submissions or queues. It is armed once after the typed batch is
recorded; neither worker completion nor a later successful submit can rearm it.
Pending completion returns no evidence without cancelling eventual completion.
The query and recording are GPU/cache-thread operations, not a concurrent lease.
A returned graph pointer remains historical metadata if retained across work.

Every subsequent public `Record` / `RecordWithUploadBuffer` cancels all retained
transfer snapshots before enqueueing. This includes ordinary Fill/Copy and
shader commands with observation disabled or incomplete, before their device
effects, and even if they subsequently fail or are skipped. Disjoint commands,
readback and state-only commands also conservatively cancel. This bounded gate
does not attempt per-byte write classification. The private submission closure
only ends and submits existing buffers; its enqueue bypasses cancellation.
Deferred operations and callbacks still record through the public boundary.

Cache `Unregister` permanently cancels membership on the retained staged payload
before delayed native destruction. Pins still own their resources for in-flight
work. This cancellation does not mutate physical identities or ancestry and does
not pretend to be device completion. Strict mapping generation checks reject
remap/ABA even when geometry later looks identical. A mapping/retirement refusal
at the current gate latches cancellation.

Qualification is limited to the controlled Scheduler and staged-resource domain.
External writers/queues, host mapped writes outside that domain, exact shader
coverage, cross-submission source import, and physical latest-writer authority
remain unproved/Unknown. This API grants no data admission and is not wired into
ordinary Memory::Write or UMA.

## Validation

The initial actual-body negative control implemented the proposed current query
as the historical mapping query. It failed after a subsequent observer-off
command was recorded: `.diagnostics/m4-current-gate-red.log`.

The focused fixture extracts the production public recording/enqueue/cancellation
methods, current query and Buffer membership hook. Its queue and Vulkan dispatch
remain simulated. Controls cover ordinary Fill, Copy, observer-off commands,
upload-buffer commands, cache membership cancellation, same-geometry mapping
generation changes, pending snapshots invalidated before worker completion,
unchanged historical roots/origins, and later completion never restoring current
eligibility. Mutation controls remove record cancellation, current eligibility,
and retirement checks separately, alongside the existing content/dependency
negative controls.

The native Linux test adds checked positive qualification, later Copy/readback
cancellation, and actual BufferCache retirement with retained historical content.
Full Linux/native and Android compilation results are recorded after CI; local
actual-body execution alone is not native Vulkan, Android or device acceptance.
