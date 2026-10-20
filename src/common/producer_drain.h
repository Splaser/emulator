// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <atomic>
#include <memory>
#include <optional>
#include <utility>
#include "common/common_types.h"

namespace Common {

// Owned execution-entry closure, NOT an alias inventory or GPU admission lease.
// No waits, callbacks, renderer work or signal handling in this primitive.
class ProducerDrain {
    static_assert(std::atomic<u64>::is_always_lock_free);
    static constexpr u64 Closed = u64{1} << 63;
    static constexpr u64 Unknown = u64{1} << 62;
    static constexpr u64 Count = 0xffff;
    struct State { std::atomic<u64> value{}; };
    std::shared_ptr<State> state{std::make_shared<State>()};
public:
    enum class Result { Pending, DrainedSubset, Unknown };
    enum class EntryAttempt { Admitted, Closed, Capacity, Contended };
    class Entry {
        friend class ProducerDrain;
        std::shared_ptr<State> state;
        explicit Entry(std::shared_ptr<State> s):state{std::move(s)}{}
    public:
        Entry(Entry&& other) noexcept:state{std::move(other.state)}{}
        Entry(const Entry&)=delete;
        ~Entry(){if(state) state->value.fetch_sub(1,std::memory_order_release);}
    };
    class Closure {
        friend class ProducerDrain;
        std::shared_ptr<State> state;
        u32 remaining;
        bool released{};
        explicit Closure(std::shared_ptr<State> s,u32 budget):state{std::move(s)},remaining{budget}{}
    public:
        Closure(Closure&& other) noexcept:state{std::move(other.state)},remaining{other.remaining},released{other.released}{}
        Closure(const Closure&)=delete;
        ~Closure(){if(state && !released) Quarantine();}
        // Budget counts polls, not a promise to interrupt a stuck backend.
        Result Poll() noexcept {
            if(!state) return Result::Unknown;
            const auto value=state->value.load(std::memory_order_acquire);
            if(released || (value & Unknown)) return Result::Unknown;
            if(!(value & Count)) return Result::DrainedSubset;
            if(!remaining || !--remaining){Quarantine();return Result::Unknown;}
            return Result::Pending;
        }
        // This prototype cannot record GPU work or certify completion. Cancellation
        // resumes only a known, fully drained subset, never an uncertain operation.
        bool ResumeNoEffects() noexcept {
            if(!state) return false;
            if(released) return false;
            u64 expected=Closed;
            if(!state->value.compare_exchange_strong(expected,0,std::memory_order_acq_rel)) return false;
            released=true;return true;
        }
        void Quarantine() noexcept {if(state && !released) state->value.fetch_or(Closed|Unknown,std::memory_order_acq_rel);}
    };
    ProducerDrain()=default;
    ProducerDrain(const ProducerDrain&)=delete;
    ~ProducerDrain(){Seal();}
    void Seal() const noexcept {state->value.fetch_or(Closed|Unknown,std::memory_order_acq_rel);}
    std::optional<Entry> TryEnter() const noexcept {
        return TryEnterImpl<false>(nullptr);
    }
    // Explicit diagnostics overload. The ordinary overload instantiates no
    // observer stores, timing, registry, lock, allocation or additional wait.
    std::optional<Entry> TryEnter(EntryAttempt& attempt) const noexcept {
        return TryEnterImpl<true>(&attempt);
    }
private:
    template <bool Diagnose>
    std::optional<Entry> TryEnterImpl(EntryAttempt* attempt) const noexcept {
        auto value=state->value.load(std::memory_order_acquire);
        if((value & (Closed|Unknown)) || (value & Count)==Count) {
            if constexpr (Diagnose) *attempt = (value & (Closed|Unknown)) ?
                EntryAttempt::Closed : EntryAttempt::Capacity;
            return {};
        }
        // One attempt: contention refuses entry; no CAS retry/spin/wait.
        if(!state->value.compare_exchange_strong(value,value+1,std::memory_order_acq_rel)) {
            if constexpr (Diagnose) *attempt = EntryAttempt::Contended;
            return {};
        }
        if constexpr (Diagnose) *attempt = EntryAttempt::Admitted;
        return Entry{state};
    }
public:
    std::optional<Closure> TryClose(u32 poll_budget=64) const noexcept {
        if(!poll_budget || poll_budget>4096) return {};
        const auto old=state->value.fetch_or(Closed,std::memory_order_acq_rel);
        if(old & (Closed|Unknown)) return {};
        return Closure{state,poll_budget};
    }
    // Even a drained managed subset cannot establish writable-alias coverage.
    static constexpr Result GuestBackingAdmission() noexcept {return Result::Unknown;}
};
} // namespace Common
