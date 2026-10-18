# M4/F3: mixed-root internal holes and Copy provenance ceiling

Baseline: `71ed2ddbed` (accepted implementation `d223b5ca33`). This round closes
the controlled Copy combination acceptance stage. Production `BuildBatch`,
`HasRoot`, Current Content Gate, checked submission, queue synchronization,
receipt ancestry and pin/lifetime mechanisms are unchanged. No production defect
has been found by the new combinations. No general DAG or authority system is added.

## Concrete partition and oracle

Four isolated staged replicas are initialized to distinct values. The three
explicit writes target [8,16), [32,40), [56,64). Two internal holes retain:

| Target interval | Historical root | Original root offset at interval start |
| --- | --- | --- |
| [16,24) | initial target Fill (2) | 16 |
| [24,32) | other replica Fill (3) | 4 |
| [40,48) | initial target Fill (2) | 40 |
| [48,56) | second source Fill (1) | 12 |

The outer [0,8) complement retains root 2 / offset 0. Source allocation-local
copies make the first and third write projections root 0 / offset 0 and root 0 /
offset 32, independently of their target offsets 8 and 56. The middle write is
root 1 / offset 32. Exactly eight pieces (three writes, four hole
pieces, one outer piece) form a complete disjoint partition of all 64 bytes.

An independent byte oracle starts from Fill labels/values and applies declared
source/destination byte assignments. It never obtains its expected labels or
values from production provenance queries. Four actual same-queue hops compose
batch -> single Copy -> batch -> batch, importing both source and target receipts.
The whole-window single Copy transports all seven mixed pieces inside [8,64).
The following batches preserve both mixed holes. Every output root/offset is
compared byte by byte; wrong projections and a fifth hop reject.

## Negative controls before acceptance

A dedicated extracted-production-body fixture has 31 modes / 34 trials: each of
the four hole root pieces has its own stale qualification probe. Missing,
duplicate, overlapping, Unknown and incorrectly projected complement pieces
reject. Admission refusal emits no new submission and leaves prospective write
intervals qualified unless an independent domain/mapping/lifetime exclusion applies.

Before worker execution, **every old target byte** is checked: all three planned
write intervals have lost qualification, while every independently known untouched
piece retains it. Host preparation can throw synchronously during admission's
Flush and poison the whole domain; that case deliberately requires global refusal.

The simulated recorder can throw after recording one or two Copy commands. Those
prefixes may execute on a successful checked submission while the receipt remains
Unknown. All possible write ranges, including the unrecorded suffix, stay revoked.
A separate hole Fill cancels only its actual overlap; every remaining old byte is
queried independently, including the other root in that same hole and both roots
in the second hole. Failed submission can have no effects or execute all recorded
writes despite returning device-loss; neither advances a successful timeline.
Domain uncertainty continues to reject all old hole qualification. No rollback is
assumed. These faults are simulated execution evidence, not real device-loss proof.

Other controls cover pending completion, missing synchronization, wrong queue,
remap before admission / before worker / after completion, retirement at the same
boundaries, unknown producer before/after, later source and hole writes, owned
immutable declarations, source/complement/command budgets, and the four-hop bound.
Historical association is checked separately from current eligibility and physical
authority; later source writes do not rebase completed downstream ancestry.

Four new mutants skip later internal-hole qualification, skip adjacent root pieces,
retain the first planned write, or bypass historical complement root validation.
They join the prior 70 assertion mutants. The targeted red witness runs only the
new mixed-hole fixture with the later-hole current gate bypassed; admission then
incorrectly succeeds on a stale second hole and `bool(result)==!refused` asserts.
No production patch is necessary to make the unmutated controls pass.

Standalone metadata acceptance also exercises both mixed holes with **64 valid
complement pieces**, then adds a valid 65th piece and requires rejection. All byte
projections remain independently checked; existing 32-command / 64-source-piece
boundaries and prior deterministic oracles are retained.

## Real Linux Vulkan and remaining boundaries

The existing native Vulkan test adds a third bounded layout, after trusted-idle
retirement frees retained receipt capacity. It executes actual Copy commands,
checked submissions, barriers and complete readback; there is no intermediate
readback submission inside the four-hop spine. It checks all four old hole pieces,
every new target root/projection, later source overwrite, later target/hole local
Fill, bytewise current eligibility after both writes, and pinned retirement.
Native values/root labels are maintained independently of the production graph.

Both extracted fixture runners include the new fixture, preserving first-
registration / observer integration coverage. The existing Linux workflow already
repeats the native test and full positive fixture three times, runs all CTest
processes and the existing coherency/backing/lifecycle suites. Android stays skipped.
Original F2/F3 fixed-required negative witnesses remain mandatory and Open.

No cross-queue support, ordinary automatic BufferCache replica selection,
latest-writer authority, Draw/Dispatch expansion or replica reconciliation is added.
Query success remains a snapshot observation, never an asynchronous admission lease.
Actual hardware failure/recovery and ordinary production F3 correctness remain unproved.

## Stage closure and next work

After this round's Linux acceptance, controlled Copy provenance expressiveness is
considered stage-complete at the existing bounded contract. Do not add further Copy
combination cases unless a test or review identifies an actual defect. The next
stage is a **bounded reconciliation planner**, starting with its contract, budgets,
source/current eligibility and failure invalidation rules. It must reuse the
accepted physical/synchronization/content/receipt evidence and keep historical
ancestry, current qualification and any future content authority distinct. Planner
implementation and automatic replica choice are outside this acceptance round.

## Verification record

Pending final source commit and Linux CI. Local targeted red evidence:
`.diagnostics/mixed-hole-second-current-red.txt`. Local focused acceptance and
assertion mutations: `.diagnostics/m4-mixed-holes-local.log`.
