// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <algorithm>
#include <array>
#include <limits>
#include <memory>
#include <span>
#include "video_core/renderer_vulkan/vk_transfer_content.h"

namespace Vulkan {

// Immutable bounded ancestry, not admission, execution, synchronization or physical authority.
// Root command IDs always refer to ParentContent(), never the new copy submission's local graph.
class ReplicaCopyProvenance {
public:
    using Index = TransferContent::Index;
    using Offset = TransferContent::Offset;
    struct RootSpan {
        Offset offset{}, size{};
        Index fill{};
        Offset root_offset{};
        bool operator==(const RootSpan&) const = default;
    };
    static constexpr Index MaxHops = 4;
    static constexpr Index MaxRootSpans = TransferContent::MaxSpans;
    static std::optional<ReplicaCopyProvenance> Build(std::shared_ptr<const TransferContent> parent,
        Index source, Index destination, Offset source_offset, Offset destination_offset, Offset size,
        Offset destination_size, Index source_fill, Offset source_root, Index destination_fill, Offset destination_root,
        std::shared_ptr<const ReplicaCopyProvenance> source_copy = {}, std::span<const RootSpan> roots = {}) {
        if (!parent || source == destination || !size || (source_offset | destination_offset | size) % 4 ||
            size > std::numeric_limits<Offset>::max() - source_offset ||
            destination_offset >= destination_size || size > destination_size - destination_offset ||
            (source_copy && (source_copy->Depth() >= MaxHops || source_copy->ParentContent() != parent ||
                             source_copy->DestinationBuffer() != source)) ||
            !parent->HasRoot(destination, 0, destination_size, destination_fill, destination_root)) return {};
        const RootSpan single{source_offset, size, source_fill, source_root};
        if (roots.empty()) roots = {&single, 1};
        if (roots.size() > MaxRootSpans) return {};
        Offset cursor = source_offset;
        for (const auto& part : roots) {
            if (part.offset != cursor || !part.size || part.size > source_offset + size - cursor ||
                !(source_copy ? source_copy->HasRoot(part.offset, part.size, part.fill, part.root_offset)
                              : parent->HasRoot(source, part.offset, part.size, part.fill, part.root_offset))) return {};
            cursor += part.size;
        }
        if (cursor != source_offset + size) return {};
        return ReplicaCopyProvenance{std::move(parent), source, destination, source_offset,
            destination_offset, size, destination_size, std::move(source_copy), roots};
    }
    bool HasRoot(Offset offset, Offset size, Index fill, Offset root_offset) const noexcept {
        if (!size || offset >= destination_size || size > destination_size - offset ||
            size > std::numeric_limits<Offset>::max() - root_offset) return false;
        Offset covered{};
        const auto check = [&](Offset begin, Offset end, bool copied) {
            begin = std::max(begin, offset);
            end = std::min(end, offset + size);
            if (begin >= end) return true;
            const auto parent_offset = copied ? source_offset + begin - destination_offset : begin;
            if (!(copied && source_copy
                    ? source_copy->HasRoot(parent_offset, end - begin, fill, root_offset + begin - offset)
                    : parent->HasRoot(copied ? source : destination, parent_offset, end - begin,
                                      fill, root_offset + begin - offset))) return false;
            covered += end - begin;
            return true;
        };
        return check(0, destination_offset, false) &&
            check(destination_offset, destination_offset + length, true) &&
            check(destination_offset + length, destination_size, false) && covered == size;
    }
    const std::shared_ptr<const TransferContent>& ParentContent() const noexcept { return parent; }
    const std::shared_ptr<const ReplicaCopyProvenance>& SourceCopy() const noexcept { return source_copy; }
    std::span<const RootSpan> SourceRoots() const noexcept { return {source_roots.data(), root_count}; }
    Index Depth() const noexcept { return depth; }
    Index SourceBuffer() const noexcept { return source; }
    Index DestinationBuffer() const noexcept { return destination; }
    bool MatchesCopy(Offset source_begin, Offset destination_begin, Offset size) const noexcept {
        return source_begin == source_offset && destination_begin == destination_offset && size == length;
    }
private:
    ReplicaCopyProvenance(std::shared_ptr<const TransferContent> parent_, Index source_, Index destination_,
        Offset source_offset_, Offset destination_offset_, Offset length_, Offset destination_size_,
        std::shared_ptr<const ReplicaCopyProvenance> source_copy_, std::span<const RootSpan> roots_)
        : parent{std::move(parent_)}, source{source_}, destination{destination_}, source_offset{source_offset_},
          destination_offset{destination_offset_}, length{length_}, destination_size{destination_size_},
          source_copy{std::move(source_copy_)}, depth{source_copy ? source_copy->Depth() + 1 : 1},
          root_count{static_cast<Index>(roots_.size())} {
        std::copy(roots_.begin(), roots_.end(), source_roots.begin());
    }
    std::shared_ptr<const TransferContent> parent;
    Index source, destination;
    Offset source_offset, destination_offset, length, destination_size;
    std::shared_ptr<const ReplicaCopyProvenance> source_copy;
    Index depth;
    std::array<RootSpan, MaxRootSpans> source_roots{};
    Index root_count{};
};
} // namespace Vulkan
