# M4-F3 HostMemory alias ledger and mapping-entry freeze

This is the next bounded component after
[managed producer drainage](M4_F3_MANAGED_PRODUCER_DRAIN.md), implementing part of
the [guest exclusion plan](M4_F3_GUEST_EXCLUSION_FEASIBILITY_AUDIT.md). It is not a
guest-backed exclusion provider. No caller currently combines these two components
into GPU admission; guest backing remains Unknown and F2/F3 remain Open.

## Actual enrollment and ownership boundary

Each HostMemory owns one HostMappingDomain, created with the arena rather than
adopting a caller's alias list. Successful production Map, Unmap and Protect calls
maintain ordered physical-offset/virtual-offset/permission intervals, including
both complements of partial changes. Canonical backing is a separate whole-arena
alias in the snapshot; lazy reserved bytes are not a claim of materialized storage.
An interval snapshot contains no mutable address, borrowed fd or backing pin.

Raw canonical/virtual pointer access, physical pin creation, chunk-lease queries
and driver-fd publication record permanent escape-family history on this owner.
These bits are diagnostic ownership facts, not a count of live borrowers, an
exhaustive owner census, or proof that an owner joined a write-use protocol. In
particular, escaped writers are not enrolled or revoked, and pointer/fd/lease
queries can still occur during a mapping freeze. Escape history is queried live;
the frozen alias table must never certify ownership based on a past zero mask.
GuestBackingAdmission always refuses, even with no observed escape history.

The first snapshot is restricted to ordinary internally owned Linux backing and
4096-byte host pages. External fds, exporters/driver backing, direct-address mode
and unsupported platforms refuse. A fixed 64-interval capacity is a refusal
limit: overflow permanently invalidates the census rather than publishing a
truncated alias list. Ordinary operations can continue after census invalidation.
Even this complete HostMemory table does not enumerate CPU PTEs in other processes,
GMMU/DAddr aliases, external OS mappings, services, plugins or renderer imports.

## Real mapping closure

The cold mutation transaction spans each actual HostMemory syscall/publication:
Map, Unmap, Protect, ClearBackingRegion, EnsureBackingRange, PinPhysicalRange and
EnableDirectMappedAddress. Nested materialization uses Impl directly within that
same transaction. There is no recursive mapping lock and no lock is added to an
NCE signal handler. Protection failure propagates even in assertion-disabled builds
and leaves the census incomplete instead of publishing successful permissions.

Already-published ready chunks retain the existing lock-free materialization-query
path (and cache-hit telemetry); they cannot be replaced within a live arena.
EnsureBackingRange joins the mapping transaction only for cold publication, so an
ordinary ready-range pointer lookup does not acquire a new global mutex or copy a
shared owner on every access. A ready-range query can still succeed while frozen;
like raw pointer getters, that grants no owner/write exclusion.

TryFreezeMappingEntries uses a single try-lock and refuses an in-progress operation,
an incomplete census, another freeze or a retired owner. On success it closes new
mapping entry under the same mutex that covers the complete actual mutation and
captures the table. Subsequent managed mutations throw before any mapping or
backing effect. The freeze retains metadata only, not the OS arena or GPU resources.
It changes no page permissions itself and supplies no CPU write exclusion.

The freeze is move-only and used by one orchestration thread with stable HostMemory
lifecycle. Explicit CancelNoEffects releases a known CPU-only mapping closure.
An unfinished drop seals mutation entry; stale cancellation cannot release a newer
freeze. Destruction/move replacement invalidates old-owner queries. Object move
construction transfers the same domain. There is no submission attachment or
release-after-GPU API; this token must not be used for asynchronous effects.

Do not freeze an ordinary running guest's HostMemory: its higher-level CPU PTE
updates can occur before the HostMemory wrapper, and other mapping domains are
unclosed. A refused inner call cannot roll back those earlier publications.
The next integration must close those outer entry points before their first
effect, retain all relevant lifetimes and drain writers without holding PTE/cache
locks. This component is exercised through dedicated test arenas only.

## Verification and current evidence

Run the focused checks with:

```sh
python tools/physical_coherency_tests/run_host_mapping_freeze_tests.py
```

On non-Linux hosts, use `--unit-only --cxx clang++`. The actual-domain tests cover
an independent 8192-byte-observation oracle over 256 alternating Map/Unmap/Protect
prefixes, physical offsets and permission complements, active-publication refusal,
stale release, early drop, retirement, moves, incomplete publication and capacity.
Ten assertion mutants challenge those boundaries. These are primitive tests, not
native guest execution or OS mapping acceptance.

The Linux-only suite compiles production HostMemory with real memfd/mmap/mprotect
and threads. Only unused logging/assert formatting is stubbed. It checks canonical
backing plus two actual physical aliases, refuses seven managed entry families
before effects, verifies a refused unprotect leaves a real store fault in a child
process, then demonstrates that a retained writable alias can still store 99.
The latter is an ownership counterexample and must keep guest admission Unknown.
Remap/cancel/drop/retirement/direct-address/external-fd controls are included.
Seven further assertion mutants bypass the actual production wrapper guards.
Both positive executables repeat three times; compiler failures/timeouts/signals
without assertion diagnostics do not count as killed mutants.

Local macOS: three unit repeats and all ten primitive assertion mutants passed.
Production Linux syscalls, seven wrapper mutants and full regression acceptance
remain pending. The existing Linux workflow runs the new suite and archives its
logs/source hashes under `.diagnostics/m4-host-mapping-freeze/`. No Android
compilation or ARM/NCE execution is requested or claimed.

Current Linux-only run
[39187373524](https://github.com/Splaser/emulator/actions/runs/39187373524) targets
exact source `465f626f7b55372eade5896fc28276a8239d4c33`, comprising initial component
`56676e3bd9`, moved-from compatibility/early validation `05acd60221` and ready-query
hot-path preservation `465f626f7b`. This run is pending acceptance; Android is
skipped. Superseded runs `39187093671` and `39187016054` were cancelled and must
not supply acceptance for this source. Read the first actual failure/result and
verify the artifact hashes, three positive repeats, ten primitive/seven wrapper
assertion mutants and original F2/F3 controls before closing this gate.

## Remaining gates

1. Enroll lifetime-scoped owner/borrow use, or stop/join the complete audited owner
   set. Raw-pointer observation alone cannot account for outstanding uses.
2. Close CPU PTE, device/GPU mapping, permission restoration and import/export
   publication before their first effect, composing them with this HostMemory
   closure. No higher-level rollback is inferred from an inner refusal.
3. Join audio/VIC/I/O, all-process CPU execution and old GPU work; prove the
   lock/dependency graph and retain physical/native lifetimes.
4. Freeze every alias and preserve saved permission intersections through checked
   GPU completion and retained Unknown isolation. Neither this token nor the
   managed drain offers a guest-wide recovery/resume endpoint.

Planner/Copy, ordinary BufferCache routing and physical content authority remain
unchanged. No new automatic rendering path is enabled.
