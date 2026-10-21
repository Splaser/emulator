// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <array>
#include <memory>
#include <thread>

#include "core/hle/kernel/guest_execution_drain.h"
#include "core/hle/kernel/k_auto_object.h"
#include "core/hle/kernel/physical_core.h"

namespace Common {
struct GuestBackingEpoch;
struct PageTable;
}

namespace Kernel {
class KProcess;

// A process-bound backend stop prerequisite, NOT Guest Exclusion/admission.
// Retains KProcess (hence its PageTable/Memory owners) and captures backing identity.
// The epoch is identity only, NOT a pin of backing storage or an alias freeze.
// Caller keeps System/Kernel/HostMemory alive; no async GPU work can adopt this type.
class ProcessExecutionStop {
    friend class KProcess;
    KScopedAutoObject<KProcess> process;
    KernelCore& kernel;
    Common::PageTable* page_table;
    std::shared_ptr<const Common::GuestBackingEpoch> backing;
    // The requester need not own the backends running on these global cores.
    // Keep their real process/PageTable/Memory owners alongside the requester.
    std::array<KScopedAutoObject<KProcess>, Core::Hardware::NUM_CPU_CORES> running_owners;
    std::array<Common::PageTable*, Core::Hardware::NUM_CPU_CORES> running_page_tables{};
    // Seal/quarantine the execution closures before releasing any retained owner.
    GuestExecutionDrain execution;
    std::array<bool, Core::Hardware::NUM_CPU_CORES> requested{};
    std::thread::id owner_thread{std::this_thread::get_id()};
    u32 remaining;
    bool unknown{}, released{}, stopped{};

    ProcessExecutionStop(KScopedAutoObject<KProcess>&& process_, KernelCore& kernel_,
                         Common::PageTable* table_,
                         std::shared_ptr<const Common::GuestBackingEpoch> backing_,
                         GuestExecutionDrain&& execution_, u32 budget);
    bool OwnerCurrent() const;

public:
    enum class Result { Pending, BackendsStopped, Unknown };
    ProcessExecutionStop(ProcessExecutionStop&&);
    ProcessExecutionStop(const ProcessExecutionStop&) = delete;
    ~ProcessExecutionStop();

    // Try-locks each actual core and requests its actual backend halt. Only after
    // every counted backend (including UnlockThread) exits can this acknowledge.
    // NCE's blocking signal handshake is deliberately unsupported in this slice.
    Result Poll();
    bool CancelNoEffects();
    void Quarantine() noexcept;
    static constexpr auto GuestBackingAdmission() {
        return Common::ProducerDrain::Result::Unknown;
    }
};
} // namespace Kernel
