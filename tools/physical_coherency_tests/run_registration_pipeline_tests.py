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
import sys

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
subprocess.run([sys.executable, str(root / 'tools/gpu_lifecycle_tests/run_thread_tests.py'),
                '--cxx', a.cxx, '--repeat', '1', '--handoff-controls'], check=True)
thread_fixture = root / '.diagnostics/gpu-lifecycle' / ('windows' if os.name == 'nt' else 'linux')
thread_source = (thread_fixture / 'gpu_thread.cpp').read_text().split('using VideoCommon::GPUThread::ThreadManager;')[0]
thread_source = thread_source.replace(
    '#define LOG_ERROR(category, format, reason) ((void)(reason))',
    '#undef LOG_ERROR\n#define LOG_ERROR(...) ((void)0)')
thread_source = thread_source.replace('int Acquire() { return 0; }',
    'struct Scope {~Scope() {}}; Scope Acquire() { return {}; }')
start = thread_source.index('namespace Vulkan::vk { struct Exception')
end = thread_source.index('namespace Core {', start)
thread_source = thread_source[:start] + 'namespace Vulkan {namespace vk=::vk;}\n' + thread_source[end:]
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
registration += body('src/video_core/buffer_cache/buffer_cache_base.h', '    class ControlledCpuWrite {')
registration += ';\n    using ControlledCpuWritePtr=std::shared_ptr<ControlledCpuWrite>;\n'
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
               'auto BufferCache<P>::BeginControlledCpuWrite(',
               'auto BufferCache<P>::BeginControlledCpuWriteRequest(',
               'Core::Memory::PreparedCpuWriteResult BufferCache<P>::CommitControlledCpuWriteRequest(',
               'void BufferCache<P>::AbandonControlledCpuWrite(',
               'auto BufferCache<P>::PollControlledCpuWrite(',
               'Core::Memory::PreparedCpuWriteResult BufferCache<P>::CommitControlledCpuTransaction(',
               'void BufferCache<P>::CheckControlledSynchronization(',
               'bool BufferCache<P>::ControlledReadbacksIdle(',
               'bool BufferCache<P>::SynchronizeBuffer(',
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
                     'template <typename Func>\n' + body('src/core/device_memory_manager.h', '    [[nodiscard]] bool WithControlledMapping(') + '\n' +
                     'template <typename Func>\n' + body('src/core/device_memory_manager.h', '    [[nodiscard]] bool WithCurrentControlledAliases(')),
                    ('ALIAS_CONTAINER', body('src/core/device_memory_manager.inc', 'class MultiAddressContainer {') + ';'),
                    ('SUBMISSION_METHODS', submission), ('TRANSFER_METHODS', transfer),
                    ('DEVICE_TRACKER', tracker), ('REGISTRATION_CLASS', registration),
                    ('CACHE_METHODS', cache),
                    ('REQUEST_ADVANCE', body('src/video_core/renderer_vulkan/vk_rasterizer.cpp',
                        'Core::Memory::ControlledCpuWriteRequest::Phase RasterizerVulkan::AdvanceControlledCpuWriteRequest(')),
                    ('REQUEST_QUEUE', body('src/video_core/renderer_vulkan/vk_rasterizer.cpp',
                        'bool RasterizerVulkan::QueueControlledCpuWriteRequest(')),
                    ('GPU_THREAD', thread_source)]:
    marker = '// @' + name + '@'
    assert template.count(marker) == 1
    template = template.replace(marker, value)
source = cpu + template
cpp = out / 'registration_pipeline.cpp'
cpp.write_text(source)
cmd = [a.cxx, '-std=c++23', '-O1', '-pthread', '-Wall', '-Wextra', '-Werror',
       '-Wno-unused-parameter', '-Wno-missing-field-initializers', '-I', str(out / 'stubs'),
       '-I', str(previous / 'stubs'), '-I', str(thread_fixture / 'shims'), '-I', str(root / 'src'),
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
assert source.count(barrier) == 2
control.write_text(source.replace(barrier, '.dstAccessMask = VK_ACCESS_MEMORY_READ_BIT'))
subprocess.run(cmd + [str(control), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 84 or 'missing explicit host visibility barrier' not in result.stderr:
    raise RuntimeError(f'Missing host barrier control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative control: missing explicit transfer-to-host read visibility fails (84)')
preserve = 'std::memcpy(target.data(), bytes.data() + segment.logical_offset, target.size());'
assert source.count(preserve) == 1
control.write_text(source.replace(preserve, '(void)target;'))
subprocess.run(cmd + [str(control), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 85 or 'GPU dirty complement lost' not in result.stderr:
    raise RuntimeError(f'Missing preservation control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative control: dropping checked GPU preservation loses complement bytes (85)')
guard = 'CheckControlledSynchronization(device_addr, size);'
assert source.count(guard) == 1
control.write_text(source.replace(guard, '/* deliberately bypass transaction exclusion */'))
subprocess.run(cmd + [str(control), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 86 or 'upload consumed publication' not in result.stderr:
    raise RuntimeError(f'Missing upload exclusion control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative control: upload inside preservation/store/publication is rejected (86)')
publication = 'memory_tracker.MarkRegionAsCpuModified(alias, tx.size);'
assert source.count(publication) == 1
control.write_text(source.replace(publication, '(void)alias;'))
subprocess.run(cmd + [str(control), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 87 or 'transaction omitted real tracker publication' not in result.stderr:
    raise RuntimeError(f'Missing transaction publication control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative control: transaction must publish each physical device alias after store (87)')
hook = 'if (TryBoundCpuWrite(vaddr, data)) [[unlikely]] return;'
assert source.count(hook) == 2  # Actual ordinary CPU body plus disabled-handshake legacy witness.
control.write_text(source.replace(hook, '/* deliberately bypass bound ordinary routing */', 1))
subprocess.run(cmd + [str(control), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 88 or 'bound ordinary Write bypassed its transaction' not in result.stderr:
    raise RuntimeError(f'Ordinary routing bypass control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative control: bypassing the actual ordinary Write transaction branch fails (88)')
preserved = 'if (submitted) return tx.phase = Phase::Preserved;'
assert source.count(preserved) == 1
control.write_text(source.replace(preserved, '''if (submitted) {
    if(tx.request) tx.request->Publish(Core::Memory::ControlledCpuWriteRequest::Phase::Stored,
                                     Core::Memory::PreparedCpuWriteResult::Stored);
    return tx.phase = Phase::Preserved;
}'''))
subprocess.run(cmd + [str(control), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 89 or 'request completed before actual store publication' not in result.stderr:
    raise RuntimeError(f'Early request success control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative control: completed readback cannot acknowledge a still-unperformed CPU store (89)')
owner = 'Owners{operation, preservation, std::move(extra_owner)}'
assert source.count(owner) == 1
control.write_text(source.replace(owner, 'Owners{operation, preservation, {}}'))
accept_stubs = out / 'missing-accept-retention/core'
accept_stubs.mkdir(parents=True, exist_ok=True)
owner_header = read('src/core/controlled_cpu_page.h')
accept_retention = 'accepted[i] = request;'
assert owner_header.count(accept_retention) == 1
accept_stubs.joinpath('controlled_cpu_page.h').write_text(owner_header.replace(accept_retention, ''))
accept_cmd = cmd[:1] + ['-I', str(accept_stubs.parent)] + cmd[1:]
subprocess.run(accept_cmd + [str(control), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 90 or 'accepted request owner escaped Unknown retention' not in result.stderr:
    raise RuntimeError(f'Dropped request retention control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative control: Unknown admission must retain the accepted CPU request after caller drop (90)')
closed = body('src/core/controlled_cpu_page.h', 'inline void CpuWriteOwner::Close()')
owner_stubs = out / 'open-owner-control/core'
owner_stubs.mkdir(parents=True, exist_ok=True)
owner_stubs.joinpath('controlled_cpu_page.h').write_text(
    read('src/core/controlled_cpu_page.h').replace(closed,
        'inline void CpuWriteOwner::Close() { std::unique_lock lock{mutex}; }'))
control_cmd = cmd[:1] + ['-I', str(owner_stubs.parent)] + cmd[1:]
subprocess.run(control_cmd + [str(cpp), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 92 or 'closed Memory owner executed a queued CPU store' not in result.stderr:
    raise RuntimeError(f'Missing owner close control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative lifecycle control: bypassing per-Memory Close permits a forbidden queued store (92)')
pending_stubs = out / 'pending-unknown-control/common'
pending_stubs.mkdir(parents=True, exist_ok=True)
bundle = read('src/common/physical_registration_bundle.h')
pending_guard = 'if (!domain->Quarantine(ticket)) return false;'
assert bundle.count(pending_guard) == 1
pending_stubs.joinpath('physical_registration_bundle.h').write_text(bundle.replace(
    pending_guard, 'if (!active || !domain->MarkUnknown(ticket)) return false;'))
pending_cmd = cmd[:1] + ['-I', str(pending_stubs.parent)] + cmd[1:]
subprocess.run(pending_cmd + [str(cpp), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 93 or 'accepted parked Unknown lost its execution identity' not in result.stderr:
    raise RuntimeError(f'Parked Unknown control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative lifecycle control: parked accepted Unknown must retain its execution identity (93)')
subprocess.run(accept_cmd + [str(cpp), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 94 or 'accepted construction failure lost request identity' not in result.stderr:
    raise RuntimeError(f'Construction Unknown control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative lifecycle control: pre-transaction Unknown must retain the accepted request (94)')
cpp.write_text(source.replace('if (!ControlledReadbacksIdle(operation)) {',
                              'if (false && !ControlledReadbacksIdle(operation)) {'))
subprocess.run(cmd + [str(cpp), '-o', str(exe)], check=True)
result = subprocess.run([str(exe), '1'], capture_output=True, text=True, timeout=60)
if result.returncode != 95 or 'readback conflict accepted before producer retirement' not in result.stderr:
    raise RuntimeError(f'Readback isolation control failed incorrectly: {result.returncode} {result.stderr}')
print('PASS negative isolation control: pending physical-alias readback must reject before acceptance (95)')

# Exercise the real alias transfer/factory/checked-submit bodies against the same
# fake Vulkan dispatch. Kept separate so original mutation controls retain their
# exact failure sites. These are fault-injection fixtures, not native driver proof.
alias_source = source.rsplit('int main(int argc,char** argv) {', 1)[0]
alias_source = alias_source.replace(
    '#include "video_core/buffer_cache/controlled_transfer.h"',
    '#include "video_core/buffer_cache/controlled_transfer.h"\n'
    '#include "video_core/buffer_cache/physical_alias_copy.h"')
declaration = 'std::shared_ptr<VideoCommon::ControlledBufferTransfer> PrepareControlledTransfer(const Buffer&);'
assert alias_source.count(declaration) == 1
alias_source = alias_source.replace(declaration, declaration + '\n'
    'std::shared_ptr<VideoCommon::ControlledAliasTransfer> PrepareAliasTransfer('
    'StagedBufferPin,StagedBufferPin,std::span<const VideoCommon::AliasCopyRange>);')
alias_source += '\nnamespace Vulkan {\n' + body(runtime_path, 'class AliasTransfer final') + ';\n'
alias_source += body(runtime_path,
    'std::shared_ptr<VideoCommon::ControlledAliasTransfer> BufferCacheRuntime::PrepareAliasTransfer(')
alias_source += '\n}\n' + r'''
int main() {
    using Poll=VideoCommon::ControlledTransferPoll;
    using Admission=Common::PhysicalRangeAdmission;
    for(int mode=0;mode<6;++mode) {
        auto s=std::make_unique<Scenario>();
        auto source=std::make_unique<Vulkan::Buffer>(s->runtime,A,4096);
        auto target=std::make_unique<Vulkan::Buffer>(s->runtime,ALIAS,4096);
        auto from=source->PinStagedRepresentation(0,4096);
        auto to=target->PinStagedRepresentation(0,4096);assert(from && to);
        auto* input=reinterpret_cast<Allocation*>(from->Handle());
        auto* output=reinterpret_cast<Allocation*>(to->Handle());
        std::fill(input->bytes.begin(),input->bytes.end(),u8{99});
        std::fill(output->bytes.begin(),output->bytes.end(),u8{10});
        const std::array copies{VideoCommon::AliasCopyRange{128,256,256,0}};
        auto transfer=s->runtime.PrepareAliasTransfer(*from,*to,copies);assert(transfer);
        auto domain=s->views.front().physical.Epoch()->ranges;
        const std::array access{Admission::Access{0,256,Admission::Mode::Write}};
        auto ticket=domain->Enqueue(access,transfer);assert(ticket);
        assert(domain->TryStart(ticket)==Admission::Start::Granted);
        if(mode==5) s->runtime.staged_pin_domain->Seal();
        const bool submitted=transfer->Submit();
        assert(submitted==(mode!=5));
        assert(!transfer->Submit()); // No second recording, even after refusal/failure.
        if(mode!=5) {
            assert(transfer->Poll()==Poll::Pending);
            if(mode==1) s->gpu.submit_result=VK_ERROR_UNKNOWN;
            s->scheduler.RunWorker();
            source.reset();target.reset();from.reset();to.reset(); // Real payload pins own both resources.
            if(mode==1) assert(transfer->Poll()==Poll::Unknown);
            else {
                assert(transfer->Poll()==Poll::Pending); // Callback return is not GPU completion.
                s->gpu.Complete();
                if(mode==2) s->gpu.counter_result=VK_ERROR_UNKNOWN;
                if(mode==3) s->gpu.invalidate_result=VK_ERROR_UNKNOWN;
                if(mode==4) reinterpret_cast<Allocation*>(s->gpu.readback_target)->bytes[256+7]^=1;
                if(mode==0) {
                    assert(transfer->Poll()==Poll::Complete && transfer->Poll()==Poll::Complete);
                    for(size_t i=0;i<4096;++i) assert(output->bytes[i]==(i>=256 && i<512?99:10));
                    assert(s->gpu.host_read_barrier);
                } else assert(transfer->Poll()==Poll::Unknown);
            }
        } else assert(transfer->Poll()==Poll::Unknown);
        if(mode==0) assert(domain->Complete(ticket));
        else assert(domain->MarkUnknown(ticket));
        auto reader=domain->Enqueue(access,std::make_shared<int>(1));assert(reader);
        if(mode==0) {
            assert(domain->TryStart(reader)==Admission::Start::Granted);
            assert(domain->Complete(reader));
        } else {
            assert(domain->TryStart(reader)==Admission::Start::Park);
            assert(domain->Cancel(reader));
        }
        std::weak_ptr<VideoCommon::ControlledAliasTransfer> retained=transfer;
        transfer.reset();ticket.reset();
        if(mode!=0) assert(!retained.expired()); // Unknown domain retains actual native owners.
        s->runtime.RetireControlledTransfersAfterDeviceIdle(); // Fixture trusted-idle boundary.
        if(auto alive=retained.lock()) {
            assert(alive->Poll()==Poll::Unknown);
            assert(!alive->SourceIdentity() && !alive->DestinationIdentity());
        }
    }
    std::cout<<"PASS actual alias transfer fault fixture: exact copy/complements, delayed completion, "
               "submit/counter/invalidate/corruption/seal failures, one-shot submission, dropped cache "
               "owners and Unknown quarantine (Vulkan dispatch remains a fixture)\n";
}
'''
alias_cpp = out / 'alias_transfer.cpp'
alias_cpp.write_text(alias_source)
alias_exe = out / ('alias_transfer.exe' if os.name == 'nt' else 'alias_transfer')
subprocess.run(cmd + [str(alias_cpp), '-o', str(alias_exe)], check=True)
subprocess.run([str(alias_exe)], check=True, timeout=60)
inputs.update(['src/common/physical_registration_bundle.h', 'src/core/controlled_cpu_page.h',
               'src/video_core/buffer_cache/controlled_conflict.h', 'src/common/range_sets.inc',
               'src/video_core/gpu_thread.cpp','src/video_core/gpu_thread.h',
               'src/core/hle/kernel/k_process.cpp','src/core/memory.h',
               'src/video_core/buffer_cache/controlled_transfer.h', 'src/video_core/physical_access_plan.h',
               'src/video_core/renderer_vulkan/vk_buffer_payload.h',
               'src/video_core/buffer_cache/physical_alias_copy.h'])
(out / 'extraction.json').write_text(json.dumps({
    'sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sorted(inputs)},
    'real': ['cold device physical plan and HostMemory pins', 'actual BufferCache controlled registration/refresh/poll and Register',
             'actual controlled Vulkan upload/readback and cache buffer pin ownership',
             'actual Scheduler checked submit/poll and MasterSemaphore timeline submission/poll bodies',
             'actual ordinary Memory::Write8/16/32/64, scoped ordinary binding and CPU stores',
             'actual MemoryTrackerBase/WordManager'],
    'fixtures': ['device mapping snapshot and CPU cached-tag fanout', 'Vulkan dispatch, allocation and command/device execution',
                 'cache binding teardown and usage stamping'],
    'acceptance': 'Neither this fixture suite nor native compilation closes ordinary-game F2',
}, indent=2))
