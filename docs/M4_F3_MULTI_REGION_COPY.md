# M4/F3: explicit-source same-queue multi-region Copy

Baseline: `70fc6ae474`. This extends the existing controlled receipt/provenance
mechanism; it does not select replicas or establish physical content authority.

## Contract and bounds

`RecordControlledReplicaCopies` takes one original anchor, one destination slot,
one target window and explicitly ordered source regions. Each region names an
anchor source slot, exact source/destination offsets, length, optional source
receipt and an exact root partition. Source and target receipts must belong to
that anchor, retain the saved native identity/pin geometry/physical binding, and
lie on the same retained actual submission spine. Structural depth selects a
candidate predecessor; ancestry alone never proves execution order. The worker
still requires the actual immediately preceding accepted checked submission on
the owned graphics queue.

Regions must be aligned, nonempty, in canonical destination order, adjacent and
cover the declared window exactly once. Internal holes, overlap, unsorted or
out-of-bounds regions reject. Self-copy into the destination allocation rejects.
This slice does not admit disjoint windows with internal retained holes. Source
partitions must cover each exact source interval, including root boundaries and
nonidentity original root projections. Unknown, stale, missing or overlapping
pieces cannot qualify. Every untouched complement byte outside the window needs
known historical provenance and independent current qualification. Physical
source/destination slices must match captured backing/epoch/segments, through
distinct DAddr/native allocations. Mapping-query exceptions reject.

The immutable `ReplicaCopyProvenance` owns all region/root declarations and
separate source/destination ancestry. Each output byte projects through its
unique source region or old destination complement. The original root IDs remain
anchor command IDs. Later source writes cannot rebase captured downstream
history; later target writes cancel only intersecting current ranges.

Bounds remain explicit: four actual submission hops, 16 retained transfers,
eight anchor resources, 32 commands per batch, 64 aggregate source root pieces,
and 64 complement pieces. One batch consumes one submission hop, not one hop per
region. All anchor resources are retained and checked; an unused resource's
mapping/lifetime cancellation may conservatively reject more than necessary.
Partition/eligibility capacity exhaustion never widens qualification.

## Failure qualification

| Event | New receipt | Earlier target qualification |
| --- | --- | --- |
| Rejected admission/allocation before recording | No receipt/completion | No new cancellation; existing unrelated writes still count |
| Accepted recording, before queue attempt | Pending or Unknown; never Complete | Entire planned write union conservatively revoked |
| Partial recording, successful submission of a possible prefix | Unknown even after timeline progress | Entire planned union revoked, including the unrecorded suffix; independently proven complement may survive |
| Submit failure, exception or unknown execution outcome | Unknown, no invented successful completion | Planned union revoked; existing submission-domain uncertainty conservatively refuses all current qualification |
| Successful checked completion with complete synchronization evidence | Historical provenance available; current gate still required | Covered bytes cannot reuse old qualification |
| Later write/remap/retirement/unknown producer | Historical graph unchanged; current gate may refuse | Existing byte-range and storage/mapping exclusions apply |

The existing `RecordTransferBatchImpl` revokes planned destinations before any
worker command may run. Each region emits a real `vkCmdCopyBuffer`, entry/internal
barriers and one final release, under one actual checked submission. Completion
checks the dependency identities, actual queue/predecessor, emission, timeline,
internal command dependencies and release evidence for every command. Recording
failure does not discard possibly recorded GPU commands or pretend to roll back
their writes. Pins remain retained until host work has drained, a queue attempt
is accounted for and trusted device idle permits retirement. Query success is
not an asynchronous admission lease.

## Acceptance and evidence boundaries

The baseline red witness `.diagnostics/m4-multi-red.log` shows ordinary batch Copy
cannot import known roots from previously initialized external replicas. The
new extracted-production-body fixture adds 35 deterministic modes covering
adjacent regions, exact roots/projections, holes/overlap/bounds/Unknown/stale
sources and complements, budgets, physical mismatch, owned declarations,
pending work, partial recording, host failure, submit failure, unknown effects,
missing synchronization/queue linkage, remap, retirement and the four-hop bound.

The simulated queue can apply recorded writes despite returning a submission
error, without advancing the completion timeline. Another fault emits a first
copy then throws, allowing that prefix to execute on successful submission.
Independent per-byte value/root/offset labels verify these outcomes without
assuming transaction rollback. Old planned coverage must be unqualified even
where no suffix bytes were copied; old untouched complement must remain
qualified in the closed partial-recording case. These injections simulate device
execution and do not prove real device-loss recovery.

Six new mutations remove current qualification, planned revocation, suffix
recording, unique destination coverage, final window coverage or original root
projection. All must fail by assertion. Standalone tests exercise the valid
32-command/64-source-piece/64-complement boundary and refusal at 33/65/65.

The native Linux Vulkan case uses four private, unregistered staged allocations
over aliases and an independent byte oracle. Anchor copies create a nonidentity
source projection and mixed target complement. Its four-hop sequence composes
batch -> single Copy -> batch -> batch, importing explicitly named source and
target receipts. Complete target readback and all 64 roots/offsets are compared
with the oracle; wrong projections and a fifth hop reject. Subsequent source and
target writes, retained target pins and trusted-idle retirement are checked.
No intermediate readback submission is inserted into the controlled spine.

Linux validation is pending. The existing full Linux production build, tests,
three native repeats, original F2/F3 negative controls and lifecycle suite remain
enabled. Because Scheduler production code/header changed, the early native
translation-unit check now explicitly includes real `vk_scheduler.cpp` and
`vk_buffer_cache.cpp`. No Android-specific paths changed; Android remains on
demand and is not claimed validated here.

Cross-queue remains Unknown. There is no ordinary BufferCache automatic source
selection, global coordinator, physical latest-writer publication, Draw/Dispatch
scope expansion, or claim that F2/F3 are fixed.
