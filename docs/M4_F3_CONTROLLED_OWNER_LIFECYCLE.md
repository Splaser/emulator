# M4-F3 controlled owner lifecycle substage

## Scope and enforcement

`Common::ControlledGuestArena` constructs fresh, private HostMemory with two fixed
4096-byte virtual aliases of one physical page. It accepts no existing backing,
caller owner census, callbacks, raw view, fd, physical pin, renderer or PageTable.
Only its private factory creates move-only owner handles. A fixed eight-slot
registry records enrollment; slots are never reused. Losing any owner seals the
entire cohort, including an idle cohort. Registry size is not a drainage proof.

Every public byte Store/Load obtains an actual ProducerDrain entry before pointer
resolution and retains it through the access and release of the byte data lock.
Admission is the owned atomic gate, not the ordinary mutex. Closing the gate also
closes registration. A pre-resolved operation keeps the gate occupied and retains
the State/HostMemory allocation independently of owner/arena/close handles.
Only an acquire observation of the owned gate's zero in-flight entries after
closure yields DrainedSubset. This means this closed CPU-only cohort only.

The byte mutex protects C++ accesses from races; it is try-only. Closure/Poll hold
no registry, byte, PTE, cache, renderer or GPU completion lock. Failed acquisition
after entry, abandoned access, registration contention/overflow, invalid range,
owner loss and retirement seal the cohort. Exceptions after admission seal before
propagating. Exhausted polling budget becomes sticky Unknown, even when the
writer later exits. A preexisting operation may finish after retirement/timeout;
its backing stays alive and the cohort cannot reopen. No forced interruption or
rollback is claimed. Failed or abandoned closure never silently resumes.

After real drainage, Close can hold the **same HostMappingDomain** owned by its
private HostMemory. Actual Map/Unmap/Protect ingress then refuses mutation before
effects. There is no second mapping authority. Cancellation is explicit and
requires a fully drained, non-Unknown CPU-only closure. This type has no API that
can submit asynchronous GPU effects; it must not be extended with an export or
device operation without replacing its cancellation/lifetime protocol.

## Explicit stop before outer CPU PTE freeze

This is a usable controlled backing owner substage, **not a guest lease**. No
KProcess/PageTable consumes this arena. It cannot enroll existing guest owners.
The following remain Unknown and block outer CPU PTE integration:

- Guest CPU/NCE and Dynarmic execution do not use these owner handles. Existing
  core entry gates alone do not prove backend exit or full all-process joins.
- Existing raw pointers, audio/VIC/I/O/kernel/host services and physical/native
  exports have no exhaustive owner lifecycle closure.
- Core::Memory publishes MapPages before the HostMemory mapping operation;
  refusal of an inner Map cannot roll back that earlier PTE side effect.
- PageTable public entries, fastmem pointers and independent permission updates
  have no enforced, lifetime-bound owner admission at every publication point.
- GPU/device mappings, imported resources and queued asynchronous effects have
  no cohort admission, completion join or retained guest-wide Unknown isolation.

Accordingly this change does not touch ordinary Core::Memory, PageTable, NCE fault
paths or BufferCache admission. GuestBackingAdmission always returns Unknown.
No CPU PTE freeze token, fabricated certificate or guest resume API is provided.
Planner, Copy forms/provenance, physical fan-out/private provider and physical
latest-writer authority stay at their previously accepted boundaries. Original
F2/F3 negative witnesses must continue to reproduce.

## Controls and acceptance

`run_controlled_guest_arena_tests.py` compiles actual Linux HostMemory/syscalls;
only logging/assert infrastructure is stubbed. It first requires assertion kills
for eleven source mutants, then three positive repeats. Compiler failures,
timeouts or unrelated crashes do not count as mutation kills. Inputs are hashed
in its artifact manifest. The privileged test peer pauses the exact private
Operation used by public Store after real pointer resolution; production users
receive neither this operation nor a raw pointer.

Controls cover a raw writer resolved before old mapping closure (still writes),
new owner/store/read refusal, in-flight drainage, frozen writable alias creation,
remap/unmap/unprotect, explicit cancellation, early owner release, retirement,
abandoned operation/exception/closure, timeout, fixed-capacity overflow, invalid
access and backing retention after early handle destruction. A separate native
Vulkan control executes checked fill/completion/readback on unrelated ordinary
backing while a controlled owner holds its resolved pointer and byte mutex;
the GPU callback must refuse arena access before trying that mutex. This proves
that dependency's progress, **not GPU ownership of the arena**.

New Linux acceptance is pending. Do not reuse prior HostMemory or private-provider
CI as acceptance for this owner substage. Android builds are excluded this round.

The first Linux-only attempt [39211644236](https://github.com/Splaser/emulator/actions/runs/39211644236)
at `603a606f56f3ebf7a79a813796e815c41497881c` stopped in mutation validation:
ten owner mutants failed assertions, but `closure-drop-reopens` survived. The
in-flight drop case alone was insufficient: its later entry decrement masked the
reopening. A separate idle-closure drop control now directly checks Store,
registration and re-close refusal. This failed attempt supplies no new owner or
native acceptance. The production implementation is unchanged by this test fix.
