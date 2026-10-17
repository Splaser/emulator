// SPDX-License-Identifier: GPL-2.0-or-later
#include <cassert>
#include <iostream>
#include <vector>
#include "video_core/renderer_vulkan/vk_transfer_content.h"

int main() {
    using Plan = Vulkan::TransferContent;
    using Kind = Plan::Kind;
    const std::array<Plan::Offset, 3> sizes{64, 64, 64};
    const std::array<Plan::Command, 5> operations{{
        {Kind::Fill, 1, 0, 0, 0, 64, 10},
        {Kind::Fill, 0, 0, 0, 0, 64, 99},
        {Kind::Copy, 1, 0, 16, 16, 16},
        {Kind::Fill, 0, 0, 0, 0, 64, 77},
        {Kind::Copy, 2, 1, 8, 8, 32},
    }};
    const auto plan = Plan::Build(sizes, operations);
    assert(plan);
    assert(plan->HasRoot(1, 16, 16, 1, 16));
    assert(plan->HasRoot(1, 0, 16, 0, 0));
    assert(plan->HasRoot(1, 32, 32, 0, 32));
    assert(!plan->HasRoot(1, 0, 64, 1, 0)); // Stale complement is never promoted.
    assert(!plan->HasRoot(1, 16, 16, 3, 16)); // Source overwritten AFTER the copy.
    assert(plan->HasRoot(0, 0, 64, 3, 0));
    assert(plan->HasRoot(2, 8, 8, 0, 8));
    assert(plan->HasRoot(2, 16, 16, 1, 16));
    assert(plan->HasRoot(2, 32, 8, 0, 32));
    assert(!plan->HasRoot(2, 0, 8, 1, 0)); // Initial bytes are Unknown, never inferred.
    assert(plan->WrittenBy(2, 1, 16, 16));
    assert(!plan->WrittenBy(2, 1, 0, 64));
    assert(!plan->WrittenBy(2, 0, 16, 16));
    assert(plan->Commands()[2].source == 0 && plan->Commands()[2].destination == 1);
    assert(plan->Spans(1).size() == 3);
    const auto partial = Plan::Build(sizes, std::span{operations}.subspan(2, 1));
    assert(partial && !partial->HasRoot(1, 16, 16, 0, 16)); // Unknown copied bytes stay Unknown.
    const std::array<Plan::Command, 2> unknown_source{{
        {Kind::Fill, 1, 0, 0, 0, 64, 10}, {Kind::Copy, 1, 0, 16, 16, 16}}};
    const auto overwritten = Plan::Build(sizes, unknown_source);
    assert(overwritten && overwritten->HasRoot(1, 0, 16, 0, 0));
    assert(!overwritten->HasRoot(1, 16, 16, 0, 16)); // Unknown copy erases the prior known source.
    assert(overwritten->HasRoot(1, 32, 32, 0, 32));
    auto bad = operations;
    bad[2].destination_offset = 60;
    assert(!Plan::Build(sizes, bad));
    bad = operations;
    bad[2].destination = 0; // Vulkan overlapping same-buffer copy is refused.
    assert(!Plan::Build(sizes, bad));
    bad = operations;
    bad[0].size = 63;
    assert(!Plan::Build(sizes, bad));
    bad = operations;
    bad[0].kind = static_cast<Kind>(9); // No generic/shader exact-coverage assertion.
    assert(!Plan::Build(sizes, bad));
    // Independent byte-label oracle, including split copy ancestry. No interval
    // splitting/overlay implementation is shared with the production graph.
    std::uint32_t random = 0x372f3;
    const auto next = [&] {random = random * 1664525u + 1013904223u;return random;};
    for (unsigned trial = 0; trial < 32; ++trial) {
        std::array<std::array<Plan::Root, 64>, 3> bytes;
        for (auto& buffer : bytes) buffer.fill({Plan::Unknown, 0});
        std::vector<Plan::Command> history;
        for (unsigned index = 0; index < 16; ++index) {
            const auto destination = next() % 3;
            const auto source = (destination + 1 + next() % 2) % 3;
            const auto size = 4 * (1 + next() % 16);
            const auto destination_offset = 4 * (next() % ((64 - size) / 4 + 1));
            const auto source_offset = 4 * (next() % ((64 - size) / 4 + 1));
            const bool fill = (next() & 0x100u) != 0;
            history.push_back({fill ? Kind::Fill : Kind::Copy, destination, source,
                               destination_offset, source_offset, size, index});
            for (unsigned byte = 0; byte < size; ++byte)
                bytes[destination][destination_offset + byte] = fill
                    ? Plan::Root{index, byte} : bytes[source][source_offset + byte];
            const auto snapshot = Plan::Build(sizes, history);
            assert(snapshot);
            for (unsigned buffer = 0; buffer < 3; ++buffer)
                for (unsigned byte = 0; byte < 64; ++byte) {
                    const auto expected = bytes[buffer][byte];
                    if (expected.command == Plan::Unknown)
                        assert(!snapshot->HasRoot(buffer, byte, 1, 0, 0));
                    else
                        assert(snapshot->HasRoot(buffer, byte, 1, expected.command, expected.offset));
                }
        }
    }
    std::cout << "PASS exact transfer content: partial copies, untouched roots, copy-of-copy, "
                 "source overwrite after copy, Unknown bytes, exact coverage bounds and 512 byte-oracle prefixes\n";
}
