// SPDX-License-Identifier: GPL-2.0-or-later
#include "core/hle/kernel/process_cohort_stop.h"
#include "core/hle/kernel/kernel.h"
#include "core/hle/kernel/k_process.h"
#include "core/core.h"
#include "core/device_memory.h"

namespace Kernel {
ProcessCohortStop::ProcessCohortStop(Common::RetainedBackingStorage&& backing_,
    KScopedAutoObject<KProcess>&& requester_, KernelCore& kernel_, Common::PageTable* table_,
    ProcessOwnerRoster::CreationClosure&& creation_, Common::ProducerDrain::Closure&& publication_,
    Common::ProducerDrain::Closure&& initialization_, u32 budget)
    : backing{std::move(backing_)}, requester{std::move(requester_)}, kernel{kernel_}, page_table{table_},
      creation{std::move(creation_)}, publication{std::move(publication_)},
      initialization{std::move(initialization_)}, remaining{budget} {}

bool ProcessCohortStop::OwnerCurrent() const {
    const auto* process = requester.GetPointerUnsafe();
    return process && !released && owner_thread == std::this_thread::get_id() &&
           backing.OwnerAlive() && process->IsInitialized() &&
           process->GetPageTable().HasImpl() &&
           std::addressof(process->GetPageTable().GetImpl()) == page_table &&
           kernel.System().DeviceMemory().buffer.BackingEpoch() == backing.Epoch() &&
           (!execution || execution->OwnerCurrent());
}

ProcessCohortStop::Result ProcessCohortStop::Poll() {
    using D = Common::ProducerDrain::Result;
    if (unknown || !OwnerCurrent() || !creation.IsClosed() ||
        (owners && !owners->IsCurrent())) {
        Quarantine(); return Result::Unknown;
    }
    const auto initialized = execution ? execution->initialization.Poll() : initialization.Poll();
    const auto published = publication.Poll();
    if (initialized == D::Unknown || published == D::Unknown) {
        Quarantine(); return Result::Unknown;
    }
    if (stopped) return Result::BackendsStopped;
    if (!remaining) { Quarantine(); return Result::Unknown; }
    --remaining;
    if (initialized == D::Pending || published == D::Pending) return Result::Pending;
    if (!owners) {
        auto captured = kernel.TryRetainProcessOwners();
        if (!captured) return Result::Pending; // Constructor/final-Close/lock race: bounded retry.
        owners.emplace(std::move(*captured));
    }
    if (!execution) {
        auto storage = kernel.System().DeviceMemory().buffer.RetainBackingStorage();
        if (!storage || !OwnerCurrent()) { Quarantine(); return Result::Unknown; }
        // Do not close CPU execution while an admitted loader/publication might
        // need it to finish. No scheduler/PTE/roster lock spans this transition.
        auto cores = kernel.TryCloseGuestExecution(remaining + 1);
        if (!cores) { Quarantine(); return Result::Unknown; }
        execution.emplace(ProcessExecutionStop{KScopedAutoObject<KProcess>{requester.GetPointerUnsafe()},
            kernel, page_table, std::move(*storage), std::move(initialization), std::move(*cores), remaining + 1});
    }
    // Creation is still closed, initialization and cold publication still owned.
    // IsCurrent supplements those sustained capabilities; it does not replace them.
    const auto result = execution->Poll();
    if (result == Result::Unknown || !owners->IsCurrent()) {
        Quarantine(); return Result::Unknown;
    }
    stopped = result == Result::BackendsStopped;
    return result;
}
bool ProcessCohortStop::CancelNoEffects() {
    if (Poll() != Result::BackendsStopped || !execution->CancelNoEffects()) return false;
    if (!publication.ResumeNoEffects() || !creation.CancelNoEffects()) {
        Quarantine(); return false;
    }
    released = true;
    return true;
}
void ProcessCohortStop::Quarantine() {
    unknown = true;
    if (execution) execution->Quarantine();
    initialization.Quarantine(); publication.Quarantine(); creation.Quarantine();
}
} // namespace Kernel
