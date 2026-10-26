# Framebuffer presentation refresh regression

This standalone native fixture extracts the actual `TryFindFramebufferImageView`,
`PrepareImage` and `SynchronizeAliases` bodies from the production texture cache. It uses
controlled image storage, CPU refresh, copy and rescale adapters; it neither executes Vulkan
nor establishes that the FFR save-menu flicker is fixed on the target device.

    cmake -S tools/framebuffer_present_tests -B build-present-tests
    cmake --build build-present-tests --config Release
    ctest --test-dir build-present-tests -C Release --output-on-failure

Use a separate directory with `-DPRESENT_SOURCE_REVISION=407834bf57` for the historical
negative control. The real old selection path returns stale background contents while a
newer partial alias contains the UI. It must fail the first pixel-content assertion.
The patched path must copy the partial alias before returning a view, propagate its tick,
refresh a CPU-dirty image, preserve newest-write ordering, react to later writes and take
the view/scaled flag after preparation. Clean images must not upload/copy or become new
GPU writes; exact-address selection, opaque alpha and missing-image fallback are controls.

The production fix reuses existing cache preparation before presentation. A positive native
result only validates this missing preparation path under controlled dependencies. Device
acceptance still requires a stable save UI on both alternating buffers, plus regression
checks for normal rendering and resolution scaling. It does not explain or fix the earlier
invalid compute address / bad_alloc sequence, and does not change ATOM_cas.
