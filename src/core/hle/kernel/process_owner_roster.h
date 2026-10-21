// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <memory>
#include <mutex>
#include <optional>
#include <vector>
#include "core/hle/kernel/k_auto_object.h"

namespace Core { struct SchedulerTestAccess; }

namespace Kernel {
class KProcess;

// Cold lifecycle inventory, independent of OS process publication. A snapshot
// retains objects, not writable-alias coverage or permission to access backing.
// Callers keep KernelCore alive through snapshot destruction. Never a signal API.
class ProcessOwnerRoster {
    friend struct Core::SchedulerTestAccess;
    struct Record { u64 id; KProcess* process; bool retiring{}; };
    struct State {
        std::mutex mutex;
        std::vector<Record> records;
        u64 next_id{1}, revision{};
        bool poisoned{};
        void Changed() noexcept;
    };
    std::shared_ptr<State> state{std::make_shared<State>()};

public:
    class Snapshot {
        friend class ProcessOwnerRoster;
        std::shared_ptr<State> state;
        std::vector<KScopedAutoObject<KProcess>> owners;
        u64 revision{};
        explicit Snapshot(std::shared_ptr<State> state_);
    public:
        Snapshot(Snapshot&&) noexcept;
        Snapshot(const Snapshot&) = delete;
        ~Snapshot();
        bool IsCurrent() const;
        bool Retains(const KProcess* process) const noexcept;
        size_t Size() const noexcept;
    };

    ProcessOwnerRoster() = default;
    ProcessOwnerRoster(const ProcessOwnerRoster&) = delete;
    // Register after construction, before any Initialize can publish a PageTable.
    u64 Register(KProcess* process);
    // Mark before finalization/Free. On an exception leave the retiring record
    // present: future captures refuse until proven recovery (not implemented).
    void BeginRetirement(u64 id);
    void CompleteRetirement(u64 id);
    // Used by normal C++ destruction, whose caller excludes simultaneous use.
    void Remove(u64 id);
    // One try-lock. Refusal/exception releases any partial pins AFTER unlocking.
    // A zero-ref constructor/retiring object refuses; it is never resurrected.
    std::optional<Snapshot> TryCapture() const;
};
} // namespace Kernel
