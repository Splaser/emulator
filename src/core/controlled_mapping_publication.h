// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <memory>
#include <mutex>
#include <optional>
#include <shared_mutex>
#include <stdexcept>
#include <thread>
#include <utility>

#include "common/producer_drain.h"

namespace Core::Memory {

// Constructor-only enrollment of one Memory's outer mapping/publication entries.
// Not an alias census, PageTable-wide freeze, producer lease or GPU capability.
class ControlledMappingPublication {
    struct State {
        Common::ProducerDrain entries;
        std::shared_mutex lifetime;
        bool retired{}; // Protected by lifetime, including initial entry validation.
    };
    std::shared_ptr<State> state;

public:
    class Refused : public std::runtime_error {
    public:
        using std::runtime_error::runtime_error;
    };
    class Teardown {
        friend class ControlledMappingPublication;
        const ControlledMappingPublication* owner{};
        std::shared_ptr<State> state;
        std::unique_lock<std::shared_mutex> lifetime;
        std::thread::id thread;
        Teardown(const ControlledMappingPublication* owner_, std::shared_ptr<State> state_)
            : owner{owner_}, state{std::move(state_)},
              lifetime{state ? std::unique_lock{state->lifetime}
                             : std::unique_lock<std::shared_mutex>{}},
              thread{std::this_thread::get_id()} {
            if (state) state->retired = true;
        }
    public:
        Teardown(Teardown&& other) noexcept
            : owner{std::exchange(other.owner, nullptr)}, state{std::move(other.state)},
              lifetime{std::move(other.lifetime)}, thread{other.thread} {}
        Teardown(const Teardown&) = delete;
        ~Teardown() = default;
    };
    class Entry {
        friend class ControlledMappingPublication;
        // Release the lifetime lock before the counted entry and retained state.
        std::shared_ptr<State> state;
        std::optional<Common::ProducerDrain::Entry> counted;
        std::shared_lock<std::shared_mutex> lifetime;
        bool finished{};
        Entry(std::shared_ptr<State> state_, Common::ProducerDrain::Entry counted_,
              std::shared_lock<std::shared_mutex> lifetime_)
            : state{std::move(state_)}, counted{std::move(counted_)},
              lifetime{std::move(lifetime_)} {}
    public:
        Entry() = default; // Ordinary Memory: no allocation, counter or mutex.
        Entry(Entry&&) = default;
        Entry(const Entry&) = delete;
        ~Entry() { if (state && !finished) state->entries.Seal(); }
        // Any unwinding after entry has an unknown publication disposition.
        void Finish() noexcept { finished = true; }
    };

    explicit ControlledMappingPublication(bool enrolled = false)
        : state{enrolled ? std::make_shared<State>() : nullptr} {}
    ControlledMappingPublication(ControlledMappingPublication&&) = default;
    ControlledMappingPublication& operator=(ControlledMappingPublication&& other) {
        if (this != &other) { Retire(); state = std::move(other.state); }
        return *this;
    }
    ControlledMappingPublication(const ControlledMappingPublication&) = delete;
    ~ControlledMappingPublication() { Retire(); }

    // Call before touching Impl/context/PTE/HostMemory, retain through the last publication.
    // A refusal is an exception BEFORE effects; never continue the legacy mutator.
    [[nodiscard]] Entry Begin() const {
        if (!state) return {};
        auto counted = state->entries.TryEnter();
        if (!counted) throw Refused("controlled mapping publication closed");
        std::shared_lock lifetime{state->lifetime, std::try_to_lock};
        if (!lifetime.owns_lock() || state->retired)
            throw Refused("controlled mapping publication retired or contended");
        return Entry{state, std::move(*counted), std::move(lifetime)};
    }
    [[nodiscard]] auto TryClose(u32 poll_budget = 64) const {
        return state ? state->entries.TryClose(poll_budget)
                     : std::optional<Common::ProducerDrain::Closure>{};
    }
    // Owner-thread cleanup only, outside other locks. Normal admission stays sealed.
    [[nodiscard]] Teardown BeginTeardown() const {
        if (state) state->entries.Seal();
        return Teardown{this, state};
    }
    void ValidateTeardown(const Teardown& entry) const {
        if (entry.owner != this || entry.thread != std::this_thread::get_id() ||
            entry.state != state || (state && !entry.lifetime.owns_lock())) {
            throw Refused("invalid mapping teardown owner");
        }
    }
    void ValidateTeardown(const Teardown* entry) const {
        if (entry) ValidateTeardown(*entry);
        else if (state) throw Refused("controlled table finalization requires owner teardown");
    }
    // Lifecycle join only. Never call while holding context/PTE/HostMemory locks
    // or from an entered publication. No GPU handoff, wait or callbacks here.
    void Retire() const {
        if (!state) return;
        state->entries.Seal();
        std::unique_lock lifetime{state->lifetime};
        state->retired = true;
    }
    static constexpr auto GuestBackingAdmission() {
        return Common::ProducerDrain::Result::Unknown;
    }
};
} // namespace Core::Memory
