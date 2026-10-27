// SPDX-License-Identifier: GPL-2.0-or-later
// Real Windows HostMemory/Kernelbase mappings and real common library linkage.
#include <windows.h>
#include <future>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string_view>
#include <thread>
#include "common/host_memory.h"

namespace {
void Check(bool condition, const char* reason) {
    if (!condition) throw std::runtime_error(reason);
}
void NativeCases(bool expect_vulnerable) {
    using Common::HostMemory;
    using P = Common::MemoryPermission;
    SYSTEM_INFO info{};
    GetSystemInfo(&info);
    const size_t g = info.dwAllocationGranularity;
    Check(g && g % 4096 == 0, "allocation-granularity");
    {
        // Move BEFORE any export: the old facade must not create an unrecorded
        // pointer after its mapping domain has transferred to the new owner.
        HostMemory source(g * 8, g * 64, {}, 0, false, false, {}, true);
        source.Map(0, 0, g, P::ReadWrite, false);
        source.ClearBackingRegion(0, g, 17);
        HostMemory moved{std::move(source)};
        const auto& old = source;
        auto* a = source.BackingBasePointer();
        auto* b = source.VirtualBasePointer();
        auto* c = old.BackingBasePointer();
        auto* d = old.VirtualBasePointer();
        if (expect_vulnerable) {
            Check(a && b && c == a && d == b, "baseline-stale-pointer-witness-absent");
            a[0] = 19;
            Check(b[0] == 19 && c[0] == 19 && d[0] == 19, "unrecorded-native-alias-write");
            std::cout << "WITNESS post-move first export bypasses the transferred owner\n";
        } else {
            Check(!a && !b && !c && !d, "moved-from-pointer");
        }
        Check(!moved.TryFreezeMappingEntries(), "unsupported-windows-freeze-refusal");
        Check(moved.BackingBasePointer()[0] == (expect_vulnerable ? 19 : 17),
              "moved-owner-native-content");
    }
    {
        HostMemory source(g * 8, g * 64, {}, 0, false, false, {}, true);
        source.Map(0, 0, g, P::ReadWrite, false);
        source.Map(g * 2, 0, g, P::ReadWrite, false);
        source.ClearBackingRegion(0, g, 10);
        source.ClearBackingRegion(g * 2, g, 20);
        auto* canonical = source.BackingBasePointer();
        auto* aliases = source.VirtualBasePointer();
        Check(canonical && aliases && aliases[0] == 10 && aliases[g * 2] == 10,
              "real-physical-alias-identity");
        auto pin = source.PinPhysicalRange(0, g);
        auto storage = source.RetainBackingStorage();
        Check(pin && storage && pin->OwnerAlive() && storage->OwnerAlive(), "actual-storage-owners");
        HostMemory moved{std::move(source)};
        auto* stale_backing = source.BackingBasePointer();
        auto* stale_virtual = source.VirtualBasePointer();
        const auto& const_source = source;
        auto* stale_const_backing = const_source.BackingBasePointer();
        auto* stale_const_virtual = const_source.VirtualBasePointer();
        if (expect_vulnerable) {
            Check(stale_backing == canonical && stale_virtual == aliases &&
                  stale_const_backing == canonical && stale_const_virtual == aliases,
                  "baseline-stale-pointer-witness-absent");
            stale_backing[0] = 11;
            Check(aliases[0] == 11 && aliases[g * 2] == 11, "baseline-native-write-not-observed");
            std::cout << "WITNESS moved-from facade exports four unowned raw pointers\n";
        } else {
            Check(!stale_backing && !stale_virtual && !stale_const_backing && !stale_const_virtual,
                  "moved-from-pointer");
        }
        Check(!source.PinPhysicalRange(0, 1) && !source.RetainBackingStorage() &&
              !source.TryFreezeMappingEntries(), "moved-from-capture-refusal");
        // Windows is deliberately unsupported by the existing ledger. A storage
        // pin, owner move and native aliases must not silently enroll this arena.
        Check(!moved.TryFreezeMappingEntries(), "unsupported-windows-freeze-refusal");
        std::promise<void> run_writer;
        auto ready = run_writer.get_future();
        std::thread writer{[&] { ready.wait(); aliases[g * 2] = 31; }};
        run_writer.set_value();
        writer.join();
        Check(canonical[0] == 31 && pin->Bytes()[0] == 31, "retained-raw-writer-bypass-witness");
        moved.Unmap(g * 2, g, false);
        moved.Map(g * 2, g * 2, g, P::ReadWrite, false);
        aliases[g * 2] = 47;
        Check(canonical[0] == 31 && canonical[g * 2] == 47 && pin->Bytes()[0] == 31,
              "remap-physical-identity");
        moved.Protect(g * 2, g, P::Read);
        MEMORY_BASIC_INFORMATION mapping{};
        Check(VirtualQuery(aliases + g * 2, &mapping, sizeof(mapping)) == sizeof(mapping) &&
              mapping.State == MEM_COMMIT && mapping.Protect == PAGE_READONLY,
              "native-readonly-protection");
        Check(!moved.TryFreezeMappingEntries(), "readonly-is-not-physical-freeze");
        moved.Protect(g * 2, g, P::ReadWrite);
        aliases[g * 2] = 53;
        Check(canonical[g * 2] == 53, "native-unprotect-byte-effect");
        Check(!Common::HostMappingDomain::Freeze::GuestBackingAdmission(), "false-guest-admission");
    }
    {
        std::optional<Common::RetainedBackingStorage> retained;
        std::optional<Common::PinnedPhysicalMemory> pin;
        u8* saved{};
        {
            HostMemory arena(g * 8, g * 64);
            saved = arena.BackingBasePointer();
            pin = arena.PinPhysicalRange(0, g);
            retained = arena.RetainBackingStorage();
            Check(pin && retained && !arena.TryFreezeMappingEntries(), "ordinary-arena-refusal");
        }
        Check(!pin->OwnerAlive() && !retained->OwnerAlive(), "retired-epoch-invalidation");
        saved[0] = 67; // Allocation is retained, but this is not access admission.
        Check(pin->Bytes()[0] == 67, "allocation-retention-is-not-pointer-revocation");
        MEMORY_BASIC_INFORMATION mapping{};
        Check(VirtualQuery(saved, &mapping, sizeof(mapping)) == sizeof(mapping) &&
              mapping.State == MEM_COMMIT, "retained-native-allocation");
        pin.reset();
        retained.reset();
        Check(VirtualQuery(saved, &mapping, sizeof(mapping)) == sizeof(mapping) &&
              mapping.State == MEM_FREE, "final-native-allocation-release");
    }
    std::cout << "PASS real Windows alias/remap/protection/retained-allocation effects; all unproved freezes refuse\n";
}
} // namespace
int main(int argc, char** argv) {
    try {
        const bool vulnerable = argc == 2 && std::string_view{argv[1]} == "--expect-vulnerable";
        NativeCases(vulnerable);
        std::cout << "COMPLETE native mapping teardown\n";
        return vulnerable ? 42 : 0;
    } catch (const std::exception& error) {
        std::cerr << "MAPPING OWNER CHECK: " << error.what() << '\n';
        return 91;
    }
}
