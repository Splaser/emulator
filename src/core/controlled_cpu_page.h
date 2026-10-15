// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include "common/page_table.h"
#include "common/physical_cpu_page.h"

namespace Core::Memory {

/// Cold prepared CPU-VA target. Owns physical storage, not the process/PageTable object.
/// Mapping validation is not writer qualification or permission to bypass OnCPUWrite.
/// No ordinary Memory::Write path consumes this view yet.
struct PreparedCpuPage {
    Common::PageTable::MappingSnapshot mapping;
    Common::PreparedPhysicalCpuPage physical;
};

} // namespace Core::Memory
