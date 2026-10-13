// SPDX-FileCopyrightText: Copyright 2019 yuzu Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include <algorithm>
#include <memory>
#include <optional>
#include <vector>
#include <span>
#include "common/common_funcs.h"
#include "common/common_types.h"
#include "common/published_guest_chunk.h"
#include "common/virtual_buffer.h"

namespace Common {

enum class MemoryPermission : u32 {
    Read = 1 << 0,
    Write = 1 << 1,
    ReadWrite = Read | Write,
    Execute = 1 << 2,
};
DECLARE_ENUM_FLAG_OPERATORS(MemoryPermission)

/// Most file descriptors a backing can be made of.
constexpr size_t MaxBackingChunks = 16;

/// CPU-ready exported chunks. Implementations serialize their driver context internally.
/// CreateChunk returns an owned fd, or -1; successful chunks are zeroed and CPU-accessible.
/// No renderer imports or GPU submissions are permitted through this interface.
class GuestBackingExporter {
public:
    virtual ~GuestBackingExporter() = default;
    virtual int CreateChunk(size_t size) = 0;
    virtual void ReleaseChunk(int fd) noexcept = 0;
    virtual std::optional<GuestChunkExportInfo> DescribeChunk(int /*fd*/) { return std::nullopt; }
};

struct LazyBackingParams {
    size_t chunk_size{32ULL << 20};
    std::shared_ptr<GuestBackingExporter> exporter;
};

struct BackingStats {
    u64 chunks_created{};
    u64 chunk_cache_hits{};
    u64 active_chunks{};
    u64 peak_fd_count{}; // backing fds owned by this arena
    u64 peak_vma_count{}; // sampled process VMAs
    u64 chunks_exported{};
    u64 export_failures{};
    u64 cpu_only_fallback_chunks{};
    u64 export_duration_ns{};
    u64 peak_export_duration_ns{};
};

/// A piece of the backing memory when the backing is a row of equally sized file descriptors.
struct BackingChunkRange {
    size_t chunk;  ///< Index of the file descriptor
    size_t offset; ///< Offset inside that file descriptor
    size_t length; ///< Bytes of the request that lie in it
};

/// The part of [host_offset, host_offset + length) that lies in the chunk holding host_offset.
/// The request lies in one chunk exactly when the returned length equals `length`.
[[nodiscard]] constexpr BackingChunkRange FirstChunkRange(size_t host_offset, size_t length,
                                                          size_t chunk_size) noexcept {
    const size_t offset = host_offset % chunk_size;
    return {host_offset / chunk_size, offset, std::min(length, chunk_size - offset)};
}

/**
 * A low level linear memory buffer, which supports multiple mappings
 * Its purpose is to rebuild a given sparse memory layout, including mirrors.
 */
struct GuestBackingRange {
    int fd{-1}; // borrowed; Vulkan must duplicate before import
    u64 offset{};
    u64 allocation_size{};
};

class HostMemory {
public:
    /// With `backing_fds` empty the backing is created here (a memfd on Linux). Otherwise the
    /// backing is the given file descriptors in order, `chunk_size` bytes each and `backing_size_`
    /// bytes together; HostMemory owns them from here on and closes them. Linux only.
    /// With lazy_backing=true, reserve the arena and create chunks on first range access.
    /// An optional exporter provides CPU-ready dma-bufs, with memfd fallback before publication.
    /// backing_fds must be empty and chunk_size must divide the arena. No direct renderer access.
    explicit HostMemory(size_t backing_size_, size_t virtual_size_,
                        std::span<const int> backing_fds = {}, size_t chunk_size = 0,
                        bool direct_importable = false, bool lazy_backing = false,
                        std::shared_ptr<GuestBackingExporter> exporter = {});
    ~HostMemory();

    /**
     * Copy constructors. They shall return a copy of the buffer without the mappings.
     * TODO: Implement them with COW if needed.
     */
    HostMemory(const HostMemory& other) = delete;
    HostMemory& operator=(const HostMemory& other) = delete;

    /**
     * Move constructors. They will move the buffer and the mappings to the new object.
     */
    HostMemory(HostMemory&& other) noexcept;
    HostMemory& operator=(HostMemory&& other) noexcept;

    void Map(size_t virtual_offset, size_t host_offset, size_t length, MemoryPermission perms,
             bool separate_heap);

    void Unmap(size_t virtual_offset, size_t length, bool separate_heap);

    void Protect(size_t virtual_offset, size_t length, MemoryPermission perms);

    void EnableDirectMappedAddress();

    void ClearBackingRegion(size_t physical_offset, size_t length, u32 fill_value);

    // Materialize the complete physical range before exposing a pointer or CPU alias.
    // Does not change an already materialized chunk, its contents, or its mappings.
    void EnsureBackingRange(size_t physical_offset, size_t length) const;
    [[nodiscard]] BackingStats GetBackingStats() const;
    [[nodiscard]] bool IsLazyBacking() const noexcept { return lazy_backing_enabled; }
    // Query only: never materializes cold chunks. Leases are not direct GPU mappings.
    [[nodiscard]] GuestChunkLease GetPublishedChunk(u64 physical_offset) const;
    [[nodiscard]] GuestChunkLease FirstPublishedExportedChunk() const;
    [[nodiscard]] u64 BackingGeneration() const {
        const auto epoch = backing_lifetime.Get();
        return epoch ? epoch->generation : 0;
    }
    // Identity only: this token does not materialize or pin arena allocations.
    [[nodiscard]] std::shared_ptr<const GuestBackingEpoch> BackingEpoch() const {
        return backing_lifetime.Get();
    }

    [[nodiscard]] u8* BackingBasePointer() noexcept {
        return backing_base;
    }
    [[nodiscard]] const u8* BackingBasePointer() const noexcept {
        return backing_base;
    }

    [[nodiscard]] u8* VirtualBasePointer() noexcept {
        return virtual_base;
    }
    [[nodiscard]] const u8* VirtualBasePointer() const noexcept {
        return virtual_base;
    }

    [[nodiscard]] size_t VirtualSize() const noexcept {
        return virtual_size;
    }

    bool IsInVirtualRange(void* address) const noexcept {
        return address >= virtual_base && address < virtual_base + virtual_size;
    }

    // Only the caller-supplied driver backing is exportable. Ordinary memfd/file
    // mappings must never be mistaken for dma-buf memory.
    [[nodiscard]] std::optional<GuestBackingRange> DriverBackingRange(u64 offset, u64 size) const {
        if (!driver_direct_importable || driver_fds.empty() || driver_chunk_size == 0 || size == 0 ||
            offset >= backing_size || size > backing_size - offset) {
            return std::nullopt;
        }
        const auto range = FirstChunkRange(offset, size, driver_chunk_size);
        if (range.length != size || range.chunk >= driver_fds.size()) {
            return std::nullopt;
        }
        return GuestBackingRange{driver_fds[range.chunk], range.offset, driver_chunk_size};
    }

    size_t backing_size{};

private:
    std::vector<int> driver_fds;
    size_t driver_chunk_size{};
    bool driver_direct_importable{};
    bool lazy_backing_enabled{};
    size_t virtual_size{};

    // Low level handler for the platform dependent memory routines
    class Impl;
    std::shared_ptr<Impl> impl;
    GuestBackingLifetime backing_lifetime;
    u8* backing_base{};
    u8* virtual_base{};
    size_t virtual_base_offset{};
};

} // namespace Common
