# M4-F3 staged byte-range current eligibility

This extends the [whole-snapshot gate](M4_F3_CURRENT_CONTENT_GATE.md) with bounded
per-pin eligibility intervals. It does not change historical ancestry, import
cross-submission content roots, reconcile replicas or publish physical authority.
F2/F3 and M3B restricted production eligibility remain Open/blocked respectively.

## Cancellation contract

`CurrentTransferContentRange(transfer, memory, buffer, offset, size)` uses a buffer
index and offsets relative to that snapshot's retained staged pin. The nonempty
interval must be wholly in bounds and wholly eligible. It retains the old checked
completion, intra-batch dependency, immutable mapping and live membership gates.
An eligible interval can still contain Unknown provenance; callers must separately
prove its exact content origin. Returned pointers remain immutable historical
metadata across subsequent operations, not concurrent admission leases.

The whole-snapshot query requires the full interval of every retained pin. Both
queries return the original graph; revocation never edits roots, copy parents,
physical origins, fill values or historical coverage.

Typed `RecordBufferFill` and `RecordBufferCopy` bind destination cancellation to
the actual command and its captured region list. BufferCache's ordinary clear,
copy, upload and readback route through these typed emitters, preserving their
existing barriers and command-buffer choice. Small copies of up to eight regions
retain inline storage. Larger lists own their regions until worker recording.
There is no public generic callback that can claim an arbitrary exact footprint.

Before enqueueing, the destination VkBuffer is matched against retained live
staged pins. Native offsets are intersected with the pin and translated to pin
offsets. Only the destination intersection is removed. Copy source ranges,
untouched complements, disjoint native offsets and other staged allocations
remain eligible even if their physical backing aliases. This qualifies individual
representations, never decides which alias is latest. Controlled transfer batches
use the same exact cancellation before recording and arm only their new snapshot.
Worker completion never rearms an older snapshot.

The interval set has at most 64 valid spans per pin. Fragmentation overflow fails
closed for that entire pin; it never retains a falsely complete prefix. Zero or
overflowing write footprints cancel conservatively. Zero-size, out-of-bounds and
overflowing query ranges are rejected.

Generic `Record`/`RecordWithUploadBuffer`, unknown shader paths, unclassified state
commands and deferred render-pass/barrier work still cancel the whole snapshot.
Their effects are not inferred from shader bindings or intent revisions. Typed
readback only changes its staging destination, so it preserves the source snapshot
unless surrounding unclassified work intervenes. Retirement/remap retain their
strict conservative gates, including original mapping generation and membership.

An actual queue error or uncertain submission callback latches a separate atomic
failure-domain rejection. It cannot be cleared by a later successful status or
completion. Ordinary device-loss reporting and exception propagation remain
unchanged; ranges are never mutated by the worker. Historical graph storage and
the original completed-event checks retain their prior meanings.

## Evidence and boundaries

The initial range query delegated to the old whole-snapshot check. A real-body
controlled Fill of `[16,32)` made its untouched `[0,16)` query fail; the expected
red assertion is retained in `.diagnostics/m4-range-gate-red.log`.

Focused actual-body controls exercise partial Fill/Copy, independent aliases,
nonzero native pin offsets, upload regions, multi-region copy, source preservation,
pending snapshots with later writes, partial recording failures, device-loss
rejection, bounds and immutable history. Vulkan dispatch and execution in these
fixtures are simulated. The fake queue now retains all accepted submissions in
order until completion; it previously replaced earlier uncompleted work, which
was exposed by the new pending-snapshot case.

The standalone independent byte oracle verifies 2,048 eligibility prefixes in
addition to 512 content-origin prefixes, plus explicit fragmentation exhaustion.
Mutation controls remove overlap, native allocation, pin offset, submission
failure, actual typed Fill/Copy and left/right complement guards separately.
Native Vulkan tests perform actual partial Fill/Copy/readback and compare both
untouched bytes and query outcomes while retaining historical origins.

Full Linux and Android workflow evidence is recorded after source validation.
Neither simulated dispatch nor Android library compilation proves device/game
acceptance. Cross-submission/queue roots remain Unknown in this slice.

## Development stages

1. Close provable content provenance: exact transfer coverage, current byte
   eligibility, and eventually explicit cross-submission source transfer under
   checked execution and real synchronization evidence. Unsupported shader and
   queue relationships remain Unknown. This range slice alone does not close
   this stage or infer cross-submission roots from preserved current ranges.
2. Implement replica reconciliation: perform actual buffer copies with proven
   dependencies and dirty-complement preservation. For A writing `[0,64)` and B
   writing `[16,32)`, preserve A's complements and apply B only where proved.
   Remap, retirement and failed submissions must prevent stale publication.
   A derived graph alone is not reconciliation acceptance.
3. Close the original ordinary F3 witness. Controlled M4 mechanism acceptance and
   production F3 repair must be reported separately. Missing producer exclusion
   in M3B restricted eligibility remains an explicit production blocker; no
   ordinary Memory::Write/UMA routing is enabled to bypass it.
