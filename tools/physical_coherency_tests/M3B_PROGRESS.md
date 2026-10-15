# M3B production integration progress

## Resumed baseline: 2026-10-15

The user authorized merging the validated #380 integration into personal main and the #375
branch, and continuing yesterday's M3B work there. Both remote branches were fast-forwarded to
`105779d2c4`. The author of #380 supplied its Android device evidence; the user declined an
additional local device run. That decision does not provide device evidence for new M3B changes.

The prior F2/M3B branch at `80c4f4d7f7` was merged as `3e5b3228c3`. Its CPU CopyBlock snapshot,
host callback acknowledgement and candidate/negative-control tests remain intact. The sole
test conflict retained the #380 logging stub and acknowledgement include. Windows tests passed:
CopyBlock, preservation acknowledgement (three repetitions), 24 candidate cases (three repetitions)
and unmap alias preservation. None is a passing production F2 fixed-code witness.

## First production boundary: DMA method continuation

`DmaPusher::SetMethodAdmission` supplies a nonblocking GPU-thread preflight before scalar, inline
or non-incrementing batch effects, including `ConsumeSink`. False copies the unexecuted words
and parks the channel without consuming the rejected method. Its decoder state and original
command position survive retry. A callback is installed before the first submission and cannot
be replaced under queued or executing work. No real admission adapter is installed yet.

Existing `Control::Scheduler::RetrySuspended` retries the saved method on its original GPU
thread. The existing ThreadManager suspended-channel polling keeps servicing queue callbacks
and other channels. An unready admission does not wait under the channel scheduler guard.
This is a decoder boundary, not permission to replay an effectful draw or an entire command list.

`run_dma_admission_tests.py` compiles the actual DMA class/header/implementation and actual
channel scheduler, with fixture engines, guest command reads, Puller dependencies and Core/GPU
shells. Windows positive cases cover prefix retirement, blocked same-channel tail, independent
channel progress, increasing/non-increasing/increase-once/inline commands, immutable callback
installation and semaphore continuation compatibility. A control bypassing admission must fail
because the blocked method executes. The extracted-source manifest records the real inputs.
No actual driver, real physical admission, transfer visibility or production mapping pin is tested.

## Next prepared boundary: pinned physical backing views

`HostMemory::PinPhysicalRange` materializes a complete bounded physical extent and returns a
`PinnedPhysicalMemory` retaining the actual shared Impl and backing epoch. The immutable extent
uses `backing_base`, never a remappable virtual alias. A retired epoch rejects new obligations
elsewhere, while already accepted views keep storage allocated; `OwnerAlive` and storage lifetime
are deliberately distinct. Moves/replacement of the HostMemory object must be excluded during
resolution by its owner; this API does not make concurrent destruction of a borrowed object safe.
Invalid/empty/overflowing extents return no view, and materialization failure precedes exposure.

Windows GCC standalone execution of the actual HostMemory implementation passes alias remap,
cross-page extent, moved owner/view, epoch retirement, backing replacement and final release
checks using real OS mappings. Only logging/assert formatting and unused dynamic-library filename
formatting are stubbed. The same runner additionally checks real lazy cross-chunk creation and
FD cleanup on Linux; those new checks have not run yet. No production consumer, CPU lookup epoch,
device/GPU representation pin or physical admission is connected by this change.

The prepared `PhysicalAccessPlan::Build` composes existing resolver snapshots with these real
pins. It validates exact ordered coverage, holes, extent bounds and backing identity before
materialization, then rechecks the snapshot under GPU-then-device mapping locks. Pin acquisition
runs outside those locks. If a mapping generation changed, the plan is rejected; an accepted
plan retains its original physical targets rather than re-resolving after a remap. Plans contain
no mapping-use lock. Resource owners retire after temporary validation locks, including rejection.
Windows tests use fixture mapping stamps with real allocations and exercise stale/retired stamps,
backing mismatch, invalid coverage/hole/overflow and retained split views. This does not yet join
the production GPU resolver, engine footprint adapter or CPU first-registration handshake.

The post-pin validation checkpoint also permits a controlled mapping change after pin acquisition.
Its Windows test rejects that stale plan. A negative control validates only before acquiring pins
and must fail by accepting the remap race. Linux additionally rejects a malformed suffix before
materializing any cold chunk; the Linux checks are pending the next remote run.

Run `38672294519` on `41c6ce4ac3` finished with the complete Linux production/regression job
successful, including actual DMA/scheduler positive/negative controls and 24 candidate cases
(three repetitions). Android's complete compile error list contained one strict Clang lambda
capture shadow in the rejoined acknowledgement helper. Renamed its capture without changing
ownership/cancellation semantics; this fix accompanies the new storage/plan slice.

## Remaining production adapters and acceptance gates

1. Build immutable access/transfer plans with real allocation/representation pins, stable physical
   footprints and read/write views. Resolution may not hold a mapping-use lease across a parked
   channel. Revalidation cannot silently redirect an already accepted old plan to a new mapping.
2. Derive supported engine footprints without effectful decode. Pending `method_sink` register
   writes must be projected by pure resolution or otherwise bounded safely; running ConsumeSink
   to discover the footprint would precede this boundary and invalidate its pre-effect contract.
   Unsupported macro/NI batches, image layouts and unbounded footprints remain ineligible.
3. Join initially uncached controlled CPU stores and first cache registration with the same
   linearizable epoch handshake. Acquire a stable view before a store and publish exact successful
   extents afterwards; failed CAS publishes nothing. CopyBlock stays outside the transaction.
4. Install range admission outside cache/PTE locks, compose old-plan preservation and mapping
   mutation in a consistent owner order, and reject conflicting inline reentry without self-wait.
5. Connect real transfer visibility, checked completion/failure acknowledgement, resource retention
   for Partial/Unknown and cancellation/sealing before manager/renderer destruction. Callback
   completion alone is not Vulkan completion; suspended external dependencies cannot retain
   broad data admission that blocks their required CPU producer.
6. Run protected-path F2 tests with independent CPU-store release and GPU-attempt rendezvous,
   retaining stale-byte assertions and old-code controls. Existing five F1/F2 witnesses still
   characterize the unprotected production path. Candidate passes are not fixed-code passes.

F1 native/NCE access, direct JIT fastmem, raw/kernel pointers, F3 and image/buffer authority are
still outside this controlled-path work. Do not activate a cache-local blocking mutex to bypass
the queue-cycle counterexamples in `M3B_F2_IMPLEMENTATION_REPORT.md`.
