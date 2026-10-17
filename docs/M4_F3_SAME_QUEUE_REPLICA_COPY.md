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
Different queues, absent/wrong scopes, incomplete journals and failed submissions
remain unproved/Unknown. Pending completion does not qualify as completed content.

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
source/target writes, remap and retained allocation lifetime.

Source `d783250b0d7cb1f79558566f00d544cb84248178` passed
[Linux-only workflow 39022879191](https://github.com/Splaser/emulator/actions/runs/39022879191),
Linux job `117368038043`:

- Full CLI/shader/unit build and all five CTest processes passed. The native
  provenance case passed 211 assertions, followed by three independent repeated
  processes with the same 211 assertions each.
- The 49 new replica modes passed alongside the previous 46 transfer-content
  modes. All 42 mutation controls failed by assertion as required. The 43 fixture
  logs and all 17 extracted production input hashes were checked against the
  committed Git blobs.
- Standalone content/eligibility tests passed, including 512 content and 2,048
  eligibility oracle prefixes and the replica overlay cases. Full registration,
  physical coherency, backing-import and lifecycle regressions passed.
- Original F3 fixed-required mode still failed two alias checks with process exit
  42; F2 still reported `expected=77 observed=10 backing=77`. Controlled copy
  acceptance is separate from those open production defects.

Logs and downloaded artifacts are retained in `.diagnostics/ci-39022879191/`.
Android was intentionally skipped. Device/game acceptance is untested. The
following documentation-only evidence update does not repeat source validation.
