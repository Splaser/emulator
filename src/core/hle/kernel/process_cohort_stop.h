// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include "core/hle/kernel/process_execution_stop.h"
#include "core/hle/kernel/process_owner_roster.h"

namespace Kernel {
// Phase-one cohort prerequisite. Owned creation/initialization/cold publication
// closures outlive capture and real backend drainage. NOT Guest Exclusion:
// cache PTE changes, ordinary writes, services, NCE/raw aliases and GPU remain open.
// Single orchestration thread; caller keeps System/Kernel/HostMemory facades alive.
// No asynchronous GPU work can adopt this type or its BackendsStopped result.
class ProcessCohortStop {
    friend class KProcess;
    Common::RetainedBackingStorage backing;
    KScopedAutoObject<KProcess> requester;
    KernelCore& kernel;
    Common::PageTable* page_table;
    std::optional<ProcessOwnerRoster::Snapshot> owners;
    ProcessOwnerRoster::CreationClosure creation;
    Common::ProducerDrain::Closure publication;
    Common::ProducerDrain::Closure initialization;
    std::optional<ProcessExecutionStop> execution;
    u32 remaining;
    std::thread::id owner_thread{std::this_thread::get_id()};
    bool unknown{}, released{}, stopped{};
    ProcessCohortStop(Common::RetainedBackingStorage&& backing_,
                      KScopedAutoObject<KProcess>&& requester_, KernelCore& kernel_, Common::PageTable* table_,
                      ProcessOwnerRoster::CreationClosure&& creation_,
                      Common::ProducerDrain::Closure&& publication_,
                      Common::ProducerDrain::Closure&& initialization_, u32 budget);
    bool OwnerCurrent() const;
public:
    using Result = ProcessExecutionStop::Result;
    ProcessCohortStop(ProcessCohortStop&&) = default;
    ProcessCohortStop(const ProcessCohortStop&) = delete;
    ~ProcessCohortStop() = default;
    Result Poll();
    bool CancelNoEffects();
    void Quarantine();
    static constexpr auto GuestBackingAdmission() { return Common::ProducerDrain::Result::Unknown; }
};
} // namespace Kernel
