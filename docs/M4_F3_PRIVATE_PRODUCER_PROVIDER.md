# M4-F3 private allocation exclusion provider

## Exact positive domain

The first real provider owns **fresh private Linux allocations**, not existing
guest backing. Rasterizer's GPU-owner/shutdown-checked factory alone can issue a
PrivateProducerDomain. The underlying Runtime factory and guard constructors are
private. No caller supplies an exclusion boolean, backing epoch, resource list,
raw address, external VkBuffer or completion certificate.

Each domain owns one anonymous, non-exported 4096-byte CPU mapping, a fresh
GuestBackingEpoch/MappingEpoch and 2-3 fresh unregistered staged allocations, with
an aligned logical extent up to 4096 bytes. It publishes neither host pointers nor
guest/NCE mappings nor native buffer handles. The snapshots use private replica
coordinates, not addresses resolvable through ordinary DeviceMemory. Native
resource identity is captured internally and bound to the guard. Debug-tool
attachment, unsupported OS/page size and ordinary guest/native resource adoption
do not acquire this permission. There is no adoption API.

This is deliberately **not** a positive certificate for existing game memory.
Ordinary CPU, NCE/fastmem, mapped raw pointers, Draw/Dispatch, external queue
bindings and alias-process mappings remain outside supported production admission
and Unknown. No ARM NCE execution or Android acceptance is claimed. Linux native
store protection is tested; it must not be relabelled an NCE runtime hook.

## Real enforcement and lifetime

Before admission, the factory finishes private native allocation/binding. Guard
acquisition serializes through private state and actually calls `mprotect` to make
the entire CPU mapping read-only **before publishing the active capability**.
Admission then performs existing physical alias fan-out before command recording.
Only exact Fill and synchronous, owner-thread private CPU stores are offered; no
Copy/Planner expression, ordinary cache selection or shader endpoint is expanded.

The private native handles cannot enter ordinary producer bindings through this
API. Competing managed entry is refused while the capability is active. A real
post-admission CPU native store to the protected mapping faults, and a same-process
competing-thread `process_vm_writev` fails. Those tests bypass notification logic;
they do not merely check a “busy” flag. The protected mapping has no exported fd
or secondary writable guest alias. Initial construction and private CPU stores
are serialized; there is no previously published raw access to drain.

Each GPU operation uses the existing RecordTransferBatch and owns the guard in
CheckedTransfer **before enqueue**. The worker rechecks the live guard/epoch. It
retains all private replica pins through worker execution, actual queue attempt,
checked completion and existing trusted-idle retirement. Merely leaving a function
or dropping the public domain does not unlock. Only Scheduler's successful actual
PollCheckedTransfer completion can restore writable CPU protection. No tick,
revision, caller boolean, historical ancestry or callback return substitutes for it.
Polling a completed old receipt cannot release a newer guard: capability identity
and completed state are independently checked.

Private CPU stores run on the same validated owner, obtain exclusive capability,
apply physical fan-out, and perform the bounded synchronous copy before releasing.
They publish no root or authority. CPU backing and staged replicas are not
automatically reconciled. There is no public read interface claiming latest bytes.
The private CPU store's short writable interval is inaccessible through any normal
guest/raw-pointer API; GPU admission cannot overlap it. This is not a general
hostile-process/debugger memory sandbox.

Domains keep only weak operation/owner references after initialization. Native
storage remains owned by the existing checked pool, not an external domain object
that could prolong VMA pins past renderer lifetime. Wrong-thread calls, expired
owner, retired/expired operation, invalid mapping and resource lifetime fail closed.
The real factory rejects wrong GPU-owner entry; tests also cover owner shutdown.

## Failure and safe quarantine

Unknown emission/submission, forced early guard drop, remap/epoch loss, retirement
and owner loss seal the domain. Sealing keeps actual CPU page protection, kills
its mapping/backing qualification and rejects all new operations. Native handles
remain unpublished and all possibly affected allocations remain pinned in the
checked transfer until the existing trusted GPU-idle retirement permits release.
No successful timeline, rollback, new root, current qualification or new admission
is manufactured from failure. Uncertain GPU effects may still change their old
private staged allocation, which remains inaccessible through the sealed domain.

This quarantine is enforced private ownership + page protection + retained native
storage, not only an Unknown status. It cannot be applied to an existing guest
arena with escaped pointers or other mappings. There is no reopen/recovery API.
Private CPU storage is reclaimed only when its domain/guard owners are gone;
native storage follows the existing checked pool and device lifetime. Historical
immutable content metadata is not modified.

The pure ProducerCoverageContract verifier is **not** wired into Scheduler as an
authority issuer. Physical latest-writer authority, cross queue, ordinary F3
selection and F2/F3 repair remain unimplemented. Guest production closure Unknown.

## Verification boundaries

Kernel-only units exercise real mmap/mprotect, an actual native store in a child
process (SIGSEGV), and live competing-thread kernel writes to the protected page.
They have six assertion mutants and three repeats. Completion transitions in
these **kernel units** use a privileged test peer and are explicitly injected;
they are not GPU completion evidence. The initial unprotected red is a deliberately
weakened implementation, not a newly reproduced game defect.

The extracted-production-body fixture uses the real builtin allocation factory,
guard, physical fan-out, checked submission and lifecycle bodies. Twelve modes
cover post-check CPU entry, direct native access, pending/submitted effects, early
guard drop, owner drop, submission failure/uncertain effects, epoch loss, domain
retirement, pending-worker retirement, renderer ownership loss and pin-domain seal.
Four additional assertion mutants remove guard retention, release while Pending,
remove worker revalidation or remove fan-out. Its Linux page protections are real;
Vulkan dispatch, submission failure and completion are simulated.

The native Vulkan case creates the domain through the real GPU-owner facade,
checks wrong-owner refusal, actual post-admission CPU denial, old-receipt polling,
CPU-before-GPU fan-out and 192 byte eligibility checks. Checked completion enables
the next private CPU store. Privileged test-only pin inspection after completion
uses actual Vulkan readback to verify written bytes and unchanged peers, then
tests permanent retirement and release of native ownership. These privileged
inspection helpers are not production capability exports.

All previous Copy/Planner/coverage mutants and original F2/F3 negative witnesses
remain in Linux CI. The real Rasterizer translation unit is now included in the
early compile step. Android is not requested. Exact acceptance is recorded after
the Linux run completes.
