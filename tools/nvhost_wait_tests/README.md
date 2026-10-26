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

The cancellation follow-up models a callback paused inside Signal after its state
became Signalling. A controlled deregistration hook finishes that callback tail;
Clear must then leave the event Cancelled, unsignalled and without its old handle.
Reusing the slot must ignore the cancelled threshold and signal only at the new
threshold. Duplicate Clear is also exercised. This hook is a simulation of the
join contract, not a native KEvent/Host1x concurrency or game test.

With `-DNVHOST_SOURCE_REVISION=9bc0f3adc3`, the new control must compile and fail
with `cancel skipped active callback join`. The production change is the cancel
portion of PR375 commit `dc91b71321`, retaining the FFR asynchronous wait fix.
It does not port the WIP destructor/terminal ownership infrastructure or establish
that this race is the source of FFR's NVN FAILED result.
