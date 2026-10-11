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

These checks do not exercise Vulkan drivers, command scheduling, Android builds
or game rendering. Device testing is still needed for correctness and performance.
