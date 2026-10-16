// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <variant>

#include "common/page_table.h"
#include "common/physical_cpu_page.h"
#include "common/physical_registration_bundle.h"

namespace VideoCommon {
template <class P> class BufferCache;
}

namespace Core::Memory {

enum class PreparedCpuWriteResult { Stored, NeedSlow, Stale, Busy, Retired, Invalid };

struct CpuAccessContext {
    mutable std::shared_mutex mutex;
    std::atomic<u64> generation{};
    std::atomic<bool> alive{true};
};

/// Memory-instance lifetime and active-address-space epoch. Cold changes invalidate views;
/// bounded prepared stores use try-locks and never wait for a context/PTE mutator.
struct CpuAccessContextOwner {
    std::shared_ptr<CpuAccessContext> state{std::make_shared<CpuAccessContext>()};
    CpuAccessContextOwner() = default;
    CpuAccessContextOwner(const CpuAccessContextOwner&) = delete;
    CpuAccessContextOwner& operator=(const CpuAccessContextOwner&) = delete;
    ~CpuAccessContextOwner() {
        const auto guard = Change();
        state->alive.store(false, std::memory_order_release);
    }
    [[nodiscard]] std::unique_lock<std::shared_mutex> Change() const {
        std::unique_lock lock{state->mutex};
        state->generation.fetch_add(1, std::memory_order_release);
        return lock;
    }
};

/// Cold prepared CPU-VA target. Owns physical storage, not the process/PageTable object.
/// Explicit prepared stores and an owner-bound ordinary scalar write can consume this view.
struct PreparedCpuPage {
    const Common::PageTable::MappingSnapshot mapping;
    const Common::PreparedPhysicalCpuPage physical;
    const std::shared_ptr<CpuAccessContext> context;
    const u64 context_generation;

    /// Queued registration qualification, not a mapping lease across suspension.
    [[nodiscard]] bool IsCurrentForRegistration() const {
        if (!context || !mapping.domain) return false;
        std::shared_lock context_guard{context->mutex, std::try_to_lock};
        if (!context_guard.owns_lock() || !context->alive.load() ||
            context->generation.load() != context_generation)
            return false;
        std::shared_lock mapping_guard{mapping.domain->mutex, std::try_to_lock};
        return mapping_guard.owns_lock() && mapping.IsCurrent();
    }

    template <typename T>
        requires(std::is_trivially_copyable_v<T> && sizeof(T) <= 16)
    [[nodiscard]] PreparedCpuWriteResult TryStore(const CpuAccessContext* caller,
                                                 u64 address, const T& value) const noexcept {
        return TryStoreImpl(
            caller, address, false, [&] { return physical.TryStore(address & 4095, value); },
            sizeof(T));
    }

    /// Explicit controlled cached path only. The cache owner must retain this admission
    /// through its post-store tracker update. GPU-dirty preservation/aliases must be qualified
    /// before this bounded call; it never invokes callbacks or falls back to legacy memcpy.
    template <typename T>
        requires(std::is_trivially_copyable_v<T> && sizeof(T) <= 16)
    [[nodiscard]] PreparedCpuWriteResult
    TryStoreCached(const CpuAccessContext* caller, u64 address, const T& value,
                   Common::PhysicalRegistrationBundle::CachedWrite& write) const noexcept {
        return TryStoreImpl(
            caller, address, true,
            [&] {
                return Common::PhysicalRegistrationBundle::StoreCached(write, physical,
                                                                       address & 4095, value);
            },
            sizeof(T));
    }

private:
    template <typename Store>
    [[nodiscard]] PreparedCpuWriteResult TryStoreImpl(const CpuAccessContext* caller, u64 address,
                                                      bool cached, Store&& store,
                                                      size_t size) const noexcept {
        if (!context || context.get() != caller || !mapping.domain)
            return PreparedCpuWriteResult::Invalid;
        // Same AArch64 top-bit masking as the legacy pointer resolver.
        address &= 0xffffffffffffULL;
        if ((address & ~u64{4095}) != mapping.virtual_page || size > 4096 - (address & 4095))
            return PreparedCpuWriteResult::Invalid;
        std::shared_lock context_guard{context->mutex, std::try_to_lock};
        if (!context_guard.owns_lock()) return PreparedCpuWriteResult::Busy;
        if (!context->alive.load(std::memory_order_acquire)) return PreparedCpuWriteResult::Retired;
        if (context->generation.load(std::memory_order_acquire) != context_generation)
            return PreparedCpuWriteResult::Stale;
        std::shared_lock mapping_guard{mapping.domain->mutex, std::try_to_lock};
        if (!mapping_guard.owns_lock()) return PreparedCpuWriteResult::Busy;
        if (!mapping.IsCurrent()) return PreparedCpuWriteResult::Stale;
        // Debug/cached paths require the existing preservation/device-alias/OnCPUWrite work.
        // Never perform those callbacks while holding these short execution guards.
        if (mapping.type != Common::PageType::Memory &&
            !(cached && mapping.type == Common::PageType::RasterizerCachedMemory))
            return PreparedCpuWriteResult::NeedSlow;
        switch (store()) {
        case Common::PhysicalStoreResult::Stored: return PreparedCpuWriteResult::Stored;
        case Common::PhysicalStoreResult::NeedSlow: return PreparedCpuWriteResult::NeedSlow;
        case Common::PhysicalStoreResult::Retired: return PreparedCpuWriteResult::Retired;
        default: return PreparedCpuWriteResult::Invalid;
        }
    }
};

/// A single synchronous ordinary Write invocation inside an already preserved/admitted cache
/// transaction. Thread-local binding never enrolls another CPU thread or Memory instance.
/// This owns the expected scalar bytes; all physical/native owners remain in the transaction.
/// Never retain this scope across suspension, callbacks or a GPU wait.
class ScopedCpuWrite {
public:
    template <typename T>
        requires(std::is_trivially_copyable_v<T> && sizeof(T) <= 8)
    ScopedCpuWrite(const PreparedCpuPage& page_,
                   Common::PhysicalRegistrationBundle::CachedWrite& write_,
                   const CpuAccessContext* context_, u64 address_, const T& value)
        : previous{current}, page{page_}, write{write_}, context{context_},
          address{address_ & 0xffffffffffffULL}, size{sizeof(T)} {
        std::memcpy(bytes.data(), &value, sizeof(T));
        current = this;
    }
    ScopedCpuWrite(const ScopedCpuWrite&) = delete;
    ScopedCpuWrite& operator=(const ScopedCpuWrite&) = delete;
    ~ScopedCpuWrite() { current = previous; }

    [[nodiscard]] static ScopedCpuWrite* Current() noexcept { return current; }
    [[nodiscard]] PreparedCpuWriteResult Outcome() const noexcept { return outcome; }

    template <typename T>
    void Store(const CpuAccessContext* caller, u64 target, const T& value) noexcept {
        if (attempted) {
            // A second ordinary call is not permission to replay or change an effected store.
            outcome = PreparedCpuWriteResult::Invalid;
            return;
        }
        attempted = true;
        if (previous) {
            outcome = PreparedCpuWriteResult::Busy;
            return;
        }
        if constexpr (sizeof(T) != 1 && sizeof(T) != 2 && sizeof(T) != 4 && sizeof(T) != 8) {
            outcome = PreparedCpuWriteResult::Invalid;
        } else {
            if (caller != context || sizeof(T) != size ||
                (target & 0xffffffffffffULL) != address ||
                std::memcmp(bytes.data(), &value, sizeof(T)) != 0) {
                outcome = PreparedCpuWriteResult::Invalid;
                return;
            }
            outcome = page.TryStoreCached(caller, target, value, write);
        }
    }

private:
    inline static thread_local ScopedCpuWrite* current{};
    ScopedCpuWrite* previous;
    const PreparedCpuPage& page;
    Common::PhysicalRegistrationBundle::CachedWrite& write;
    const CpuAccessContext* context;
    u64 address;
    size_t size;
    std::array<u8, 8> bytes{};
    bool attempted{};
    PreparedCpuWriteResult outcome{PreparedCpuWriteResult::NeedSlow};
};

/// Immutable CPU-side request, not a binding/lease across suspension. GPU-owner acceptance is
/// single-use. Only actual cache commit may publish Stored after post-store tracker publication
/// and admission release. Callers poll terminal state; this object never waits or dispatches.
class ControlledCpuWriteRequest {
    friend class Memory;
    template <class P> friend class VideoCommon::BufferCache;
public:
    using Value = std::variant<u8, u16, u32, u64>;
    enum class Phase { Prepared, Accepted, Stored, Refused, Cancelled, Unknown };
    [[nodiscard]] Phase State() const noexcept { return phase.load(std::memory_order_acquire); }
    [[nodiscard]] std::optional<PreparedCpuWriteResult> Outcome() const noexcept {
        const auto state = State();
        if (state != Phase::Stored && state != Phase::Refused) return std::nullopt;
        return result.load(std::memory_order_relaxed);
    }
    /// Cancellation may win only before the GPU owner accepts responsibility. A late caller
    /// cancellation cannot release an admitted/native request or replay its CPU store.
    [[nodiscard]] bool Cancel() noexcept {
        auto expected = Phase::Prepared;
        return phase.compare_exchange_strong(expected, Phase::Cancelled,
                                              std::memory_order_acq_rel);
    }
    [[nodiscard]] const PreparedCpuPage& View() const { return view; }
    [[nodiscard]] u64 Address() const { return address; }
    [[nodiscard]] u64 Size() const {
        return std::visit([](const auto& scalar) { return sizeof(scalar); }, value);
    }
    [[nodiscard]] const Value& Payload() const { return value; }

private:
    ControlledCpuWriteRequest(PreparedCpuPage view_, u64 address_, Value value_)
        : view{std::move(view_)}, address{address_}, value{std::move(value_)} {}
    [[nodiscard]] bool TryAccept() noexcept {
        auto expected = Phase::Prepared;
        return phase.compare_exchange_strong(expected, Phase::Accepted,
                                              std::memory_order_acq_rel);
    }
    void Publish(Phase terminal, PreparedCpuWriteResult outcome = PreparedCpuWriteResult::NeedSlow) {
        result.store(outcome, std::memory_order_relaxed);
        phase.store(terminal, std::memory_order_release);
    }
    const PreparedCpuPage view;
    const u64 address;
    const Value value;
    std::atomic<Phase> phase{Phase::Prepared};
    std::atomic<PreparedCpuWriteResult> result{PreparedCpuWriteResult::NeedSlow};
};
using ControlledCpuWriteRequestPtr = std::shared_ptr<ControlledCpuWriteRequest>;

} // namespace Core::Memory
