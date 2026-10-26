// SPDX-FileCopyrightText: Copyright 2026 citron Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include <algorithm>
#include <array>
#include <iostream>
#include <limits>
#include <numeric>
#include <span>
#include <stdexcept>
#include <vector>

#include "video_core/engines/inline_upload.h"

namespace {
using Tegra::Engines::Upload::DataAccumulator;
using Tegra::Engines::Upload::SourceTracker;

void Check(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void CheckBytes(std::span<const u8> actual, std::span<const u8> expected) {
    Check(std::ranges::equal(actual, expected), "completed upload bytes differ");
}

void CheckPacketBoundaries() {
    std::array<u32, 64> qmd{};
    std::iota(qmd.begin(), qmd.end(), 0x1000U);
    qmd[8] = 0x800; // Aligned program entry, distinct from the thread dimensions.
    qmd[19] = 0x10001;
    const std::span<const u8> bytes{reinterpret_cast<const u8*>(qmd.data()), sizeof(qmd)};
    DataAccumulator upload;

    // Include the 44 + 212 byte split that would put word 19 in word 8 if the
    // second packet were incorrectly written at the start of the descriptor.
    for (size_t split = 4; split < bytes.size(); split += 4) {
        upload.Begin(bytes.size());
        {
            const std::vector<u8> first{bytes.begin(), bytes.begin() + split};
            Check(!upload.Append(first), "partial packet committed early");
        } // The first command buffer can be released before the next arrives.
        const std::vector<u8> second{bytes.begin() + split, bytes.end()};
        const auto complete = upload.Append(second);
        Check(complete.has_value(), "split upload did not complete");
        CheckBytes(*complete, bytes);
        Check(!upload.Append(bytes.first(4)), "completed upload committed twice");
    }

    upload.Begin(bytes.size());
    const auto single = upload.Append(bytes);
    Check(single.has_value(), "single packet did not complete");
    CheckBytes(*single, bytes);

    upload.Begin(bytes.size());
    Check(!upload.Append(bytes.first(44)), "mixed upload committed early");
    for (size_t offset = 44; offset < 60; offset += 4) {
        Check(!upload.Append(bytes.subspan(offset, 4)), "scalar packet committed early");
    }
    const auto mixed = upload.Append(bytes.subspan(60));
    Check(mixed.has_value(), "mixed scalar/bulk upload did not complete");
    CheckBytes(*mixed, bytes);
}

void CheckPaddingAndRestart() {
    std::array<u8, 20> wire{};
    std::iota(wire.begin(), wire.end(), u8{1});
    DataAccumulator upload;
    upload.Begin(17);
    Check(!upload.Append(std::span{wire}.first(16)), "padded upload committed early");
    const auto tail = upload.Append(std::span{wire}.subspan(16));
    Check(tail.has_value(), "padded upload did not complete");
    CheckBytes(*tail, std::span{wire}.first(17));

    upload.Begin(20);
    Check(!upload.Append(std::span{wire}.first(4)), "partial transfer committed");
    upload.Begin(8); // A new EXEC abandons the old partial transfer.
    Check(!upload.Append(std::span{wire}.subspan(8, 4)), "restart reused old bytes");
    const auto restarted = upload.Append(std::span{wire}.subspan(12, 4));
    Check(restarted.has_value(), "restarted transfer did not complete");
    CheckBytes(*restarted, std::span{wire}.subspan(8, 8));

    upload.Begin(0);
    Check(!upload.Append(wire), "empty transfer published data");
    upload.Begin(8);
    Check(!upload.Append({}), "empty packet published data");
    const auto padded_single = upload.Append(wire);
    Check(padded_single.has_value(), "oversized final packet did not complete");
    CheckBytes(*padded_single, std::span{wire}.first(8));
}

void CheckCurrentTransferSource() {
    SourceTracker source;
    source.Begin(0x3000, 256, true);
    Check(!source.Append(0x1000, 44), "partial source was published");
    const auto first = source.Append(0x102c, 212);
    Check(first.has_value() && first->contiguous, "contiguous source was rejected");
    Check(first->upload_address == 0x1000 && first->copy_size == 256,
          "first transfer source/length differ");
    Check(!source.Append(0x1100, 4), "source was published twice");

    source.Begin(0x4030, 12, true);
    const auto second = source.Append(0x9000, 12);
    Check(second.has_value(), "second transfer source missing");
    Check(second->exec_address == 0x4030 && second->copy_size == 12 &&
              second->upload_address == 0x9000,
          "second transfer retained the old source or length");
    Check(second->IndirectAddress(0x4030, 12) == 0x9000, "valid indirect source missing");
    Check(!second->IndirectAddress(0x4031, 12), "misaligned destination accepted");
    Check(second->Overlaps(0x4034, 12), "overwriting range was not detected");
    Check(!second->Overlaps(0x403c, 12), "adjacent range overlaps");

    source.Begin(0x4030, 8, true);
    const auto short_upload = source.Append(0xa000, 8);
    Check(short_upload.has_value() && !short_upload->IndirectAddress(0x4030, 12),
          "short transfer was accepted as three dispatch dimensions");
}

void CheckNonContiguousSources() {
    SourceTracker source;
    source.Begin(0x4030, 12, true);
    Check(!source.Append(0x1000, 4), "partial source was published");
    const auto split = source.Append(0x2000, 8);
    Check(split.has_value() && !split->contiguous && !split->IndirectAddress(0x4030, 12),
          "disjoint packets were treated as one indirect buffer");
    Check(split->Overlaps(0x4030, 12), "disjoint source lost its destination write");

    source.Begin(0x4030, 12, false);
    const auto pitched = source.Append(0x1000, 12);
    Check(pitched.has_value() && !pitched->contiguous, "pitched destination was accepted");
    source.Begin(0x4030, 12, true);
    const auto immediate = source.Append(0, 12);
    Check(immediate.has_value() && !immediate->contiguous, "immediate data became a GPU address");
    source.Begin(0x4030, 12, true);
    const auto wrapped = source.Append(std::numeric_limits<GPUVAddr>::max() - 3, 12);
    Check(wrapped.has_value() && !wrapped->contiguous, "wrapping source range was accepted");

    source.Begin(0x4030, 12, true);
    Check(!source.Append(0x1000, 4), "partial source was published");
    source.Begin(0x5000, 4, true);
    const auto restarted = source.Append(0x9000, 4);
    Check(restarted.has_value() && restarted->contiguous && restarted->upload_address == 0x9000 &&
              restarted->copy_size == 4,
          "new EXEC retained incomplete source tracking");
    source.Begin(0x5000, 0, true);
    Check(!source.Append(0x1000, 4), "empty transfer published a source");
}
} // namespace

int main() {
    try {
        CheckPacketBoundaries();
        CheckPaddingAndRestart();
        CheckCurrentTransferSource();
        CheckNonContiguousSources();
        std::cout
            << "Inline upload regressions passed (63 QMD splits and transfer/source controls)\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
