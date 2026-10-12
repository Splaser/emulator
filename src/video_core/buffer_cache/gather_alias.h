// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <algorithm>
#include <stdexcept>
#include <unordered_map>
#include <vector>
#include "common/common_types.h"

namespace VideoCommon {

class UnsupportedGatherMapping final : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct GatherAliasRange {
    u64 gpu_addr;
    u32 size;
    bool scratch;
    bool operator==(const GatherAliasRange&) const = default;
};

// Inputs fit within one physical page. Different GPU positions cannot represent
// the same byte in a dense scratch allocation. Identical GPU positions remain
// legal: PrepareGatherBindings gives overlapping views one shared allocation.
class GatherAliasValidator {
public:
    explicit GatherAliasValidator(u64 page_size_) : page_size{page_size_} {}

    void Add(u64 physical, u64 gpu, u64 size, bool scratch) {
        auto& page = pages[physical / page_size];
        for (const Segment& other : page) {
            const u64 begin = std::max(physical, other.physical);
            const u64 end = std::min(physical + size, other.physical + other.size);
            if ((scratch || other.scratch) && begin < end &&
                gpu + (begin - physical) != other.gpu + (begin - other.physical)) {
                throw UnsupportedGatherMapping(
                    "Split GPU buffer has overlapping physical aliases; dense scratch cannot "
                    "preserve shader alias semantics");
            }
        }
        page.push_back({physical, gpu, size, scratch});
    }

private:
    struct Segment {
        u64 physical;
        u64 gpu;
        u64 size;
        bool scratch;
    };
    u64 page_size;
    std::unordered_map<u64, std::vector<Segment>> pages;
};

} // namespace VideoCommon
