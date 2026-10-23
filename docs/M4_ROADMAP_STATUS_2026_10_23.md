# PR375 roadmap status — 2026-10-23

This snapshot compares the current branch (baseline `aa58136d59` plus the fence
retirement repair committed here) against the original
[M0–M7 roadmap](../tools/physical_coherency_tests/DESIGN.md#13-independently-testable-roadmap)
and the [three remaining M4 phases](M4_F3_PROCESS_GUEST_EXCLUSION.md#remaining-roadmap-three-phases).
It does not replace their advancement gates. Historical results below are taken
from repository records; this round only reruns the focused fence suite and two
Windows production units. No fresh whole-project/device acceptance is implied.

## Overall position

| Roadmap item | Current position | Still required |
| --- | --- | --- |
| M0 independent DMA snapshot | Existing source-snapshot implementation and recorded regression evidence | Android DMA-heavy runtime/default-rollout acceptance remains separate |
| M1 coverage audit/shadow | Resolver/shadow registration infrastructure exists | Complete producer/binding/alias coverage and device overhead validation; observation is not ownership |
| M2 pure coherency model | Standalone reference model and recorded tests exist | Its controlled-domain proofs do not authorize production Guest access |
| M3 controlled leases and mapping/completion contracts | Prototype plus production integration slices exist | Complete ordinary producer, escaped-pointer and lifetime coverage; F2 remains open |
| M4 scoped staged-buffer coherency | Active work; controlled arenas/adapters and many ownership prerequisites exist | All three ordinary Guest admission phases below remain incomplete; F3 open |
| M5 image/other binding interop | No completed acceptance established by this work | Image layout/footprints, other binding readers/writers, explicit whole-dispatch rejection and device tests |
| M6 complete CPU/NCE gate feasibility | Some whole-guest stop/exclusion prerequisites overlap current M4 work | Full CPU/NCE/raw-alias coverage and Android/Linux validation; no fine-grained fault gate is claimed |
| M7 selective DirectGuestView | Blocked by prerequisite gates | M5/M6, real driver synchronization/visibility and shared-byte ownership; main waits for this final version |

M4 cannot be promoted from controlled access to ordinary Guest backing merely
because a fixture or controlled Vulkan arena succeeds. M5/M6 work may overlap
dependency audits, but M7 is not unlocked. No percentage is assigned: remaining
producer and native ownership coverage dominates the correctness risk.

## M4: the three actual acceptance phases

The subsequent [P2 producer-closure update](M4_P2_PRODUCER_CLOSURE.md) adds the
shared non-NCE Memory facade write domain and atomic cohort cancellation. It
narrows the managed-write gap but does not close NCE/service/raw/native-owner
coverage or complete P2. HAS_NCE explicitly refuses this domain's closure.

| Phase | Implemented prerequisites / evidence | Missing acceptance facts |
| --- | --- | --- |
| 1. Retained Process roster plus real execution drainage | Roster ownership, sustained cold creation/init/publication gates, cohort cancellation and checked backend integration slices are recorded | Complete continuous boundary over every relevant publisher/view; real execution halt and lifecycle composition across all supported paths |
| 2. Close every independent producer | Terminal GPU/NV channel creation/init/bind and mapping routes, checked callback completion, retained unmap failure, native fence wait/reset/submit ownership fixes | All ordinary scalar/bulk/atomic writes, NCE stores, unchecked fastmem, Audio/VIC/services, raw aliases, shader/image writers and durable whole-owner Unknown resource retention |
| 3. First ordinary Guest-backed admission | Controlled arena/adapters and explicit checked submission mechanisms exist | Real KProcess + ordinary physical backing, all producer drains, alias/publication freeze, native completion plus visibility, backing/PageTable/GPU resources retained through success or Unknown; full remap/teardown/retirement coverage |

No phase is complete. Ordinary GuestBackingAdmission remains Unknown; the original
F2/F3 negative controls retain their meanings. Callback Completed only proves CPU
callback return, not native queue completion, readback visibility or permission
to release backing.

## Recent concrete progress

- A subsequent [checked-write retirement repair](M4_F3_CHECKED_WRITE_RETIREMENT.md)
  retains write and transfer owners when any checked write remains host-pending,
  even if device idle is asserted. This is another phase-two ownership guard,
  not completion of that phase.

- Channel creation, binding and GMMU mapping/initialization now retain terminal
  publication ownership across their actual NV acknowledgements.
- Checked unmap/callback handling distinguishes cancellation, failure and partial
  effects; malformed FreeSpace lookup no longer creates phantom owners.
- Native fence fallback now checks wait results, handles reset failure, reserves
  owning records before native submission, retains unsuccessful submissions and
  preserves new isolation against older completion/failure races.
- This round closes allocation failure while returning a completed fence to its
  reusable pool. It retains the handle, fails/wakes waiters and prevents a worker
  exception from stranding completion. See
  [retirement validation](M4_F3_FENCE_RETIREMENT_ALLOCATION.md).

These changes repair concrete failure paths within phase two. They are not four
new milestones or proof that normal Guest backing can be admitted.

## Next development priorities

1. Connect native submission identity to retained backing/alias/native resource
   owners under a durable Unknown protocol. Fence retention alone is insufficient.
2. Complete and compose ordinary CPU/NCE/service/raw-alias close-and-join facts
   with sustained Process/PageTable/publication exclusion. Do not substitute
   terminal shutdown for a proven reversible whole-guest pause.
3. Only then attempt the restricted real Guest-backed Vulkan Copy with exact
   completion/visibility and success/refusal/partial/remap/teardown/retirement
   coverage, preserving F2/F3 negative controls.

Terminal quarantine remains conservative. Android runtime incidence and any
recovery policy require later device evidence. Local object compilation and
actual-body simulations are useful regression evidence, not device acceptance.
Main remains unchanged and no local Android build is requested.
