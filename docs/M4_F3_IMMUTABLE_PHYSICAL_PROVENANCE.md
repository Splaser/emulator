# M4 F3: immutable physical provenance

This slice associates historical physical identity with the existing opt-in storage
observer. It does not implement latest-writer selection or content authority.
Ordinary Memory::Write/UMA routing remains inactive; F2/F3 remain Open and
restricted eligibility remains blocked.

## Identity before execution

A current DAddr translation alone cannot identify an older staged allocation's
physical source. While explicit observation is enabled, a newly created staged
Buffer captures a bounded allocation-origin identity: its native payload identity,
device address geometry, Device MappingEpoch, GuestBackingEpoch and physical byte
segments. The PTE snapshot uses the existing mapping lock and fixed 64-segment
storage. It does not allocate/materialize physical backing or wait for the GPU.
Only bounded host metadata is allocated under the existing cache owner.

At the actual writable storage binding, PhysicalIdentityForBinding slices that
saved origin to the exact native offset/length and checks the current mapping
against it. Revalidation can refuse the association; it cannot replace its physical
identity with today's mapping. The immutable slice is attached to the same
CheckedWrite that retains the actual native payload and actual submission.
Completion never resolves DAddr again.

Allocations predating observation have no origin and stay unqualified. Scratch,
direct/imported buffers, holes, oversized/unknown footprints and representation
identity mismatches also make capture incomplete. Cache JoinOverlap explicitly
invalidates the new representation's origin: this slice does not prove inherited
representations through merge. Origins are not reconstructed after this refusal.
Native resource recreation captures a fresh identity; earlier events retain their
own immutable geometry.
Origin capture is one-shot, including disabled/failed capture attempts. Calling
the hook again cannot rebase an existing allocation or requalify a merged one.

PhysicalWriteIdentity is an identity plan, not the pinned PhysicalAccessPlan used
for actual data transfer. It retains epoch tokens and geometry, not HostMemory
arena/page ownership, and exposes no backing byte pointer. Epoch death disables
qualified completion access while historical values remain inspectable. Building
a future content publisher requires real storage ownership/admission separately;
identity metadata must never be used as permission to access backing data.

Two DAddr ranges can overlap the same GuestBackingEpoch/physical offsets while
using different staged allocations. OverlapsPhysical detects that relation without
comparing resource revisions or ordering submission IDs. This identifies aliases,
not the latest writer or an execution dependency.

## Coverage is shared and monotonic

All ordinary events in one explicit observation scope retain the same coverage
token. The token starts Open: a currently valid prefix is not complete coverage.
Disabling observation closes the scope and preserves its records for inspection.
Starting another scope does not complete an abandoned open scope.

Any unsupported/failed capture, metadata failure or capacity refusal permanently
invalidates that shared token, including the events retained before the failure.
Sealing cannot repair an incomplete scope. Retaining 200 successful records from
an overflowing interval therefore cannot produce complete producer coverage.
This remains a storage projection; closing it does not enroll images, transfers,
gather, attachments or other producers in the same Vulkan batch.

Scheduler::CompletedPhysicalIdentity is the checked historical access gate. It
requires actual Complete execution, a closed complete coverage scope, matching
native/range metadata and live identity epochs. Pending, Submitted, Skipped,
Unknown, retired, open or incomplete records cannot pass it. Its result still
describes the OLD association after remap and is never a current-authority
certificate. A future publisher must additionally revalidate the intended mapping,
retain/admit storage, account for every overlapping writer and establish actual
synchronization/visibility relations.

## Review regressions and evidence boundaries

The deterministic actual-body Draw/observer/Scheduler fixture explicitly injects
VK_ERROR_DEVICE_LOST from SubmitQueue. It checks the original exception result and
device-loss reporting, observed Unknown, no successful timeline progress or queued
device effects, and permanent refusal by CompletedPhysicalIdentity even after the
fake driver stops reporting errors. Ordinary error propagation is preserved.

The overflow fixture records 257 actual Draw worker callbacks: all execute exactly
once in the existing batch, the first 256 metadata records remain, and the shared
coverage token makes every retained record ineligible for completed physical
provenance. The fixture also covers late remap, replacement native identity,
pre-observation allocations, physical aliases, partial cross-page slices, holes,
origin invalidation and dead backing epochs. Vulkan/PTE dispatch in this layer is
simulated; the method bodies and identity implementation are production code.
An additional mutation removes the actual completed-provenance coverage check;
the overflowing-prefix assertion must fail. Its expected failure output and
generated C++ are retained with the workflow evidence.

The native [f3-provenance] process uses real System/Kernel device mappings,
ordinary staged allocations and checked Vulkan transfers. It verifies stable
association, independent staged aliases to the same physical storage, a remap
after actual queue acceptance, immutable old geometry/bytes and rejection of
pre-observation allocations. These are transfer commands, not actual shader/game
execution or Android device acceptance. Original F2/F3 negative witnesses remain
required.

## Next gate

Real synchronization provenance is still unimplemented: same-queue execution and
memory dependencies, cross-queue semaphore relationships, transfer/shader access
dependencies and partial interval coverage must be established explicitly. Do not
replace those proofs with a global content_version, resource revision ordering or
the largest submission ID. Latest-writer authority is a later, separate step.
