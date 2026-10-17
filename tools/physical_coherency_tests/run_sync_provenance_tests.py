"""Actual synchronization journal and Scheduler bodies; Vulkan/device execution is simulated."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--cxx', default=os.environ.get('CXX', 'g++'))
p.add_argument('--vulkan-include', type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
out = root / '.diagnostics/m4-sync-provenance'
stub = out / 'stubs/video_core/vulkan_common'
stub.mkdir(parents=True, exist_ok=True)
(stub / 'vulkan_wrapper.h').write_text('#pragma once\n// Fixture dispatch types precede payload.\n')
inputs = set()


def read(path):
    inputs.add(path)
    return (root / path).read_text()


def body(path, marker):
    text = read(path)
    start = text.index(marker)
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


header = 'src/video_core/renderer_vulkan/vk_scheduler.h'
cpp = 'src/video_core/renderer_vulkan/vk_scheduler.cpp'
checked = body(header, '    class CheckedSubmission {') + ';\nusing Submission=std::shared_ptr<CheckedSubmission>;\n'
checked += 'enum class WriteState { Pending, Submitted, Skipped, Complete, Unknown };\n'
checked += body(header, '    class CheckedWrite {') + ';\nusing Write=std::shared_ptr<CheckedWrite>;\n'
checked += body(header, '    struct WriteFootprint {') + ';\nusing ObservedWrites=std::shared_ptr<const std::vector<Write>>;\n'
methods = '\n'.join(body(cpp, marker) for marker in [
    'Scheduler::Submission Scheduler::FlushChecked(', 'VkResult Scheduler::PollChecked(',
    'u64 Scheduler::SubmitExecution(', 'Scheduler::Write Scheduler::RecordCheckedWrite(',
    'Scheduler::ObservedWrites Scheduler::RecordObservedWrites(',
    'const VideoCommon::PhysicalWriteIdentity* Scheduler::CompletedPhysicalIdentity(',
    'bool Scheduler::HasConfirmedMemoryDependency(', 'void Scheduler::RecordProvenanceBarrier(',
    'Scheduler::WriteState Scheduler::PollCheckedWrite(',
    'void Scheduler::RetireCheckedWritesAfterDeviceIdle('])
master = 'src/video_core/renderer_vulkan/vk_master_semaphore.cpp'
methods += '\n' + body(master, 'static constexpr std::array<VkPipelineStageFlags, 2> master_wait_stage_masks') + ';\n'
methods += body(master, 'VkResult MasterSemaphore::SubmitQueueTimeline(')
runtime = 'src/video_core/renderer_vulkan/vk_buffer_cache.cpp'
bindings = '\n'.join(body(runtime, marker) for marker in [
    'void BufferCacheRuntime::CapturePhysicalOrigin(',
    'std::shared_ptr<const VideoCommon::PhysicalWriteIdentity>\nBufferCacheRuntime::PhysicalIdentityForBinding('])
template = read('tools/physical_coherency_tests/first_registration_pipeline.cpp.in')
scaffold = template[template.index('struct Allocation {'):template.index('// @TRANSFER_METHODS@')]
for key, value in [('CHECKED_SUBMISSION', checked), ('SUBMISSION_METHODS', methods),
                   ('POLL_TIMELINE', body('src/video_core/renderer_vulkan/vk_master_semaphore.h',
                                          '    [[nodiscard]] VkResult PollTimeline(')),
                   ('RAW_STORAGE_BIND', '')]:
    scaffold = scaffold.replace('// @' + key + '@', value)
source = '''#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cstring>
#include <deque>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <span>
#include <stdexcept>
#include <utility>
#include <vector>
#include <vulkan/vulkan.h>
#include "common/common_types.h"
#include "video_core/buffer_cache/controlled_transfer.h"
#include "video_core/renderer_vulkan/vk_sync_provenance.h"
''' + scaffold + bindings + '''
struct StorageObserverHarness {
    std::shared_ptr<VideoCommon::PhysicalWriteCoverage> storage_write_coverage =
        std::make_shared<VideoCommon::PhysicalWriteCoverage>();
    StorageObserverHarness(Scheduler&, BufferCacheRuntime& runtime) {
        runtime.SetPhysicalObservationMemory(&runtime.test_mapping);
    }
};
} // namespace Vulkan
constexpr u64 A = 65536;
struct Scenario {
    Driver gpu;
    Vulkan::Device device;
    Vulkan::Scheduler scheduler{device};
    Vulkan::BufferCacheRuntime runtime{device, scheduler};
    Scenario() {driver = &gpu;}
};
''' + read('tools/physical_coherency_tests/sync_dependency_fixture.cpp.in') + '\nint main() {TestSyncDependencies();}\n'
command = [a.cxx, '-std=c++23', '-O1', '-Wall', '-Wextra', '-Werror',
           '-Wno-unused-parameter', '-Wno-missing-field-initializers',
           '-I', str(out / 'stubs'), '-I', str(root / 'src'),
           '-I', str(a.vulkan_include or root / 'externals/Vulkan-Headers/include')]


def run(name, text):
    path = out / (name + '.cpp')
    path.write_text(text)
    exe = out / (name + ('.exe' if os.name == 'nt' else ''))
    subprocess.run(command + [str(path), '-o', str(exe)], check=True)
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    (out / (name + '.txt')).write_text(result.stdout + result.stderr)
    return result


result = run('dependencies', source)
print(result.stdout, end='')
if result.returncode:
    raise RuntimeError(result.stderr)
for name, guard, replacement in [
    ('missing-native-identity', 'a->Representation() != b->Representation()', 'false'),
    ('missing-range-coverage', 'if (!advance) return false;', 'if (!advance) break;'),
    ('missing-submission-boundary', 'before->submission != after->submission', 'false'),
    ('missing-barrier-record', 'if (submission) submission->synchronization.RecordBarrier(source, destination, memory);', '(void)submission;'),
    ('missing-actual-barrier', 'cmdbuf.PipelineBarrier(source, destination, 0, memory);', '(void)cmdbuf;')]:
    assert source.count(guard) == 1, name
    result = run(name, source.replace(guard, replacement))
    if result.returncode == 0 or 'Assertion' not in result.stderr:
        raise RuntimeError(f'{name} failed to expose the removed guard: {result.returncode} {result.stderr}')
    print('PASS expected mutation failure:', name)
inputs.add('src/video_core/renderer_vulkan/vk_sync_provenance.h')
(out / 'extraction.json').write_text(json.dumps({
    'sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(inputs)},
    'boundary': 'Actual production dependency and submission methods, simulated Vulkan/device execution; no authority',
}, indent=2))
