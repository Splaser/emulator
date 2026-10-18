# M4/F3: controlled partial copy into a mixed target

This slice composes existing transfer provenance and Current Content Gate receipts.
It does not implement physical latest-writer authority, cross-queue ordering,
ordinary BufferCache replica selection, or F2/F3 production acceptance.

## Contract

`ReplicaCopyRequest` can name an existing `destination_receipt` and an explicit
`destination_roots` partition of the untouched target complement. Source roots
still cover exactly the requested source interval. Complement roots cover exactly
`[0,destination_offset)` and `[destination_offset+size,target_size)`, in order.
Missing tails, duplicated/overlapping pieces, pieces inside the overwritten hole,
zero sizes, wrong root projections, Unknown and over-budget declarations reject.
Each side may contain several distinct original anchor Fill IDs and projections.

The builder validates immutable ancestry, then owns copies of both partitions in
fixed arrays (64 pieces each). Admission separately checks every source piece and
every retained target piece, before and after leaving the render-pass context.
Each target binding must match the saved native identity, pin offset/size and
physical identity of both the anchor slot and the old target receipt. Its current
mapping must still match the captured epoch. Mapping-query exceptions reject.
An allocation which exposed a writable host mapping or was retired cannot qualify.

The overwritten target bytes need no old content root/current byte qualification:
none of that old content is retained. Unknown or stale *retained* bytes reject.
For full replacement the complement is empty, but the supplied old target receipt
must still have real checked completion and a valid mapping/storage identity.
The original no-receipt/no-partition API keeps its conservative whole-target-root
requirement. Query success is not an asynchronous admission lease; controlled
qualification and recording remain on the existing GPU/cache thread.

## Immutable composition and actual submission evidence

A new immutable graph points separately to its source-copy ancestry and old
destination-copy ancestry. Covered byte queries project through the source;
uncovered queries project through the old destination. Neither old graph is
modified or compressed into a single root. Root IDs always refer to the original
anchor graph, not the new copy's local command index.

The two dependencies must lie on one existing bounded actual submission spine.
The newer dependency must contain the other as an ancestor; independent branches
are refused. Structural depth helps choose a candidate, but never proves GPU
execution order. The worker requires the actual immediately preceding accepted
checked submission on its owned graphics `VkQueue`. Completed qualification
checks every queue/predecessor, dependency identity, emitted entry/release barrier,
emission and completion edge back to the anchor. An intervening unchecked submit
or unsupported queue cannot qualify. No semaphore/cross-queue model is added.

One real `vkCmdCopyBuffer` performs the exact replacement, with the existing real
entry/release barriers and checked submission. Recording conservatively revokes
overlap on earlier snapshots of that allocation. The new receipt arms its target
range once, using the verified old complement plus copied bytes. Failure never
rearms an old receipt or manufactures successful completion. Native pins remain
retained through queued host work, real queue attempt and trusted device-idle
retirement; uncertain effects remain quarantined.

The four-hop and 16-retained-receipt limits remain. Source and destination may
both reference earlier receipts only when the actual submission-spine constraints
hold. This is bounded composition of existing records, not a new content authority
or coordinator.

## Example and cancellation

Start with A=99, B=10, C=20, D=30. A→B replaces `[16,32)`. B→C copies `[8,40)`,
so C contains 20/10/99/10/20. A later D→C replaces `[12,28)`, crossing two old
roots. C must retain:

| Interval | Original root/value |
| --- | --- |
| `[0,8)` | C / 20 |
| `[8,12)` | B / 10 |
| `[12,28)` | D / 30 |
| `[28,32)` | A / 99 |
| `[32,40)` | B / 10 |
| `[40,64)` | C / 20 |

Later source/intermediate writes do not rebase already copied downstream history.
A later target write cancels only its overlap; other current byte ranges survive.
Generic Unknown recording, uncertain submission, stale mapping, storage/domain
retirement and escaped host pointers remain conservative exclusions. Immutable
planned/history metadata remains inspectable after current eligibility is lost;
it is never a statement of global physical authority.

## Verification

The old implementation's expected refusal is retained in
`.diagnostics/m4-destination-red.log`. The actual-production-body simulated fixture
adds 51 mixed-target modes: distinct left/right roots, replacement across roots,
partial/full replacement, stale covered bytes versus stale/Unknown complements,
gaps/tails/overlaps, wrong projections or bindings, pending/failed submissions,
missing earlier/final barriers, remap, retirement, borrowed declarations, writes
after recording, source+target receipt composition, four hops and fifth-hop refusal.

An independent byte-label oracle adds 256 prefixes with shifted source/destination
positions, original root projections and immutable previous snapshots. Standalone
controls reject unknown left/right complements and test the 64-piece budget.
Mutation controls remove current-complement checks, partition guards, owned
declarations, target-history completion/identity and the target hop limit; each
must fail by assertion rather than compilation error.

The native Vulkan case uses five private unregistered staged allocations over
physical aliases. A separate per-byte value/root array applies copies independently
of production ancestry. Real C readback after mixed-target replacement and E
readback after a fourth-hop copy are compared with it. Later D/C writes test
partial current revocation and unchanged downstream bytes/history. Async target
retirement tests retained native lifetime through trusted idle.

Linux validation is pending. Android remains on demand. The original F2/F3
fixed-required negative witnesses must remain failing; controlled success cannot
close those production defects.
