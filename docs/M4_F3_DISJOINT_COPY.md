# M4/F3: explicit-source non-contiguous same-queue Copy

Baseline: `22438fd604` (Linux acceptance of `4bb3231040`). This is a bounded
extension of `RecordControlledReplicaCopies`, not a new content authority.

## Exact partition contract

Regions remain explicit, aligned, nonempty and canonically ordered, but need not
be adjacent. They must be non-overlapping and inside the declared window; the
last region ends at the window end. Every target byte outside the actual write
union, including internal holes, requires an ordered, exact complement partition.
The merge of writes and complement pieces covers the entire target exactly once.
Missing, duplicate, overlapping, Unknown or incorrectly projected pieces reject.
The existing immutable source and target roots, physical association, native pin
identity, mapping epoch and independently checked current qualification apply to
holes just as to outer complements. Receipt ancestry remains immutable.

The production change is confined to `ReplicaCopyProvenance::BuildBatch`.
The existing scheduler already qualifies every declared complement twice and
revokes each planned command destination before worker execution. No new buffer
selection, coordinator, content counter or submission mechanism is introduced.
Actual checked queue predecessor, barriers, completion and retained resources
remain mandatory. Cross queue stays Unknown. A successful query is not an
asynchronous admission lease.

## Failure boundary

Pre-recording refusal emits no new write or completion and does not revoke old
qualification. Once accepted, **all planned write intervals** lose earlier current
qualification, including a suffix that never gets recorded. Internal holes are
not part of that write union. A recording exception can leave a real prefix in
the command buffer; the resulting receipt stays Unknown even if that prefix
executes and its submission completes. There is no transaction rollback.

In this closed partial-recording case, independent old evidence for holes can
survive. A separate Fill into a hole revokes precisely its overlapping bytes;
the remaining hole bytes still need valid evidence. Submission failure or an
unknown execution outcome continues to poison the submission domain globally:
we do **not** claim that holes remain qualified after device-loss uncertainty.
No failed/unknown/unattempted submission manufactures successful completion.
Remap, retirement and later unknown producers continue to fail closed, while
historical root association remains unchanged.

## Deterministic and native acceptance design

The extracted-production-body fixture runs the previous 35 contiguous modes and
41 non-contiguous modes. New controls cover missing/Unknown/wrong-projection/
overlapping/stale hole partitions and a partial recording followed by a separately
flushed hole Fill. Independent per-byte value/root/offset labels check the entire
64-byte target, written prefix and unrecorded suffix. Simulated queue failures
include possible writes despite failure without advancing the timeline; these
are model evidence, not actual hardware device-loss evidence.

Mutation regression retains the prior controls and adds three faults: revoking
the whole bounding window, retaining the unrecorded suffix, and omitting internal
hole current qualification. Complement coverage and final window boundary
mutants have independent metadata probes; all mutants must fail by assertion,
never by a compiler error. Standalone tests add 512 deterministic disjoint mixed
target oracle prefixes over four immutable ancestry hops with multiple holes,
while retaining command/partition budget boundaries and prior oracles.

The real Linux Vulkan test runs both contiguous and disjoint variants using four
isolated staged replicas over physical aliases. Two source intervals [8,24) and
[32,48) leave [24,32) untouched. The first source crosses a nonidentity root
projection; outer complement [48,56) has a different root. The four-hop chain
batch -> single Copy -> batch -> batch imports both source and destination
receipts. All 64 root projections, wrong-projection rejection and complete
readback are compared with an independent oracle. Old hole evidence survives,
old copied-range evidence does not. A later hole Fill invalidates only [24,28),
retains [28,32), and leaves historical ancestry unchanged. A fifth hop rejects;
retained native storage is released only after trusted-idle retirement.

The existing Linux workflow already builds actual Scheduler/BufferCache objects,
runs all five CTest processes, repeats native provenance and extracted fixture
acceptance three times, and archives mutation/extraction/full test logs. No CI
scope reduction is needed. Android is skipped by default. Original fixed-required
F2/F3 negative witnesses remain mandatory and open. This controlled mechanism
neither selects ordinary BufferCache replicas nor publishes physical latest-writer
authority, and does not establish F2/F3 production correctness.

## Verification record

Pending final source commit and Linux CI. Local baseline red evidence:
`.diagnostics/m4-disjoint-red.log`, assertion `bool(result)==!refused` on the new
non-contiguous positive case. Local focused acceptance and mutations are in
`.diagnostics/m4-disjoint-green.log`; full final evidence is recorded separately.
