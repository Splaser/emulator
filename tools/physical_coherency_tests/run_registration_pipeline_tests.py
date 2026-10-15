# SPDX-License-Identifier: GPL-2.0-or-later
"""Extract actual cache/native-transfer/checked-submit bodies; Vulkan dispatch remains a fixture.

Run run_first_registration_tests.py first. This suite never certifies real driver execution or
ordinary-game F2 repair. Native compilation of the actual Rasterizer endpoint is done by CI.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--cxx', default=os.environ.get('CXX', 'g++'))
p.add_argument('--boost-include', type=Path)
p.add_argument('--repeat', type=int, default=10)
a = p.parse_args()
if a.repeat < 1:
    p.error('--repeat must be positive')
root = Path(__file__).resolve().parents[2]
previous = root / '.diagnostics/m3b-first-registration'
for name, digest in json.loads((previous / 'extraction.json').read_text())['sha256'].items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
        raise RuntimeError('Stale prerequisite: rerun run_first_registration_tests.py: ' + name)
out = root / '.diagnostics/m3b-registration-pipeline'
stub = out / 'stubs/video_core/vulkan_common'
stub.mkdir(parents=True, exist_ok=True)
(stub / 'vulkan_wrapper.h').write_text('#pragma once\n// Fixture vk types are defined before the actual payload header.\n')
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


cache_path = 'src/video_core/buffer_cache/buffer_cache.h'
base = read('src/video_core/buffer_cache/buffer_cache_base.h')
registration = body('src/video_core/buffer_cache/buffer_cache_base.h', '    class ControlledRegistration {')
registration += ';\n    using ControlledRegistrationPtr=std::shared_ptr<ControlledRegistration>;\n'
declarations = read('src/video_core/renderer_vulkan/vk_scheduler.h')
checked = body('src/video_core/renderer_vulkan/vk_scheduler.h', '    class CheckedSubmission {')
checked += ';\n    using Submission=std::shared_ptr<CheckedSubmission>;\n'
timeline = body('src/video_core/renderer_vulkan/vk_master_semaphore.h',
                '    [[nodiscard]] VkResult PollTimeline(')
scheduler_path = 'src/video_core/renderer_vulkan/vk_scheduler.cpp'
submission = body('src/video_core/renderer_vulkan/vk_master_semaphore.cpp',
                  'static constexpr std::array<VkPipelineStageFlags, 2> master_wait_stage_masks') + ';\n'
submission += body('src/video_core/renderer_vulkan/vk_master_semaphore.cpp',
                   'VkResult MasterSemaphore::SubmitQueueTimeline(') + '\n'
for marker in ['Scheduler::Submission Scheduler::FlushChecked(',
               'VkResult Scheduler::PollChecked(', 'u64 Scheduler::SubmitExecution(']:
    submission += body(scheduler_path, marker) + '\n'
runtime_path = 'src/video_core/renderer_vulkan/vk_buffer_cache.cpp'
transfer = body(runtime_path, 'VkBufferCopy MakeBufferCopy(') + '\n'
transfer += body(runtime_path, 'class ControlledTransfer final') + ';\n'
for marker in ['bool BufferCacheRuntime::SupportsControlledTransfers(',
               'std::shared_ptr<VideoCommon::ControlledBufferTransfer> BufferCacheRuntime::\n    PrepareControlledTransfer(',
               'void BufferCacheRuntime::RetireControlledTransfersAfterDeviceIdle(',
               'void BufferCacheRuntime::CopyBuffer(']:
    transfer += body(runtime_path, marker) + '\n'
cache = ''
for marker in ['auto BufferCache<P>::BeginControlledFirstRegistration(',
               'BufferId BufferCache<P>::ControlledReadyBuffer(',
               'BufferId BufferCache<P>::ControlledBufferId(',
               'bool BufferCache<P>::BeginControlledRefresh(',
               'auto BufferCache<P>::PollControlledRegistration(',
               'Core::Memory::PreparedCpuWriteResult BufferCache<P>::CommitControlledCachedWrite(',
               'void BufferCache<P>::Register(', 'void BufferCache<P>::Unregister(',
               'void BufferCache<P>::ChangeRegister(',
               'BufferCache<P>::CommitControlledCpuWrite(']:
    text = read(cache_path)
    method_start = text.index(marker)
    template_start = text.rfind('template <class P>', 0, method_start)
    # Include the return type if the selected marker begins at the function name.
    cache += text[template_start:method_start] + body(cache_path, marker) + '\n'
old = (previous / 'first_registration.cpp').read_text()
cpu = old[:old.index('using DAddr=u64;')]
tracker = old[old.index('struct DeviceTracker {'):old.index('struct BufferCopy {')]
template = read('tools/physical_coherency_tests/first_registration_pipeline.cpp.in')
template = template.replace('using DAddr=u64;',
    'using VideoCommon::ControlledBufferTransfer;\nusing VideoCommon::ControlledTransferPoll;\nusing DAddr=u64;')
for name, value in [('POLL_TIMELINE', timeline), ('CHECKED_SUBMISSION', checked),
                    ('DEVICE_WRITE_GUARDS',
                     'template <typename Func>\n' + body('src/core/device_memory_manager.h', '    [[nodiscard]] bool WithControlledPhysicalAliases(') + '\n' +
                     'template <typename Func>\n' + body('src/core/device_memory_manager.h', '    [[nodiscard]] bool WithControlledMapping(')),
                    ('ALIAS_CONTAINER', body('src/core/device_memory_manager.inc', 'class MultiAddressContainer {') + ';'),
                    ('SUBMISSION_METHODS', submission), ('TRANSFER_METHODS', transfer),
                    ('DEVICE_TRACKER', tracker), ('REGISTRATION_CLASS', registration),
                    ('CACHE_METHODS', cache)]:
    marker = '// @' + name + '@'
    assert template.count(marker) == 1
    template = template.replace(marker, value)
source = cpu + template
cpp = out / 'registration_pipeline.cpp'
cpp.write_text(source)
cmd = [a.cxx, '-std=c++23', '-O1', '-pthread', '-Wall', '-Wextra', '-Werror',
       '-Wno-unused-parameter', '-Wno-missing-field-initializers', '-I', str(out / 'stubs'),
       '-I', str(previous / 'stubs'), '-I', str(root / 'src'),
       '-I', str(root / 'externals/Vulkan-Headers/include')]
if a.boost_include:
    cmd += ['-I', str(a.boost_include)]
cmd += [str(root / 'src/common/host_memory.cpp'), str(root / 'src/common/page_table.cpp'),
        str(root / 'src/common/virtual_buffer.cpp')]
if os.name == 'nt':
    cmd += [str(root / 'src/common/dynamic_library.cpp')]
exe = out / ('registration_pipeline.exe' if os.name == 'nt' else 'registration_pipeline')
subprocess.run(cmd + [str(cpp), '-o', str(exe)], check=True)
subprocess.run([str(exe), str(a.repeat)], check=True, timeout=60)
control = out / 'early_completion.cpp'
assert source.count(timeline) == 1
control.write_text(source.replace(timeline, '[[nodiscard]] VkResult PollTimeline(u64) const noexcept {return VK_SUCCESS;}'))
subprocess.run(cmd + [str(control), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 82 or 'mistaken for completed readback' not in result.stderr:
    raise RuntimeError(f'Early completion control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative control: accepting submission without target completion fails delayed-readback gate (82)')
publication = 'memory_tracker.MarkRegionAsCpuModified(alias, size);'
assert source.count(publication) == 1
control.write_text(source.replace(publication, 'if (alias < ALIAS) ' + publication))
subprocess.run(cmd + [str(control), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 83 or 'missed a real tracker alias' not in result.stderr:
    raise RuntimeError(f'Missing alias publication control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative control: dropping a real device alias from post-store publication fails (83)')
barrier = '.dstAccessMask = VK_ACCESS_HOST_READ_BIT'
assert source.count(barrier) == 1
control.write_text(source.replace(barrier, '.dstAccessMask = VK_ACCESS_MEMORY_READ_BIT'))
subprocess.run(cmd + [str(control), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 84 or 'missing explicit host visibility barrier' not in result.stderr:
    raise RuntimeError(f'Missing host barrier control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative control: missing explicit transfer-to-host read visibility fails (84)')
inputs.update(['src/common/physical_registration_bundle.h', 'src/core/controlled_cpu_page.h',
               'src/video_core/buffer_cache/controlled_transfer.h', 'src/video_core/physical_access_plan.h',
               'src/video_core/renderer_vulkan/vk_buffer_payload.h'])
(out / 'extraction.json').write_text(json.dumps({
    'sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(inputs)},
    'real': ['cold device physical plan and HostMemory pins', 'actual BufferCache controlled registration/refresh/poll and Register',
             'actual controlled Vulkan upload/readback and cache buffer pin ownership',
             'actual Scheduler checked submit/poll and MasterSemaphore timeline submission/poll bodies',
             'actual CPU stores and MemoryTrackerBase/WordManager'],
    'fixtures': ['device mapping snapshot and CPU cached-tag fanout', 'Vulkan dispatch, allocation and command/device execution',
                 'cache binding teardown and usage stamping'],
    'acceptance': 'Neither this fixture suite nor native compilation closes ordinary-game F2',
}, indent=2))
