# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile current split-buffer helpers against a deterministic fake GPU runtime."""

import argparse
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description="Exercise split-buffer helpers with fake GPU memory.")
parser.add_argument("--cxx", default=os.environ.get("CXX", "c++"))
parser.add_argument("--build-dir", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
p = args.build_dir or root / ".diagnostics" / "gather-buffer-tests"
p.mkdir(parents=True, exist_ok=True)
s = (root / 'src/video_core/buffer_cache/buffer_cache.h').read_text(encoding='utf-8')


def func(marker):
    start = s.index(marker)
    start = s.rfind('template <class P>', 0, start)
    end = s.index('\n}\n', start) + 3
    return s[start:end]


head = r'''

#include <algorithm>
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <deque>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <ranges>
#include <set>
#include <shared_mutex>
#include <span>
#include <stdexcept>
#include <unordered_map>
#include <vector>
using u8 = uint8_t;
using u32 = uint32_t;
using u64 = uint64_t;
using GPUVAddr = u64;
using DAddr = u64;
using BufferId = size_t;
constexpr u64 operator""_MiB(unsigned long long x) {
    return x * 1024 * 1024;
}
constexpr u64 operator""_KiB(unsigned long long x) {
    return x * 1024;
}
namespace boost::container {
template <class T, size_t N>
using small_vector = std::vector<T>;
}
namespace Core {
constexpr u64 DEVICE_PAGESIZE = 4;
}
constexpr u64 DEVICE_PAGESIZE = Core::DEVICE_PAGESIZE;
namespace Common {
template <class T>
T AlignUp(T x, u64 a) {
    return (x + a - 1) / a * a;
}
template <class T>
T AlignDown(T x, u64 a) {
    return x / a * a;
}
} // namespace Common
namespace VideoCore {
struct RasterizerDownloadArea {
    DAddr start_address = 0, end_address = 0;
    bool preemtive = false;
};
} // namespace VideoCore
struct ScopeExit {
    std::function<void()> f;
    ~ScopeExit() {
        f();
    }
};
struct ScopeMaker {
    template <class F>
    ScopeExit operator+(F f) {
        return {f};
    }
};
#define SCOPE_EXIT auto scope_exit = ScopeMaker{} + [&]()
struct BufferCopy {
    u64 src_offset, dst_offset, size;
};
struct Runtime;
struct FakeBuffer {
    static inline bool fail_next = false;
    DAddr base = 0;
    std::vector<u64> page_gpu_tick;
    std::vector<u8> bytes;
    FakeBuffer() = default;
    FakeBuffer(Runtime&, DAddr d, u64 size) : base(d), page_gpu_tick((size + 4095) / 4096), bytes(size) {
        if (fail_next) {
            fail_next = false;
            throw std::bad_alloc();
        }
    }
    u64 SizeBytes() const {
        return bytes.size();
    }
    u32 Offset(DAddr d) {
        return u32(d - base);
    }
    void MarkUsage(u64, u64) {}
};
struct Runtime {
    bool fail_copy = false;
    u64 CurrentTick() const { return 20; }
    int copies = 0;
    std::vector<BufferCopy> writes;
    template <class C>
    void CopyBuffer(FakeBuffer& dst, FakeBuffer& src, const C& copies_, bool) {
        if (fail_copy) {
            fail_copy = false;
            throw std::runtime_error("copy failed");
        }
        for (auto c : copies_) {
            if (c.src_offset + c.size > src.bytes.size() ||
                c.dst_offset + c.size > dst.bytes.size())
                throw std::runtime_error("out of bounds");
            std::memmove(dst.bytes.data() + c.dst_offset, src.bytes.data() + c.src_offset, c.size);
            writes.push_back(c);
        }
        ++copies;
    }
    void ClearBuffer(FakeBuffer& b, u32 off, u64 size, u32 value) {
        std::fill(b.bytes.begin() + off, b.bytes.begin() + off + size, u8(value));
    }
};
struct Memory {
    u64 id = 1, generation = 2;
    std::map<u64, u64> pages;
    u64 MapGeneration() {
        return generation;
    }
    u64 GetID() {
        return id;
    }
    std::optional<DAddr> GpuToCpuAddress(u64 x) {
        auto it = pages.find(Common::AlignDown(x, 4));
        if (it == pages.end())
            return {};
        return it->second + x % 4;
    }
    size_t MaxContinuousRange(u64 x, u64 size) {
        auto start = GpuToCpuAddress(x);
        if (!start)
            return 0;
        u64 count = std::min<u64>(4 - x % 4, size);
        while (count < size) {
            auto next = GpuToCpuAddress(x + count);
            if (!next || *next != *start + count)
                break;
            count += std::min<u64>(4, size - count);
        }
        return count;
    }
};
struct Tracker {
    std::set<u64> gpu, cpu, pre;
    bool IsRegionGpuModified(u64 d, u64 n) {
        for (u64 i = 0; i < n; ++i)
            if (gpu.contains(d + i))
                return true;
        return false;
    }
    bool IsRegionPreflushable(u64 d, u64 n) {
        for (u64 i = 0; i < n; ++i)
            if (pre.contains(d + i))
                return true;
        return false;
    }
    void MarkRegionAsGpuModified(u64 d, u64 n) {
        for (u64 i = 0; i < n; ++i)
            gpu.insert(d + i);
    }
    void MarkRegionAsCpuModified(u64 d, u64 n) {
        for (u64 i = 0; i < n; ++i) {
            cpu.insert(d + i);
            gpu.erase(d + i);
        }
    }
    void MarkRegionAsPreflushable(u64 d, u64 n) {
        for (u64 i = 0; i < n; ++i)
            pre.insert(d + i);
    }
};
struct RangeSet {
    void Add(u64, u64) {}
    void Subtract(u64, u64) {}
};
struct Binding {
    DAddr device_addr = 0;
    u32 size = 0;
    BufferId buffer_id = 0;
    GPUVAddr gather_gpu_addr = 0, gpu_addr = 0;
    u32 gather_size = 0, gather_offset = 0;
};
constexpr size_t NUM_STAGES = 2;
constexpr BufferId NULL_BUFFER_ID = 0;
template <class F>
void ForEachEnabledBit(u32 mask, F f) {
    for (u32 i = 0; i < 32; ++i)
        if (mask & (1u << i))
            f(i);
}
struct Channel {
    u32 enabled_compute_uniform_buffer_mask = 0, enabled_compute_storage_buffers = 0;
    std::array<Binding, 4> compute_uniform_buffers{}, compute_storage_buffers{};
    std::array<u32, NUM_STAGES> enabled_uniform_buffer_masks{}, enabled_storage_buffers{};
    std::array<std::array<Binding, 4>, NUM_STAGES> uniform_buffers{}, storage_buffers{};
};
template <class P>
struct BufferCache {
    using Buffer = FakeBuffer;
    std::mutex mutex;
    Memory* gpu_memory;
    Runtime runtime;
    Tracker memory_tracker;
    Channel channel;
    Channel* channel_state = &channel;
    RangeSet gpu_modified_ranges, uncommitted_gpu_modified_ranges;
    std::deque<Buffer> slot_buffers{Buffer{}};
    std::map<u64, BufferId> ids;
    std::map<u64, u8> ram;
    struct Ring {
        std::vector<Buffer> retired;
        void Push(Buffer&& b) {
            retired.push_back(std::move(b));
        }
    } delayed_destruction_ring;
    struct GatherChunk {
        DAddr device_addr;
        u32 size, offset;
        u8 dirty;
    };
    struct GatherEntry {
        std::unique_ptr<Buffer> buffer;
        std::vector<GatherChunk> chunks;
        u64 last_used = 0;
        u32 prepared_size = 0;
        bool scatter_pending = false;
    };
    std::unordered_map<u64, GatherEntry> gather_buffers;
    u64 gather_used_memory = 0, frame_tick = 0;
    std::vector<u64> scatter_pending, pending_gather_writes;
    bool scatter_busy = false;
    u64 scatter_skip = 0;
    struct ContiguityKey {
        u64 gpu_addr;
        u32 size;
        bool operator==(const ContiguityKey&) const = default;
    };
    struct ContiguityKeyHash {
        size_t operator()(const ContiguityKey& k) const {
            return k.gpu_addr ^ (u64(k.size) << 40);
        }
    };
    mutable std::unordered_map<ContiguityKey, bool, ContiguityKeyHash> contiguity_cache;
    mutable u64 contiguity_cache_generation = ~0ull;
    mutable size_t contiguity_cache_address_space = ~size_t{};
    bool IsRegionPageTableAddressable(u64 d, u64 n) {
        return d != 0 && d + n < 1ull << 39;
    }
    bool IsRegionRegistered(u64, u64) {
        return true;
    }
    BufferId FindBuffer(u64 d, u32 size) {
        ResolveScatter(d, size);
        auto it = ids.find(d);
        if (it != ids.end())
            return it->second;
        BufferId id = slot_buffers.size();
        slot_buffers.emplace_back(runtime, d, size);
        for (u32 i = 0; i < size; ++i)
            slot_buffers.back().bytes[i] = ram[d + i];
        ids[d] = id;
        return id;
    }
    void TouchBuffer(Buffer&, BufferId) {}
    void SynchronizeBuffer(Buffer& b, u64 d, u32 size) {
        bool dirty = false;
        for (u32 i = 0; i < size; ++i)
            dirty |= memory_tracker.cpu.contains(d + i);
        if (dirty) {
            for (u32 i = 0; i < size; ++i) {
                b.bytes[b.Offset(d + i)] = ram[d + i];
                memory_tracker.cpu.erase(d + i);
            }
            NotifyGatherWrite(d, size);
        }
    }
    void ClearDownload(u64, u64) {}
    u64 WidenHotWrite(u64, u64 size) { return size; }
    void MarkGpuUse(Buffer&, u64, u64);
    bool IsRegionGpuModified(u64 d, u64 size) {
        return memory_tracker.IsRegionGpuModified(d, size);
    }
    int dma_copies = 0, dma_clears = 0;
    bool DMACopy(u64, u64, u64) {
        ++dma_copies;
        return true;
    }
    bool DMAClear(u64, u64, u32) {
        ++dma_clears;
        return true;
    }
    Buffer& GatherBuffer(u64, u32);
    void ResolveGatherChunks(u64, u32);
    void NotifyGatherWrite(u64, u64, u8 = 1, u64 = 0);
    void FlushGatherWrites();
    void ScatterGatherEntry(u64, GatherEntry&);
    void ResolveScatter(u64, u64);
    bool IsGpuRangeContiguous(u64, u32) const;
    void TrimGatherBuffers(bool);
    void InvalidateGatherMemory(u64, u64);
    void WriteMemory(u64, u64);
    void ResetGatherBindings(bool);
    void PrepareGatherBindings(bool);
    boost::container::small_vector<Binding*, 32> GatherBindings(bool);
    bool DMACopySplit(u64, u64, u64);
    bool DMAClearSplit(u64, u64, u32);
    std::optional<VideoCore::RasterizerDownloadArea> GetFlushArea(u64, u64);
};
'''
names = [
    'GatherBindings', 'ResetGatherBindings', 'PrepareGatherBindings', 'ResolveGatherChunks',
    'NotifyGatherWrite', 'GatherBuffer', 'FlushGatherWrites', 'ScatterGatherEntry',
    'ResolveScatter', 'IsGpuRangeContiguous', 'TrimGatherBuffers', 'InvalidateGatherMemory',
    'WriteMemory', 'MarkGpuUse', 'DMACopySplit', 'DMAClearSplit', 'GetFlushArea',
]
uma = (root / 'src/video_core/buffer_cache/uma.h').read_text(encoding='utf-8')
uma = uma[uma.index('namespace VideoCommon::Uma'): ] + '\nnamespace Uma = VideoCommon::Uma;\n'
parts = [head, uma] + [func('BufferCache<P>::' + name + '(') for name in names]
# Exercise the current reactive filtering lambda with a controlled download sink.
start = s.index('const auto add_preflushable =')
end = s.index('\n                        };', start) + len('\n                        };')
parts.append(r"""
std::vector<std::pair<u64, u64>> filter(Tracker& memory_tracker, u64 start, u64 end) {
    std::vector<std::pair<u64, u64>> result;
    auto add_download = [&](u64 lo, u64 hi) { result.emplace_back(lo, hi); };
""" + s[start:end] + '\nadd_preflushable(start, end); return result;\n}')
rasterizer = (root / 'src/video_core/renderer_vulkan/vk_rasterizer.cpp').read_text(encoding='utf-8')
start = rasterizer.index('VideoCore::RasterizerDownloadArea RasterizerVulkan::GetFlushArea')
end = rasterizer.index('\n}\n', start) + 3
parts.append(r"""
struct TextureCache {
 std::mutex mutex;
 std::optional<VideoCore::RasterizerDownloadArea> area;
 auto GetFlushArea(u64,u64){return area;}
};
struct RasterizerVulkan {
 std::shared_mutex shutdown_mutex;bool is_shutting_down=false;
 TextureCache texture_cache;BufferCache<int>& buffer_cache;
 explicit RasterizerVulkan(BufferCache<int>& cache):buffer_cache(cache){}
 VideoCore::RasterizerDownloadArea GetFlushArea(u64,u64);
};
""" + rasterizer[start:end])

main = r'''

void check(bool ok, const char* label) {
    if (!ok)
        throw std::runtime_error(label);
    std::cout << "PASS " << label << '\n';
}
Memory split(u64 id = 1) {
    Memory m;
    m.id = id;
    m.pages = {{64, 1008}, {68, 1004}, {72, 1000}};
    return m;
}
void seed(BufferCache<int>& c) {
    for (u64 d = 1000; d < 1012; ++d)
        c.ram[d] = u8(d - 990);
}
int main() {
    auto m = split();
    BufferCache<int> c;
    c.gpu_memory = &m;
    seed(c);
    auto& scratch = c.GatherBuffer(64, 12);
    check(scratch.bytes[0] == 18 && scratch.bytes[4] == 14 && scratch.bytes[8] == 10,
          "descending physical chunks gathered in GPU order");
    check(!Uma::CanWriteDirectly(true, c.slot_buffers[c.ids.at(1008)].page_gpu_tick, 0, 4, 20),
          "gather GPU read prevents a concurrent direct UMA write");
    check(Uma::CanWriteDirectly(true, c.slot_buffers[c.ids.at(1008)].page_gpu_tick, 0, 4, 21),
          "gather source allows direct UMA writes after GPU completion");
    std::fill(scratch.bytes.begin(), scratch.bytes.end(), 99);
    c.pending_gather_writes = {64};
    c.FlushGatherWrites();
    c.GatherBuffer(64, 8);
    check(!Uma::CanWriteDirectly(true, c.slot_buffers[c.ids.at(1000)].page_gpu_tick, 0, 4, 20),
          "scatter GPU write prevents a concurrent direct UMA write");
    check(c.slot_buffers[c.ids.at(1000)].bytes[0] == 99 &&
              c.gather_buffers.at(64).buffer->bytes[0] == 99,
          "shrinking view preserves all old pending writes");
    std::fill(c.gather_buffers.at(64).buffer->bytes.begin(),
              c.gather_buffers.at(64).buffer->bytes.end(), 88);
    c.pending_gather_writes = {64};
    c.FlushGatherWrites();
    for (u64 d = 1008; d < 1012; ++d) {
        c.ram[d] = 42;
    }
    c.WriteMemory(1008, 4);
    auto& after = c.GatherBuffer(64, 8);
    check(after.bytes[0] == 42 && after.bytes[4] == 88,
          "CPU write overrides touched chunk while preserving other GPU writes");
    Memory a;
    a.id = 10;
    a.pages = {{64, 2000}, {68, 2004}};
    auto b = split(11);
    BufferCache<int> cache;
    cache.gpu_memory = &a;
    check(cache.IsGpuRangeContiguous(64, 8), "first address space contiguous");
    cache.gpu_memory = &b;
    check(!cache.IsGpuRangeContiguous(64, 8),
          "same generation in another address space cannot hit cache");
    auto g = split();
    BufferCache<int> views;
    views.gpu_memory = &g;
    seed(views);
    views.channel.enabled_compute_storage_buffers = 3;
    views.channel.compute_storage_buffers[0] = {1008, 8, 0, 0, 64};
    views.channel.compute_storage_buffers[1] = {1004, 8, 0, 0, 68};
    views.ResetGatherBindings(true);
    views.PrepareGatherBindings(true);
    auto x = views.channel.compute_storage_buffers[0], y = views.channel.compute_storage_buffers[1];
    check(x.gather_gpu_addr == 64 && y.gather_gpu_addr == 64 && x.gather_size == 12 &&
              y.gather_offset == 4,
          "overlapping writable views share allocation with original offsets");
    auto& shared = views.GatherBuffer(x.gather_gpu_addr, x.gather_size);
    shared.bytes[y.gather_offset] = 77;
    check(views.GatherBuffer(y.gather_gpu_addr, y.gather_size).bytes[4] == 77,
          "second view observes same-command scratch writes");
    views.pending_gather_writes = {64};
    views.FlushGatherWrites();
    views.InvalidateGatherMemory(1004, 4);
    check(views.gather_buffers.empty() && views.gather_used_memory == 0 &&
              !views.delayed_destruction_ring.retired.empty(),
          "unmap releases scratch through deferred retirement");
    g.pages.erase(68);
    ++g.generation;
    ++g.generation;
    BufferCache<int> holes;
    holes.gpu_memory = &g;
    seed(holes);
    auto& hole = holes.GatherBuffer(65, 7);
    check(hole.bytes[0] == 19 && hole.bytes[3] == 0 && hole.bytes[6] == 0,
          "unaligned unmapped hole is skipped and zero filled");
    auto trim_mem = split();
    BufferCache<int> trim;
    trim.gpu_memory = &trim_mem;
    for (u64 i = 0; i < 140; ++i) {
        trim_mem.pages[100 + i * 4] = 5000 + i * 8;
        trim.GatherBuffer(100 + i * 4, 4);
    }
    trim.TrimGatherBuffers(false);
    check(trim.gather_buffers.size() == 128, "scratch cache entry budget enforced");
    trim.TrimGatherBuffers(true);
    check(trim.gather_buffers.empty() && trim.gather_used_memory == 0,
          "critical pressure retires scratch allocations");

    Memory growth_mem;
    growth_mem.pages = {{64, 1008}};
    BufferCache<int> growth;
    growth.gpu_memory = &growth_mem;
    seed(growth);
    growth.GatherBuffer(64, 4);
    auto& larger = growth.GatherBuffer(64, 8);
    check(larger.bytes[0] == 18 && larger.bytes[4] == 0,
          "growing into a hole preserves mapped data with unchanged layout");
    std::fill(larger.bytes.begin(), larger.bytes.end(), 91);
    growth.pending_gather_writes = {64};
    growth.FlushGatherWrites();
    check(growth.GatherBuffer(64, 12).bytes[0] == 91,
          "growth into a hole scatters pending writes before replacing allocation");
    auto* old_buffer = growth.gather_buffers.at(64).buffer.get();
    auto old_bytes = growth.gather_used_memory;
    FakeBuffer::fail_next = true;
    bool allocation_failed = false;
    try {
        growth.GatherBuffer(64, 16);
    } catch (const std::bad_alloc&) {
        allocation_failed = true;
    }
    check(allocation_failed && growth.gather_buffers.at(64).buffer.get() == old_buffer &&
              growth.gather_used_memory == old_bytes,
          "allocation failure retains previous scratch and memory accounting");
    growth.pending_gather_writes = {64};
    growth.FlushGatherWrites();
    growth.runtime.fail_copy = true;
    bool copy_failed = false;
    try {
        growth.ResolveScatter(0, 0);
    } catch (const std::runtime_error&) {
        copy_failed = true;
    }
    check(copy_failed && !growth.scatter_busy && growth.gather_buffers.at(64).scatter_pending,
          "failed scatter preserves pending writes and releases recursion guard");
    growth.ResolveScatter(0, 0);
    check(!growth.gather_buffers.at(64).scatter_pending, "failed scatter can be retried");
    auto dma = split();
    dma.pages[128] = 3000;
    dma.pages[132] = 3008;
    BufferCache<int> d;
    d.gpu_memory = &dma;
    check(d.DMACopySplit(64, 128, 8) && d.dma_copies == 2,
          "non-contiguous DMA copy executes complete plan");
    d.dma_copies = 0;
    check(!d.DMACopySplit(64, 68, 8) && d.dma_copies == 0,
          "overlapping DMA falls back before modifying any source");
    dma.pages.erase(132);
    check(!d.DMACopySplit(64, 128, 8) && d.dma_copies == 0,
          "DMA mapping hole rejects whole plan before execution");
    check(d.DMAClearSplit(64, 2, 5) && d.dma_clears == 2,
          "DMA clear splits byte count into word counts");
    BufferCache<int> reads;
    reads.gpu_memory = &m;
    reads.memory_tracker.MarkRegionAsGpuModified(1008, 4);
    auto area = reads.GetFlushArea(1008, 4);
    check(!area->preemtive, "first CPU read requires buffer flush");
    reads.memory_tracker.MarkRegionAsGpuModified(1008, 4);
    check(!reads.GetFlushArea(1008, 4)->preemtive,
          "preflushable flag cannot bypass newer GPU writes");
    RasterizerVulkan raster(reads);
    raster.texture_cache.area = VideoCore::RasterizerDownloadArea{1000, 1020, true};
    auto merged = raster.GetFlushArea(1008, 4);
    check(!merged.preemtive && merged.start_address == 1000 && merged.end_address == 1020,
          "texture result cannot hide buffer writes on CPU read");
    Tracker tracker;
    check(filter(tracker, 4, 4 + 512_KiB).empty(), "reactive flush skips unread large ranges");
    tracker.MarkRegionAsPreflushable(8, 4);
    auto filtered = filter(tracker, 4, 4 + 512_KiB);
    check(filtered.size() == 1 && filtered[0] == std::pair<u64, u64>{8, 12},
          "reactive flush retains only CPU-read pages");
    check(filter(tracker, 4, 4 + 256_KiB).size() == 1, "small GPU-written ranges still downloaded");
}
'''
(p/'phase2_tests.cpp').write_text('\n'.join(parts)+main,encoding='utf-8')

source = p / "phase2_tests.cpp"
executable = p / ("gather_buffer_tests.exe" if os.name == "nt" else "gather_buffer_tests")
subprocess.run([args.cxx, "-std=c++23", "-O0", "-Wall", "-Wextra", str(source), "-o", str(executable)], check=True)
subprocess.run([str(executable)], check=True)
