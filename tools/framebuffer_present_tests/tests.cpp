// SPDX-License-Identifier: GPL-2.0-or-later
#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>
using u8 = std::uint8_t;
using u64 = std::uint64_t;
using DAddr = u64;
using ImageId = std::size_t;
using ImageMapId = std::size_t;
namespace boost::container {
template<class T, std::size_t> using small_vector = std::vector<T>;
}
namespace Service::android { enum class PixelFormat { Rgba8888, Rgb565, Bgra8888 }; }
namespace Tegra {
enum class BlendMode { Opaque, Premultiplied };
struct FramebufferConfig {
    Service::android::PixelFormat pixel_format{};
    BlendMode blending{};
};
}
namespace Settings {
struct { struct { bool active = false; } resolution_info; } values;
}
enum class PixelFormat { A8B8G8R8_UNORM, B8G8R8A8_UNORM, R5G6B5_UNORM };
enum class ImageViewType { e2D };
enum class SwizzleSource { R, G, B, OneFloat };
struct ImageViewInfo {
    ImageViewType type;
    PixelFormat format;
    u8 x_source{}, y_source{}, z_source{}, w_source{};
};
enum ImageFlagBits : unsigned { CpuModified = 4, GpuModified = 8, Tracked = 16, Rescaled = 8192 };
bool True(unsigned flags) { return flags != 0; }
bool False(unsigned flags) { return flags == 0; }
struct ImageCopy { std::size_t src, dst, size; };
struct AliasedImage { std::vector<ImageCopy> copies; ImageId id; };
struct Image {
    DAddr cpu_addr{};
    DAddr gpu_addr{};
    std::size_t guest_size_bytes = 16;
    std::vector<unsigned> pixels{10, 10, 10, 10};
    std::vector<unsigned> cpu_pixels{20, 20, 20, 20};
    std::vector<std::size_t> image_view_ids{1};
    std::vector<AliasedImage> aliased_images;
    u64 modification_tick{};
    unsigned flags = GpuModified | Tracked;
    std::size_t lru_index{};
    bool IsRescaled() const { return True(flags & Rescaled); }
};
using ImageBase = Image;
enum class ShadowKind { Texture };
struct PhysicalShadow {
    unsigned reads{}, writes{};
    void Observe(int&, DAddr, std::size_t, ShadowKind, bool write, DAddr) {
        if (write) ++writes; else ++reads;
    }
};
#include "framebuffer_present_config.inc"
struct ImageMapView { ImageId image_id{}; };
struct ImageView { ImageId image_id{}; ImageViewInfo info{}; };
struct Params { using ImageView = ::ImageView; };
template<class P> struct TextureCache {
    static constexpr unsigned CITRON_PAGEBITS = 14;
    using Image = ::Image;
    std::array<Image, 12> slot_images;
    std::array<ImageMapView, 12> slot_map_views;
    std::array<ImageView, 12> slot_image_views;
    std::unordered_map<u64, std::vector<ImageMapId>> page_table;
    std::size_t copies{}, uploads{}, tracks{}, scales{}, modifications{};
    bool allow_rescale = true;
    u64 frame_tick = 77;
    struct Lru {
        std::size_t touches{};
        void Touch(std::size_t, u64) { ++touches; }
    } lru_cache;
    void Add(ImageId id, DAddr address, u64 tick) {
        slot_images[id].cpu_addr = address;
        slot_images[id].modification_tick = tick;
        slot_map_views[id].image_id = id;
        page_table[address >> CITRON_PAGEBITS].push_back(id);
    }
    std::size_t FindOrEmplaceImageView(ImageId id, ImageViewInfo info) {
        slot_image_views[id] = {id, info}; return id;
    }
    void RefreshContents(Image& image, ImageId) {
        if (False(image.flags & CpuModified)) return;
        image.pixels = image.cpu_pixels;
        image.flags &= ~CpuModified;
        ++uploads;
    }
    void TrackImage(Image& image, ImageId) { image.flags |= Tracked; ++tracks; }
    void MarkModification(Image&, ShadowKind = ShadowKind::Texture) { ++modifications; }
    bool ImageCanRescale(Image&) { return allow_rescale; }
    void ScaleUp(Image& image) { image.flags |= Rescaled; image.image_view_ids.clear(); ++scales; }
    void ScaleDown(Image& image) { image.flags &= ~Rescaled; image.image_view_ids.clear(); ++scales; }
    void CopyImage(ImageId dst, ImageId src, const std::vector<ImageCopy>& regions) {
        for (const auto& r : regions)
            std::copy_n(slot_images[src].pixels.begin() + r.src, r.size,
                        slot_images[dst].pixels.begin() + r.dst);
        ++copies;
    }
    std::pair<typename P::ImageView*, bool> TryFindFramebufferImageView(const Tegra::FramebufferConfig&, DAddr);
    void SynchronizeAliases(ImageId);
#if FRAMEBUFFER_PRESENT_HAS_SHADOW
    PhysicalShadow* physical_shadow{};
    int* gpu_memory{};
    void PrepareImage(ImageId, bool, bool, ShadowKind = ShadowKind::Texture);
#else
    void PrepareImage(ImageId, bool, bool);
#endif
};
#include "framebuffer_present.inc"
void require(bool ok, const char* message) {
    if (!ok) throw std::runtime_error(message);
}
int main() try {
    constexpr DAddr address = 0xb021000;
    const Tegra::FramebufferConfig config{};
    TextureCache<Params> cache;
    cache.Add(1, address, 10);
    cache.Add(2, address + 4, 20);
    cache.slot_images[2].pixels = {42, 43, 44, 45};
    cache.slot_images[1].aliased_images.push_back({{{0, 1, 2}}, 2});
    auto [view, scaled] = cache.TryFindFramebufferImageView(config, address);
    require(view && !scaled, "display image not found");
    require(cache.slot_images[view->image_id].pixels == std::vector<unsigned>{10, 42, 43, 10},
            "presentation returned stale background instead of the newer partial alias");
    require(cache.copies == 1 && cache.slot_images[1].modification_tick == 20,
            "alias copy/tick did not complete");
    require(cache.modifications == 0 && cache.lru_cache.touches == 1,
            "presentation must touch LRU without marking a new write");
    cache.TryFindFramebufferImageView(config, address);
    require(cache.copies == 1, "unchanged frame redundantly copied alias");
    cache.slot_images[2].pixels[0] = 99;
    cache.slot_images[2].modification_tick = 30;
    cache.TryFindFramebufferImageView(config, address);
    require(cache.slot_images[1].pixels[1] == 99 && cache.copies == 2,
            "later alias update was not displayed");

    TextureCache<Params> cpu;
    cpu.Add(1, address, 3); cpu.slot_images[1].flags = CpuModified;
    cpu.TryFindFramebufferImageView(config, address);
    require(cpu.uploads == 1 && cpu.slot_images[1].pixels[0] == 20,
            "CPU-dirty display image was not refreshed");
    require(cpu.modifications == 0, "CPU refresh incorrectly marked GPU write");

    TextureCache<Params> ordered;
    ordered.Add(1, address, 1); ordered.Add(2, address+4, 20); ordered.Add(3, address+8, 30);
    ordered.slot_images[2].pixels = {21, 22, 23, 24};
    ordered.slot_images[3].pixels = {31, 32, 33, 34};
    ordered.slot_images[1].aliased_images = {{{{0, 0, 2}}, 3}, {{{0, 0, 2}}, 2}};
    ordered.TryFindFramebufferImageView(config, address);
    require(ordered.slot_images[1].pixels[0] == 31 && ordered.copies == 2,
            "overlapping aliases were not copied in modification order");

    TextureCache<Params> rescale;
    rescale.Add(1, address, 1); rescale.Add(2, address+4, 2);
    rescale.slot_images[2].flags |= Rescaled;
    rescale.slot_images[1].aliased_images = {{{{0, 0, 1}}, 2}};
    auto [new_view, new_scaled] = rescale.TryFindFramebufferImageView(config, address);
    require(new_view && new_scaled && rescale.scales == 1,
            "presentation view/scaled flag was taken before alias preparation");

    TextureCache<Params> clean;
    clean.Add(1, address, 50); clean.Add(2, address, 40);
    auto [latest, ignored] = clean.TryFindFramebufferImageView(config, address);
    (void)ignored;
    require(latest && latest->image_id == 1 && clean.copies == 0 && clean.uploads == 0,
            "latest exact-address selection or clean-image fast path changed");
    require(latest->info.w_source == static_cast<u8>(SwizzleSource::OneFloat),
            "opaque display alpha changed");
    require(!clean.TryFindFramebufferImageView(config, address+0x100000).first,
            "unmapped display address must fall back");
    require(!clean.TryFindFramebufferImageView(config, address+4).first,
            "overlap alone is not an exact-address candidate");
    clean.slot_images[1].image_view_ids.clear(); clean.slot_images[2].image_view_ids.clear();
    require(!clean.TryFindFramebufferImageView(config, address).first,
            "image without display views must fall back");
#if FRAMEBUFFER_PRESENT_HAS_SHADOW
    TextureCache<Params> shadow_cache;
    PhysicalShadow shadow;
    int memory = 0;
    shadow_cache.Add(1, address, 1);
    shadow_cache.physical_shadow = &shadow;
    shadow_cache.gpu_memory = &memory;
    shadow_cache.TryFindFramebufferImageView(config, address);
    require(shadow.reads == 1 && shadow.writes == 0, "presentation changed shadow observation into a write");
#endif
    std::cout << "PASS: partial aliases, refresh, later writes, ordering, rescale, selection and fallback controls\n";
    return 0;
} catch (const std::exception& e) {
    std::cerr << "FAIL: " << e.what() << '\n'; return 1;
}
