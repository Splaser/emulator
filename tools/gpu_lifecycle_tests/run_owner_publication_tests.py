# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual GPU/NV address-space publication; fixture renderer, allocator and GMMU."""
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
base = base.replace('struct Impl {', fake_memory + '\nstruct Impl {')
init = method(gpu, '    std::optional<Common::TerminalIngress::Entry>\n    InitAddressSpace(')
base += '\n' + init + '\n};\n'
public_init = method(gpu, 'std::optional<Common::TerminalIngress::Entry>\nGPU::InitAddressSpace(')
public_init = public_init.replace('GPU::', '')
vm = method(read('src/core/hle/service/nvdrv/devices/nvhost_as_gpu.h'), '    struct VM {')
vm = vm.replace('Common::FlatAllocator<u32, 0, 32>', 'TestAllocator')
allocate = method(read('src/core/hle/service/nvdrv/devices/nvhost_as_gpu.cpp'),
                  'NvResult nvhost_as_gpu::AllocAsEx(').replace('nvhost_as_gpu::', '')
commit = '    pending_vm.initialised = true;'
assert allocate.count(commit) == 1
allocate = allocate.replace(commit, '    if(commit_hook) commit_hook();\n' + commit)
caller = r'''
struct PublicGpu {Impl* impl;
''' + public_init + r'''
};
struct FixtureSystem {PublicGpu& facade;PublicGpu& GPU() {return facade;}};
enum class NvResult {Success,InvalidState,BadValue};
struct IoctlAllocAsEx {u32 big_page_size=0;u64 va_range_start=0,va_range_split=0,va_range_end=0;};
#define LOG_DEBUG(...) ((void)0)
#define LOG_ERROR(...) ((void)0)
#define ASSERT_MSG(...) ((void)0)
struct AddressSpace {
    FixtureSystem& system;std::mutex mutex;std::function<void()> commit_hook;
''' + vm + ';\n    VM vm;\n    std::shared_ptr<Tegra::MemoryManager> gmmu;\n' + allocate + '\n};\n'
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
source = '#include <cstdlib>\n#include "common/bit_util.h"\n' + base + caller + tests
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
    assert result.returncode == 0 and 'PASS retained GPU address-space publication:' in log, log
print(f'PASS retained GPU owner publication ({a.repeat} repetitions)', flush=True)
refusal = '    if (!publication) {\n        return NvResult::InvalidState;\n    }'
assert source.count(refusal) == 1
controls = [
    ('missing-close', source.replace('        owner_publications.Close();', ''), 'closed publication bound rasterizer'),
    ('missing-join', source.replace('        owner_publications.Join();', ''), 'teardown escaped retained owner publication'),
    ('early-caller-release', source.replace('    if(commit_hook) commit_hook();',
        '    publication.reset();\n    if(commit_hook) commit_hook();'), 'teardown escaped retained owner publication'),
    ('ignored-refusal', source.replace(refusal, ''), 'refused publication reported service success'),
    ('unstaged-vm', source.replace('    VM pending_vm;', '    VM& pending_vm = vm;'), 'refused publication changed service owner state'),
]
for name, changed, expected in controls:
    assert changed != source
    mutant = compile_source(name, changed)
    result = subprocess.run([str(mutant)], capture_output=True, text=True, timeout=30)
    log = result.stdout + result.stderr;(out / (name + '.log')).write_text(log)
    assert result.returncode != 0 and 'FAIL ' + expected in log, (name, log)
    print('PASS GPU publication control: ' + name, flush=True)
paths = ['src/video_core/gpu.cpp', 'src/video_core/gpu.h', 'src/video_core/memory_manager.cpp',
         'src/core/hle/service/nvdrv/devices/nvhost_as_gpu.cpp',
         'src/core/hle/service/nvdrv/devices/nvhost_as_gpu.h', 'src/common/terminal_ingress.h',
         'tools/gpu_lifecycle_tests/run_tests.py', 'tools/gpu_lifecycle_tests/run_owner_publication_tests.py']
(out / 'extraction.json').write_text(json.dumps({
    'sha256': {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths},
    'positive_repeats': a.repeat, 'controls': [c[0] for c in controls],
    'actual': ['GPU publication API and forwarding', 'GPU destructor and NotifyShutdown',
               'MemoryManager BindRasterizer assignment', 'AllocAsEx and VM layout'],
    'fixtures': ['System owner lifetime', 'renderer', 'allocator', 'GMMU allocation', 'GPU worker'],
    'instrumentation': ['counter/hook before rasterizer assignment', 'hook before caller commit', 'event after fixture worker stop'],
    'boundary': 'Terminal address-space publication only; channel creation/init/binding and existing mappings remain independent; Guest admission Unknown',
}, indent=2))
