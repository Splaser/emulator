# M4 physical alias coherency: WIP handoff

Checkpoint date: 2026-10-16. Work stopped at the user's requested 5-hour usage
threshold. This is a continuation checkpoint, not M4 acceptance.

## Status and constraints

- M3B-F2 remains **Open**. Restricted eligibility remains **blocked**; see
  [eligibility blockers](M3B_F2_RESTRICTED_ELIGIBILITY.md) and
  [producer inventory](M3B_F2_PRODUCER_INVENTORY.md).
- Ordinary `Memory::Write` routing and selective UMA zero-copy remain inactive.
- No new coordinator or broad BufferCache rewrite has been introduced.
- This checkpoint adds a native F3 witness candidate and test observation helpers.
  **They have not been compiled or run. F3 reproduction is not yet established.**
- No local Android build was attempted; validation continues through remote workflow.

## Last verified baseline

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

Working F3 explanation: warm two independent staged buffers A/B from physical
backing 10, then complete a GPU write of 99 through A. Ordinary synchronization
through B can still consult B's DAddr-local tracking and serve its old staged
value 10. Completing physical range admission establishes ordering but does not
itself transfer authoritative content between staged aliases. This explanation
is source-derived and awaits execution of the new native witness.

## Unverified native witness candidate

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
| Retirement/remap | Retire B before remapping it to backing 55; a retained old pin remains an old allocation, the old physical plan fails current-device validation, and a fresh representation has a new identity and reads 55. |

The driver uses actual System/Kernel/process objects, device mappings, ordinary
BufferCache code and native Vulkan transfer execution through the existing
software-device test renderer. The sequence and manual admission enrollment are
test drivers. This is not a game image, an ARM scalar store, a shader draw, a
GPUVAddr translation witness, or proof that ordinary producers participate in
production admission. Existing extracted cache/pin and renderer fixtures remain
fixtures; do not report their results as this native F3 reproduction.

Candidate commands on the remote Linux build:

```sh
build-integration/bin/controlled_cpu_scheduler_tests '[f3]'
CITRON_REQUIRE_F3_FIXED=1 build-integration/bin/controlled_cpu_scheduler_tests '[f3]'
```

Default mode intentionally requires stale alias values 10 and prints
`F3 REPRODUCED (not fixed)` only after positive controls pass. The second command
requires coherent values 99 and should fail until F3 is fixed. Neither command
has been executed for this checkpoint. Catch assertions outside the GPU callback
receive captured setup/observation exceptions rather than terminating the GPU
worker on an uncaught test exception.

## Resume roadmap

1. Review and compile the witness remotely. Resolve test setup/build issues first;
   do not change production coherency to make an unproven witness pass.
2. Dispatch `pr375-pr380-integration.yml` on `codex/issue-372-fixes` with
   `validation_scope=linux-only`. Run the normal native suite, then explicitly
   run `[f3]` with `CITRON_REQUIRE_F3_FIXED=1`; retain output and exit status.
   A green default known-defect test alone is not F3 acceptance.
3. Establish deterministic repeated full-page and partial-alias stale results
   with same-address, untouched, disjoint and retirement/remap controls. If
   observations differ from the hypothesis, diagnose the actual path before
   planning a fix. Audit higher-level remap/retirement callers and missing
   stale-representation cases; the retire-before-remap control is not exhaustive.
4. Preserve all existing M3B native/integration/mutation regressions. Re-run the
   original F2 command below and its expected-failing `--require-fixed` variant:
   `python tools/physical_coherency_tests/run_write_coherency_witnesses.py --case f2 --repeat 3`.
5. Once reproduced, publish exact logs, source-level cause and a bounded
   implementation plan. Reuse epoch/range admission and immutable physical pins;
   distinguish representation lifetime from current mapping/content authority.
6. Proposed implementation direction, pending witness: attach physical association
   metadata to staged representations; publish GPU-written physical subranges;
   resolve authoritative content for alias consumers under existing admission;
   revalidate mapping/retirement before effects. Keep DAddr resource lookup and
   preserve GPU dirty complements. Do not widen activation or add a coordinator.
7. Add fixed-mode passing controls only after an implementation exists, while
   retaining a reproducible pre-fix negative witness and the original F2 defect.

No remote workflow has been dispatched for this WIP checkpoint. Resume from this
commit; the earlier baseline's green builds do not cover the new test code.
