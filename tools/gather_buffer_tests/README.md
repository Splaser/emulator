# Split-buffer regression checks

Run with Python 3 and a GCC-compatible C++23 compiler:

```sh
python tools/gather_buffer_tests/run_tests.py --cxx g++
```

The runner extracts current buffer-cache helpers and the Vulkan flush-area merge
from production source, then compiles them against fake GPU memory, buffers and
tracking. Generated files stay under `.diagnostics/gather-buffer-tests`; use
`--build-dir` to select another directory.

Checks cover split mappings, overlapping views, layout changes, CPU/GPU writes,
address-space cache isolation, scratch retirement, allocation/copy failures,
DMA fallback and reactive readback filtering. Four-byte fixture pages keep the
mapping cases small and deterministic.

`run_vulkan_import_tests.py` also checks that a small buffer over a 1 GiB dma-buf
falls back before importing, synchronizing or waiting. Whole-allocation CPU cache
maintenance is conservatively limited to 4 MiB; this is a cost limit, not a claim
that smaller allocations are coherent. All accepted dma-bufs still require their
CPU access protocol and GPU ordering. The current 1 GiB exported guest chunks
therefore retain gather/scatter until a bounded range or proven coherent alias
protocol is available. Repeated CPU writes in the same ownership interval must
not repeat GPU waits; GPU reuse must restore the wait requirement.

On 2026-10-12, an Odin3 running Turnip was sampled with `simpleperf` for five
seconds while Super Mario U stalled at startup. With zero-copy enabled, cache
invalidation and cleaning accounted for 47.10% and 46.17% of CPU cycles. Two
native backtraces placed the GPU thread in the dma-buf START/END ioctls. Disabling
only `use_uma_zero_copy` allowed the same game to start normally; the cache sweep
functions no longer appeared above the 3% report threshold. This validates the
cause and the existing fallback, not the patched APK or an FPS improvement.

These checks do not exercise Vulkan drivers, command scheduling, Android builds
or game rendering. Device testing is still needed for correctness and performance.
