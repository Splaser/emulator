// SPDX-FileCopyrightText: Copyright 2026 Citron Emulator Project
// SPDX-License-Identifier: GPL-3.0-or-later

#include <array>
#include <atomic>

#include "common/logging.h"
#include "core/hle/service/nvdrv/nvdata.h"

namespace Service::Nvidia {
namespace {

constexpr size_t TraceCapacity = 32;
constexpr size_t TraceDumpCount = 16;

struct NvFenceTraceEntry {
    std::atomic<u64> sequence{};
    std::atomic<s32> id{};
    std::atomic<u32> value{};
    std::atomic<NvFenceTraceSource> source{};
};

std::array<NvFenceTraceEntry, TraceCapacity> trace_entries{};
std::atomic<u64> trace_sequence{};

const char* NameOf(NvFenceTraceSource source) {
    switch (source) {
    case NvFenceTraceSource::AllocGpfifo:
        return "alloc_gpfifo_out";
    case NvFenceTraceSource::SubmitGpfifo:
        return "submit_gpfifo_out";
    case NvFenceTraceSource::EventWait:
        return "event_wait_in";
    case NvFenceTraceSource::BufferQueueDequeue:
        return "buffer_queue_dequeue_out";
    }
    return "unknown";
}

} // namespace

void RecordNvFenceTrace(NvFenceTraceSource source, NvFence fence) {
    const u64 sequence = trace_sequence.fetch_add(1, std::memory_order_relaxed) + 1;
    auto& entry = trace_entries[sequence % TraceCapacity];
    entry.sequence.store(0, std::memory_order_relaxed);
    entry.id.store(fence.id, std::memory_order_relaxed);
    entry.value.store(fence.value, std::memory_order_relaxed);
    entry.source.store(source, std::memory_order_relaxed);
    entry.sequence.store(sequence, std::memory_order_release);
}

void LogRecentNvFenceTrace() {
    const u64 end = trace_sequence.load(std::memory_order_acquire);
    const u64 begin = end > TraceDumpCount ? end - TraceDumpCount + 1 : 1;
    LOG_CRITICAL(Service_NVDRV, "Recent NvFence trace: begin={}, end={}", begin, end);
    for (u64 sequence = begin; sequence <= end; ++sequence) {
        const auto& entry = trace_entries[sequence % TraceCapacity];
        if (entry.sequence.load(std::memory_order_acquire) != sequence) {
            continue;
        }
        const s32 id = entry.id.load(std::memory_order_relaxed);
        const u32 value = entry.value.load(std::memory_order_relaxed);
        const auto source = entry.source.load(std::memory_order_relaxed);
        if (entry.sequence.load(std::memory_order_acquire) != sequence) {
            continue;
        }
        LOG_CRITICAL(Service_NVDRV,
                     "NvFence trace #{}: source={}, id={}, value={:#x}, packed={:#018x}",
                     sequence, NameOf(source), id, value,
                     (static_cast<u64>(value) << 32) | static_cast<u32>(id));
    }
}

} // namespace Service::Nvidia
