# nvhost wait regression

This isolated native fixture extracts the actual InternalEvent/parameter declarations and
IocCtrlEventWait / IocCtrlClearEventWait bodies. Kernel events, syncpoint storage and the system
are controlled doubles; it does not emulate a device or prove game progress.

    cmake -S tools/nvhost_wait_tests -B build-nvhost-wait
    cmake --build build-nvhost-wait --config Release
    ctest --test-dir build-nvhost-wait -C Release --output-on-failure

Configure a separate directory with `-DNVHOST_SOURCE_REVISION=b99e02ea1c` for the historical
negative control: it must fail with `global stall reached` on the fourth wait. The fixture
throws at the old stall boundary rather than hanging its test runner. The patched version
must survive six cancellations, preserve zero-timeout pending behavior, and signal only after
the genuine tenth increment. It also checks allocation, active event reuse and invalid slots.
