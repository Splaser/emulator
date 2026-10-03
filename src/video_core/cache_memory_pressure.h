// SPDX-FileCopyrightText: Copyright 2026 citron Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include <algorithm>

#include "common/common_types.h"

namespace VideoCommon {

struct CacheMemoryPressure {
    u64 usage;
    u64 expected;
    u64 critical;

    [[nodiscard]] bool IsHigh() const {
        return usage >= expected;
    }

    [[nodiscard]] bool IsCritical() const {
        return usage >= critical;
    }
};

// Cache ownership remains separate from heap usage, which includes other GPU resources.
// A shrinking driver budget must tighten the limits without increasing the startup limits.
[[nodiscard]] inline CacheMemoryPressure GetCacheMemoryPressure(u64 owned_bytes, u64 heap_usage,
                                                              u64 heap_budget, u64 expected,
                                                              u64 critical) {
    if (heap_budget != 0) {
        expected = std::min(expected, heap_budget - heap_budget / 4);
        critical = std::min(critical, heap_budget - heap_budget / 10);
    }
    return {std::max(owned_bytes, heap_usage), expected, critical};
}

} // namespace VideoCommon
