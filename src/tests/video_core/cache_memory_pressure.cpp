// SPDX-FileCopyrightText: Copyright 2026 citron Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <limits>

#include <catch2/catch_test_macros.hpp>

#include "common/literals.h"
#include "video_core/cache_memory_pressure.h"

using namespace Common::Literals;
using VideoCommon::GetCacheMemoryPressure;

TEST_CASE("Cache GC responds to heap pressure with small individual caches", "[video_core]") {
    // Textures and buffers can each be below their thresholds while their shared heap is full.
    const auto pressure = GetCacheMemoryPressure(3_GiB, 9_GiB, 10_GiB, 6_GiB, 8_GiB);
    REQUIRE(pressure.usage == 9_GiB);
    REQUIRE(pressure.IsHigh());
    REQUIRE(pressure.IsCritical());
}

TEST_CASE("Cache GC tightens its limits when the driver budget shrinks", "[video_core]") {
    const auto pressure = GetCacheMemoryPressure(2_GiB, 6_GiB, 6_GiB, 6_GiB, 8_GiB);
    REQUIRE(pressure.expected == 6_GiB - 6_GiB / 4);
    REQUIRE(pressure.critical == 6_GiB - 6_GiB / 10);
    REQUIRE(pressure.IsHigh());
    REQUIRE(pressure.IsCritical());

    const auto increased = GetCacheMemoryPressure(2_GiB, 3_GiB, 16_GiB, 6_GiB, 8_GiB);
    REQUIRE(increased.expected == 6_GiB);
    REQUIRE(increased.critical == 8_GiB);
    REQUIRE_FALSE(increased.IsHigh());
}

TEST_CASE("Cache GC retains owned-byte fallback and exact threshold boundaries", "[video_core]") {
    const auto below = GetCacheMemoryPressure(1_GiB, 0, 0, 2_GiB, 3_GiB);
    REQUIRE_FALSE(below.IsHigh());
    REQUIRE_FALSE(below.IsCritical());

    const auto high = GetCacheMemoryPressure(2_GiB, 0, 0, 2_GiB, 3_GiB);
    REQUIRE(high.IsHigh());
    REQUIRE_FALSE(high.IsCritical());

    // A delayed driver snapshot must not hide resources allocated since the snapshot.
    const auto critical = GetCacheMemoryPressure(3_GiB, 1_GiB, 0, 2_GiB, 3_GiB);
    REQUIRE(critical.IsCritical());
}

TEST_CASE("Cache GC budget arithmetic cannot wrap", "[video_core]") {
    constexpr u64 max = std::numeric_limits<u64>::max();
    const auto pressure = GetCacheMemoryPressure(0, max, max, max, max);
    REQUIRE(pressure.expected == max - max / 4);
    REQUIRE(pressure.critical == max - max / 10);
    REQUIRE(pressure.IsCritical());
}
