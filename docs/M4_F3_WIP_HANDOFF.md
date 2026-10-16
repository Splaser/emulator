# M4 physical alias coherency: WIP handoff

Initial checkpoint date: 2026-10-16, at the user's requested 5-hour usage
threshold. Evening continuation established a stable native F3 reproduction.
This is a continuation checkpoint, not M4 acceptance or a production F3 fix.

## Status and constraints

- Write-intent follow-up `d8764c0cf0` records resource-local GPU write revisions at
  ordinary write marking, staged DMA copy/clear and scatter destinations. The
  isolated adapter rejects pre-submit source/target rewrites even when dirty
  geometry is unchanged; post-submit rewrites retain Unknown and quarantine.
  This starts producer metadata but is not submission completion, historical
  physical provenance or latest-writer subrange authority. See the
  [revision record](M4_F3_CONTROLLED_ALIAS_ADAPTER.md#resource-write-intent-revisions).
  Full Linux/Android run [38907387312](https://github.com/Splaser/emulator/actions/runs/38907387312)
  passed at that source: 88 native adapter assertions in CTest and each of three
  extra processes, all configured integration/fault/lifecycle gates and actual
  Android arm64 core/video/shader compilation. Original F3/F2 negative controls
  remain unchanged. Baseline run `38906918308` separately confirms the repeated
  source write was accepted by the old adapter. Both runs' evidence is retained
  under `.diagnostics/ci-<run>/`; no Android/device execution is claimed.

- M3B-F2 remains **Open**. Restricted eligibility remains **blocked**; see
  [eligibility blockers](M3B_F2_RESTRICTED_ELIGIBILITY.md) and
  [producer inventory](M3B_F2_PRODUCER_INVENTORY.md).
- Ordinary `Memory::Write` routing and selective UMA zero-copy remain inactive.
- No new coordinator or broad BufferCache rewrite has been introduced.
- The native F3 witness and test observation helpers have compiled remotely. The
  standalone `[f3]` processes reproduce stale full/partial aliases with whole-byte
  controls, remap rejection and physically equivalent representation qualification.
  Final remote validation is tracked below. **F3 is reproduced, not fixed.**
- No local Android build was attempted; validation continues through remote workflow.

## Initial verified baseline

The checkpoint starts from `3462bbadcf`, previously pushed to both `main` and
`codex/issue-372-fixes` (PR 375 source branch).

- Production source at `3ebb655b97`: Android job passed in run `38870993595`.
- Linux workflow `38873324462` at `46687f1bfa`: passed, including 1708 native
  assertions, 130 production unit cases, integration/mutation checks, renderer
  and FenceManager fixtures. These are baseline results, not validation of this WIP.
- Original F2 witness was reproduced three times: expected CPU value 77,
  observed cache value 10, backing 77. Its `--require-fixed` invocation failed as
  expected. This defect remains open and must remain a regression witness.

## Source audit and current hypothesis

| Area | Existing source and finding |
| --- | --- |
| Physical backing lifetime | `src/common/published_guest_chunk.h`: backing epoch owns generation/alive state, range admission and page gates; lifetime invalidation closes authority even while storage remains pinned. |
| Immutable physical plans | `src/video_core/physical_access_plan.h`: snapshots device mappings, pins physical storage outside mapping locks, then revalidates. `MatchesCurrentDevice` checks captured epoch/generation and physical pages. A storage pin is not content authority. |
| DAddr aliases | `src/core/device_memory_manager.inc`: odd/even mapping generation, reverse alias collection, bounded alias enumeration and inverse-translation verification. Staged-mode Map itself does not perform the UMA unmap path. Higher-level mapping callers still require audit. |
| Staged ownership | `src/video_core/buffer_cache/buffer_cache.h`: ordinary lookup, overlap joining, upload tracking and GPU dirty publication are keyed by DAddr. Physically overlapping but disjoint DAddr windows can own independent staged buffers. |
| Native resource pin | `src/video_core/renderer_vulkan/vk_buffer_payload.h`: pins retain allocation and byte bounds. They do not prove cache membership, current physical association, authoritative content, admission or completion. |
| Representation qualification | `PinExistingDmaRepresentation` validates physical geometry and takes/revalidates a fresh mapping snapshot around pin acquisition. It does not simply reject every historical plan generation change; existing physical-equivalence behavior must be preserved. |

Observed F3 sequence: warm two independent staged buffers A/B from physical
backing 10, then complete a GPU write of 99 through A. Ordinary synchronization
through B can still consult B's DAddr-local tracking and serve its old staged
value 10. Completing physical range admission establishes ordering but does not
itself transfer authoritative content between staged aliases. This explanation
matches the standalone native result. See
[source cause and bounded authority plan](M4_F3_ALIAS_AUTHORITY_PLAN.md).

## Native witness and process-isolation correction

`src/tests/core/controlled_cpu_scheduler.cpp` adds the `[f3]` case to the existing
`controlled_cpu_scheduler_tests` target. `src/core/scheduler_test_access.h` adds
test helpers for ordinary buffer acquisition, Vulkan fill/readback, retained
staged pins and cache retirement.

| Case | Required observation |
| --- | --- |
| Full-page alias | A/B map identical physical pages; GPU writes A=99; same A reads 99; B currently expected to reproduce stale 10. |
| Partial alias | C starts one physical page into A; a 256-byte GPU fill within that page reads 99 through A, currently expected stale 10 through C. Adjacent untouched bytes stay 10. |
| Disjoint control | Separate physical backing D remains 10. |
| Admission control | Existing physical range admission parks the B reader behind A's writer and grants it after completion; no new coordinator is used. |
| Retirement/remap | Retire B before remapping it to backing 55; a retained old pin remains an old allocation, the old physical plan and representation query reject the new mapping, and a fresh representation has a new identity and reads 55. A's unchanged physical association still qualifies despite the global mapping-generation change. |

The driver uses actual System/Kernel/process objects, device mappings, ordinary
BufferCache code and native Vulkan transfer execution through the existing
software-device test renderer. The sequence and manual admission enrollment are
test drivers. This is not a game image, an ARM scalar store, a shader draw, a
GPUVAddr translation witness, or proof that ordinary producers participate in
production admission. Existing extracted cache/pin and renderer fixtures remain
fixtures; do not report their results as this native F3 reproduction.

Commands on the remote Linux build:

```sh
build-integration/bin/controlled_cpu_scheduler_tests '[f3]'
CITRON_REQUIRE_F3_FIXED=1 build-integration/bin/controlled_cpu_scheduler_tests '[f3]'
```

The F3 case is hidden from an unfiltered Catch2 invocation and explicitly selected
by its own CTest process. KernelCore's host dummy KThread is thread-local and
retains the first Kernel; creating two complete System instances sequentially
in the same host test thread reused stale kernel state. Run `ctest`, the original
unfiltered scheduler executable, or the explicit `[f3]` process; do not select both
System lifetimes in one executable invocation.

Default mode intentionally requires stale alias values 10 and prints
`F3 REPRODUCED (not fixed)` only after positive controls pass. The second command
requires coherent values 99 and should fail until F3 is fixed. The repeat driver
`python tools/physical_coherency_tests/run_native_f3_tests.py --repeat 3` retains
each normal log and explicitly rejects crashes, timeouts, failed positive controls
and unexpected negative-mode failures. Catch assertions outside the GPU callback
receive captured setup/observation exceptions rather than terminating the GPU
worker on an uncaught test exception.

## Resume roadmap

1. Extend the [bounded authority implementation plan](M4_F3_ALIAS_AUTHORITY_PLAN.md)
   with persistent write-site physical/provenance metadata and latest-writer
   subrange ownership. Reuse the now verified
   [isolated alias adapter](M4_F3_CONTROLLED_ALIAS_ADAPTER.md) for qualified exact
   copies. Its per-operation snapshots are not a general write-site version issuer.
   Preserve DAddr lookup and GPU dirty complements; do not add a coordinator.
2. Integrate overlapping alternating writers (currently refused), merge/GC
   authority transfer and frame-reuse exclusion. The adapter already covers
   disjoint reverse writes, source/target retirement and submitted remap Unknown;
   native adapter success is not ordinary-path or allocator-lifetime acceptance.
3. Preserve the original ordinary F3 negative witness and F2 defect. A manually
   driven copy adapter cannot count as an ordinary-path coherency fix. Only after
   the implementation exists may fixed-mode passing controls replace this gate.
4. Run the complete `pr375-pr380-integration.yml` gates after source changes.
   Preserve M3B native/integration/mutation regressions; Android production source
   changes require the remote full scope, without a local Android build.

## Continuation evidence: 2026-10-16 evening

- Initial run [38891421101](https://github.com/Splaser/emulator/actions/runs/38891421101)
  compiled production and native targets, passed the 130-case ordinary test suite,
  and printed full/partial stale 10, same-DAddr 99 and remap 55. Its combined native
  executable timed out; this was not clean witness acceptance.
- Diagnostic run [38896969297](https://github.com/Splaser/emulator/actions/runs/38896969297)
  confirmed standalone F3 normal exit under GDB (28 assertions). Both native
  cases in one process failed in whichever complete System lifetime ran second.
  Test process isolation is implemented at `0fd0f17c9e`.
- Run [38897769357](https://github.com/Splaser/emulator/actions/runs/38897769357)
  at `f6ab101715` passed all three CTest processes (130 ordinary cases, 1708
  scheduler assertions, 36 F3 assertions) and three additional standalone F3
  repetitions. Fixed mode produced precisely the two expected alias failures;
  the wrapper incorrectly assumed the older Catch2 exit convention. `62259c5dbd`
  recognizes Catch2 3.16's test-failure status 42 and records process exit codes.
- Final validation of `48d95a8ba3`, with two additional native mapping qualification
  controls, passed in run
  [38898475861](https://github.com/Splaser/emulator/actions/runs/38898475861).
  All three CTest processes passed: 130 ordinary cases, 1708 scheduler assertions,
  and 38 F3 assertions. Three additional F3 processes each passed 38 assertions
  and exited 0. Fixed mode exited 42 with exactly the two expected alias failures
  (36 passing/2 failing assertions), after normal guest teardown. F2 reproduced
  three times and its negative mode exited 1 as required. Real Linux HostMemory/
  import lifetime and every configured coherency/lifecycle/mutation regression
  passed. Android was intentionally skipped because production code is unchanged.
  Downloaded source stamp, CTest logs, each F3 process log, F2 negative log and
  complete job output are retained in `.diagnostics/ci-38898475861/`.
- Local Windows extracted F2 witness ran three repetitions: backing 77, cache 10;
  invoking its compiled `f2 require-fixed` returned 1 as expected. This is fixture
  regression evidence, not native Vulkan or Android acceptance.

The witness-only continuation through `425de3055b` did not change production code.

## Subsequent continuation: isolated staged alias copy verified

Production source `642a71fb07` implements the explicit admitted alias-copy adapter;
full run [38903097142](https://github.com/Splaser/emulator/actions/runs/38903097142)
passed Linux and Android compilation. Linux passed the original 130 ordinary cases,
1708 scheduler assertions, 38 F3 assertions and 67 new native adapter assertions,
plus three extra adapter repetitions. Test-only weak-payload-owner checks at
`a415dea618` passed full Linux run
[38903908981](https://github.com/Splaser/emulator/actions/runs/38903908981), including
the new exact-copy/failure/retention fixture and every existing integration/mutation
regression. Production source/workflow differences between those heads are empty.

See [adapter contract and evidence](M4_F3_CONTROLLED_ALIAS_ADAPTER.md) for exact
scope, commands/cases, retained resources and Unknown behavior. The original ordinary
F3/F2 negatives still reproduce; automatic ordinary routing, latest-writer authority
and general producer eligibility remain blocked. Next development starts at the
resume roadmap above, not by redoing the verified adapter.
