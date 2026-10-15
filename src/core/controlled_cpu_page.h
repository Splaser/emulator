// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include "common/page_table.h"
#include "common/physical_cpu_page.h"
#include "common/physical_registration_bundle.h"

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
/// Only the explicit prepared Write entry consumes this view. Ordinary writes remain legacy.
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

} // namespace Core::Memory
