// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <memory>
#include <optional>
#include <utility>

#include "video_core/vulkan_common/vulkan_wrapper.h"

namespace Vulkan {

class Buffer;
class StagedBufferPin;

/// Owns the actual VMA buffer/allocation used by staged DMA copies. This does not own the
/// renderer's VkDevice/VMA allocator: callers must release all pins before those domains retire.
class StagedBufferPayload {
public:
    StagedBufferPayload(vk::Buffer resource, u64 size_bytes)
        : buffer{std::move(resource)}, size{size_bytes} {}

private:
    friend class Buffer;
    friend class StagedBufferPin;
    vk::Buffer buffer;
    const u64 size;
};

/// Immutable byte interval and real staged-buffer ownership. Not cache membership, physical
/// footprint proof, content preservation, admission or device completion. GPU/cache-thread only
/// during acquisition; no cache lock is retained. Direct/imported representations are excluded.
class StagedBufferPin {
public:
    [[nodiscard]] VkBuffer Handle() const noexcept {
        return payload ? *payload->buffer : VK_NULL_HANDLE;
    }
    [[nodiscard]] u64 Offset() const noexcept { return offset; }
    [[nodiscard]] u64 Size() const noexcept { return size; }
    [[nodiscard]] const void* Identity() const noexcept { return payload.get(); }

    [[nodiscard]] static std::optional<StagedBufferPin> Build(
        const std::shared_ptr<StagedBufferPayload>& owner, u64 offset_bytes, u64 size_bytes) {
        if (!owner || !owner->buffer || !size_bytes || offset_bytes >= owner->size ||
            size_bytes > owner->size - offset_bytes) {
            return std::nullopt;
        }
        return StagedBufferPin{owner, offset_bytes, size_bytes};
    }

private:
    StagedBufferPin(std::shared_ptr<const StagedBufferPayload> owner, u64 offset_, u64 size_)
        : payload{std::move(owner)}, offset{offset_}, size{size_} {}
    std::shared_ptr<const StagedBufferPayload> payload;
    u64 offset, size;
};

} // namespace Vulkan
