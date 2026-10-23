# M4 P2: remaining actual producer and ownership boundaries

Source audit: 2026-10-23 (Asia/Singapore), following the NVDRV dispatch update.
This is an acceptance inventory, not a certificate that all writers are known.

| Actual route | Current fact | Required next capability |
| --- | --- | --- |
| NVDRV Module Open/Ioctl1/2/3/Close/QueryEvent | Shared sustained synchronous dispatch closure, with outer-before-inner cohort ordering | Real runtime and complete caller/owner lifetime; native work remains separate |
| NVDRV::Initialize -> Container::OpenSession | Ordinary Initialize now shares dispatch admission through local success reply; exceptions seal without fabricated Success | Direct Container use and full Process/session/backing lifetime still require continuous ownership; the raw accessor is not a capability |
| NVDRV::~NVDRV -> Container::CloseSession | Shutdown path mutates session refs/activity outside Module dispatch | Explicit teardown entry coordinated with closures; destructor cannot simply Busy/skip owner release |
| SurfaceFlinger::CreateBufferQueue -> BufferQueueProducer -> android::GraphicBuffer | Escaped GetContainer/NvMap reference; GraphicBuffer constructor DuplicateHandle + PinHandle | Retained container/module/backing owner and publication transaction spanning actual buffer lifetime transitions |
| android::GraphicBuffer destructor | Direct UnpinHandle + FreeHandle, including final owner/eviction effects | Close-and-join actual retirement producer, or defer with a durable owner bundle; never silently skip a destructor on closure |
| Direct Module GetDevice, Host1x::PushEntries, GPU::PushCommandBuffer and CDmaPusher::ProcessEntries | Public borrowed/direct routes are not automatically covered by Module dispatch | Inventory actual callers and require lifetime-bearing access/admission instead of an escaped raw/shared facade |
| Memory::GetPointer/GetPointerSilent/GetSpan and direct prepared/HostMemory access | Managed facade store counting does not revoke previously escaped borrows | Census plus borrow retirement/revocation or a proven whole-guest stop spanning every user |
| Native NCE and unchecked fastmem | HAS_NCE managed-write closure explicitly unsupported; no native/store signal parking proof | Actual backend halt/ack, retained running owners and validated absence of outstanding stores; do not add blocking signal-handler bookkeeping |
| Audio renderer and AudioManager | The two actual counted worker subsets exist; direct service/lifecycle operations remain separate | Prove all session/publication/retirement dependencies, plus native sink/backend access, before claiming complete Audio exclusion |
| GPUThread, scheduler continuations, recorded/native transfer and shader/image work | Terminal ingress and checked completion/failure retention slices exist | A sustained reversible GPU closure that accounts for suspended channels, deferred callbacks, native completion and visibility |
| Unknown backing/PageTable/alias/native owners | Local checked holders/fence and mapping-failure owners are retained in several paths | Durable whole-owner bundle, including allocator/device, backing, aliases and Process/PageTable, through completion or explicit terminal retirement |

Concrete source pointers:

- `src/core/hle/service/nvdrv/nvdrv_interface.cpp`: Initialize and ~NVDRV.
- `src/core/hle/service/nvdrv/core/container.cpp`: OpenSession and CloseSession.
- `src/core/hle/service/nvnflinger/surface_flinger.cpp`: CreateBufferQueue.
- `src/core/hle/service/nvnflinger/buffer_queue_producer.cpp`: creation of GraphicBuffer.
- `src/core/hle/service/nvnflinger/ui/graphic_buffer.cpp`: constructor and destructor directly mutate nvmap.
- `src/core/memory.h`, `src/core/managed_guest_writes.h`: escaped views and unsupported HAS_NCE gate.
- `src/video_core/gpu_thread.cpp`, `src/video_core/renderer_vulkan/vk_scheduler.cpp`: queued/continuation/native ownership.

## Audio/Opus classification found during this audit

Do not equate every Opus worker buffer with ordinary guest physical backing.
OpusDecoder::Initialize allocates shared_buffer with make_unique; decode input
and DSP output spans refer to that private allocation. The ordinary hardware
Opus service receives OutBuffer through CMIF scratch storage, and CMIF later
copies it via HLERequestContext WriteBufferB/C. Relevant sources are
`src/audio_core/opus/decoder.cpp`,
`src/core/hle/service/audio/hardware_opus_decoder.cpp` and
`src/core/hle/service/cmif_serialization.h` (OutBuffer argument preparation and
WriteOutArgument).

This narrows the observed path; it does NOT close the Opus/service lifecycle
domain. Public decoder spans, raw DSP protocol pointers, teardown dependencies,
incorrect acknowledgements and the later HLE copy still need their own proof.
No native worker stop or absence of all other aliases follows from private
scratch allocation. Similarly, renderer workbuffer is currently a private
allocation, while CircularBuffer/Aux commands make actual managed guest stores.

## Completion gate

P2 cannot be completed by adding counters to the remaining destructors. A
closed destructor must either run under a legal owned teardown protocol or
transfer every still-needed owner to durable deferred retirement. Counting
ordinary ioctl return cannot supply native GPU visibility, and one-time owner
snapshots cannot replace continuous publication closure.

Keep GuestBackingAdmission Unknown until all producer families have sustained
close-and-drain evidence and the necessary Unknown owner bundle is held. The
subsequent actual guest-backed Vulkan test is still a separate M4 phase; a
controlled arena or passing focused Windows compilation cannot replace it.
