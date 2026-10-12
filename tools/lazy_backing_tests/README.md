# Lazy physical backing and CPU range coverage

This first stage adds a Linux CPU-only backing experiment. It does not export or
import Vulkan memory, enable a renderer fast path, change ownership synchronization,
or modify the 8-frame retirement mechanism.

The default remains off. For remote Android device validation, close the app,
set these values under `[Renderer]` in `config.ini`, and restart the app:

```ini
use_lazy_guest_backing\default=false
use_lazy_guest_backing=true
```

Backing is reserved at a stable address, with 32 MiB logical slots. A slot gets a
memfd and physical CPU mapping when a typed physical pointer, explicit bulk CPU
range, clear operation or guest virtual mapping first needs it. CPU aliases are
installed only after the complete physical range is materialized. Slots remain
stable and reusable until the arena is destroyed; freeing a guest allocation
does not close or reassign its chunk fd.

The kernel can map a large heap before touching all its pages. Such a mapping
necessarily materializes all intersecting chunks in this stage; this is lazy by
range access/mapping, not a page-fault allocator. No Vulkan calls occur in a CPU
signal handler, and no live memfd payload is migrated to a dma-buf.

`DriverBackingRange` deliberately rejects these CPU-only chunks, so the renderer
continues to use existing gather/scatter/readback. The existing 1 GiB exported
backing and large-backing safety limit remain available when this experiment is
off. A later stage must provide whole-chunk CPU alias/ownership coverage before
making chunk backing directly accessible to Vulkan.

CPU range coverage includes slab initialization, optimization bitmaps, page
clearing, shared/code memory initialization, secure resources, IPC buffers, VI
buffer loops and page-table copy/cache-maintenance helpers. CPU page-table
publication also materializes the entire range before installing pointers. Full lengths are
passed before bulk pointers escape; iterator end pointers are derived from the
already materialized start instead of materializing an extra chunk.

The arena exposes `BackingStats` and logs a shutdown summary at `HW.Memory:Info`:
`chunks_created`, `chunk_cache_hits`, `active_chunks`, `peak_backing_fd_count`, and
`peak_vma_count`. The fd peak counts arena-owned fds, not every process fd. Active
chunks are retained until arena destruction. Import, ownership and sync telemetry
is deferred with the renderer stage rather than reporting fictional counters.

Run focused tests on Linux with Python 3, a C++23 compiler and Boost headers:

```sh
python3 tools/lazy_backing_tests/run_tests.py --boost-include /path/to/boost/include
```

The tests compile production `host_memory.cpp`; only logging/assert formatting
is stubbed. They execute actual memfd, mmap, RX mapping, fd limits and process
cleanup. Production physical-pointer helpers are extracted for the CPU range
tests. Coverage includes initially cold reservations, ranges crossing chunks,
zero-length and overflow handling, aliases/remapping, concurrent creation,
failure/retry, move and fd cleanup, a 4 GiB arena with only its last 32 MiB slot created,
ordinary memory and the legacy external-fd path. These tests do not validate
Android NCE fault handling or game compatibility; remote APK testing is required.
