// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <atomic>
#include <memory>
#include <mutex>
#include "common/common_types.h"

namespace Common {

// Retained by mapping stamps, not by a global registry. This state contains no
// page tables or owner pointers; validation remains safe after owner destruction.
struct MappingEpoch {
    mutable std::mutex mutex;
    std::atomic<u64> generation{};
    std::atomic<bool> alive{true};
};

class MappingLifetime {
public:
    MappingLifetime() : state{std::make_shared<MappingEpoch>()} {}
    MappingLifetime(const MappingLifetime&) = delete;
    MappingLifetime& operator=(const MappingLifetime&) = delete;
    ~MappingLifetime() {
        Invalidate();
    }

    void Invalidate() {
        std::scoped_lock lock{state->mutex};
        state->alive.store(false, std::memory_order_release);
    }
    std::shared_ptr<MappingEpoch> Get() const {
        return state;
    }

private:
    std::shared_ptr<MappingEpoch> state;
};

} // namespace Common
