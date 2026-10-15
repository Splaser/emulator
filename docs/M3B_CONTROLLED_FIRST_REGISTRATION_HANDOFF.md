# M3B - Controlled First Registration Integration

Handoff updated 2026-10-15 (Asia/Singapore). **The end-to-end first-registration stage is
NOT implemented or accepted yet. F2 remains open.** This file is the home-machine roadmap,
not a claim that prepared-store tests fixed production cache registration.

### Evening continuation from `8ca6197c67`: roadmap step 3 ordering gate

`PhysicalRegistrationBundle` reserves one bounded physical range request before closing every
deduplicated page gate. A writer on the second/last page (including a CPU physical alias) keeps
the entire registration Draining. It supplies owned pages and an external representation owner;
the controlled caller still has to derive and qualify the actual complete cache footprint.

After externally certified registration completion, a separate admitted `CachedWrite` can use
actual `Memory::WritePreparedCached8/16/32/64`. `BufferCache::CommitControlledCpuWrite` invokes the
store first and updates the real tracker for every supplied qualified device alias afterwards,
while admission remains held. Stale CPU views and GPU-dirty/pending-scatter targets refuse without
a legacy fallback. The alias list/stability and absence of required preservation are explicit
caller prerequisites, NOT automatically proved by this adapter. No ordinary caller is installed.

`run_first_registration_tests.py --repeat 10` composes actual Memory Write/WriteCached, HostMemory,
PageTable, BufferCache Register/ChangeRegister and SynchronizeBuffer/UploadMemory/
ImmediateUploadMemory with actual MemoryTrackerBase/WordManager. Its acceptance gates are:

| Interleaving | Final backing | Final cache upload | Real tracker |
| --- | --- | --- | --- |
| CPU writer enters first; full registration waits for its actual store | 77 | 77 at both device aliases | clean after upload |
| Registration closes first; NeedSlow is followed by an actual protected cached store | 77 | 77 at both device aliases | dirty after store, clean after upload |
| Ordinary legacy Write with handshake disabled | 77 | 10 at both device aliases | clean, exposing the stale-cache defect |

Removing post-store tracker publication fails with 72; closing only the first page fails with
71; omitting snapshot/store exclusion fails with 75. Snapshot exclusion is nonblocking and does
not add a range lookup, cold pin or allocation to the prepared fast store. Cumulative publication
is still not a consumable dirty batch. Device mapping/tag fanout, cache allocation and synchronous
upload completion in this suite are fixtures. This is controlled step-3 evidence, not Vulkan
driver evidence or completion of the end-to-end stage. The original F2 witness remains required
and failing; steps 1/2 footprint/owner preparation and steps 4-6 immutable upload, quarantine,
checked real completion and production caller integration remain open.

The earlier native run [38711873776](https://github.com/Splaser/emulator/actions/runs/38711873776)
is now confirmed successful for both Android and Linux at `ecf9bb31e8`. That result predates
this continuation. Current-slice Android/Linux validation must be matched to its own source SHA.

## Checkout and branch policy

Work on `codex/issue-372-fixes` in the personal fork `Splaser/emulator`. Personal `main` is
fast-forwarded to the same commits; push both atomically. The completed PR380 integration
branch was deleted locally/remotely. Do not recreate it, close/merge upstream PR375, or modify
the historical F2 branch. No local full Android build is required.

On the home machine, preserve its local work before switching/pulling:

```powershell
git status --short --branch
git diff
git fetch origin --prune
git switch codex/issue-372-fixes
git merge --ff-only origin/codex/issue-372-fixes
gh run list --repo Splaser/emulator --workflow pr375-pr380-integration.yml --branch main --limit 3
```

If that branch is absent, create it tracking `origin/codex/issue-372-fixes`. Do not reset a
divergent home checkout or discard pending work. Match native evidence to the exact production
source SHA; read all failed jobs' full logs only for the latest applicable run.

## Saved implementation and evidence

Latest prepared-write production source: `ecf9bb31e8`. Remote validation was dispatched as
[38711873776](https://github.com/Splaser/emulator/actions/runs/38711873776); its result was
not yet available at handoff. Any subsequent evidence-only commit changes documentation,
not the production source tested by that run.

- `0ed92c3efd`: real HostMemory physical-page storage, backing-canonical page writer gates,
  successful post-store byte publication, failed CAS without publication, nonblocking
  first-registration page drain. Native run 38704560296 passed Android and full Linux jobs.
- `06408b9ce5`: actual PageTable consistent tag/backing snapshots, real CPU map/debug/cached
  mutator guards, resize/retirement invalidation, cold `Memory::PrepareControlledCpuPage`.
  Native run 38708541040 passed Android and full Linux production/regressions.
- The subsequent prepared-write implementation adds explicit public
  `Memory::WritePrepared8/16/32/64` and an actual `Memory::Impl::Write(prepared, VA, T)` overload.
  Ordinary Write wrappers/body remain legacy. Cold preparation captures an active-context epoch;
  actual SetCurrentPageTable invalidates views even on switch-away/switch-back. Hot execution
  uses context/PTE try-locks, checks immutable view identity/epochs/page bounds/tag, then page
  writer entry, actual store, exact publication and writer exit. Refusals never fall back.
- Windows actual CPU mapping/Write tests pass alias gates, 48-bit normalization, remap/tag
  invalidation, stale active context, Busy under mutator, cross-page refusal, independent
  writer release versus registration drain, exact bytes and 2,000 writes with zero hot heap
  allocations or range enqueue. Negative controls 51/54 remove cold/hot validation and fail.
  System/device services, registration representation owner and driver services remain fixtures.
- Original F2 remains `expected=77 observed=10 backing=77`; `require-fixed` exits 1. Keep this
  failure, original stale-byte assertions, queue-cycle witnesses and unsafe-insertion controls.

**There is no normal-game enrollment, actual controlled BufferCache first-registration path,
cached-store preservation adapter, DMA admission or new Vulkan device evidence.** The current
prepared Write result is explicit: Stored, NeedSlow, Stale, Busy, Retired or Invalid. Callers
must not drop a refused write or bypass admission with legacy memcpy. No per-store cold pin,
shared-owner creation, physical registry lookup or range ticket is allowed.

## Next controlled end-to-end contract

1. Prepare the complete stable CPU VA views and immutable physical registration plan cold.
   Include the actual coarse BufferCache allocation, cache/protection and upload coverage,
   not just the requested byte or starting page. Deduplicate physical aliases by backing
   epoch/page. Reject holes, mixed/retired identities and unsupported layouts before effects.
2. On the actual BufferCache side, prepare a bounded all-page registration request and retain
   real representation/storage owners. Reserve ONE atomic physical range bundle before
   Closing every affected fast-entry gate. Never hold partial page admission while parked.
   Unknown/capacity/failure is not permission to bypass. No cache/PTE locks across suspension.
3. While an independently released prepared CPU writer is paused before its actual store,
   registration must return Draining/Park without CPU cached marking or backing upload.
   The writer stores 77, publishes exact bytes and exits. Admission can then grant the whole
   footprint. A queued view invalidated by remap or process switch must refuse/reprepare
   before acceptance; pinned storage alone is not current-address-space CPU permission.
4. Only after qualification may the controlled path call the actual cache registration and
   initial CPU cached/protection marking and upload. Upload from retained immutable physical
   targets; do not retranslate a queued old plan through live DAddr/VA. Keep newly allocated
   cache content unavailable to ordinary readers until registration readiness is certified.
5. Record/submit actual transfer work and retain its exact completion identity. Callback return,
   slot registration, `Flush` return, `PublishTracked` and unchecked `Finish`/WaitIdle are not
   completion or visibility proofs. Use checked transfer completion and required Vulkan
   visibility barriers; poll without blocking/recursively pumping the sole GPU worker.
6. After trustworthy completion/data visibility and a controlled read of 77, publish Tracked
   and registration-ready state, then release admission. Partial/uncertain upload/submit or
   completion failure goes Unknown with owners retained and dependent access isolated.
   Certified no-effect cancellation must keep failed/uninitialized cache content inaccessible.

The prior generic PublishTracked helper permits early closure tracking; that is not the
controlled stage's success sequence or permission to treat content as valid. Published byte
bits are cumulative observations, not a clearable dirty batch. Do not consume/clear them without
a separate sequence/incremental acknowledgement proof.

## Real source edges to integrate

- `src/core/memory.cpp`: ordinary and explicit prepared Write, cold preparation,
  SetCurrentPageTable, HandleRasterizerWrite, RasterizerMarkRegionCached and MapPages.
- `src/core/controlled_cpu_page.h`: immutable prepared view/context qualification and bounded
  actual store; cached/debug targets currently return NeedSlow without callbacks.
- `src/common/physical_cpu_page.h`, `physical_page_gate.h`, `physical_range_admission.h`:
  current single-page registration boundary and backing-domain request ownership. A complete
  coarse-range/all-page registration bundle is still required.
- `src/video_core/buffer_cache/buffer_cache.h`: CreateBuffer aligns to CACHING_PAGESIZE and
  can expand through ResolveOverlaps. Register/ChangeRegister installs cache slots; it does
  not alone prove upload completion. SynchronizeBuffer calls tracker ForEachUploadRange then
  UploadMemory. Existing upload paths reread device mappings and cannot execute an immutable
  accepted plan unchanged.
- `memory_tracker_base.h` / `word_manager.h`: ForEachUploadRange can clear CPU-modified state
  and update tracked pages. WordManager's NotifyRasterizer path calls UpdatePagesCachedCount.
  Guard its full rounded coverage before its first marking, not after RasterizerMarkRegionCached.
- `src/core/device_memory_manager.inc`: UpdatePagesCachedCount fans out CPU marking through
  registered process mappings. These aliases and coarse coverage must join the same handshake.
- `vk_buffer_cache.*`, `vk_scheduler.*`, `vk_master_semaphore.*`: real upload/staging,
  submit tick, completion/error and visibility evidence. Refresh/GetCounter errors and submit
  failure must not become success. The existing renderer shutdown seal does not prove final-pin
  drainage before Device/VMA destruction or trusted Unknown recovery.

## Required positive and negative gates

Use the real prepared Memory Write and actual BufferCache registration/upload bodies. Keep
fixture scope visible; fixture GPU bytes are not driver/device execution evidence.

- Protected original race: backing starts 10; writer independently stores 77 while registration
  is attempted; cache/GPU observation must be 77. Old-code/order-bypass control must still show
  backing77/cache10, not merely a missing callback or counter mismatch.
- Coarse multi-page registration: pause a writer on the SECOND/LAST covered page, plus a
  physical alias. Start-page-only gating must fail explicitly.
- Pre-mark/pre-upload ordering: spies reject any initial CPU cached marking/upload before the
  complete gate bundle is Granted and all entered writers have published.
- Queued stale VA/context and device remap: refuse before effects, retain old pinned storage,
  and never redirect an accepted transfer to a new physical target.
- Callback return before delayed transfer completion: ticket remains held, dependent writes
  refuse, and uninitialized content remains inaccessible. Early-Complete control must fail.
- Partial/upload/submit/completion failure, Unknown, shutdown and slot replacement while
  pending/submitted: no success publication, no owner release before trusted retirement.

Do not enable DMA admission, NCE F1, direct JIT/raw pointers, F3, images, or whole-game routing.
Do not use a second GPU dispatcher, recursive pump, cache-local blocking lock, whole-owner
lease, or effected-command replay to make the controlled scenario pass.

## Reproduction and remote validation

Windows pin-related scripts use existing Boost headers:

```powershell
python tools/physical_coherency_tests/run_gpu_plan_tests.py --boost-include .diagnostics/lazy-backing-tests/deps/usr/include
python tools/physical_coherency_tests/run_representation_pin_tests.py
python tools/physical_coherency_tests/run_cache_representation_tests.py --boost-include .diagnostics/lazy-backing-tests/deps/usr/include
python tools/physical_coherency_tests/run_physical_admission_tests.py --boost-include .diagnostics/lazy-backing-tests/deps/usr/include
python tools/physical_coherency_tests/run_page_writer_tests.py --boost-include .diagnostics/lazy-backing-tests/deps/usr/include
python tools/physical_coherency_tests/run_cpu_mapping_tests.py --boost-include .diagnostics/lazy-backing-tests/deps/usr/include
python tools/physical_coherency_tests/run_write_coherency_witnesses.py --cxx g++ --case f2 --repeat 1 --require-fixed
```

The last command MUST still fail until the real production witness is repaired. Home-machine
toolchain/dependencies may need setup; generated .diagnostics files are not transferred by Git.
Run generators in the order above; downstream runners reject stale source hashes. Linux-only
lazy backing/FD tests run in the remote workflow, not Windows. After meaningful changes, update
M3B_PROGRESS, commit English on PR375, fast-forward main, push both atomically, then dispatch:

```powershell
gh workflow run pr375-pr380-integration.yml --repo Splaser/emulator --ref main
```

This handoff intentionally separates verified groundwork from the unimplemented controlled
first-registration positive gate. Do not mark the stage or F2 complete based on green CI alone.
