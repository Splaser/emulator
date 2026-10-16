// SPDX-License-Identifier: GPL-2.0-or-later
// Native acceptance: real CpuManager/KThread/KScheduler fibers, process Finalize, GPU owner,
// Vulkan cache and checked transfers. The headless renderer omits presentation only.
#include <atomic>
#include <chrono>
#include <future>
#include <iostream>
#include <thread>

#include <catch2/catch_test_macros.hpp>
#include "common/settings.h"
#include "common/scope_exit.h"
#include "core/cpu_manager.h"
#include "core/frontend/emu_window.h"
#include "core/frontend/graphics_context.h"
#include "core/hle/kernel/k_hardware_timer.h"
#include "core/hle/kernel/k_resource_limit.h"
#include "core/hle/kernel/k_scoped_resource_reservation.h"
#include "core/hle/kernel/kernel.h"
#include "core/scheduler_test_access.h"
#include "video_core/host1x/host1x.h"
#include "video_core/control/channel_state.h"
#include "video_core/memory_manager.h"
#include "video_core/renderer_base.h"
#include "video_core/vulkan_common/vulkan_instance.h"
#include "video_core/vulkan_common/vulkan_library.h"

namespace {
using namespace std::chrono_literals;
using Access = Core::SchedulerTestAccess;
using Request = Core::Memory::ControlledCpuWriteRequest;
using Action = Request::SchedulerAction;
using Registration = Vulkan::RasterizerVulkan::ControlledRegistrationPtr;
constexpr u64 Footprint = 65536;

class Window final : public Core::Frontend::EmuWindow {
public:
    std::unique_ptr<Core::Frontend::GraphicsContext> CreateSharedContext() const override {
        return std::make_unique<Core::Frontend::GraphicsContext>();
    }
    bool IsShown() const override { return false; }
};

class TransferRenderer final : public VideoCore::RendererBase {
public:
    TransferRenderer(Window& window, Core::System& system)
        : RendererBase(window, window.CreateSharedContext()), library{Vulkan::OpenLibrary()},
          instance{Vulkan::CreateInstance(*library, dispatch, VK_API_VERSION_1_1)},
          device{*instance, Vulkan::vk::PhysicalDevice{instance.EnumeratePhysicalDevices().at(0),
                                                     dispatch}, VK_NULL_HANDLE, dispatch},
          allocator{device}, scheduler{device, state},
          rasterizer{window, system.GPU(), system.Host1x().MemoryManager(), device, allocator,
                     state, scheduler} {}
    ~TransferRenderer() override { Shutdown(); }
    void Shutdown() override {
        if (closed) return;
        rasterizer.Shutdown();
        scheduler.Shutdown();
        {
            std::scoped_lock lock{scheduler.submit_mutex};
            if (device.GetLogical().WaitIdle() == VK_SUCCESS)
                rasterizer.RetireControlledTransfersAfterDeviceIdle();
        }
        scheduler.GetMasterSemaphore().Shutdown();
        closed = true;
    }
    void Composite(std::span<const Tegra::FramebufferConfig>) override {}
    std::vector<u8> GetAppletCaptureBuffer() override { return {}; }
    std::string GetDeviceVendor() const override { return device.GetDriverName(); }
    VideoCore::RasterizerInterface* ReadRasterizer() override { return &rasterizer; }
    std::shared_ptr<Common::DynamicLibrary> library;
    Vulkan::vk::InstanceDispatch dispatch;
    Vulkan::vk::Instance instance;
    Vulkan::Device device;
    Vulkan::MemoryAllocator allocator;
    Vulkan::StateTracker state;
    Vulkan::Scheduler scheduler;
    Vulkan::RasterizerVulkan rasterizer;
    bool closed{};
};

template <typename Predicate>
bool Until(Predicate predicate, std::chrono::milliseconds timeout = 5000ms) {
    const auto end = std::chrono::steady_clock::now() + timeout;
    while (!predicate()) {
        if (std::chrono::steady_clock::now() >= end) return false;
        std::this_thread::sleep_for(1ms);
    }
    return true;
}

struct Process {
    explicit Process(Core::System& system_) : system{system_} {
        auto& kernel = system.Kernel();
        process = Kernel::KProcess::Create(kernel);
        REQUIRE(process);
        const Kernel::Svc::CreateProcessParameter params{
            .code_address = 0x700000, .code_num_pages = 1,
            .flags = Kernel::Svc::CreateProcessFlag::Is64Bit |
                     Kernel::Svc::CreateProcessFlag::AddressSpace32Bit,
        };
        const std::array<u32, 2> caps{7U | (63U << 4) | (4U << 10) | (3U << 24),
                                       0x7fffU | (64U << 16)};
        REQUIRE(R_SUCCEEDED(process->Initialize(params, caps, kernel.GetSystemResourceLimit(),
                                                Kernel::KMemoryManager::Pool::Application, 0)));
        Kernel::KProcess::Register(kernel, process);
        REQUIRE(R_SUCCEEDED(process->GetPageTable().SetMaxHeapSize(16 * 1024 * 1024)));
        REQUIRE(R_SUCCEEDED(process->GetPageTable().SetHeapSize(&heap, 2 * 1024 * 1024)));
        Access::StartProcess(*process);
    }
    ~Process() { Close(); }
    void Close() {
        if (!process) return;
        REQUIRE(R_SUCCEEDED(process->Terminate()));
        process->Close();
        process = nullptr;
    }
    Kernel::KThread* Start(std::function<void()> callback) {
        auto& kernel = system.Kernel();
        Kernel::KScopedResourceReservation reservation{process,
                                                       Kernel::Svc::LimitableResource::ThreadCountMax};
        REQUIRE(reservation.Succeeded());
        auto* thread = Kernel::KThread::Create(kernel);
        REQUIRE(thread);
        REQUIRE(R_SUCCEEDED(Kernel::KThread::InitializeServiceThread(system, thread,
                                      std::move(callback), 16, 3, process)));
        Kernel::KThread::Register(kernel, thread);
        reservation.Commit();
        REQUIRE(R_SUCCEEDED(thread->Run()));
        // Keep this reference for observations; Terminate/Close in the test releases it.
        return thread;
    }
    Core::System& system;
    Kernel::KProcess* process{};
    Kernel::KProcessAddress heap{};
};

void EndThread(Kernel::KThread* thread) {
    REQUIRE(R_SUCCEEDED(thread->Terminate()));
    thread->Close();
}

TEST_CASE("Controlled writes cross real guest fibers and process finalization",
          "[controlled-cpu][native]") {
    Settings::values.use_multi_core.SetValue(true);
    Settings::values.use_asynchronous_gpu_emulation.SetValue(true);
    Settings::values.use_uma_zero_copy.SetValue(false);
    Settings::values.cpu_debug_mode.SetValue(false);
    Core::System system;
    Window window;
    system.Initialize();
    TransferRenderer* renderer{};
    Access::Initialize(system, window, [&](Core::System& owner) {
        auto result = std::make_unique<TransferRenderer>(window, owner);
        renderer = result.get();
        return result;
    });
    SCOPE_EXIT { system.ShutdownMainProcess(); };
    auto& gpu = system.GPU();
    auto& rasterizer = renderer->rasterizer;
    auto& device_memory = system.Host1x().MemoryManager();
    auto channel = gpu.AllocateChannel();
    channel->memory_manager = std::make_shared<Tegra::MemoryManager>(system);
    gpu.RunOnGpuThread([&] {
        gpu.InitChannel(*channel, 0);
        gpu.BindChannel(channel->bind_id);
    });

    // Full KProcess/heap/TLS/PTE construction and Terminate/Finalize destruction. Leave a
    // request queued while its guest CPU fiber is in AwaitControlledCpuWrite, then terminate.
    for (unsigned iteration = 0; iteration < 64; ++iteration) {
        Process owner{system};
        auto& memory = owner.process->GetMemory();
        memory.RasterizerMarkRegionCached(owner.heap, 4096, true);
        auto request = memory.PrepareControlledWrite8(owner.heap + 7, 77);
        REQUIRE(request);
        auto domain = request->View().mapping.domain;
        std::atomic<bool> entered{}, interrupted{};
        auto* thread = owner.Start([&] {
            entered = true;
            interrupted = !system.GetCpuManager().AwaitControlledCpuWrite(request).has_value();
        });
        REQUIRE(Until([&] { return entered.load(); }));
        REQUIRE(Until([&] {
            Kernel::KScopedSchedulerLock lock{system.Kernel()};
            return thread->GetState() == Kernel::ThreadState::Waiting;
        }));
        std::atomic<bool> release{}, retired{};
        REQUIRE(gpu.TryQueueCpuWrite([request, &release, &retired] {
            if (!release.load()) return false;
            (void)request->Cancel();
            retired = true;
            return true;
        }));
        owner.Close(); // Waits for guest exit; PTE is not finalized until the thread ref closes.
        EndThread(thread);
        REQUIRE(Until([&] { return !domain->alive.load(); }));
        REQUIRE(interrupted);
        REQUIRE(request->State() == Request::Phase::Cancelled);
        REQUIRE(!request->Owner()->TryVisit([](auto&) {}));
        // This unrelated callback must retire while the old per-process continuation remains.
        std::atomic<bool> other_progress{};
        REQUIRE(gpu.TryQueueCpuWrite([&] { other_progress = true; return true; }));
        REQUIRE(Until([&] { return other_progress.load(); }));
        release = true;
        REQUIRE(Until([&] { return retired.load(); }));
        gpu.SynchronizeGPUThread();
    }

    Process owner{system};
    auto& memory = owner.process->GetMemory();
    auto* keeper = owner.Start([&] {
        auto& kernel = system.Kernel();
        auto& self = Kernel::GetCurrentThread(kernel);
        while (!self.IsTerminationRequested())
            (void)self.Sleep(kernel.HardwareTimer().GetTick() + 1'000'000);
    });
    const auto asid = device_memory.RegisterProcess(&memory);
    const DAddr address = Footprint;
    device_memory.AllocateFixed(address, Footprint);
    device_memory.Map(address, GetInteger(owner.heap), Footprint, asid);
    std::vector<Core::Memory::PreparedCpuPage> views;
    for (u64 offset = 0; offset < Footprint; offset += 4096) {
        auto view = memory.PrepareControlledCpuPage(owner.heap + offset);
        REQUIRE(view);
        views.push_back(*view);
    }
    Registration operation;
    std::atomic<bool> registered{};
    REQUIRE(gpu.TryQueueCpuWrite([&] {
        if (!operation) operation = rasterizer.BeginControlledBufferRegistration(address, 1, views);
        if (!operation) { registered = true; return true; }
        const auto phase = rasterizer.PollControlledBufferRegistration(operation);
        if (phase == Vulkan::BufferCache::ControlledRegistration::Phase::Ready) {
            registered = true;
            return true;
        }
        return false;
    }));
    REQUIRE(Until([&] { return registered.load(); }));
    REQUIRE(operation);
    gpu.RunOnGpuThread([&] { Access::FillGpu(rasterizer, operation, address, Footprint); });
    auto request = memory.PrepareControlledWrite8(owner.heap + 7, 77);
    REQUIRE(request);
    std::atomic<bool> producer_entered{}, consumer_done{}, queued{};
    std::optional<Action> observed;
    // Contend on REAL production sys-core and device counter locks. These must not occur
    // anywhere in the controlled store/publication lease or require the CPU to release them.
    auto sys_lock = Access::LockSysCore(memory);
    auto counter_lock = std::make_unique<Common::ScopedRangeLock>(
        Access::CounterGuard(device_memory), address, Footprint);
    std::unique_lock cache_lock{Access::Cache(rasterizer).mutex};
    auto* thread = owner.Start([&] {
        queued = rasterizer.QueueControlledCpuWriteRequest(operation, request);
        producer_entered = true;
        observed = system.GetCpuManager().AwaitControlledCpuWrite(request);
        consumer_done = true;
    });
    REQUIRE(Until([&] { return producer_entered.load(); }));
    REQUIRE(queued);
    const bool suspended = Until([&] {
        Kernel::KScopedSchedulerLock lock{system.Kernel()};
        return thread->GetState() == Kernel::ThreadState::Waiting;
    });
    std::atomic<bool> marker{};
    REQUIRE(gpu.TryQueueCpuWrite([&] { marker = true; return true; }));
    const bool progressed = Until([&] { return marker.load(); }, 500ms);
    const auto before_unlock = request->State();
    cache_lock.unlock(); // Always break the negative-control cycle before reporting failure.
    REQUIRE(suspended);
    REQUIRE(progressed);
    REQUIRE(before_unlock == Request::Phase::Prepared);
    REQUIRE(Until([&] { return consumer_done.load(); }));
    REQUIRE(observed == Action::Complete);
    REQUIRE(request->Outcome() == Core::Memory::PreparedCpuWriteResult::Stored);
    const auto bytes = request->View().physical.storage.Bytes();
    REQUIRE(bytes[6] == 99);
    REQUIRE(bytes[7] == 77);
    REQUIRE(bytes[8] == 99);
    REQUIRE(request->View().physical.Published()->sequence == 1);
    for (unsigned poll = 0; poll < 16; ++poll)
        REQUIRE(!rasterizer.QueueControlledCpuWriteRequest(operation, request));
    REQUIRE(system.GetCpuManager().AwaitControlledCpuWrite(nullptr) == Action::DoNotExecute);
    sys_lock.unlock();
    counter_lock.reset();
    EndThread(thread);

    // Owner acceptance can certify refusal before any physical/native effects. Consume it
    // through the same guest API, never by treating enqueue acknowledgement as completion.
    memory.RasterizerMarkRegionCached(owner.heap + Footprint, 4096, true);
    auto refused = memory.PrepareControlledWrite8(owner.heap + Footprint + 7, 78);
    REQUIRE(refused);
    consumer_done = false;
    thread = owner.Start([&] {
        queued = rasterizer.QueueControlledCpuWriteRequest(operation, refused);
        observed = system.GetCpuManager().AwaitControlledCpuWrite(refused);
        consumer_done = true;
    });
    REQUIRE(Until([&] { return consumer_done.load(); }));
    REQUIRE(queued);
    REQUIRE(observed == Action::ReprepareCertified);
    REQUIRE(refused->State() == Request::Phase::Refused);
    EndThread(thread);

    // A successful enqueue can be dropped at the 64-slot owner boundary. The real guest
    // consumer must see Cancelled rather than waiting forever or reporting completion.
    std::atomic<bool> release_slots{};
    for (unsigned slot = 0; slot < 64; ++slot)
        REQUIRE(gpu.TryQueueCpuWrite([&] { return release_slots.load(); }));
    gpu.SynchronizeGPUThread();
    auto cancelled = memory.PrepareControlledWrite8(owner.heap + 9, 78);
    REQUIRE(cancelled);
    consumer_done = false;
    thread = owner.Start([&] {
        queued = rasterizer.QueueControlledCpuWriteRequest(operation, cancelled);
        observed = system.GetCpuManager().AwaitControlledCpuWrite(cancelled);
        consumer_done = true;
    });
    REQUIRE(Until([&] { return consumer_done.load(); }));
    REQUIRE(queued);
    REQUIRE(observed == Action::DoNotExecute);
    REQUIRE(cancelled->State() == Request::Phase::Cancelled);
    release_slots = true;
    gpu.SynchronizeGPUThread();
    EndThread(thread);

    // Restore the GPU representation before another controlled request. This is an actual
    // checked upload/readback, not a fabricated completion or a native queue drain.
    gpu.RunOnGpuThread([&] { REQUIRE(rasterizer.RefreshControlledBufferRegistration(operation)); });
    registered = false;
    REQUIRE(gpu.TryQueueCpuWrite([&] {
        if (rasterizer.PollControlledBufferRegistration(operation) ==
            Vulkan::BufferCache::ControlledRegistration::Phase::Ready) {
            registered = true;
            return true;
        }
        return false;
    }));
    REQUIRE(Until([&] { return registered.load(); }));
    auto uncertain = memory.PrepareControlledWrite8(owner.heap + 10, 79);
    REQUIRE(uncertain);
    const auto admission = uncertain->View().physical.Epoch()->ranges;
    const std::array dependency_access{Common::PhysicalRangeAdmission::Access{
        uncertain->View().physical.PhysicalOffset(), 4096,
        Common::PhysicalRangeAdmission::Mode::Write}};
    auto dependency = admission->Enqueue(dependency_access, std::make_shared<int>(1));
    REQUIRE(dependency);
    REQUIRE(admission->TryStart(dependency) == Common::PhysicalRangeAdmission::Start::Granted);
    consumer_done = false;
    producer_entered = false;
    thread = owner.Start([&] {
        queued = rasterizer.QueueControlledCpuWriteRequest(operation, uncertain);
        producer_entered = true;
        observed = system.GetCpuManager().AwaitControlledCpuWrite(uncertain);
        consumer_done = true;
    });
    REQUIRE(Until([&] { return producer_entered.load() && uncertain->State() == Request::Phase::Accepted; }));
    gpu.SynchronizeGPUThread(); // accepted, parked behind the real physical predecessor
    std::unique_lock pte_lock{uncertain->View().mapping.domain->mutex};
    REQUIRE(admission->Complete(dependency));
    // A CPU PTE owner waits for a later GPU callback; the GPU must refuse rather than
    // synchronously acquire this PTE lock while this CPU waits for its progress.
    marker = false;
    REQUIRE(gpu.TryQueueCpuWrite([&] { marker = true; return true; }));
    const bool pte_progress = Until([&] { return marker.load() && consumer_done.load(); }, 500ms);
    pte_lock.unlock();
    REQUIRE(pte_progress);
    REQUIRE(queued);
    REQUIRE(observed == Action::Quarantine);
    REQUIRE(uncertain->State() == Request::Phase::Unknown);
    EndThread(thread);

    // Negative witnesses on the SAME native objects: legacy publication waits for a CPU
    // counter owner; legacy PTE mutation waits for a CPU PTE owner. A later GPU callback
    // cannot run until we explicitly break each cycle. This validates the progress probe.
    for (const bool counter : {true, false}) {
        auto range = counter ? std::make_unique<Common::ScopedRangeLock>(
                                   Access::CounterGuard(device_memory), address, Footprint)
                             : nullptr;
        std::unique_lock pte{request->View().mapping.domain->mutex, std::defer_lock};
        if (!counter) pte.lock();
        std::atomic<bool> legacy_entered{};
        marker = false;
        REQUIRE(gpu.TryQueueCpuWrite([&] {
            legacy_entered = true;
            if (counter) Access::LegacyPublish(rasterizer, address);
            else memory.RasterizerMarkRegionCached(owner.heap, 4096, true);
            return true;
        }));
        REQUIRE(Until([&] { return legacy_entered.load(); }));
        REQUIRE(gpu.TryQueueCpuWrite([&] { marker = true; return true; }));
        const bool bypassed_blocking_legacy = Until([&] { return marker.load(); }, 50ms);
        range.reset();
        if (pte.owns_lock()) pte.unlock();
        REQUIRE(Until([&] { return marker.load(); }));
        REQUIRE_FALSE(bypassed_blocking_legacy);
        gpu.SynchronizeGPUThread();
    }

    // Accepted native work can outlive its process without a full GPU queue drain. Hold
    // the REAL Vulkan submission mutex so preservation cannot complete during termination.
    Process pending_owner{system};
    auto& pending_memory = pending_owner.process->GetMemory();
    const auto pending_asid = device_memory.RegisterProcess(&pending_memory);
    const DAddr pending_address = 2 * Footprint;
    device_memory.AllocateFixed(pending_address, Footprint);
    device_memory.Map(pending_address, GetInteger(pending_owner.heap), Footprint, pending_asid);
    std::vector<Core::Memory::PreparedCpuPage> pending_views;
    for (u64 offset = 0; offset < Footprint; offset += 4096) {
        auto view = pending_memory.PrepareControlledCpuPage(pending_owner.heap + offset);
        REQUIRE(view);
        pending_views.push_back(*view);
    }
    Registration pending_operation;
    registered = false;
    REQUIRE(gpu.TryQueueCpuWrite([&] {
        if (!pending_operation)
            pending_operation = rasterizer.BeginControlledBufferRegistration(
                pending_address, 1, pending_views);
        if (!pending_operation) { registered = true; return true; }
        if (rasterizer.PollControlledBufferRegistration(pending_operation) ==
            Vulkan::BufferCache::ControlledRegistration::Phase::Ready) {
            registered = true;
            return true;
        }
        return false;
    }));
    REQUIRE(Until([&] { return registered.load(); }));
    REQUIRE(pending_operation);
    auto pending = pending_memory.PrepareControlledWrite8(pending_owner.heap + 7, 77);
    REQUIRE(pending);
    auto pending_domain = pending->View().mapping.domain;
    std::unique_lock submit_lock{renderer->scheduler.submit_mutex};
    std::atomic<bool> pending_entered{};
    auto* pending_thread = pending_owner.Start([&] {
        queued = rasterizer.QueueControlledCpuWriteRequest(pending_operation, pending);
        pending_entered = true;
        (void)system.GetCpuManager().AwaitControlledCpuWrite(pending);
    });
    REQUIRE(Until([&] { return pending_entered.load() && pending->State() == Request::Phase::Accepted; }));
    REQUIRE(queued);
    gpu.SynchronizeGPUThread(); // FIFO acknowledgement only; native submission is still blocked.
    device_memory.UnregisterProcess(pending_asid);
    auto exit = std::async(std::launch::async, [&] {
        system.RegisterHostThread();
        pending_owner.Close();
    });
    const bool exited_without_gpu_drain = exit.wait_for(500ms) == std::future_status::ready;
    if (!exited_without_gpu_drain) submit_lock.unlock(); // break a regression's dependency cycle
    exit.get();
    EndThread(pending_thread);
    REQUIRE(exited_without_gpu_drain);
    REQUIRE(Until([&] { return !pending_domain->alive.load(); }));
    REQUIRE(pending->State() == Request::Phase::Unknown);
    REQUIRE(pending->Action() == Action::Quarantine);
    REQUIRE(!pending->Owner()->TryVisit([](auto&) {}));
    marker = false;
    REQUIRE(gpu.TryQueueCpuWrite([&] { marker = true; return true; }));
    const bool unrelated_during_native_wait = Until([&] { return marker.load(); }, 500ms);
    submit_lock.unlock();
    REQUIRE(unrelated_during_native_wait);
    gpu.SynchronizeGPUThread();
    REQUIRE(pending->View().physical.storage.Bytes()[7] != 77);
    gpu.RunOnGpuThread([&] { device_memory.Unmap(pending_address, Footprint); });

    std::cout << "PASS native guest KThread/KScheduler suspend/resume, all terminal observations, "
                 "64 full process teardowns, real cache/sys-core/PTE/counter contention; "
                 "GPU99 CPU77 GPU99; accepted native teardown without queue drain\n";
    // Unregister the process while its Memory/PTE still exist. The cache is owner-drained
    // through an ordinary queue barrier here; individual teardown loops above never drain it.
    gpu.RunOnGpuThread([&] { device_memory.Unmap(address, Footprint); });
    device_memory.UnregisterProcess(asid);
    owner.Close();
    EndThread(keeper);
}
} // namespace
