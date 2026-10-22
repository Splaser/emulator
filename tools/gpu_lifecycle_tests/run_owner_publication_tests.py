# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual GPU/NV owner publication; fixture renderer, channel engines and GMMU."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--repeat', type=int, default=3)
p.add_argument('--cxx', default=os.environ.get('CXX', 'g++'))
p.add_argument('--output-dir', type=Path)
a = p.parse_args()
if a.repeat < 1:
    p.error('--repeat must be positive')
root = Path(__file__).resolve().parents[2]
out = a.output_dir.resolve() if a.output_dir else root / '.diagnostics/m4-gpu-owner-publication'
out.mkdir(parents=True, exist_ok=True)

def read(path):
    return (root / path).read_text()

def method(text, marker):
    start = text.index(marker)
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

gpu = read('src/video_core/gpu.cpp')
fixture = out / 'gpu/gpu_requests.cpp'
required = [method(gpu, '~Impl()'), method(gpu, 'void NotifyShutdown()')]
if not fixture.exists() or not all(m in fixture.read_text() for m in required):
    subprocess.run([sys.executable, str(root / 'tools/gpu_lifecycle_tests/run_tests.py'),
                    '--cxx', a.cxx, '--repeat', str(a.repeat), '--output-dir', str(out / 'gpu')], check=True)
base = fixture.read_text().split('};\nvoid lifecycle()')[0]
assert all(m in base for m in required)
assert 'owner_publications.Open();' in gpu[:gpu.index('~Impl()')]
base = base.replace('struct Manager {', 'struct Manager {\n    Event* stopped=nullptr;')
stopped = 'if(worker.joinable()) { worker.request_stop(); worker.join(); }'
assert base.count(stopped) == 1
base = base.replace(stopped, stopped + '\n        if(stopped) stopped->Set();')

memory = method(read('src/video_core/memory_manager.cpp'),
                'void MemoryManager::BindRasterizer(').replace('MemoryManager::', '')
memory = memory.replace('    rasterizer = rasterizer_;',
                        '    if(bind_hook) bind_hook();\n    ++binds;\n    rasterizer = rasterizer_;')
fake_memory = r'''
struct TestAllocator {
    inline static int live=0,fail_after=-1;
    TestAllocator(u32,u32) {if(fail_after==0)throw std::bad_alloc();if(fail_after>0)--fail_after;++live;}
    ~TestAllocator() {--live;}
};
namespace Tegra {
struct MemoryManager {
    inline static int live=0,binds=0; inline static bool fail=false;
    inline static std::function<void()> bind_hook;
    VideoCore::Rasterizer* rasterizer=nullptr;
    template<class System> MemoryManager(System&,u64,u64,u64,u64) {if(fail)throw std::bad_alloc();++live;}
    ~MemoryManager() {--live;}
''' + memory.replace('VideoCore::RasterizerInterface*', 'VideoCore::Rasterizer*') + '\n};\n}\n'
channel_fixture = r'''
namespace Tegra {
struct CommandList {std::vector<int> entries;};
namespace Control {
struct ChannelState {
    s32 bind_id;u64 program_id=0;bool initialized=false,initialization_failed=false;
    std::shared_ptr<MemoryManager> memory_manager;
    int init_calls=0,bind_calls=0;std::function<void()> init_hook;
    explicit ChannelState(s32 id):bind_id{id} {}
    template<class System,class Gpu> void Init(System&,Gpu&,u64 id) {
        ++init_calls;program_id=id;if(init_hook)init_hook();
    }
    void BindRasterizer(VideoCore::Rasterizer*) {++bind_calls;}
};
}
}
'''
base = base.replace('struct Rasterizer {', '''struct Rasterizer {
    int channel_inits=0;std::function<void()> initialize_channel;
    template<class Channel> void InitializeChannel(Channel& channel) {
        Require(!channel.initialized,"channel advertised ready before backend initialization");
        ++channel_inits;if(initialize_channel)initialize_channel();
    }''')
base = base.replace('struct Scheduler {', '''struct Scheduler {
    int declared=0;template<class Channel> void DeclareChannel(std::shared_ptr<Channel>) {++declared;}''')
base = base.replace('struct Impl {', fake_memory + channel_fixture + '''
struct Impl {
    int system=0,gpu=0;s32 new_channel_id=1;
    std::unordered_map<s32,std::shared_ptr<Tegra::Control::ChannelState>> channels;
''')
init = method(gpu, '    std::optional<Common::TerminalIngress::Entry>\n    InitAddressSpace(')
channel_init = method(gpu, '    std::optional<Common::TerminalIngress::Entry>\n    InitChannel(')
channel_init = channel_init.replace('Control::ChannelState', 'Tegra::Control::ChannelState')
assert 'initialized = true' not in method(read('src/video_core/control/channel_state.cpp'), 'void ChannelState::Init(')
base += '\n' + init + '\n' + channel_init + '\n' + method(gpu, '    std::shared_ptr<Control::ChannelState> CreateChannel(').replace(
    'std::shared_ptr<Control::ChannelState>', 'std::shared_ptr<Tegra::Control::ChannelState>') + '\n};\n'
public_init = method(gpu, 'std::optional<Common::TerminalIngress::Entry>\nGPU::InitAddressSpace(')
public_init = public_init.replace('GPU::', '')
public_channel = method(gpu, 'std::optional<Common::TerminalIngress::Entry>\nGPU::InitChannel(')
public_channel = public_channel.replace('GPU::', '').replace('Control::ChannelState', 'Tegra::Control::ChannelState')
public_channel = public_channel.replace('bool allow_deferred)', 'bool allow_deferred = false)')
vm = method(read('src/core/hle/service/nvdrv/devices/nvhost_as_gpu.h'), '    struct VM {')
vm = vm.replace('Common::FlatAllocator<u32, 0, 32>', 'TestAllocator')
allocate = method(read('src/core/hle/service/nvdrv/devices/nvhost_as_gpu.cpp'),
                  'NvResult nvhost_as_gpu::AllocAsEx(').replace('nvhost_as_gpu::', '')
commit = '    pending_vm.initialised = true;'
assert allocate.count(commit) == 1
allocate = allocate.replace(commit, '    if(commit_hook) commit_hook();\n' + commit)
caller = r'''
struct PublicGpu {Impl* impl;
    int submissions=0;void PushGPUEntries(s32,Tegra::CommandList&&) {++submissions;}
''' + public_init + '\n' + public_channel + r'''
};
struct FixtureSystem {PublicGpu& facade;PublicGpu& GPU() {return facade;}};
enum class NvResult {Success,InvalidState,BadValue,AlreadyAllocated,BadParameter};
struct IoctlAllocAsEx {u32 big_page_size=0;u64 va_range_start=0,va_range_split=0,va_range_end=0;};
#define LOG_DEBUG(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
#define ASSERT_MSG(...) ((void)0)
struct AddressSpace {
    FixtureSystem& system;std::mutex mutex;std::function<void()> commit_hook;
''' + vm + ';\n    VM vm;\n    std::shared_ptr<Tegra::MemoryManager> gmmu;\n' + allocate + '\n};\n'
nv_channel = read('src/core/hle/service/nvdrv/devices/nvhost_gpu.cpp')
setup = method(nv_channel, 'NvResult nvhost_gpu::SetupGPFIFOChannel(').replace('nvhost_gpu::', '')
setup = setup.replace('    channel_state->program_id = program_id;',
                      '    if(setup_hook) setup_hook();\n    channel_state->program_id = program_id;')
submit = method(nv_channel, 'NvResult nvhost_gpu::SubmitGPFIFOImpl(').replace('nvhost_gpu::', '')
submit = submit.replace('    flags.raw = 0;', '    if(submit_hook) submit_hook();\n    flags.raw = 0;')
caller += r'''
#define LOG_WARNING(...) ((void)0)
#define LOG_TRACE(...) ((void)0)
struct Fence {u32 id=0,value=0;};
struct Flag {bool enabled=false;bool Value() const {return enabled;}};
struct Flags {Flag fence_wait,increment_value,fence_increment,suppress_wfi;u32 raw=0;};
struct IoctlAllocGpfifoEx {Fence fence_out;};
struct IoctlSubmitGpfifo {Flags flags;Fence fence;};
using DeviceFD=int;
struct ChannelSyncpoints {
    int queries=0,increments=0;
    Fence GetSyncpointFence(u32 id) {++queries;return {id,9};}
    bool IsFenceSignalled(Fence) {return true;}
    u32 IncrementSyncpointMaxExt(u32,u32 n) {++increments;return n;}
};
auto BuildWaitCommandList(Fence) {return std::vector<int>{};}
auto BuildIncrementCommandList(Fence) {return std::vector<int>{};}
auto BuildIncrementWithWfiCommandList(Fence) {return std::vector<int>{};}
struct Process {u64 GetProgramId() {return 77;}};
struct Session {Process* process;};
struct Container {
    Process process;Session session{&process};Session* GetSession(int) {return &session;}
};
struct ChannelDevice {
    FixtureSystem& system;Container core;std::unordered_map<int,int> sessions;
    std::shared_ptr<Tegra::Control::ChannelState> channel_state;
    std::mutex channel_mutex;ChannelSyncpoints syncpoint_manager;u32 channel_syncpoint=1;
    std::function<void()> setup_hook,submit_hook;
    ChannelDevice(FixtureSystem& s,std::shared_ptr<Tegra::Control::ChannelState> c):system{s},channel_state{std::move(c)} {}
''' + setup + '\n' + submit + '\n};\n'
tests = r'''
void HardRequire(bool condition,const char* message) {
    if(!condition) {std::cerr<<"FAIL "<<message<<"\n";std::cerr.flush();std::_Exit(91);}
}
void ClosedAndFailure() {
    Host host;VideoCore::Rasterizer raster;Impl gpu{host};gpu.rasterizer=&raster;
    PublicGpu facade{&gpu};FixtureSystem system{facade};AddressSpace device{system,{}, {}, {}, {}};
    IoctlAllocAsEx params;params.big_page_size=65536;
    const auto old_start=device.vm.va_range_start;
    const auto old_page=device.vm.big_page_size;
    gpu.NotifyShutdown();const auto binds=Tegra::MemoryManager::binds;
    auto result=device.AllocAsEx(params);
    // A missing-Close mutant would terminate in its destructor's Join; report
    // the earlier forbidden effect without unwinding through that invalid join.
    HardRequire(Tegra::MemoryManager::binds==binds,"closed publication bound rasterizer");
    Require(result==NvResult::InvalidState,"refused publication reported service success");
    Require(!device.gmmu && !device.vm.initialised && !device.vm.small_page_allocator &&
            !device.vm.big_page_allocator && device.vm.va_range_start==old_start && device.vm.big_page_size==old_page,
            "refused publication changed service owner state");
    Require(TestAllocator::live==0 && Tegra::MemoryManager::live==0,"refused publication leaked candidates");
}
void HealthyAndFailures() {
    Host host;VideoCore::Rasterizer raster;Impl gpu{host};gpu.rasterizer=&raster;
    PublicGpu facade{&gpu};FixtureSystem system{facade};
    for(int failure=0;failure<3;++failure) {
        AddressSpace device{system,{}, {}, {}, {}};IoctlAllocAsEx params;
        TestAllocator::fail_after=failure<2?failure:-1;Tegra::MemoryManager::fail=failure==2;
        bool threw=false;try {device.AllocAsEx(params);}catch(const std::bad_alloc&) {threw=true;}
        TestAllocator::fail_after=-1;Tegra::MemoryManager::fail=false;
        Require(threw && !device.gmmu && !device.vm.initialised && !device.vm.small_page_allocator &&
                !device.vm.big_page_allocator,"candidate construction failure published owner state");
        Require(TestAllocator::live==0 && Tegra::MemoryManager::live==0,"construction failure leaked candidates");
    }
    AddressSpace device{system,{}, {}, {}, {}};IoctlAllocAsEx params;
    Require(device.AllocAsEx(params)==NvResult::Success,"healthy pre-Start publication refused");
    Require(device.gmmu && device.gmmu->rasterizer==&raster && device.vm.initialised &&
            device.vm.small_page_allocator && device.vm.big_page_allocator,"healthy publication lost owner state");
    Require(device.AllocAsEx(params)==NvResult::InvalidState,"duplicate publication accepted");
}
void RetainAcrossTeardown(bool pause_bind) {
    Host host;VideoCore::Rasterizer raster;auto gpu=std::make_unique<Impl>(host);gpu->rasterizer=&raster;
    gpu->renderer->rasterizer=&raster;PublicGpu facade{gpu.get()};FixtureSystem system{facade};
    AddressSpace device{system,{}, {}, {}, {}};IoctlAllocAsEx params;Event entered,release,stopped;
    auto block=[&] {entered.Set();release.Wait();};
    if(pause_bind)Tegra::MemoryManager::bind_hook=block;else device.commit_hook=block;
    gpu->gpu_thread.stopped=&stopped;
    auto publish=std::async(std::launch::async,[&] {return device.AllocAsEx(params);});entered.Wait();
    auto destroy=std::async(std::launch::async,[gpu=std::move(gpu)]() mutable {gpu.reset();});stopped.Wait();
    if(destroy.wait_for(100ms)==std::future_status::ready) {
        // Do not destroy a surviving Entry after a mutant has freed its owner.
        std::cerr<<"FAIL teardown escaped retained owner publication\n";std::cerr.flush();std::_Exit(91);
    }
    release.Set();Require(Ready(publish)==NvResult::Success,"entered publication lost commit");Ready(destroy);
    Tegra::MemoryManager::bind_hook={};device.commit_hook={};
    Require(device.gmmu && device.vm.initialised,"joined publication omitted service commit");
}
int main() {
    try {
        ClosedAndFailure();HealthyAndFailures();RetainAcrossTeardown(true);RetainAcrossTeardown(false);
        Require(TestAllocator::live==0 && Tegra::MemoryManager::live==0,"fixture owners leaked");
        std::cout<<"PASS retained GPU address-space publication: closed refusal, pre-Start success, staged failure, bind and caller commit join\n";
    }catch(const std::exception& e) {std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}
}
'''
channel_tests = r'''
auto NewChannel(Impl& gpu,FixtureSystem& system,bool bound) {
    auto channel=gpu.CreateChannel(gpu.new_channel_id++);
    if(bound)channel->memory_manager=std::make_shared<Tegra::MemoryManager>(system,37,0,17,12);
    return channel;
}
void ChannelClosed() {
    Host host;VideoCore::Rasterizer raster;Impl gpu{host};gpu.rasterizer=&raster;
    PublicGpu facade{&gpu};FixtureSystem system{facade};gpu.NotifyShutdown();
    for(bool ready:{false,true}) {
        auto channel=NewChannel(gpu,system,true);channel->initialized=ready;channel->program_id=17;
        Require(gpu.channels.contains(channel->bind_id) && gpu.scheduler->declared>0,
                "post-close channel creation counterexample disappeared");
        ChannelDevice device{system,channel};IoctlAllocGpfifoEx setup_params;setup_params.fence_out={3,55};
        const auto result=device.SetupGPFIFOChannel(setup_params,7);
        HardRequire(result==(ready?NvResult::AlreadyAllocated:NvResult::InvalidState) &&
                    channel->program_id==17 && setup_params.fence_out.value==55 &&
                    device.syncpoint_manager.queries==0 && channel->init_calls==0,
                    "closed setup published channel metadata");
        IoctlSubmitGpfifo submit_params;submit_params.flags.raw=42;submit_params.fence={3,8};
        HardRequire(device.SubmitGPFIFOImpl(submit_params,Tegra::CommandList{})==NvResult::InvalidState &&
                    submit_params.fence.id==3 && submit_params.fence.value==8 && submit_params.flags.raw==42 &&
                    device.syncpoint_manager.increments==0 && facade.submissions==0,
                    "closed submit changed fence or queue state");
    }
}
void ChannelHealthyDeferred() {
    Host host;VideoCore::Rasterizer raster;Impl gpu{host};gpu.rasterizer=&raster;
    PublicGpu facade{&gpu};FixtureSystem system{facade};auto channel=NewChannel(gpu,system,false);
    ChannelDevice device{system,channel};IoctlAllocGpfifoEx params;
    Require(device.SetupGPFIFOChannel(params,7)==NvResult::Success && channel->program_id==77 &&
            !channel->initialized && !channel->initialization_failed && channel->init_calls==0,
            "healthy deferred setup changed initialization semantics");
    IoctlSubmitGpfifo submit_params;
    Require(device.SubmitGPFIFOImpl(submit_params,Tegra::CommandList{})==NvResult::InvalidState &&
            facade.submissions==0,"unbound channel submission accepted");
    channel->memory_manager=std::make_shared<Tegra::MemoryManager>(system,37,0,17,12);
    Require(device.SubmitGPFIFOImpl(submit_params,Tegra::CommandList{})==NvResult::Success &&
            channel->initialized && !channel->initialization_failed && channel->init_calls==1 &&
            channel->bind_calls==1 && raster.channel_inits==1 && facade.submissions==1,
            "healthy deferred channel failed to materialize");
    Require(device.SubmitGPFIFOImpl(submit_params,Tegra::CommandList{})==NvResult::Success &&
            channel->init_calls==1 && facade.submissions==2,"ready channel was reinitialized");
}
void ChannelFailures() {
    Host host;VideoCore::Rasterizer raster;Impl gpu{host};gpu.rasterizer=&raster;
    PublicGpu facade{&gpu};FixtureSystem system{facade};
    for(bool backend:{false,true}) {
        auto channel=NewChannel(gpu,system,true);ChannelDevice device{system,channel};IoctlAllocGpfifoEx params;
        auto fail=[] {throw std::runtime_error("channel init failure");};
        if(backend)raster.initialize_channel=fail;else channel->init_hook=fail;
        bool threw=false;try {device.SetupGPFIFOChannel(params,7);}catch(const std::runtime_error&) {threw=true;}
        Require(threw && channel->initialization_failed && !channel->initialized,
                "partial channel failure lost retry isolation");
        channel->init_hook={};raster.initialize_channel={};const auto calls=channel->init_calls;
        IoctlSubmitGpfifo submit_params;
        Require(device.SetupGPFIFOChannel(params,7)==NvResult::InvalidState &&
                device.SubmitGPFIFOImpl(submit_params,Tegra::CommandList{})==NvResult::InvalidState &&
                channel->init_calls==calls && facade.submissions==0,
                "partial channel initialization was replayed");
    }
}
void ChannelRetain(int stage) {
    Host host;VideoCore::Rasterizer raster;auto gpu=std::make_unique<Impl>(host);gpu->rasterizer=&raster;
    gpu->renderer->rasterizer=&raster;PublicGpu facade{gpu.get()};FixtureSystem system{facade};
    auto channel=NewChannel(*gpu,system,true);ChannelDevice device{system,channel};IoctlAllocGpfifoEx params;
    if(stage==3)Require(device.SetupGPFIFOChannel(params,7)==NvResult::Success,"ready-channel fixture failed");
    Event entered,release,stopped;auto block=[&] {entered.Set();release.Wait();};
    if(stage==0)channel->init_hook=block;
    else if(stage==1)raster.initialize_channel=block;
    else if(stage==2)device.setup_hook=block;
    else device.submit_hook=block;
    gpu->gpu_thread.stopped=&stopped;
    auto publish=std::async(std::launch::async,[&] {
        if(stage<3)return device.SetupGPFIFOChannel(params,7);
        IoctlSubmitGpfifo submit_params;return device.SubmitGPFIFOImpl(submit_params,Tegra::CommandList{});
    });entered.Wait();
    auto destroy=std::async(std::launch::async,[gpu=std::move(gpu)]() mutable {gpu.reset();});stopped.Wait();
    HardRequire(destroy.wait_for(100ms)!=std::future_status::ready,"teardown escaped retained channel initialization");
    release.Set();Require(Ready(publish)==NvResult::Success,"entered channel publication lost service completion");
    Ready(destroy);channel->init_hook={};raster.initialize_channel={};device.setup_hook={};device.submit_hook={};
}
'''
tests = tests.replace('int main() {', channel_tests + '\nint main() {')
final_check='        Require(TestAllocator::live==0 && Tegra::MemoryManager::live==0,"fixture owners leaked");'
assert tests.count(final_check)==1
tests = tests.replace(final_check,
                      '        ChannelClosed();ChannelHealthyDeferred();ChannelFailures();\n'
                      '        for(int stage=0;stage<4;++stage)ChannelRetain(stage);\n'+final_check+
                      '\n        std::cout<<"PASS retained channel initialization: deferred setup, ready commit, partial failure isolation and NV lease retention\\n";')
source = '#include <cstdlib>\n#include <unordered_map>\n#include "common/bit_util.h"\n' + base + caller + tests
flags = [a.cxx, '-std=c++23', '-O1', '-g', '-pthread', '-Wall', '-Wextra', '-Werror',
         '-I', str(root / 'src')]

def compile_source(name, text):
    cpp = out / (name + '.cpp');cpp.write_text(text)
    exe = out / (name + ('.exe' if os.name == 'nt' else ''))
    subprocess.run(flags + [str(cpp), '-o', str(exe)], check=True)
    return exe

exe = compile_source('publication', source)
for i in range(a.repeat):
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
    log = result.stdout + result.stderr;(out / f'positive-{i}.log').write_text(log)
    assert result.returncode == 0 and 'PASS retained GPU address-space publication:' in log and 'PASS retained channel initialization:' in log, log
print(f'PASS retained GPU owner publication ({a.repeat} repetitions)', flush=True)
refusal = '    if (!publication) {\n        return NvResult::InvalidState;\n    }'
assert allocate.count(refusal) == 1
controls = [
    ('missing-close', source.replace('        owner_publications.Close();', ''), 'closed publication bound rasterizer'),
    ('missing-join', source.replace('        owner_publications.Join();', ''), 'teardown escaped retained owner publication'),
    ('early-caller-release', source.replace('    if(commit_hook) commit_hook();',
        '    publication.reset();\n    if(commit_hook) commit_hook();'), 'teardown escaped retained owner publication'),
    ('ignored-refusal', source.replace(allocate,allocate.replace(refusal, '')), 'refused publication reported service success'),
    ('unstaged-vm', source.replace('    VM pending_vm;', '    VM& pending_vm = vm;'), 'refused publication changed service owner state'),
]
channel_controls = [
    ('channel-premature-ready', source.replace(channel_init,channel_init.replace(
        '            rasterizer->InitializeChannel(to_init);',
        '            to_init.initialized = true;\n            rasterizer->InitializeChannel(to_init);')),
     'channel advertised ready before backend initialization'),
    ('channel-missing-failure-isolation', source.replace(channel_init,channel_init.replace(
        '            to_init.initialization_failed = true;', '')),'partial channel failure lost retry isolation'),
    ('channel-setup-ignored-refusal', source.replace(setup,setup.replace(refusal,'')),
     'closed setup published channel metadata'),
    ('channel-submit-ignored-refusal', source.replace(submit,submit.replace(refusal,'')),
     'closed submit changed fence or queue state'),
    ('channel-setup-early-release', source.replace(setup,setup.replace('    if(setup_hook) setup_hook();',
        '    publication.reset();\n    if(setup_hook) setup_hook();')),'teardown escaped retained channel initialization'),
    ('channel-submit-early-release', source.replace(submit,submit.replace('    if(submit_hook) submit_hook();',
        '    publication.reset();\n    if(submit_hook) submit_hook();')),'teardown escaped retained channel initialization'),
]
for name, changed, expected in controls + channel_controls:
    assert changed != source
    mutant = compile_source(name, changed)
    result = subprocess.run([str(mutant)], capture_output=True, text=True, timeout=30)
    log = result.stdout + result.stderr;(out / (name + '.log')).write_text(log)
    assert result.returncode != 0 and 'FAIL ' + expected in log, (name, log)
    print('PASS GPU publication control: ' + name, flush=True)
paths = ['src/video_core/gpu.cpp', 'src/video_core/gpu.h', 'src/video_core/memory_manager.cpp',
         'src/core/hle/service/nvdrv/devices/nvhost_as_gpu.cpp',
         'src/core/hle/service/nvdrv/devices/nvhost_as_gpu.h', 'src/common/terminal_ingress.h',
         'src/core/hle/service/nvdrv/devices/nvhost_gpu.cpp',
         'src/video_core/control/channel_state.cpp', 'src/video_core/control/channel_state.h',
         'tools/gpu_lifecycle_tests/run_tests.py', 'tools/gpu_lifecycle_tests/run_owner_publication_tests.py']
(out / 'extraction.json').write_text(json.dumps({
    'sha256': {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths},
    'positive_repeats': a.repeat, 'controls': [c[0] for c in controls],
    'channel_controls': [c[0] for c in channel_controls],
    'actual': ['GPU publication API and forwarding', 'GPU destructor and NotifyShutdown',
               'MemoryManager BindRasterizer assignment', 'AllocAsEx and VM layout',
               'GPU channel initialization and creation', 'NV SetupGPFIFOChannel and SubmitGPFIFOImpl'],
    'fixtures': ['System owner lifetime', 'renderer', 'allocator', 'GMMU allocation', 'GPU worker',
                 'channel engine allocation/binding', 'queue and syncpoint services'],
    'instrumentation': ['counter/hook before rasterizer assignment', 'hook before caller commit', 'event after fixture worker stop'],
    'boundary': 'Terminal address-space/channel initialization and NV acknowledgement only; channel creation/binding, pre-submit buffer reads, queue acceptance/native completion remain independent; Guest admission Unknown',
}, indent=2))
