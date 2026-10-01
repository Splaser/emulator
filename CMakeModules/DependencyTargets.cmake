# SPDX-FileCopyrightText: Copyright 2026 citron Emulator Project
# SPDX-License-Identifier: GPL-2.0-or-later

# Normalize provider-specific names once, before adding Citron consumers.
function(citron_dependency_alias canonical provider)
    if (NOT TARGET "${canonical}" AND TARGET "${provider}")
        add_library("${canonical}" ALIAS "${provider}")
    endif()
endfunction()

citron_dependency_alias(sirit::sirit sirit)
citron_dependency_alias(adrenotools::adrenotools adrenotools)

# Keep provider-specific FFmpeg paths and flags out of consumers.
function(citron_resolve_ffmpeg_target)
    if (TARGET FFmpeg::FFmpeg)
        return()
    endif()
    if (NOT FFmpeg_LIBRARIES)
        message(FATAL_ERROR "The selected dependency provider did not supply FFmpeg libraries")
    endif()
    add_library(citron_ffmpeg INTERFACE)
    target_include_directories(citron_ffmpeg SYSTEM INTERFACE ${FFmpeg_INCLUDE_DIR})
    target_link_libraries(citron_ffmpeg INTERFACE ${FFmpeg_LIBRARIES})
    target_link_options(citron_ffmpeg INTERFACE ${FFmpeg_LDFLAGS})
    add_library(FFmpeg::FFmpeg ALIAS citron_ffmpeg)
endfunction()

if (NOT TARGET sirit::sirit)
    message(FATAL_ERROR "The selected dependency provider did not supply sirit::sirit")
endif()
if (ANDROID AND ARCHITECTURE_arm64 AND NOT TARGET adrenotools::adrenotools)
    message(FATAL_ERROR "The selected dependency provider did not supply adrenotools::adrenotools")
endif()
