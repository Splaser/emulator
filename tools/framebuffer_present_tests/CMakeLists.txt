# SPDX-License-Identifier: GPL-2.0-or-later
cmake_minimum_required(VERSION 3.22)
project(framebuffer_present_tests LANGUAGES CXX)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(PRESENT_SOURCE_REVISION "" CACHE STRING "Optional historical revision")
set(revision_args)
if(PRESENT_SOURCE_REVISION)
    list(APPEND revision_args --revision "${PRESENT_SOURCE_REVISION}")
endif()
set(generated "${CMAKE_CURRENT_BINARY_DIR}/framebuffer_present.inc")
set(generated_config "${CMAKE_CURRENT_BINARY_DIR}/framebuffer_present_config.inc")
add_custom_command(OUTPUT "${generated}" "${generated_config}"
    COMMAND Python3::Interpreter "${CMAKE_CURRENT_SOURCE_DIR}/generate.py" "${generated}" ${revision_args}
    DEPENDS generate.py ../../src/video_core/texture_cache/texture_cache.h)
add_executable(framebuffer_present_tests tests.cpp "${generated}" "${generated_config}")
target_compile_features(framebuffer_present_tests PRIVATE cxx_std_20)
target_include_directories(framebuffer_present_tests PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
enable_testing()
add_test(NAME framebuffer_present_refresh COMMAND framebuffer_present_tests)
