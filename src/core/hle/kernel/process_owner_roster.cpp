// SPDX-License-Identifier: GPL-2.0-or-later
#include "core/hle/kernel/process_owner_roster.h"

#include <algorithm>
#include <limits>
#include <stdexcept>
#include "core/hle/kernel/k_process.h"

namespace Kernel {
void ProcessOwnerRoster::State::Changed() noexcept {
    if (revision == std::numeric_limits<u64>::max()) poisoned = true;
    else ++revision;
}

ProcessOwnerRoster::Snapshot::Snapshot(std::shared_ptr<State> state_) : state{std::move(state_)} {}
ProcessOwnerRoster::Snapshot::Snapshot(Snapshot&&) noexcept = default;
ProcessOwnerRoster::Snapshot::~Snapshot() = default;

bool ProcessOwnerRoster::Snapshot::IsCurrent() const {
    if (!state) return false;
    std::unique_lock lock{state->mutex, std::try_to_lock};
    return lock.owns_lock() && !state->poisoned && state->revision == revision;
}

bool ProcessOwnerRoster::Snapshot::Retains(const KProcess* process) const noexcept {
    return std::ranges::any_of(owners, [process](const auto& owner) {
        return owner.GetPointerUnsafe() == process;
    });
}

size_t ProcessOwnerRoster::Snapshot::Size() const noexcept { return owners.size(); }

u64 ProcessOwnerRoster::Register(KProcess* process) {
    std::scoped_lock lock{state->mutex};
    if (!process || state->next_id == std::numeric_limits<u64>::max()) {
        state->poisoned = true;
        throw std::overflow_error("process owner registration unavailable");
    }
    const auto id = state->next_id++;
    state->records.push_back({id, process});
    state->Changed();
    return id;
}

void ProcessOwnerRoster::BeginRetirement(u64 id) {
    std::scoped_lock lock{state->mutex};
    const auto it = std::ranges::find(state->records, id, &Record::id);
    if (it == state->records.end() || it->retiring) state->poisoned = true;
    else it->retiring = true;
    state->Changed();
}

void ProcessOwnerRoster::CompleteRetirement(u64 id) { Remove(id); }

void ProcessOwnerRoster::Remove(u64 id) {
    std::scoped_lock lock{state->mutex};
    // Exact registration identity: Free may already have allowed address reuse.
    if (std::erase_if(state->records, [id](const auto& record) { return record.id == id; }) != 1)
        state->poisoned = true;
    state->Changed();
}

std::optional<ProcessOwnerRoster::Snapshot> ProcessOwnerRoster::TryCapture() const {
    Snapshot snapshot{state}; // Must outlive the lock, even on partial capture failure.
    std::unique_lock lock{state->mutex, std::try_to_lock};
    if (!lock.owns_lock() || state->poisoned) return std::nullopt;
    snapshot.owners.reserve(state->records.size());
    for (const auto& record : state->records) {
        if (record.retiring) return std::nullopt;
        auto owner = KScopedAutoObject<KProcess>::TryOpen(record.process);
        if (!owner) return std::nullopt;
        snapshot.owners.push_back(std::move(*owner));
    }
    snapshot.revision = state->revision;
    return snapshot;
}
} // namespace Kernel
