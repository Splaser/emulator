// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include "video_core/physical_access_plan.h"

namespace VideoCommon {

enum class ControlledTransferPoll { Pending, Complete, Unknown };

/// Backend-owned actual destination, upload and readback allocations. No cache membership is
/// implied. Submit reads immutable physical pins only; Complete requires checked submission,
/// device visibility and an actual readback matching those same physical bytes.
class ControlledBufferTransfer {
public:
    virtual ~ControlledBufferTransfer() = default;
    [[nodiscard]] virtual const void* DestinationIdentity() const = 0;
    [[nodiscard]] virtual bool Submit(const Tegra::PhysicalAccessPlan& plan) = 0;
    [[nodiscard]] virtual ControlledTransferPoll Poll(const Tegra::PhysicalAccessPlan& plan) = 0;
    /// Renderer owner only, after all producers joined and checked successful device idle.
    virtual void RetireAfterDeviceIdle() = 0;
};

} // namespace VideoCommon
