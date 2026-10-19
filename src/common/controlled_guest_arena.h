// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <array>
#include <atomic>
#include <memory>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <utility>
#include "common/host_memory.h"
#include "common/producer_drain.h"

namespace Common {
struct ControlledGuestArenaTestAccess;

// A fresh, fixed CPU-only backing cohort. No adoption, raw view, fd, callback,
// PageTable, renderer or device export. This is NOT an ordinary guest capability.
class ControlledGuestArena {
    friend struct ControlledGuestArenaTestAccess;
    struct State {
        HostMemory backing{4096 * 8, 4096 * 4096, {}, 0, false, false, {}, true};
        ProducerDrain admission;
        std::mutex registry_mutex, bytes_mutex;
        size_t registered{}; // Bounded registration only; never used to prove drainage.
        std::array<std::atomic<bool>, 8> owners{}; // Stable slots; never reused.
        State() {
            backing.Map(0, 0, 4096, MemoryPermission::ReadWrite, false);
            backing.Map(4096, 0, 4096, MemoryPermission::ReadWrite, false);
            auto check = backing.TryFreezeMappingEntries();
            if (!check || !check->CancelNoEffects())
                throw std::runtime_error("controlled arena mapping unsupported");
        }
    };
    std::shared_ptr<State> state{std::make_shared<State>()};

    // Entry is acquired BEFORE resolution and released AFTER the access/lock.
    // A paused operation owns backing independently of Owner and arena handles.
    class Operation {
        friend class ControlledGuestArena;
        friend struct ControlledGuestArenaTestAccess;
        std::shared_ptr<State> state;
        ProducerDrain::Entry entry;
        std::unique_lock<std::mutex> bytes_lock;
        u8* pointer{};
        bool completed{};
        Operation(std::shared_ptr<State> s, ProducerDrain::Entry e, size_t offset)
            : state{std::move(s)}, entry{std::move(e)},
              bytes_lock{state->bytes_mutex, std::try_to_lock} {
            if (bytes_lock.owns_lock()) pointer = state->backing.VirtualBasePointer() + offset;
        }
    public:
        Operation(Operation&& other) noexcept
            : state{std::move(other.state)}, entry{std::move(other.entry)},
              bytes_lock{std::move(other.bytes_lock)}, pointer{other.pointer},
              completed{other.completed} {}
        Operation(const Operation&) = delete;
        ~Operation() { if (state && !completed) state->admission.Seal(); }
        bool Store(u8 value) noexcept {
            if (!pointer || completed) return false;
            *pointer = value;
            completed = true;
            return true;
        }
        std::optional<u8> Load() noexcept {
            if (!pointer || completed) return {};
            const u8 value = *pointer;
            completed = true;
            return value;
        }
    };
    static std::optional<Operation> Begin(const std::shared_ptr<State>& s, size_t offset) {
        if (!s) return {};
        if (offset >= 8192) { s->admission.Seal(); return {}; }
        auto entry = s->admission.TryEnter();
        if (!entry) return {};
        try { return Operation{s, std::move(*entry), offset}; }
        catch (...) { s->admission.Seal(); throw; }
    }
public:
    static constexpr size_t OwnerCapacity = 8;
    using Result = ProducerDrain::Result;
    class Owner {
        friend class ControlledGuestArena;
        friend struct ControlledGuestArenaTestAccess;
        std::shared_ptr<State> state;
        size_t slot;
        Owner(std::shared_ptr<State> s, size_t index) : state{std::move(s)}, slot{index} {}
    public:
        Owner(Owner&& other) noexcept : state{std::move(other.state)}, slot{other.slot} {}
        Owner(const Owner&) = delete;
        // Fixed cohort: losing ANY owner seals it. No unregister/reuse loophole.
        ~Owner() {
            if (state) {
                state->owners[slot].store(false, std::memory_order_release);
                state->admission.Seal();
            }
        }
        bool Store(size_t offset, u8 value) const {
            auto op = Begin(state, offset);
            return op && op->Store(value);
        }
        std::optional<u8> Load(size_t offset) const {
            auto op = Begin(state, offset);
            return op ? op->Load() : std::nullopt;
        }
    };
    class Close {
        friend class ControlledGuestArena;
        std::shared_ptr<State> state;
        ProducerDrain::Closure closure;
        std::optional<HostMappingDomain::Freeze> mappings;
        Close(std::shared_ptr<State> s, ProducerDrain::Closure c)
            : state{std::move(s)}, closure{std::move(c)} {}
    public:
        Close(Close&&) = default;
        Close(const Close&) = delete;
        Result Poll() noexcept { return state ? closure.Poll() : Result::Unknown; }
        bool TryFreezeHostMappings() {
            if (!state || mappings || Poll() != Result::DrainedSubset) return false;
            try {
                auto frozen = state->backing.TryFreezeMappingEntries();
                if (frozen) { mappings.emplace(std::move(*frozen)); return true; }
            } catch (...) { closure.Quarantine(); throw; }
            closure.Quarantine();
            return false;
        }
        // CPU-only closed type has no asynchronous effects API. Never usable for
        // a GPU/guest lease; adding such an endpoint requires a different protocol.
        bool CancelNoEffects() noexcept {
            if (!state || Poll() != Result::DrainedSubset) return false;
            if (mappings && !mappings->CancelNoEffects()) {
                closure.Quarantine(); return false;
            }
            mappings.reset();
            return closure.ResumeNoEffects();
        }
        static constexpr Result GuestBackingAdmission() { return Result::Unknown; }
    };
    ControlledGuestArena() = default;
    ControlledGuestArena(const ControlledGuestArena&) = delete;
    ~ControlledGuestArena() { Retire(); }
    void Retire() noexcept { state->admission.Seal(); }
    std::optional<Owner> RegisterOwner() {
        auto entry = state->admission.TryEnter();
        if (!entry) return {};
        try {
            std::unique_lock lock{state->registry_mutex, std::try_to_lock};
            if (!lock || state->registered == OwnerCapacity) {
                state->admission.Seal(); return {};
            }
            const auto slot = state->registered++;
            state->owners[slot].store(true, std::memory_order_release);
            return Owner{state, slot};
        } catch (...) {
            state->admission.Seal(); throw;
        }
    }
    std::optional<Close> TryClose(u32 budget = 64) {
        auto close = state->admission.TryClose(budget);
        if (!close) return {};
        return Close{state, std::move(*close)};
    }
};
} // namespace Common
