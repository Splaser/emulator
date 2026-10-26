# SPDX-License-Identifier: GPL-3.0-or-later
cmake_minimum_required(VERSION 3.22)
project(nvhost_wait_tests LANGUAGES CXX)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(NVHOST_SOURCE_REVISION "" CACHE STRING "Optional baseline Git revision")
set(revision_args)
if(NVHOST_SOURCE_REVISION)
    list(APPEND revision_args --revision "${NVHOST_SOURCE_REVISION}")
endif()
set(generated "${CMAKE_CURRENT_BINARY_DIR}/nvhost_wait.inc")
add_custom_command(OUTPUT "${generated}"
    COMMAND Python3::Interpreter "${CMAKE_CURRENT_SOURCE_DIR}/generate.py" "${generated}" ${revision_args}
    DEPENDS generate.py ../../src/core/hle/service/nvdrv/devices/nvhost_ctrl.h
        ../../src/core/hle/service/nvdrv/devices/nvhost_ctrl.cpp)
add_executable(nvhost_wait_tests tests.cpp "${generated}")
target_compile_features(nvhost_wait_tests PRIVATE cxx_std_20)
target_include_directories(nvhost_wait_tests PRIVATE "${CMAKE_CURRENT_BINARY_DIR}"
    "${CMAKE_CURRENT_SOURCE_DIR}" ../../src)
enable_testing()
add_test(NAME nvhost_wait_retry COMMAND nvhost_wait_tests)
