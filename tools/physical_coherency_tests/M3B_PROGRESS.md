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
