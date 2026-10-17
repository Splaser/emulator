// SPDX-FileCopyrightText: Copyright 2019 yuzu Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <memory>
#include <limits>
#include <stdexcept>
#include <mutex>
#include <thread>
#include <utility>

#include "video_core/renderer_vulkan/vk_query_cache.h"

#include "common/thread.h"
#include "common/profiling.h"
#include "video_core/renderer_vulkan/vk_command_pool.h"
#include "video_core/renderer_vulkan/vk_master_semaphore.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "video_core/renderer_vulkan/vk_state_tracker.h"
#include "video_core/renderer_vulkan/vk_texture_cache.h"
#include "video_core/vulkan_common/vulkan_device.h"
#include "video_core/vulkan_common/vulkan_wrapper.h"

namespace Vulkan {

void Scheduler::SetQueryCache(VideoCommon::QueryCacheBase<QueryCacheParams>& query_cache_) {
    query_cache = &query_cache_;
}

void Scheduler::CommandChunk::ExecuteAll(vk::CommandBuffer cmdbuf,
                                         vk::CommandBuffer upload_cmdbuf) {
    auto command = first;
    while (command != nullptr) {
        auto next = command->GetNext();
        command->Execute(cmdbuf, upload_cmdbuf);
        command->~Command();
        command = next;
    }
    submit = false;
    command_offset = 0;
    first = nullptr;
    last = nullptr;
}

Scheduler::Scheduler(const Device& device_, StateTracker& state_tracker_)
    : device{device_}, state_tracker{state_tracker_},
      master_semaphore{std::make_unique<MasterSemaphore>(device)},
      command_pool{std::make_unique<CommandPool>(*master_semaphore, device)} {
    AcquireNewChunk();
    AllocateWorkerCommandBuffer();
    worker_thread = std::jthread([this](std::stop_token token) { WorkerThread(token); });
}

Scheduler::~Scheduler() {
    submission_owner->store(false, std::memory_order_release);
    // Normal renderer shutdown explicitly drains while callback owners still live.
    // On construction failure/unwinding, never dispatch new callbacks from here:
    // later-declared renderer members may already have been destroyed.
    worker_thread.request_stop();
    event_cv.notify_all();
    if (worker_thread.joinable()) {
        worker_thread.join();
    }
}

void Scheduler::Shutdown() {
    submission_owner->store(false, std::memory_order_release);
    if (!worker_thread.joinable()) {
        return;
    }
    WaitWorker();
    worker_thread.request_stop();
    event_cv.notify_all();
    worker_thread.join();
}

u64 Scheduler::Flush(VkSemaphore signal_semaphore, VkSemaphore wait_semaphore) {
    // When flushing, we only send data to the worker thread; no waiting is necessary.
    const u64 signal_value = SubmitExecution(signal_semaphore, wait_semaphore);
    AllocateNewContext();
    return signal_value;
}

Scheduler::Submission Scheduler::FlushChecked() {
    if (!submission_owner->load(std::memory_order_acquire) || !device.HasTimelineSemaphore())
        return {};
    auto submission = observed_submission ? observed_submission :
        Submission{new CheckedSubmission{submission_owner}};
    SubmitExecution(nullptr, nullptr, submission);
    AllocateNewContext();
    return submission;
}

VkResult Scheduler::PollChecked(const Submission& submission) const noexcept {
    if (!submission || submission->owner != submission_owner ||
        !submission_owner->load(std::memory_order_acquire))
        return VK_ERROR_UNKNOWN;
    const auto result = submission->result.load(std::memory_order_acquire);
    if (result != VK_SUCCESS) return result;
    return master_semaphore->PollTimeline(submission->tick);
}

Scheduler::Write Scheduler::RecordCheckedWrite(std::shared_ptr<const void> resources,
    const void* identity, u64 offset, u64 size, u64 intent_revision,
    std::function<bool(vk::CommandBuffer)> command) {
    if (!resources || !identity || !size || !intent_revision ||
        size > std::numeric_limits<u64>::max() - offset ||
        !command || !submission_owner->load(std::memory_order_acquire) ||
        !device.HasTimelineSemaphore() || checked_writes.size() >= 256) return {};
    auto write = Write{new CheckedWrite{std::move(resources), identity, offset, size,
                                      intent_revision, submission_owner}};
    checked_writes.push_back(write); // Retain before recording, including uncertain failures.
    try {
        Record([write, bound_command = std::move(command)](vk::CommandBuffer cmdbuf) {
            try {
                const bool emitted = bound_command(cmdbuf);
                auto expected = CheckedWrite::Emission::Pending;
                (void)write->emission.compare_exchange_strong(
                    expected, emitted ? CheckedWrite::Emission::Recorded : CheckedWrite::Emission::Skipped,
                    std::memory_order_release, std::memory_order_relaxed);
            } catch (...) {
                // A command may have emitted partial effects. Never replay it.
                write->emission.store(CheckedWrite::Emission::Unknown, std::memory_order_release);
            }
        });
        write->submission = FlushChecked();
    } catch (...) {
        write->emission.store(CheckedWrite::Emission::Unknown, std::memory_order_release);
    }
    return write;
}

Scheduler::WriteState Scheduler::PollCheckedWrite(const Write& write) const noexcept {
    using Emission = CheckedWrite::Emission;
    if (!write || write->owner != submission_owner || write->retired ||
        !submission_owner->load(std::memory_order_acquire)) return WriteState::Unknown;
    const auto emission = write->emission.load(std::memory_order_acquire);
    if (emission == Emission::Unknown) return WriteState::Unknown;
    const auto status = PollChecked(write->submission);
    if (status != VK_SUCCESS && status != VK_NOT_READY) {
        write->emission.store(Emission::Unknown, std::memory_order_release);
        return WriteState::Unknown;
    }
    if (emission == Emission::Pending) return WriteState::Pending;
    if (status != VK_SUCCESS) {
        return write->submission && write->submission->result.load(std::memory_order_acquire) == VK_SUCCESS
            ? WriteState::Submitted : WriteState::Pending;
    }
    return emission == Emission::Skipped ? WriteState::Skipped : WriteState::Complete;
}

Scheduler::ObservedWrites Scheduler::RecordObservedWrites(std::span<const WriteFootprint> footprints,
    std::function<bool(vk::CommandBuffer)> command,
    std::shared_ptr<VideoCommon::PhysicalWriteCoverage> coverage) {
    if (!command) return {};
    std::shared_ptr<std::vector<Write>> writes;
    Submission submission;
    try {
        if (footprints.size() > 64 || checked_writes.size() + footprints.size() > 256 ||
            !submission_owner->load(std::memory_order_acquire) || !device.HasTimelineSemaphore() ||
            (coverage && !coverage->Accepting()))
            throw std::runtime_error("unsupported observed write batch");
        for (const auto& range : footprints) {
            if (!range.resources || !range.identity || !range.size || !range.intent_revision ||
                range.size > std::numeric_limits<u64>::max() - range.offset)
                throw std::runtime_error("invalid observed write footprint");
        }
        writes = std::make_shared<std::vector<Write>>();
        writes->reserve(footprints.size());
        checked_writes.reserve(checked_writes.size() + footprints.size());
        if (!footprints.empty()) {
            submission = observed_submission ? observed_submission :
                Submission{new CheckedSubmission{submission_owner}};
            for (const auto& range : footprints) {
                auto write = Write{new CheckedWrite{range.resources, range.identity, range.offset,
                    range.size, range.intent_revision, submission_owner}};
                write->submission = submission;
                write->coverage = coverage;
                write->access = range.access;
                const bool associated = range.physical &&
                    range.physical->Representation() == range.identity &&
                    range.physical->NativeOffset() == range.offset &&
                    range.physical->Size() == range.size && range.physical->OwnersAlive();
                if (associated) write->physical = range.physical;
                else if (coverage) coverage->Invalidate();
                writes->push_back(std::move(write));
            }
        }
    } catch (...) {
        if (coverage) coverage->Invalidate();
        // No observed command has been queued. Diagnostics never drop/replay rendering.
        Record(std::move(command));
        return {};
    }
    if (submission) observed_submission = submission;
    checked_writes.insert(checked_writes.end(), writes->begin(), writes->end());
    try {
        Record([writes, bound_command = std::move(command)](vk::CommandBuffer cmdbuf) {
            try {
                const auto emission = bound_command(cmdbuf) ? CheckedWrite::Emission::Recorded :
                                                            CheckedWrite::Emission::Skipped;
                const auto position = !writes->empty() && emission == CheckedWrite::Emission::Recorded
                    ? writes->front()->submission->synchronization.RecordAccess() : 0;
                for (const auto& write : *writes) {
                    write->position = position;
                    auto expected = CheckedWrite::Emission::Pending;
                    (void)write->emission.compare_exchange_strong(expected, emission,
                        std::memory_order_release, std::memory_order_relaxed);
                }
            } catch (...) {
                for (const auto& write : *writes)
                    write->emission.store(CheckedWrite::Emission::Unknown, std::memory_order_release);
                throw; // Preserve the ordinary worker's exception behavior.
            }
        });
    } catch (...) {
        for (const auto& write : *writes)
            write->emission.store(CheckedWrite::Emission::Unknown, std::memory_order_release);
        throw;
    }
    return writes;
}

const VideoCommon::PhysicalWriteIdentity* Scheduler::CompletedPhysicalIdentity(
    const Write& write) const noexcept {
    if (PollCheckedWrite(write) != WriteState::Complete || !write->PhysicalCoverageComplete() ||
        !write->physical || !write->physical->OwnersAlive()) return nullptr;
    return write->physical.get();
}

bool Scheduler::HasConfirmedMemoryDependency(const Write& before, const Write& after,
                                            u64 physical_offset, u64 size) const noexcept {
    const auto* a = CompletedPhysicalIdentity(before);
    const auto* b = CompletedPhysicalIdentity(after);
    if (!a || !b || !size || size > std::numeric_limits<u64>::max() - physical_offset ||
        before->submission != after->submission || a->Backing() != b->Backing() ||
        a->Representation() != b->Representation()) return false;
    const auto unique_projection = [](const VideoCommon::PhysicalWriteIdentity& plan) {
        const auto segments = plan.Segments();
        for (size_t i = 0; i < segments.size(); ++i)
            for (size_t j = i + 1; j < segments.size(); ++j)
                if (segments[i].physical_offset < segments[j].physical_offset + segments[j].length &&
                    segments[j].physical_offset < segments[i].physical_offset + segments[i].length)
                    return false;
        return true;
    };
    if (!unique_projection(*a) || !unique_projection(*b)) return false;
    // Each requested physical byte must project to the SAME native allocation byte.
    // Physical aliases backed by independent staged buffers do not inherit contents.
    for (u64 cursor = physical_offset; cursor < physical_offset + size;) {
        u64 advance{};
        for (const auto& left : a->Segments()) {
            if (cursor < left.physical_offset || cursor - left.physical_offset >= left.length) continue;
            for (const auto& right : b->Segments()) {
                if (cursor < right.physical_offset || cursor - right.physical_offset >= right.length)
                    continue;
                const auto native_a = a->NativeOffset() + left.logical_offset + cursor - left.physical_offset;
                const auto native_b = b->NativeOffset() + right.logical_offset + cursor - right.physical_offset;
                if (native_a == native_b)
                    advance = std::min({physical_offset + size - cursor,
                        left.length - (cursor - left.physical_offset),
                        right.length - (cursor - right.physical_offset)});
            }
        }
        if (!advance) return false;
        cursor += advance;
    }
    return before->submission->synchronization.Proves(
        before->position, before->access, after->position, after->access);
}

void Scheduler::RecordProvenanceBarrier(VkPipelineStageFlags source,
                                       VkPipelineStageFlags destination,
                                       const VkMemoryBarrier& memory) {
    Record([submission = observed_submission, source, destination, memory](vk::CommandBuffer cmdbuf) {
        cmdbuf.PipelineBarrier(source, destination, 0, memory);
        if (submission) submission->synchronization.RecordBarrier(source, destination, memory);
    });
}

void Scheduler::RetireCheckedWritesAfterDeviceIdle() {
    if (observed_submission) return; // Device idle does not submit recorded host work.
    for (const auto& write : checked_writes) {
        write->retired = true;
        write->resources.reset();
    }
    checked_writes.clear();
}

void Scheduler::Finish(VkSemaphore signal_semaphore, VkSemaphore wait_semaphore) {
    // When finishing, we need to wait for the submission to have executed on the device.
    const u64 presubmit_tick = CurrentTick();
    SubmitExecution(signal_semaphore, wait_semaphore);
    Wait(presubmit_tick);
    AllocateNewContext();
}

void Scheduler::WaitWorker() {
    DispatchWork();

    // Ensure the queue is drained.
    {
        std::unique_lock ql{queue_mutex};
        event_cv.wait(ql, [this] { return work_queue.empty(); });
    }

    // Now wait for execution to finish.
    std::scoped_lock el{execution_mutex};
}

void Scheduler::DispatchWork() {
    if (chunk->Empty()) {
        return;
    }
    {
        std::scoped_lock ql{queue_mutex};
        work_queue.push(std::move(chunk));
    }
    event_cv.notify_all();
    AcquireNewChunk();
}

void Scheduler::RequestRenderpass(const Framebuffer* framebuffer) {
    const VkRenderPass renderpass = framebuffer->RenderPass();
    const VkFramebuffer framebuffer_handle = framebuffer->Handle();
    const VkExtent2D render_area = framebuffer->RenderArea();
    if (renderpass == state.renderpass && framebuffer_handle == state.framebuffer &&
        render_area.width == state.render_area.width &&
        render_area.height == state.render_area.height) {
        return;
    }
    EndRenderPass();
    state.renderpass = renderpass;
    state.framebuffer = framebuffer_handle;
    state.render_area = render_area;

    Record([renderpass, framebuffer_handle, render_area](vk::CommandBuffer cmdbuf) {
        const VkRenderPassBeginInfo renderpass_bi{
            .sType = VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO,
            .pNext = nullptr,
            .renderPass = renderpass,
            .framebuffer = framebuffer_handle,
            .renderArea =
                {
                    .offset = {.x = 0, .y = 0},
                    .extent = render_area,
                },
            .clearValueCount = 0,
            .pClearValues = nullptr,
        };
        cmdbuf.BeginRenderPass(renderpass_bi, VK_SUBPASS_CONTENTS_INLINE);
    });
    num_renderpass_images = framebuffer->NumImages();
    renderpass_images = framebuffer->Images();
    renderpass_image_ranges = framebuffer->ImageRanges();
}

void Scheduler::RequestOutsideRenderPassOperationContext() {
    EndRenderPass();
    RecordDeferredWaitForIdle();
    // Copies, clears, dispatches and query work all come through here
    unsynced_writes = true;
}

void Scheduler::RequestOutsideRenderPassSyncedOperationContext() {
    EndRenderPass();
    RecordDeferredWaitForIdle();
}

void Scheduler::WaitForIdle(VkPipelineStageFlags src_stages) {
    deferred_wfi_stages |= src_stages;
    if (state.renderpass && !unsynced_writes) {
        // Draws since the last barrier wrote attachments only, which later draws of this render
        // pass see in order. The barrier waits until something reads or writes memory in a way
        // the pass does not order.
        return;
    }
    EndRenderPass();
    RecordDeferredWaitForIdle();
    unsynced_writes = false;
}

void Scheduler::RecordDeferredWaitForIdle() {
    if (deferred_wfi_stages == 0) {
        return;
    }
    // A pipeline barrier with a memory barrier: later work starts after earlier work has
    // finished and sees its writes. The event pair this replaced had TOP_OF_PIPE as its second
    // scope, which carries no memory dependency, and the event was never reset, so every wait
    // after the first did nothing.
    static constexpr VkMemoryBarrier WRITES_VISIBLE{
        .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
        .pNext = nullptr,
        .srcAccessMask = VK_ACCESS_MEMORY_WRITE_BIT,
        .dstAccessMask = VK_ACCESS_MEMORY_READ_BIT | VK_ACCESS_MEMORY_WRITE_BIT,
    };
    RecordProvenanceBarrier(deferred_wfi_stages, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, WRITES_VISIBLE);
    deferred_wfi_stages = 0;
}

bool Scheduler::UpdateGraphicsPipeline(GraphicsPipeline* pipeline) {
    if (state.graphics_pipeline == pipeline) {
        return false;
    }
    state.graphics_pipeline = pipeline;
    return true;
}

bool Scheduler::UpdateRescaling(bool is_rescaling) {
    if (state.rescaling_defined && is_rescaling == state.is_rescaling) {
        return false;
    }
    state.rescaling_defined = true;
    state.is_rescaling = is_rescaling;
    return true;
}

void Scheduler::WorkerThread(std::stop_token stop_token) {
    Common::SetCurrentThreadName("VulkanWorker");

    const auto TryPopQueue{[this](auto& work) -> bool {
        if (work_queue.empty()) {
            return false;
        }

        work = std::move(work_queue.front());
        work_queue.pop();
        event_cv.notify_all();
        return true;
    }};

    while (!stop_token.stop_requested()) {
        std::unique_ptr<CommandChunk> work;

        {
            std::unique_lock lk{queue_mutex};

            // Wait for work.
            Common::CondvarWait(event_cv, lk, stop_token, [&] { return TryPopQueue(work); });

            // If we've been asked to stop, we're done.
            if (stop_token.stop_requested()) {
                return;
            }

            // Exchange lock ownership so that we take the execution lock before
            // the queue lock goes out of scope. This allows us to force execution
            // to complete in the next step.
            std::exchange(lk, std::unique_lock{execution_mutex});

            // Perform the work, tracking whether the chunk was a submission
            // before executing.
            const bool has_submit = work->HasSubmit();
            {
                CITRON_PROFILE_SCOPE("Vulkan::WorkerExecute");
                work->ExecuteAll(current_cmdbuf, current_upload_cmdbuf);
            }

            // If the chunk was a submission, reallocate the command buffer.
            if (has_submit) {
                AllocateWorkerCommandBuffer();
            }
        }

        {
            std::scoped_lock rl{reserve_mutex};

            // Recycle the chunk back to the reserve.
            chunk_reserve.emplace_back(std::move(work));
        }
    }
}

void Scheduler::AllocateWorkerCommandBuffer() {
    current_cmdbuf = vk::CommandBuffer(command_pool->Commit(), device.GetDispatchLoader());
    current_cmdbuf.Begin({
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .pNext = nullptr,
        .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
        .pInheritanceInfo = nullptr,
    });
    current_upload_cmdbuf = vk::CommandBuffer(command_pool->Commit(), device.GetDispatchLoader());
    current_upload_cmdbuf.Begin({
        .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
        .pNext = nullptr,
        .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
        .pInheritanceInfo = nullptr,
    });
}

u64 Scheduler::SubmitExecution(VkSemaphore signal_semaphore, VkSemaphore wait_semaphore,
                               Submission checked) {
    CITRON_PROFILE_SCOPE("Vulkan::SubmitExecution");
    const bool ordinary_errors = !checked;
    if (observed_submission) {
        checked = std::exchange(observed_submission, {});
    }
    try {
        EndPendingOperations();
        InvalidateState();

        const u64 signal_value = master_semaphore->NextTick();
        if (checked) checked->tick = signal_value;
        RecordWithUploadBuffer([signal_semaphore, wait_semaphore, signal_value, checked, ordinary_errors,
                                this](vk::CommandBuffer cmdbuf, vk::CommandBuffer upload_cmdbuf) {
            try {
                static constexpr VkMemoryBarrier WRITE_BARRIER{
                    .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER,
                    .pNext = nullptr,
                    .srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT,
                    .dstAccessMask = VK_ACCESS_MEMORY_READ_BIT | VK_ACCESS_MEMORY_WRITE_BIT,
                };
                upload_cmdbuf.PipelineBarrier(VK_PIPELINE_STAGE_TRANSFER_BIT,
                                              VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, WRITE_BARRIER);
                upload_cmdbuf.End();
                cmdbuf.End();

                if (on_submit) {
                    on_submit();
                }

                std::scoped_lock lock{submit_mutex};
                const VkResult result = master_semaphore->SubmitQueue(
                    cmdbuf, upload_cmdbuf, signal_semaphore, wait_semaphore, signal_value);
                if (checked) {
                    checked->result.store(result, std::memory_order_release);
                    if (!ordinary_errors) return; // Explicit checked callers observe Unknown.
                }
                switch (result) {
                case VK_SUCCESS:
                    break;
                case VK_ERROR_DEVICE_LOST:
                    device.ReportLoss();
                    [[fallthrough]];
                default:
                    vk::Check(result);
                    break;
                }
            } catch (const vk::Exception& error) {
                if (checked) checked->result.store(error.GetResult(), std::memory_order_release);
                if (ordinary_errors || !checked) throw;
            } catch (...) {
                if (checked) checked->result.store(VK_ERROR_UNKNOWN, std::memory_order_release);
                if (ordinary_errors || !checked) throw;
            }
        });
        chunk->MarkSubmit();
        DispatchWork();
        return signal_value;
    } catch (...) {
        if (checked) checked->result.store(VK_ERROR_UNKNOWN, std::memory_order_release);
        throw; // Host-side failure before queue acceptance is not indefinitely Pending.
    }
}

void Scheduler::AllocateNewContext() {
    // Enable counters once again. These are disabled when a command buffer is finished.
    if (query_cache) {
#if ANDROID
        if (Settings::IsGPULevelHigh()) {
            // This is problematic on Android, disable on GPU Normal and Low.
            query_cache->NotifySegment(true);
        }
#else
        if (Settings::IsGPULevelNormal()) {
            // Skip query cache operations for Low accuracy
            query_cache->NotifySegment(true);
        }
#endif
    }
}

void Scheduler::InvalidateState() {
    state.graphics_pipeline = nullptr;
    state.rescaling_defined = false;
    state_tracker.InvalidateCommandBufferState();
}

void Scheduler::EndPendingOperations() {
#if ANDROID
    if (Settings::IsGPULevelHigh()) {
        // This is problematic on Android, disable on GPU Normal and Low.
        // query_cache->DisableStreams();
    }
#else
    // query_cache->DisableStreams();
#endif
    if (Settings::IsGPULevelNormal()) {
        // Skip query cache operations for Low accuracy
        query_cache->NotifySegment(false);
    }
    EndRenderPass();
}

void Scheduler::EndRenderPass() {
    if (!state.renderpass) {
        return;
    }
    Record([num_images = num_renderpass_images, images = renderpass_images,
            ranges = renderpass_image_ranges](vk::CommandBuffer cmdbuf) {
        std::array<VkImageMemoryBarrier, 9> barriers;
        for (size_t i = 0; i < num_images; ++i) {
            barriers[i] = VkImageMemoryBarrier{
                .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER,
                .pNext = nullptr,
                .srcAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT |
                                 VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT,
                .dstAccessMask = VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT |
                                 VK_ACCESS_COLOR_ATTACHMENT_READ_BIT |
                                 VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT |
                                 VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_READ_BIT |
                                 VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT,
                .oldLayout = VK_IMAGE_LAYOUT_GENERAL,
                .newLayout = VK_IMAGE_LAYOUT_GENERAL,
                .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
                .image = images[i],
                .subresourceRange = ranges[i],
            };
        }
        cmdbuf.EndRenderPass();
        cmdbuf.PipelineBarrier(VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT |
                                   VK_PIPELINE_STAGE_LATE_FRAGMENT_TESTS_BIT |
                                   VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
                               VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, nullptr, nullptr,
                               vk::Span(barriers.data(), num_images));
    });
    state.renderpass = nullptr;
    num_renderpass_images = 0;
}

void Scheduler::AcquireNewChunk() {
    std::scoped_lock rl{reserve_mutex};

    if (chunk_reserve.empty()) {
        // If we don't have anything reserved, we need to make a new chunk.
        chunk = std::make_unique<CommandChunk>();
    } else {
        // Otherwise, we can just take from the reserve.
        chunk = std::move(chunk_reserve.back());
        chunk_reserve.pop_back();
    }
}

} // namespace Vulkan
