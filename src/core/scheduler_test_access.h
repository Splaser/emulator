// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

// Linked only by CITRON_TESTS builds. These peers select real owners/locks; they do not
// replace scheduler, store, tracker, GPU queue, completion or process finalization bodies.
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <vector>

#include "core/core.h"
#include "core/scheduler_system_test_access.h"
#include "core/memory.h"
#include "core/hle/kernel/k_process.h"
#include "video_core/renderer_vulkan/vk_rasterizer.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"

namespace Core {
struct SchedulerTestAccess : SystemTestAccess {
    static auto& Cache(Vulkan::RasterizerVulkan& rasterizer) { return rasterizer.buffer_cache; }
    static auto& CounterGuard(Tegra::MaxwellDeviceMemoryManager& memory) {
        return memory.counter_guard;
    }
    static void StartProcess(Kernel::KProcess& process) {
        // Same running reference/state transition as Run(), with a service fiber entrypoint
        // instead of executing an ARM application image. All termination/finalization is real.
        process.Open();
        process.ChangeState(Kernel::KProcess::State::Running);
    }
    static void FillGpu(Vulkan::RasterizerVulkan& rasterizer,
                        const Vulkan::RasterizerVulkan::ControlledRegistrationPtr& op,
                        DAddr address, u64 size) {
        auto& cache = Cache(rasterizer);
        const auto id = cache.ControlledReadyBuffer(op);
        auto& buffer = cache.slot_buffers[id];
        rasterizer.buffer_cache_runtime.ClearBuffer(buffer.Handle(), 0, size, 0x63636363);
        cache.memory_tracker.MarkRegionAsGpuModified(address, size);
        cache.gpu_modified_ranges.Add(address, size);
    }
    static void LegacyPublish(Vulkan::RasterizerVulkan& rasterizer, DAddr address) {
        Cache(rasterizer).memory_tracker.MarkRegionAsCpuModified(address, 1);
    }
    static bool QueueLegacyReadback(Vulkan::RasterizerVulkan& rasterizer,
                                   const Vulkan::RasterizerVulkan::ControlledRegistrationPtr& op,
                                   DAddr address, u32 size) {
        auto& cache = Cache(rasterizer);
        const auto id = cache.ControlledReadyBuffer(op);
        cache.MarkWrittenBuffer(id, address, size);
        cache.CommitAsyncFlushes();
        return cache.ShouldWaitAsyncFlushes();
    }
    static void RetireLegacyReadback(Vulkan::RasterizerVulkan& rasterizer) {
        rasterizer.scheduler.Finish();
        Cache(rasterizer).PopAsyncFlushes();
    }
    static unsigned ProbeLegacyReadbackGuards(
        Vulkan::RasterizerVulkan& rasterizer,
        const Vulkan::RasterizerVulkan::ControlledRegistrationPtr& op,
        DAddr address, u32 size) {
        auto& cache = Cache(rasterizer);
        const auto id = cache.ControlledBufferId(op, false, true);
        unsigned blocked{};
        const auto probe = [&](auto&& operation) {
            try { operation(); } catch (const std::runtime_error&) { ++blocked; }
        };
        probe([&] { cache.DownloadMemory(address, size); });
        probe([&] { cache.DownloadBufferMemory(cache.slot_buffers[id], address, size); });
        const u8 stale = 10;
        probe([&] { cache.WriteBackDownload(address, &stale, 1); });
        // Deliberately attempt a legacy scheduling violation. Rejection must precede
        // AccumulateFlushes, so the test can remove its untouched candidate afterwards.
        cache.uncommitted_gpu_modified_ranges.Add(address, 1);
        probe([&] { cache.CommitAsyncFlushes(); });
        if (cache.uncommitted_gpu_modified_ranges.Empty()) return 0;
        cache.uncommitted_gpu_modified_ranges.Subtract(address, 1);
        return blocked;
    }
    // M4 observation helpers: real ordinary cache methods and Vulkan transfers. These
    // select/observe resources; they provide no production coherency or eligibility policy.
    static Vulkan::StagedBufferPin OrdinaryPin(Vulkan::RasterizerVulkan& rasterizer,
                                              DAddr address, u32 size) {
        auto& cache = Cache(rasterizer);
        std::scoped_lock lock{cache.mutex};
        auto [buffer, offset] = cache.ObtainCPUBuffer(address, size,
            VideoCommon::ObtainBufferSynchronize::FullSynchronize,
            VideoCommon::ObtainBufferOperation::DoNothing);
        auto pin = buffer->PinStagedRepresentation(offset, size);
        if (!pin) throw std::runtime_error("ordinary staged observation pin unavailable");
        return *pin;
    }
    static std::vector<u8> ReadPin(Vulkan::RasterizerVulkan& rasterizer,
                                   const Vulkan::StagedBufferPin& pin) {
        auto& runtime = rasterizer.buffer_cache_runtime;
        auto staging = runtime.DownloadStagingBuffer(pin.Size());
        const std::array<VideoCommon::BufferCopy, 1> copies{{
            {.src_offset = pin.Offset(), .dst_offset = staging.offset, .size = pin.Size()}}};
        runtime.CopyBuffer(staging.buffer, pin.Handle(), copies, true);
        rasterizer.scheduler.Finish(); // No cache, mapping, PTE or execution lease held.
        return {staging.mapped_span.begin(), staging.mapped_span.begin() + pin.Size()};
    }
    static void WriteOrdinaryGpu(Vulkan::RasterizerVulkan& rasterizer,
                                 DAddr address, u32 size, u32 value) {
        auto& cache = Cache(rasterizer);
        std::optional<Vulkan::StagedBufferPin> pin;
        {
            std::scoped_lock lock{cache.mutex};
            auto [buffer, offset] = cache.ObtainCPUBuffer(address, size,
                VideoCommon::ObtainBufferSynchronize::FullSynchronize,
                VideoCommon::ObtainBufferOperation::MarkAsWritten);
            pin = buffer->PinStagedRepresentation(offset, size);
            if (!pin) throw std::runtime_error("ordinary GPU writer pin unavailable");
            rasterizer.buffer_cache_runtime.ClearBuffer(pin->Handle(), offset, size, value);
        }
        rasterizer.scheduler.Finish();
    }
    static void RetireOrdinary(Vulkan::RasterizerVulkan& rasterizer, DAddr address) {
        auto& cache = Cache(rasterizer);
        std::scoped_lock lock{cache.mutex};
        cache.DeleteBuffer(cache.FindBuffer(address, 1));
    }
};
} // namespace Core
