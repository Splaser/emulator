// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <array>
#include <chrono>
#include <optional>
#include <vector>
#include "video_core/physical_memory.h"

namespace VideoCommon {

// Access intent and historical geometry only. Never a data owner, resource lease,
// dispatch permission, or reason to change synchronization/fallback selection.
enum class ShadowKind : size_t { Buffer, Scratch, Texel, Texture, Count };
struct ShadowCoverage {
    u64 observations{}, write_intents{}, registered_writes{}, unresolved{};
    u64 bytes{}, max_range{}, registered_segments{}, split_observations{};
    std::array<u64, 8> size_buckets{};
};
struct ShadowCounters {
    std::array<ShadowCoverage, static_cast<size_t>(ShadowKind::Count)> coverage{};
    u64 dispatches{}, queries{}, query_ns{}, max_dispatch_query_ns{}, validation_ns{};
    u64 observer_ns{}, max_dispatch_observer_ns{};
    u64 cache_hits{}, cache_invalidations{}, snapshot_invalidations{}, holes{}, budget_drops{};
    u64 historical_aliases{}, different_daddr_aliases{}, different_manager_aliases{};
    u64 provenance_mismatches{}, comparison_drops{}, errors{}, evictions{};
    u64 outside_dispatch_queries{}, max_dispatch_queries{};
};

// GPU-thread confined. Bounded metadata; contains no backing allocation, driver
// handle, MemoryManager pointer or producer lifetime reference. Shared stamps only
// retain inert lifetime tokens. Sampling loss is explicit in counters.
class PhysicalShadow {
public:
    static constexpr size_t Capacity = 128;
    static constexpr u64 MaxRange = 64ULL << 20;
    static constexpr size_t MaxSegments = 256;

    void BeginDispatch() noexcept {
        in_dispatch = true;
        dispatch_query_ns = dispatch_queries = 0;
        dispatch_observer_ns = 0;
    }
    void EndDispatch() noexcept {
        if (!in_dispatch) {
            return;
        }
        ++counters.dispatches;
        counters.max_dispatch_query_ns =
            std::max(counters.max_dispatch_query_ns, dispatch_query_ns);
        counters.max_dispatch_queries = std::max(counters.max_dispatch_queries, dispatch_queries);
        counters.max_dispatch_observer_ns =
            std::max(counters.max_dispatch_observer_ns, dispatch_observer_ns);
        in_dispatch = false;
    }
    const ShadowCounters& Counters() const noexcept {
        return counters;
    }

    template <class Memory>
    void Observe(Memory& memory, GPUVAddr address, u64 size, ShadowKind kind, bool writable,
                 std::optional<DAddr> expected_device = {}) noexcept {
        struct Measure {
            PhysicalShadow& shadow;
            Clock::time_point start{Clock::now()};
            ~Measure() {
                const u64 elapsed = NsSince(start);
                shadow.counters.observer_ns += elapsed;
                if (shadow.in_dispatch) {
                    shadow.dispatch_observer_ns += elapsed;
                }
            }
        } measure{*this};
        auto& coverage = counters.coverage[static_cast<size_t>(kind)];
        ++coverage.observations;
        coverage.write_intents += writable;
        coverage.bytes += size;
        coverage.max_range = std::max(coverage.max_range, size);
        constexpr std::array<u64, 7> limits{64, 1024, 16384, 65536, 262144, 1048576, 16777216};
        ++coverage.size_buckets[std::ranges::upper_bound(limits, size) - limits.begin()];
        try {
            if (!address || !size || size > MaxRange) {
                ++counters.budget_drops;
                ++coverage.unresolved;
                return;
            }
            Entry* entry = nullptr;
            std::optional<Entry>* cache_slot = nullptr;
            for (auto& candidate : entries) {
                if (candidate && candidate->manager == memory.GetID() &&
                    candidate->address == address && candidate->size == size &&
                    candidate->kind == kind) {
                    entry = &*candidate;
                    cache_slot = &candidate;
                    break;
                }
            }
            if (entry) {
                const auto start = Clock::now();
                const bool current = Tegra::ValidatePhysicalSnapshot(entry->physical);
                counters.validation_ns += NsSince(start);
                if (current) {
                    ++counters.cache_hits;
                } else {
                    ++counters.cache_invalidations;
                    entry = nullptr;
                }
            }
            if (!entry) {
                auto physical = ResolveTimed(memory, address, size);
                if (physical.status != Tegra::PhysicalResolveStatus::Success ||
                    std::ranges::any_of(physical.segments,
                                        [](const auto& s) { return !s.physical; })) {
                    ++counters.holes;
                    ++coverage.unresolved;
                    return;
                }
                if (physical.segments.size() > MaxSegments) {
                    ++counters.budget_drops;
                    ++coverage.unresolved;
                    return;
                }
                Entry next{memory.GetID(), address, size, std::move(physical), {}, kind};
                // Capture DAddr provenance under the same pair of mapping locks,
                // only if the original physical stamp still matches. This avoids
                // assembling a physical/DAddr pair that never existed together.
                const auto validate_start = Clock::now();
                const bool captured = CaptureDeviceRanges(memory, next);
                counters.validation_ns += NsSince(validate_start);
                if (!captured) {
                    ++counters.snapshot_invalidations;
                    ++coverage.unresolved;
                    return;
                }
                if (next.device.size() > MaxSegments) {
                    ++counters.budget_drops;
                    ++coverage.unresolved;
                    return;
                }
                // Replace stale geometry in place. Retaining an older same-key
                // entry first in the array would turn every lookup into a miss.
                auto& slot = cache_slot ? *cache_slot : entries[cursor++ % Capacity];
                counters.evictions += !cache_slot && slot.has_value();
                slot = std::move(next);
                entry = &*slot;
            }
            // A cached texture/texel resource is identified by its actual DAddr
            // span. Its old GPU VA may now name different storage. Don't register
            // that unrelated translation as the resource's physical identity.
            if (expected_device &&
                (entry->device.size() != 1 || entry->device.front().address != *expected_device)) {
                ++counters.provenance_mismatches;
                ++coverage.unresolved;
                entry->registered = false;
                return;
            }
            coverage.registered_writes += writable;
            coverage.registered_segments += entry->physical.segments.size();
            coverage.split_observations += entry->physical.segments.size() > 1;
            entry->registered = true;
            Compare(*entry);
        } catch (...) {
            // Diagnostics must not reject work or alter emulation on OOM/error.
            ++counters.errors;
            ++coverage.unresolved;
        }
    }

private:
    using Clock = std::chrono::steady_clock;
    struct DeviceRange {
        u64 logical{}, address{}, length{};
    };
    struct Entry {
        size_t manager{};
        u64 address{}, size{};
        Tegra::PhysicalResolveResult physical;
        std::vector<DeviceRange> device;
        ShadowKind kind{};
        bool registered{};
    };
    static u64 NsSince(Clock::time_point start) {
        return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - start).count();
    }
    template <class Memory>
    Tegra::PhysicalResolveResult ResolveTimed(Memory& memory, u64 address, u64 size) {
        const auto start = Clock::now();
        ++counters.queries;
        const auto record = [&] {
            const u64 elapsed = NsSince(start);
            counters.query_ns += elapsed;
            if (in_dispatch) {
                dispatch_query_ns += elapsed;
                ++dispatch_queries;
            } else {
                ++counters.outside_dispatch_queries;
            }
        };
        try {
            auto result = memory.ResolvePhysicalRanges(address, size);
            record();
            return result;
        } catch (...) {
            record();
            throw;
        }
    }
    template <class Memory>
    static bool CaptureDeviceRanges(Memory& memory, Entry& entry) {
        const auto& stamp = entry.physical.stamp;
        if (!stamp.gpu_address_space || !stamp.device_address_space ||
            stamp.gpu_address_space == stamp.device_address_space) {
            return false;
        }
        std::unique_lock gpu_lock{stamp.gpu_address_space->mutex};
        std::unique_lock device_lock{stamp.device_address_space->mutex};
        if (!Tegra::Detail::MappingStampCurrentLocked(stamp)) {
            return false;
        }
        // GMMU's smallest supported page is 4 KiB; splitting here is also safe
        // for big pages. No GetPointer, guest read, backing creation or GPU call.
        constexpr u64 page = 4096;
        for (u64 offset = 0; offset < entry.size;) {
            const auto device = memory.GpuToCpuAddress(entry.address + offset);
            if (!device) {
                return false;
            }
            const u64 length =
                std::min(entry.size - offset, page - (entry.address + offset) % page);
            if (!entry.device.empty() &&
                entry.device.back().address + entry.device.back().length == *device) {
                entry.device.back().length += length;
            } else {
                entry.device.push_back({offset, *device, length});
                if (entry.device.size() > MaxSegments) {
                    return true; // explicit caller budget drop, never a successful registration
                }
            }
            offset += length;
        }
        return true;
    }
    static u64 DeviceAt(const Entry& entry, u64 logical) {
        for (const auto& range : entry.device) {
            if (logical >= range.logical && logical - range.logical < range.length) {
                return range.address + logical - range.logical;
            }
        }
        return 0;
    }
    void Compare(const Entry& current) {
        size_t comparisons = 0;
        for (const auto& old : entries) {
            if (!old || !old->registered || &*old == &current) {
                continue;
            }
            bool alias = false, different_device = false;
            for (const auto& a : current.physical.segments) {
                for (const auto& b : old->physical.segments) {
                    if (++comparisons > 4096) {
                        ++counters.comparison_drops;
                        return;
                    }
                    if (Tegra::PhysicalRangesOverlap(*a.physical, *b.physical)) {
                        alias = true;
                        u64 physical =
                            std::max(a.physical->physical_offset, b.physical->physical_offset);
                        const u64 end = std::min(a.physical->physical_offset + a.length,
                                                 b.physical->physical_offset + b.length);
                        while (physical < end && !different_device) {
                            if (++comparisons > 4096) {
                                ++counters.comparison_drops;
                                return;
                            }
                            const u64 logical_a =
                                a.logical_offset + physical - a.physical->physical_offset;
                            const u64 logical_b =
                                b.logical_offset + physical - b.physical->physical_offset;
                            different_device |=
                                DeviceAt(current, logical_a) != DeviceAt(*old, logical_b);
                            // Device ranges change only at 4 KiB guest page boundaries.
                            physical += std::min({end - physical,
                                                  4096 - (current.address + logical_a) % 4096,
                                                  4096 - (old->address + logical_b) % 4096});
                        }
                    }
                }
            }
            counters.historical_aliases += alias;
            counters.different_daddr_aliases += alias && different_device;
            counters.different_manager_aliases +=
                alias &&
                current.physical.stamp.gpu_address_space != old->physical.stamp.gpu_address_space;
        }
    }
    std::array<std::optional<Entry>, Capacity> entries;
    size_t cursor{};
    bool in_dispatch{};
    u64 dispatch_query_ns{}, dispatch_queries{}, dispatch_observer_ns{};
    ShadowCounters counters;
};

} // namespace VideoCommon
