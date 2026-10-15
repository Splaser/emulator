// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <optional>
#include <span>
#include <vector>

#include "common/host_memory.h"
#include "video_core/physical_memory.h"

namespace Tegra {

struct PinnedPhysicalSegment {
    u64 logical_offset;
    Common::PinnedPhysicalMemory storage;
};

/// Immutable logical ordering and real physical storage ownership. No data admission or GPU
/// representation ownership is implied. Callers must protect the HostMemory object's lifetime
/// throughout Build, and call outside cache/PTE locks: cold materialization can allocate.
class PhysicalAccessPlan {
public:
    [[nodiscard]] std::span<const PinnedPhysicalSegment> Segments() const { return segments; }
    [[nodiscard]] u64 Size() const { return size; }
    [[nodiscard]] u64 BackingGeneration() const { return generation; }

    [[nodiscard]] static std::optional<PhysicalAccessPlan> Build(
        const PhysicalResolveResult& snapshot, const Common::HostMemory& backing) {
        if (snapshot.stamp.backing != backing.BackingEpoch() ||
            snapshot.stamp.backing_size != backing.backing_size) {
            return std::nullopt;
        }
        return BuildWithPins(snapshot, [&backing](u64 offset, u64 length) {
            return backing.PinPhysicalRange(offset, length);
        });
    }

    /// The provider must return actual storage pins for the snapshot's backing. It runs outside
    /// mapping locks; no provider result grants data admission or representation ownership.
    template <typename Pin>
    [[nodiscard]] static std::optional<PhysicalAccessPlan> BuildWithPins(
        const PhysicalResolveResult& snapshot, Pin&& pin_range) {
        const auto& stamp = snapshot.stamp;
        if (snapshot.status != PhysicalResolveStatus::Success || !snapshot.size ||
            !stamp.gpu_address_space || !stamp.device_address_space ||
            stamp.gpu_address_space == stamp.device_address_space || !stamp.backing) {
            return std::nullopt;
        }
        // Validate all geometry before a cold range can be materialized.
        u64 covered = 0;
        for (const auto& segment : snapshot.segments) {
            if (segment.hole != PhysicalHole::None || !segment.physical || !segment.length ||
                segment.logical_offset != covered || covered > snapshot.size ||
                segment.length > snapshot.size - covered ||
                segment.physical->length != segment.length ||
                segment.physical->backing_epoch != stamp.backing->generation ||
                segment.physical->physical_offset >= stamp.backing_size ||
                segment.length > stamp.backing_size - segment.physical->physical_offset) {
                return std::nullopt;
            }
            covered += segment.length;
        }
        if (covered != snapshot.size) {
            return std::nullopt;
        }
        PhysicalAccessPlan plan;
        plan.segments.reserve(snapshot.segments.size());
        for (const auto& segment : snapshot.segments) {
            auto pin = pin_range(segment.physical->physical_offset, segment.length);
            if (!pin || !pin->OwnerAlive() || pin->Epoch() != stamp.backing ||
                pin->PhysicalOffset() != segment.physical->physical_offset ||
                pin->Bytes().size() != segment.length) {
                return std::nullopt;
            }
            plan.segments.push_back({segment.logical_offset, std::move(*pin)});
        }
        // No allocation, materialization or GPU wait under mapping locks. On rejection the
        // locks retire before plan and its resource owners; no owner destructor reentry here.
        const auto gpu_lock = std::unique_lock{stamp.gpu_address_space->mutex};
        const auto device_lock = std::unique_lock{stamp.device_address_space->mutex};
        if (!Detail::MappingStampCurrentLocked(stamp)) {
            return std::nullopt;
        }
        plan.size = snapshot.size;
        plan.generation = stamp.backing->generation;
        return plan;
    }

private:
    PhysicalAccessPlan() = default;
    std::vector<PinnedPhysicalSegment> segments;
    u64 size{}, generation{};
};

} // namespace Tegra
