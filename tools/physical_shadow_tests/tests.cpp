// SPDX-License-Identifier: GPL-2.0-or-later
#include <map>
#include "video_core/physical_shadow.h"
#define FMT_HEADER_ONLY
#include <fmt/format.h>
using namespace VideoCommon;
constexpr size_t NUM_STAGES = 2;
struct Binding {
    u64 device_addr{}, gpu_addr{}, size{}, gather_gpu_addr{}, gather_size{};
    u32 buffer_id{1};
};
constexpr u32 NULL_BUFFER_ID = 0;
struct Channel {
    u32 enabled_compute_uniform_buffer_mask{}, enabled_compute_storage_buffers{},
        written_compute_storage_buffers{}, enabled_compute_texture_buffers{},
        written_compute_texture_buffers{};
    std::array<Binding, 4> compute_uniform_buffers{}, compute_storage_buffers{},
        compute_texture_buffers{};
    std::array<u32, NUM_STAGES> enabled_uniform_buffer_masks{}, enabled_storage_buffers{},
        written_storage_buffers{}, enabled_texture_buffers{}, written_texture_buffers{};
    std::array<std::array<Binding, 4>, NUM_STAGES> uniform_buffers{}, storage_buffers{},
        texture_buffers{};
    std::array<Binding, 4> transform_feedback_buffers{};
};
template <class P>
struct BufferCache {
    Channel channel;
    Channel* channel_state{&channel};
    Tegra::MemoryManager* gpu_memory{};
    struct Engine {
        struct {
            bool transform_feedback_enabled{};
        } regs;
    } engine;
    Engine* maxwell3d{&engine};
    struct Buffer {
        bool direct{};
    };
    std::array<Buffer, 2> slot_buffers{};
    struct Gather {
        std::unique_ptr<Buffer> buffer;
    };
    std::map<u64, Gather> gather_buffers;
    static bool IsDirectGuest(const Buffer& b) {
        return b.direct;
    }
    template <class F>
    void ForEachEnabledBit(u32 mask, F&& f) {
        for (u32 i = 0; i < 4; ++i)
            if ((mask >> i) & 1)
                f(i);
    }
    void ObservePhysicalBindings(PhysicalShadow&, bool);
};
/* BINDING_VISITOR */
namespace ImageFlagBits {
constexpr u32 GpuModified = 2;
constexpr u32 CpuModified = 4, Tracked = 8;
} // namespace ImageFlagBits
bool False(u32 flags) {
    return !flags;
}
using ImageId = u32;
struct ImageBase {
    u64 gpu_addr{}, cpu_addr{}, guest_size_bytes{}, modification_tick{};
    u32 flags{};
    size_t lru_index{};
};
template <class P>
struct TextureCache {
    PhysicalShadow* physical_shadow{};
    Tegra::MemoryManager* gpu_memory{};
    u64 modification_tick{};
    using Image = ImageBase;
    std::array<Image, 2> slot_images{};
    struct Lru {
        void Touch(size_t, u64) {}
    } lru_cache;
    u64 frame_tick{};
    void TrackImage(Image&, ImageId) {}
    void RefreshContents(Image&, ImageId) {}
    void SynchronizeAliases(ImageId) {}
    void MarkModification(ImageBase&, ShadowKind = ShadowKind::Texture) noexcept;
    void PrepareImage(ImageId, bool, bool, ShadowKind = ShadowKind::Texture);
};
/* TEXTURE_HOOK */
/* TEXTURE_PREPARE */

namespace ReportFixture {
std::vector<std::string> messages;
#define LOG_INFO(category, ...) messages.push_back(fmt::format(__VA_ARGS__))
struct RasterizerVulkan {
    std::unique_ptr<PhysicalShadow> physical_shadow;
    void ReportPhysicalShadow() noexcept;
};
/* SHADOW_REPORT */
#undef LOG_INFO
} // namespace ReportFixture

struct RacyMemory {
    Tegra::MemoryManager& real;
    bool fail{}, remap{};
    size_t GetID() {
        return real.GetID();
    }
    auto GpuToCpuAddress(u64 a) {
        return real.GpuToCpuAddress(a);
    }
    auto ResolvePhysicalRanges(u64 a, u64 n, Tegra::PhysicalResolveTiming* timing = nullptr) {
        if (fail)
            throw std::bad_alloc{};
        auto snapshot = real.ResolvePhysicalRanges(a, n, timing);
        if (remap)
            real.memory.Map(0x10000, 0x15000);
        return snapshot;
    }
};
int main() {
    constexpr u64 G = 0x10000, D = 0x10000, P = 4096;
    DeviceFixture dev;
    MemoryManager gpu{dev}, other{dev};
    dev.Map(D, 0x5000, 4 * P);
    dev.Map(D + 8 * P, 0x5000);
    gpu.Map(G, D, 4 * P);
    gpu.Map(G + 8 * P, D + 8 * P, P);
    other.Map(G, D + 8 * P, P);
    const u64 gpu_generation = gpu.MapGeneration(), device_generation = dev.MapGeneration();
    PhysicalShadow shadow;
    shadow.BeginDispatch();
    shadow.Observe(gpu, G, P, ShadowKind::Scratch, true);
    shadow.Observe(gpu, G, P, ShadowKind::Texel, true, D);
    shadow.Observe(gpu, G + 8 * P + 17, P - 17, ShadowKind::Buffer, false, D + 8 * P + 17);
    shadow.Observe(other, G, P, ShadowKind::Buffer, true, D + 8 * P);
    shadow.EndDispatch();
    assert(shadow.Counters().different_daddr_aliases > 0);
    assert(shadow.Counters().different_manager_aliases > 0);
    assert(gpu.MapGeneration() == gpu_generation && dev.MapGeneration() == device_generation);
    assert(shadow.Counters().dispatches == 1 && shadow.Counters().max_dispatch_queries == 4);
    assert(shadow.Counters().observer_ns >= shadow.Counters().query_ns);
    assert(shadow.Counters().resolve_latency.count == shadow.Counters().queries);
    assert(shadow.Counters().dispatch_latency.count == 1);
    assert(shadow.Counters().max_distinct_gpu_refs >= 3);
    assert(shadow.Counters().max_distinct_device_refs == 2);
    assert(shadow.Counters().writable_alias_pairs > 0);
    std::cout << "PASS physical aliases across DAddr/MemoryManager, partial ranges, timing; "
                 "mapping state unchanged\n";

    const auto queries = shadow.Counters().queries;
    shadow.Observe(gpu, G, P, ShadowKind::Scratch, true);
    assert(shadow.Counters().queries == queries && shadow.Counters().cache_hits == 1);
    gpu.Map(G + 16 * P, D, P); // unrelated whole-address-space generation invalidates cached stamp
    shadow.Observe(gpu, G, P, ShadowKind::Scratch, true);
    assert(shadow.Counters().cache_invalidations == 1 && shadow.Counters().queries == queries + 1);
    shadow.Observe(gpu, G, P, ShadowKind::Scratch, true);
    assert(shadow.Counters().cache_hits == 2 && shadow.Counters().queries == queries + 1);
    dev.Map(D, 0x9000);
    shadow.Observe(gpu, G, P, ShadowKind::Scratch, true);
    assert(shadow.Counters().cache_invalidations == 2);
    assert(shadow.Counters().generation_invalidations == 2);
    assert(shadow.Counters().generation_requeries == 2);
    std::cout << "PASS cache reuse and GPU/device mapping-generation invalidation\n";

    PhysicalShadow coverage;
    coverage.Observe(gpu, G, P, ShadowKind::Texture, true, D + P); // stale resource provenance
    coverage.Observe(gpu, G + 32 * P, P, ShadowKind::Texel, true); // hole
    coverage.Observe(gpu, G, PhysicalShadow::MaxRange + 1, ShadowKind::Buffer, true);
    assert(coverage.Counters().provenance_mismatches == 1 && coverage.Counters().holes == 1);
    assert(coverage.Counters().budget_drops == 1);
    RacyMemory fault{gpu, true, false};
    coverage.Observe(fault, G, P, ShadowKind::Scratch, true);
    assert(coverage.Counters().errors == 1);
    fault.fail = false;
    fault.remap = true;
    coverage.Observe(fault, G, P, ShadowKind::Scratch, true);
    assert(coverage.Counters().snapshot_invalidations == 1);
    for (const auto& c : coverage.Counters().coverage)
        assert(c.registered_writes == 0);
    std::cout << "PASS holes, budget, stale provenance, injected OOM and mixed-generation snapshot "
                 "fail observation only\n";

    PhysicalShadow hooks;
    BufferCache<int> buffers;
    buffers.gpu_memory = &gpu;
    buffers.channel.compute_uniform_buffers[0] = {D, G, 16};
    buffers.channel.enabled_compute_uniform_buffer_mask = 1;
    buffers.channel.compute_storage_buffers[0] = {D, G + 17, 32, G, 2 * P};
    buffers.channel.enabled_compute_storage_buffers =
        buffers.channel.written_compute_storage_buffers = 1;
    buffers.channel.compute_texture_buffers[0] = {D, G, P};
    buffers.channel.enabled_compute_texture_buffers =
        buffers.channel.written_compute_texture_buffers = 1;
    hooks.BeginDispatch();
    buffers.ObservePhysicalBindings(hooks, true);
    TextureCache<int> textures{&hooks, &gpu};
    ImageBase image{G, D, P};
    textures.MarkModification(image);
    hooks.EndDispatch();
    assert(hooks.Counters().coverage[0].observations == 1);
    for (size_t i = 1; i < 4; ++i)
        assert(hooks.Counters().coverage[i].registered_writes == 1);
    assert(hooks.Counters().historical_aliases > 0);
    assert(image.flags == ImageFlagBits::GpuModified && image.modification_tick == 1);
    assert(buffers.channel.compute_storage_buffers[0].size == 32);
    buffers.channel.uniform_buffers[1][0] = {D, G, 16};
    buffers.channel.enabled_uniform_buffer_masks[1] = 1;
    buffers.channel.storage_buffers[1][0] = {D, G + P, P};
    buffers.channel.enabled_storage_buffers[1] = buffers.channel.written_storage_buffers[1] = 1;
    buffers.channel.texture_buffers[1][0] = {D, G, P};
    buffers.channel.enabled_texture_buffers[1] = buffers.channel.written_texture_buffers[1] = 1;
    buffers.channel.transform_feedback_buffers[0] = {D, 0, P};
    buffers.engine.regs.transform_feedback_enabled = true;
    buffers.ObservePhysicalBindings(hooks, false);
    assert(hooks.Counters().coverage[0].unresolved ==
           2); // stale contiguous SSBO DAddr plus TF without GPU VA
    const auto count = hooks.Counters().coverage[3].observations;
    textures.physical_shadow = nullptr;
    textures.MarkModification(image);
    assert(hooks.Counters().coverage[3].observations == count && image.modification_tick == 2);
    std::cout << "PASS extracted compute/graphics buffer visitor and texture producer hook; "
                 "scratch padding and unresolved TF\n";

    PhysicalShadow split;
    const u64 C = Tegra::PhysicalBackingChunkSize;
    dev.Map(D + 32 * P, C - P, 2 * P);
    gpu.Map(G + 32 * P, D + 32 * P, 2 * P);
    split.Observe(gpu, G + 32 * P, 2 * P, ShadowKind::Scratch, true);
    dev.Map(D + 48 * P, 0x5000);
    dev.Map(D + 49 * P, 0x5000);
    gpu.Map(G + 48 * P, D + 48 * P, 2 * P);
    split.Observe(gpu, G + 48 * P, 2 * P, ShadowKind::Scratch, true);
    assert(split.Counters().coverage[1].registered_writes == 2);
    assert(split.Counters().coverage[1].split_observations == 2);
    assert(split.Counters().coverage[1].registered_segments == 4);
    assert(split.Counters().coverage[1].size_buckets[2] == 2);
    std::cout << "PASS cross-chunk and repeated-page geometry registered without "
                 "fallback/ownership decisions\n";

    PhysicalShadow lifetime;
    {
        DeviceFixture temporary_device;
        MemoryManager temporary_gpu{temporary_device};
        temporary_device.Map(D, 0x5000);
        temporary_gpu.Map(G, D, P);
        lifetime.Observe(temporary_gpu, G, P, ShadowKind::Buffer, true);
    }
    lifetime.Observe(gpu, G, P, ShadowKind::Buffer, true);
    assert(lifetime.Counters().historical_aliases == 0);
    std::cout << "PASS dead manager/backing tokens remain inert; epochs prevent false physical "
                 "identity\n";

    PhysicalShadow bounded;
    for (u64 i = 0; i < PhysicalShadow::Capacity + 5; ++i) {
        gpu.Map(G + i * P, D, P);
        bounded.Observe(gpu, G + i * P, P, ShadowKind::Buffer, true);
    }
    assert(bounded.Counters().evictions == 5);
    assert(bounded.Counters().active_entries == PhysicalShadow::Capacity);
    assert(bounded.Counters().peak_entries == PhysicalShadow::Capacity);
    assert(bounded.Counters().peak_metadata_bytes >= bounded.Counters().metadata_bytes);
    std::cout << "PASS bounded historical metadata window with explicit evictions\n";

    ShadowLatency latency;
    for (u64 ns : {1, 2, 4, 8, 16, 32, 64, 128, 256, 512})
        latency.Add(ns);
    assert(latency.Percentile(50) == 16 && latency.Percentile(95) == 512 &&
           latency.Percentile(99) == 512);
    PhysicalShadow references;
    dev.Map(D, 0x5000);
    gpu.Map(G, D, P);
    gpu.Map(G + 8 * P, D + 8 * P, P);
    other.Map(G, D + 8 * P, P);
    references.Observe(gpu, G, P, ShadowKind::Buffer, false);
    references.Observe(gpu, G, P, ShadowKind::Texel, false); // two descriptors, one GPU reference
    references.Observe(gpu, G + 8 * P, P, ShadowKind::Buffer, false);
    references.Observe(other, G, P, ShadowKind::Buffer, false);
    assert(references.Counters().max_distinct_gpu_refs == 3);
    assert(references.Counters().max_distinct_device_refs == 2);
    assert(references.Counters().readonly_alias_pairs > 0 &&
           references.Counters().writable_alias_pairs == 0);
    references.Observe(gpu, G, P, ShadowKind::Scratch, true);
    assert(references.Counters().max_distinct_gpu_refs == 3 &&
           references.Counters().max_writable_refs == 1);
    assert(references.Counters().sample_length == P);
    std::cout << "PASS percentile buckets, distinct references and read-only versus "
                 "potential-write classification\n";

    Tegra::PhysicalResolveTiming timing;
    gpu.ResolvePhysicalRanges(G, P, &timing);
    assert(timing.walk_ns > 0);
    gpu.ResolvePhysicalRanges(G, P); // default path uses null timer sinks
    std::cout << "PASS production optional resolver timing separates lock acquisition and walk; "
                 "default sinks absent\n";
    PhysicalShadow classified;
    buffers.slot_buffers[1].direct = true;
    buffers.channel.compute_uniform_buffers[0].buffer_id = 1;
    buffers.ObservePhysicalBindings(classified, true);
    assert(classified.Counters()
               .coverage[static_cast<size_t>(ShadowKind::DirectBuffer)]
               .observations == 1);
    textures.physical_shadow = &classified;
    textures.MarkModification(image, ShadowKind::RenderTarget);
    assert(classified.Counters()
               .coverage[static_cast<size_t>(ShadowKind::RenderTarget)]
               .write_intents == 1);
    assert(classified.Counters().coverage[static_cast<size_t>(ShadowKind::Texture)].observations ==
           0);
    textures.slot_images[0] = image;
    const auto tick = textures.modification_tick;
    textures.PrepareImage(0, false, false);
    assert(classified.Counters().coverage[static_cast<size_t>(ShadowKind::Texture)].observations ==
           1);
    assert(classified.Counters().coverage[static_cast<size_t>(ShadowKind::Texture)].write_intents ==
           0);
    assert(textures.modification_tick == tick);
    std::cout << "PASS direct/staged classifications and explicit render-target producer tag\n";
    ReportFixture::RasterizerVulkan reporting;
    reporting.ReportPhysicalShadow();
    assert(ReportFixture::messages.empty());
    reporting.physical_shadow = std::make_unique<PhysicalShadow>();
    reporting.ReportPhysicalShadow();
    assert(ReportFixture::messages.size() == 10);
    assert(ReportFixture::messages[0].find("coverage=unknown") != std::string::npos);
    assert(ReportFixture::messages[2].find("resolve_p99_upper_ns=") != std::string::npos);
    assert(ReportFixture::messages[8].find("kind=render_target") != std::string::npos);
    std::cout << "PASS production report with real fmt: explicit unknown coverage and percentile fields; disabled report is inert\n";
}
