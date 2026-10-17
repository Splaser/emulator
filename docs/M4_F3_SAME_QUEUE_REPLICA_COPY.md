# M4/F3: controlled same-queue replica copy

This slice transfers exact content ancestry across two actual checked Vulkan
submissions. It does not publish physical latest-writer authority, reconcile
ordinary game buffers, or close F3/F2.

## Admission and execution

The bounded case uses two different staged allocations initialized by one closed
controlled parent Fill/Copy batch. Two different DAddr bindings must name exactly
the same saved physical interval in the same `GuestBackingEpoch` and mapping
epoch. The source interval must have an exact completed, current parent root;
the entire target pin must have one exact completed, current parent root so both
untouched complements have explicit ancestry. Mixed/unknown complements fail.

Neither allocation may ever have exposed a writable mapped host pointer. This
sticky restriction closes a producer path that typed GPU range cancellation
cannot observe. The native witness uses private staged buffers outside ordinary
BufferCache registration/selection. Qualification and recording run on the
existing GPU/cache thread; these queries are not concurrent admission leases.

The consumer owns one actual `vkCmdCopyBuffer`, with an actual entry memory
barrier and release memory barrier. The worker requires the parent to be the
immediately preceding accepted checked submission on the actual owned graphics
`VkQueue`. An intervening unchecked submission clears that witness. This is
deliberately narrower than all legal same-queue dependency chains. Numeric ticks,
resource revisions and completion order do not establish the relation.

The entry barrier covers earlier transfer writes and the consumer's transfer
read/write; the release covers the copy before subsequent shader/transfer
accesses. Both emitted barriers are journaled and checked separately. Vulkan
pipeline barriers can scope commands across submissions in same-queue submission
order; submission order alone does not establish the required memory dependency.
See the [Vulkan synchronization specification](https://docs.vulkan.org/spec/latest/chapters/synchronization.html)
and [`vkCmdPipelineBarrier`](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdPipelineBarrier.html).
Different queues, absent/wrong scopes, incomplete journals, failed submission or
unconfirmed completion remain Unknown.

## Immutable ancestry and current qualification

`ReplicaCopyProvenance` holds the immutable parent graph and exact copy geometry.
Root command IDs retain their parent namespace. The new local copy graph is not
relabeled as a new Fill root. For A = 99 and B = 10 on `[0,64)`, copying only
`[16,32)` proves B's left/right complements still originate from its old 10 root,
while the middle originates from A's 99 root. It cannot prove B's whole range
originates from A.

Admission rechecks current roots after leaving a render pass. Before emission,
the worker checks payload membership/retirement, escaped host pointers and the
captured epoch generation. The copy receipt retains pins through the real queue
attempt and trusted device-idle retirement. Remap never resolves the historical
event against a new backing. Current queries additionally check current mapping,
the submission failure domain and destination byte eligibility.

A later source overwrite does not change bytes already copied or their history.
A later target write revokes only overlapping current destination bytes; generic
unknown recording cancels current eligibility conservatively. Remap, dead backing,
retired allocation and newly exposed host pointers fail current qualification.
Historical metadata remains inspectable. A completed historical receipt is not a
statement about current physical authority.

Only one hop from a local parent graph is admitted. Chained imported receipts,
nonadjacent unknown submissions, mixed-root whole targets, concurrent producers
and cross-queue semaphore/ownership chains are outside this slice.

## Verification

The retained initial negative witness is
`.diagnostics/m4-replica-sync-red.log`: history/bytes alone incorrectly accepted a
copy after entry dependency evidence was removed. The implemented gate rejects
that case even when simulated bytes look correct.

The actual-production-body simulated fixture has 49 replica modes. Controls cover
missing/wrong entry/release barriers, broken actual queue/predecessor evidence,
pending completion, failed parent/consumer submissions (including ordinary error
propagation), stale source intervals, unknown or overwritten complements,
geometry/resource substitution, remap before/after emission, escaped mapped host
pointers, post-copy source/target writes, and asynchronous retirement. Mutation
controls independently remove each critical guard or command and must fail by
assertion rather than compilation error. These are simulated-driver evidence.

The native Vulkan witness separately creates two private staged allocations over
physical aliases, submits parent Fills and a second checked Copy, waits for real
completion and reads back the middle plus both complements. It also checks later
source/target writes, remap and retained allocation lifetime. Linux CI evidence
will be recorded after the source run completes. Android validation is on demand;
this portable scheduler slice uses Linux compilation and unit/native regressions.
