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
p.add_argument('--content', action='store_true', help='Also validate exact transfer content and copy provenance')
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
checked += body(header, '    struct TransferBuffer {') + ';\n'
checked += body(header, '    class CheckedTransfer {') + ';\nusing Transfer=std::shared_ptr<CheckedTransfer>;\n'
checked += 'enum class WriteState { Pending, Submitted, Skipped, Complete, Unknown };\n'
checked += body(header, '    class CheckedWrite {') + ';\nusing Write=std::shared_ptr<CheckedWrite>;\n'
checked += body(header, '    struct WriteFootprint {') + ';\nusing ObservedWrites=std::shared_ptr<const std::vector<Write>>;\n'
methods = '\n'.join(body(cpp, marker) for marker in [
    'u64 Scheduler::Flush(',
    'Scheduler::Submission Scheduler::FlushChecked(', 'VkResult Scheduler::PollChecked(',
    'u64 Scheduler::SubmitExecution(', 'Scheduler::Write Scheduler::RecordCheckedWrite(',
    'Scheduler::ObservedWrites Scheduler::RecordObservedWrites(',
    'const VideoCommon::PhysicalWriteIdentity* Scheduler::CompletedPhysicalIdentity(',
    'bool Scheduler::HasConfirmedMemoryDependency(', 'void Scheduler::RecordProvenanceBarrier(',
    'Scheduler::WriteState Scheduler::PollCheckedWrite(',
    'Scheduler::Transfer Scheduler::RecordTransferBatch(',
    'Scheduler::WriteState Scheduler::PollCheckedTransfer(',
    'const TransferContent* Scheduler::CompletedTransferContent(',
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
scaffold = scaffold.replace('// @TRANSFER_MAPPING_GATE@', 'template <typename Memory>\n' +
                           body(header, '    const TransferContent* TransferContentForMapping('))
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
#include "video_core/renderer_vulkan/vk_transfer_content.h"
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
''' + read('tools/physical_coherency_tests/sync_dependency_fixture.cpp.in')
if a.content:
    source += read('tools/physical_coherency_tests/transfer_content_fixture.cpp.in')
source += '\nint main() {TestSyncDependencies();' + ('TestTransferContent();' if a.content else '') + '}\n'
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
if a.content:
    for name, guard, replacement in [
        ('content-without-completion', 'if (PollCheckedTransfer(transfer) != WriteState::Complete) return nullptr;', 'if (false) return nullptr;'),
        ('content-without-mapping-check', 'if (!origin->MatchesCurrent(memory)) return nullptr;', '(void)origin;'),
        ('copy-without-device-command', 'cmdbuf.CopyBuffer(source.Handle(), destination.Handle(), region);', '(void)region;'),
        ('fill-without-device-command', 'cmdbuf.FillBuffer(destination.Handle(), destination.Offset() + operation.destination_offset,\n                                          operation.size, operation.value);', '(void)destination;'),
        ('content-without-sync-evidence', 'transfer->positions[i], next)) return nullptr;', 'transfer->positions[i], next)) {}'),
        ('content-without-host-retention', 'if (transfer->worker_pending.load(std::memory_order_acquire)) return;', 'if (false && transfer->worker_pending.load(std::memory_order_acquire)) return;')]:
        assert source.count(guard) == 1, name
        result = run(name, source.replace(guard, replacement))
        if result.returncode == 0 or 'Assertion' not in result.stderr:
            raise RuntimeError(f'{name} failed incorrectly: {result.returncode} {result.stderr}')
        print('PASS expected content mutation failure:', name)
    header = read('src/video_core/renderer_vulkan/vk_transfer_content.h').replace('#pragma once', '')
    expanded = source.replace('#include "video_core/renderer_vulkan/vk_transfer_content.h"', header)
    for name, guard, replacement in [
        ('stale-whole-replica-promotion', 'if (!root || root->command != fill || root->offset != root_offset + begin - offset) return false;', 'if (!root) return false;'),
        ('missing-left-complement', 'if (part.offset < offset) {', 'if (false) {'),
        ('missing-right-complement', 'if (begin < part.offset + part.size) {', 'if (false) {')]:
        assert expanded.count(guard) == 1, name
        result = run(name, expanded.replace(guard, replacement))
        if result.returncode == 0 or 'Assertion' not in result.stderr:
            raise RuntimeError(f'{name} failed incorrectly: {result.returncode} {result.stderr}')
        print('PASS expected content mutation failure:', name)
inputs.add('src/video_core/renderer_vulkan/vk_sync_provenance.h')
inputs.add('src/video_core/renderer_vulkan/vk_transfer_content.h')
(out / 'extraction.json').write_text(json.dumps({
    'sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(inputs)},
    'boundary': 'Actual production dependency and submission methods, simulated Vulkan/device execution; no authority',
}, indent=2))
