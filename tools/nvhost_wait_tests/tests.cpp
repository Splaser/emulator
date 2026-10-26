// SPDX-License-Identifier: GPL-3.0-or-later
#include <array>
#include <atomic>
#include <functional>
#include <iostream>
#include <map>
#include <mutex>
#include <stdexcept>
#include "common/scope_exit.h"
#include "core/hle/service/nvdrv/nvdata.h"
using namespace Service::Nvidia;
#define LOG_DEBUG(...) ((void)0)
#define LOG_WARNING(...) ((void)0)
namespace Kernel {
struct KEvent {
    bool signalled{};
    void Signal() { signalled = true; }
    void Clear() { signalled = false; }
};
}
struct FakeHostSyncpoints {
    using ActionHandle = u64;
    u32 value = 39388;
    u64 next = 0;
    std::map<u64, std::pair<u32, std::function<void()>>> actions;
    std::function<void()> finish_active_callback;
    template<class F> u64 RegisterHostAction(u32 id, u32 target, F action) {
        if (id != 1) throw std::runtime_error("unexpected syncpoint");
        if (value >= target) { action(); return 0; }
        actions.emplace(++next, std::pair{target, std::function<void()>{action}});
        return next;
    }
    void DeregisterHostAction(u32, u64 handle) {
        if (auto finish = std::move(finish_active_callback)) finish();
        actions.erase(handle);
    }
    void Increment() {
        ++value;
        for (auto it = actions.begin(); it != actions.end();) {
            if (it->second.first <= value) { auto action = std::move(it->second.second); it = actions.erase(it); action(); }
            else ++it;
        }
    }
    void WaitHost(u32, u32) { throw std::runtime_error("unbounded host wait reached"); }
};
struct FakeSystem {
    struct Host { FakeHostSyncpoints manager; auto& GetSyncpointManager() { return manager; } } host;
    bool stalled = false;
    bool reject_stalls = true;
    std::mutex mutex;
    auto& Host1x() { return host; }
    auto StallApplication() {
        stalled = true;
        if (reject_stalls) throw std::runtime_error("global stall reached");
        return std::unique_lock{mutex};
    }
    void UnstallApplication() { stalled = false; }
};
struct FakeNvSyncpoints {
    FakeHostSyncpoints& host;
    u32 cached_min = 39385;
    bool IsSyncpointAllocated(u32 id) { return id == 1; }
    bool IsFenceSignalled(NvFence fence) { return cached_min >= fence.value; }
    u32 ReadSyncpointMinValue(u32) { return cached_min; }
    u32 UpdateMin(u32) { return cached_min = host.value; }
};
namespace Tegra::Host1x { using SyncpointManager = FakeHostSyncpoints; }
#ifdef _MSC_VER
#pragma warning(push)
#pragma warning(disable : 4201) // Production ioctl ABI uses anonymous unions/structs.
#endif
#include "nvhost_wait.inc"
#ifdef _MSC_VER
#pragma warning(pop)
#endif
void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
int main() try {
    nvhost_ctrl ctrl;
    Kernel::KEvent event;
    auto& e = ctrl.events[0]; e.kevent = &event; e.registered = true;
    e.status = EventState::Available;
    auto wait = [&](u32 timeout, bool allocate = false, u32 target = 39398, u32 slot = 0) {
        nvhost_ctrl::IocCtrlEventWaitParams p{};
        p.fence = {1, target}; p.timeout = timeout; p.value.raw = slot;
        return ctrl.IocCtrlEventWait(p, allocate);
    };
    nvhost_ctrl::IocCtrlEventClearParams clear{};
    for (int i = 0; i < 6; ++i) {
        require(wait(100) == NvResult::Timeout, "retry must return pending");
        require(!ctrl.system.stalled && !event.signalled, "pending fence must not stall or signal");
        require(ctrl.IocCtrlClearEventWait(clear) == NvResult::Success, "cancel failed");
        require(ctrl.system.host.manager.actions.empty(), "cancel retained waiter");
    }
    require(wait(0) == NvResult::Timeout, "zero timeout must remain pending after repeated cancels");
    require(ctrl.system.host.manager.actions.empty(), "zero timeout registered waiter");
    require(wait(100) == NvResult::Timeout, "rearm failed");
    require(wait(100) == NvResult::BadParameter, "active event reused");
    for (int i = 0; i < 9; ++i) ctrl.system.host.manager.Increment();
    require(!event.signalled, "event signalled before genuine target");
    ctrl.system.host.manager.Increment();
    require(event.signalled && e.status == EventState::Signalled, "genuine increment did not signal");
    require(wait(0) == NvResult::Success, "reached fence not successful");
    require(ctrl.IocCtrlClearEventWait(clear) == NvResult::Success, "clear completed event failed");
    require(wait(100, true, 39399) == NvResult::Timeout, "allocation wait failed");
    ctrl.system.host.manager.Increment();
    require(event.signalled, "allocation event did not signal");
    require(wait(100, false, 39400, MaxNvEvents) == NvResult::BadParameter, "invalid slot accepted");
    require(wait(100, false, 39400) == NvResult::Timeout, "active callback setup failed");
    // Model a callback paused inside Signal after Waiting became Signalling.
    // Deregistration must join that tail before Clear or slot reuse can proceed.
    e.status = EventState::Signalling;
    bool joined = false;
    ctrl.system.host.manager.finish_active_callback = [&] {
        require(e.status == EventState::Cancelling, "cancel did not claim event before join");
        require(e.wait_handle != 0, "callback handle cleared before join");
        event.Signal();
        e.status = EventState::Signalled;
        joined = true;
    };
    require(ctrl.IocCtrlClearEventWait(clear) == NvResult::Success, "active callback cancel failed");
    require(joined, "cancel skipped active callback join");
    require(!event.signalled && e.status == EventState::Cancelled && e.wait_handle == 0,
            "callback tail escaped cancellation");
    require(ctrl.system.host.manager.actions.empty(), "active callback handle retained");
    require(wait(100, false, 39401) == NvResult::Timeout, "slot reuse after join failed");
    ctrl.system.host.manager.Increment();
    require(!event.signalled, "cancelled threshold signalled reused slot");
    ctrl.system.host.manager.Increment();
    require(event.signalled, "reused slot did not complete at new threshold");
    require(ctrl.IocCtrlClearEventWait(clear) == NvResult::Success, "completed clear failed");
    require(ctrl.IocCtrlClearEventWait(clear) == NvResult::Success, "duplicate clear failed");
    std::cout << "PASS: repeated cancellation, zero timeout, asynchronous rearm, exact completion, allocation, invalid slot\n";
    std::cout << "PASS: active callback join before clear, cancelled-threshold reuse, duplicate clear\n";
    return 0;
} catch (const std::exception& error) {
    std::cerr << "FAIL: " << error.what() << '\n';
    return 1;
}
