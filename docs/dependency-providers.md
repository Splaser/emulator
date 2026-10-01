# Dependency providers

This audit applies to the Android CPM PR (`codex/android-oboe-cpm`) and its
`codex/dynarmic-latest-android-test` validation branch. It does not change the
personal `main` branch or upgrade all dependencies to a common version.

## Contract

Consumers link canonical targets. Provider discovery, source population, path
adapters and aliases belong in the root CMake/provider modules and `externals`.
`DependencyTargets.cmake` normalizes Sirit, Adrenotools and FFmpeg. Oboe's vcpkg
layout stays in `OboeVcpkg.cmake`; audio consumers use `oboe::oboe`.

Submodule fallbacks remain useful for non-CPM builds. They must check for the
canonical target before adding sources. Sirit accepts a parent-provided
`SPIRV-Headers::SPIRV-Headers` target instead of searching a second installation
or using its nested submodule. This also removes the clang-cl-specific alternate
SPIRV-Headers source.

FFmpeg consumers now link `FFmpeg::FFmpeg`. Legacy bundled library paths,
include directories and linker options are confined to its adapter. Linux VA-API
uses `PkgConfig::LIBVA` so its include and link requirements travel together.

## Version matrix (2026-10-01)

The vcpkg column comes from manifest baseline
`c3173be258001c60814b6adf161322b6eb3688ee`, with manifest overrides applied.
System-provider versions depend on the build host and must be recorded in CI.

| Dependency | CPM selection | vcpkg selection | Bundled/submodule selection | Decision |
| --- | --- | --- | --- | --- |
| OpenSSL | 3.6.1 | 3.6.1, port 2 | No active OpenSSL submodule | Already aligned; older 3.4.1 notes are not the current baseline |
| Boost | 1.87.0 | 1.90.0 (context port 1) | System/vcpkg for non-CPM | Significant drift; keep separate until desktop validation |
| fmt | `e8244777ee1c32df8233c215ac9ff626b2dd2c38` | 12.1.0 override | System/vcpkg | Keep exact CPM pin; do not assume a commit is a release tag |
| lz4 | 1.10.0 | 1.10.0 | System/vcpkg | Aligned |
| zstd | 1.5.6 | 1.5.7 | System/vcpkg | Small drift; no bulk upgrade |
| Opus | 1.5.2 | 1.5.2, port 1 | `101a71e03bbf860aaafb7090a0e440675cb27660` (post-1.4) | Bundled drift merits its own audio regression change |
| Oboe | `a81bb9f87d4105b84b682685d3bfbb5beca371d1` | 1.10.0 | Android provider adapter | Compare API/version before changing pin |
| Cubeb | `48689ae7a73caeb747953f9ed664dc71d2f918d8` | Not in manifest | Same commit | Aligned |
| Dynarmic | `b1440b456b80f3dde0c01665932d114c4961ee93` | Not in manifest | Same commit | Keep tested Android baseline |
| Sirit | `ab75463999f4f3291976b079d42d52ee91eebf3f` | Not in manifest | Same commit | Target reuse patch applies to both source providers |
| SPIRV-Headers | `vulkan-sdk-1.4.304.1` | Not in manifest (baseline port is 1.4.341.0) | `00898b201b4153d7198c3e0134dbf953c83bbfd7` | Provider versions still differ; explicit, not silently unified |
| Sirit nested SPIRV-Headers | Previously used by clang-cl | Not applicable | `c214f6f2d1a7253bb0e9f195c2dc5b0659dc99ef` | No longer selected when parent supplies a target |
| Vulkan-Headers / Utility-Libraries | 1.4.337 | Not in manifest | Separate source pins | Not assumed to share SPIRV-Headers release numbering |

## Android branches

Keep Android audio backends, ARM64 driver hooks, NDK/API-specific OpenSSL
configuration, system library linking and the missing `wordexp.h` exclusion for
Boost.Process. These are platform/toolchain requirements, not provider discovery.
No Android condition was removed merely because the CPM build succeeded.

## Dynarmic boundary

The compatibility patch still fixes missing `<print>` and tuple-key hashing in
Dynarmic, but no longer includes Citron's `common/container_hash.h`. A standalone
`Dynarmic::TupleHash` is passed explicitly to the x64 tuple maps and marker sets.
Other containers retain their existing default hash behavior. This removes the
host-header coupling without inventing `std::hash` specializations for tuples
containing only standard/built-in types.

This is not a claim that upstream Dynarmic requires no patches. The remaining
self-contained source changes can be proposed upstream independently.

## Validation and remaining boundaries

Configure the small adapter fixture with `CANONICAL_PROVIDER=ON` and `OFF` to
check canonical provider priority, idempotence and FFmpeg usage requirements:

```sh
cmake -S CMakeModules/tests/provider_contract -B build-contract-raw
cmake -S CMakeModules/tests/provider_contract -B build-contract-canonical -DCANONICAL_PROVIDER=ON
```

The CI test branch pairs the existing Android/CPM workflow with a manual desktop
provider workflow: Windows/MSVC + vcpkg/submodules and Linux + system/submodules.
It builds the SDL CLI and tests without Qt and does not publish releases.
Existing Clangtron/Linux packaging scripts use CPM; they are separate coverage,
not evidence for these default-provider routes. Desktop workflow success and
game/runtime correctness must be reported separately.

Remaining work includes packaged Qt frontends, iOS framework paths, local
FidelityFX shader-generation inputs, default-provider version drift and real
desktop CPM builds. Project-owned vendored sources (`tz`, `glad`, `bc_decoder`)
are not duplicate external provider sources simply because they use bare targets.
