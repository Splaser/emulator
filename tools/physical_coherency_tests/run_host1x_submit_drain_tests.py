# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual synchronous host1x Submit with controlled memory/device collaborators."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--repeat', type=int, default=3)
p.add_argument('--cxx', default=os.environ.get('CXX', 'g++'))
p.add_argument('--output-dir', type=Path)
a = p.parse_args()
if a.repeat < 1:
    p.error('--repeat must be positive')
root = Path(__file__).resolve().parents[2]
out = (a.output_dir or root / '.diagnostics/m4-host1x-submit-drain').resolve()
out.mkdir(parents=True, exist_ok=True)
cpp_path = 'src/core/hle/service/nvdrv/devices/nvhost_nvdec_common.cpp'
header_path = 'src/core/hle/service/nvdrv/devices/nvhost_nvdec_common.h'
cpp = (root / cpp_path).read_text()
header = (root / header_path).read_text()


def block(text, marker):
    start = text.index(marker)
    opening = text.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


submit = block(cpp, 'NvResult nvhost_nvdec_common::Submit(').replace('nvhost_nvdec_common::', '')
helpers = cpp[cpp.index('template <typename T>'):cpp.index('} // Anonymous namespace')]
# Scheduling annotation only, immediately before the actual response memcpy.
copy = '    std::memcpy(dst.data() + offset, src.data(), bytes_copied);'
assert helpers.count(copy) == 1
helpers = helpers.replace(copy, '    if (before_response_copy) before_response_copy();\n' + copy)
structs = '\n'.join(block(header, 'struct ' + name + ' {') + ';'
                    for name in ('IoctlSubmit', 'CommandBuffer', 'Reloc', 'SyncptIncr'))
source = r'''
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <future>
#include <iostream>
#include <span>
#include <unordered_map>
#include <vector>
#include "common/producer_drain.h"
#include "common/scope_exit.h"
using namespace std::chrono_literals;
using DeviceFD=int;using u8=unsigned char;using u32=unsigned;using u32_le=u32;using s32=int;
void Require(bool value,const char* why) {if(!value) {std::cerr<<"FAIL "<<why<<"\n";std::cerr.flush();std::_Exit(91);}}
#define LOG_DEBUG(...) ((void)0)
#define ASSERT_OR_EXECUTE(condition,action) do {if(!(condition)){action;}} while(false)
enum class NvResult {Success,Busy,InvalidState};
namespace Tegra {using ChCommandHeaderList=std::vector<u32>;}
std::function<void()> before_response_copy;
''' + helpers + r'''
struct Kernel {
    std::shared_ptr<Common::ProducerDrain> domain=std::make_shared<Common::ProducerDrain>();
    const auto& Host1xSubmitDomain() const {return domain;}
};
struct Memory {
    int reads=0;std::function<void()> on_read;
    void ReadBlock(unsigned long long,void*,size_t) {++reads;if(on_read)on_read();}
};
struct Process {Memory memory;Memory& GetMemory() {return memory;}};
struct Session {Process* process;};
struct HostFile {std::unordered_map<int,unsigned> fd_to_id{{1,9}};};
struct Container {
    Process process;Session session{&process};HostFile file;
    Session* GetSession(int) {return &session;}
    HostFile& Host1xDeviceFile() {return file;}
};
struct Gpu {
    bool enabled=true;int calls=0;std::function<void()> on_dispatch;
    bool UseNvdec() const {return enabled;}
    void PushCommandBuffer(u32,Tegra::ChCommandHeaderList&) {++calls;if(on_dispatch)on_dispatch();}
};
struct System {struct Kernel kernel;Gpu gpu;struct Kernel& Kernel() {return kernel;}Gpu& GPU() {return gpu;}};
struct Syncpoints {
    int changes=0;std::function<void()> on_change;
    u32 IncrementSyncpointMaxExt(u32,u32) {++changes;if(on_change)on_change();return 123;}
};
struct Object {unsigned long long address=4096;};
struct Nvmap {std::optional<Object> GetHandle(int id) {return id<0?std::nullopt:std::optional<Object>{Object{}};}};
struct Device {
''' + structs + r'''
    System system;Container core;Nvmap nvmap;Syncpoints syncpoint_manager;
    std::unordered_map<int,int> sessions{{1,4}};
''' + submit + r'''
};
struct Packet {
    Device::IoctlSubmit params{};std::vector<u8> bytes;
    Packet(bool sync,bool suffix=false,bool invalid=false) {
        params.cmd_buffer_count=suffix?2:1;params.syncpoint_count=sync?1:0;params.fence_count=sync?1:0;
        std::vector<Device::CommandBuffer> commands(params.cmd_buffer_count);
        commands[0]={invalid?-1:1,0,1};if(suffix)commands[1]={-1,0,1};
        bytes.resize(commands.size()*sizeof(commands[0])+params.syncpoint_count*sizeof(Device::SyncptIncr)+params.fence_count*sizeof(u32));
        std::memcpy(bytes.data(),commands.data(),commands.size()*sizeof(commands[0]));
    }
};
void Closed() {
    Device d;Packet p{true};const auto before=p.bytes;
    auto closed=d.system.kernel.domain->TryClose(64);Require(bool(closed),"host1x close failed");
    Require(d.Submit(p.params,p.bytes,1)==NvResult::Busy && d.syncpoint_manager.changes==0 &&
            d.core.process.memory.reads==0 && d.system.gpu.calls==0 && p.bytes==before,
            "closed host1x Submit performed effects or accepted commands");
    Require(closed->ResumeNoEffects(),"host1x resume failed");
    Require(d.Submit(p.params,p.bytes,1)==NvResult::Success && d.system.gpu.calls==1 && d.syncpoint_manager.changes==1,
            "resumed host1x Submit lost commands");
}
void InFlight(int stage) {
    Device d;Packet p{true};std::promise<void> entered,release;
    auto began=entered.get_future();auto leave=release.get_future().share();
    auto pause=[&] {entered.set_value();leave.wait();};
    if(stage==0)d.core.process.memory.on_read=pause;
    else if(stage==1)d.system.gpu.on_dispatch=pause;
    else before_response_copy=pause;
    // Response memcpy is called for command and fence vectors; pause just once.
    bool response_paused=false;
    if(stage==2)before_response_copy=[&] {if(!response_paused){response_paused=true;pause();}};
    auto work=std::async(std::launch::async,[&] {return d.Submit(p.params,p.bytes,1);});
    Require(began.wait_for(3s)==std::future_status::ready,"host1x work rendezvous timeout");
    auto closure=d.system.kernel.domain->TryClose(64);
    Require(closure && closure->Poll()==Common::ProducerDrain::Result::Pending,
            "active host1x Submit escaped producer drain");
    release.set_value();Require(work.get()==NvResult::Success,"admitted host1x Submit failed");
    before_response_copy={};
    Require(closure->Poll()==Common::ProducerDrain::Result::DrainedSubset,"finished host1x Submit failed drain");
}
void RefusedSuffix() {
    Device d;Packet p{false,true};
    Require(d.Submit(p.params,p.bytes,1)==NvResult::InvalidState && d.system.gpu.calls==1,
            "host1x partial prefix fixture failed");
    Require(!d.system.kernel.domain->TryClose(64) && !d.system.kernel.domain->TryEnter(),
            "host1x refused suffix granted drain authority");
}
void NoEffectsFailure() {
    Device d;Packet p{false,false,true};
    Require(d.Submit(p.params,p.bytes,1)==NvResult::InvalidState && d.system.gpu.calls==0,
            "host1x validation fixture failed");
    auto closure=d.system.kernel.domain->TryClose(64);
    Require(closure && closure->Poll()==Common::ProducerDrain::Result::DrainedSubset,
            "no-effects host1x validation unnecessarily sealed");
}
void Failed(int stage) {
    Device d;Packet p{stage==0};auto fail=[] {throw 42;};
    if(stage==0)d.syncpoint_manager.on_change=fail;
    else if(stage==1)d.core.process.memory.on_read=fail;
    else d.system.gpu.on_dispatch=fail;
    bool caught=false;try {(void)d.Submit(p.params,p.bytes,1);}catch(int) {caught=true;}
    Require(caught,"host1x throwing collaborator failed");
    const char* why=stage==0?"host1x syncpoint exception granted drain authority":
                    stage==1?"host1x read exception granted drain authority":"host1x dispatch exception granted drain authority";
    Require(!d.system.kernel.domain->TryClose(64) && !d.system.kernel.domain->TryEnter(),why);
}
int main() {Closed();for(int i=0;i<3;++i)InFlight(i);NoEffectsFailure();RefusedSuffix();for(int i=0;i<3;++i)Failed(i);
    std::cout<<"PASS host1x Submit refusal, complete-body drain and partial-effect quarantine\n";}
'''
flags = [a.cxx, '-std=c++23', '-O1', '-pthread', '-Wall', '-Wextra', '-Werror', '-I', str(root / 'src')]


def build(name, text):
    path = out / (name + '.cpp')
    path.write_text(text)
    exe = out / (name + ('.exe' if os.name == 'nt' else ''))
    subprocess.run(flags + [str(path), '-o', str(exe)], check=True)
    return exe


exe = build('host1x-submit', source)
for i in range(a.repeat):
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
    log = result.stdout + result.stderr
    (out / f'positive-{i}.log').write_text(log)
    assert result.returncode == 0 and 'PASS host1x Submit' in log, log
print(f'PASS actual host1x Submit ({a.repeat} repetitions)', flush=True)
controls = [
    ('omit-admission', source.replace('    if (!submission) return NvResult::Busy;', ''),
     'closed host1x Submit performed effects or accepted commands'),
    ('release-before-dispatch', source.replace('        gpu.PushCommandBuffer(', '        submission.reset();\n        gpu.PushCommandBuffer('),
     'active host1x Submit escaped producer drain'),
    ('omit-partial-seal', source.replace('if (effects_started && !completed) domain->Seal();', '(void)effects_started; (void)completed;'),
     'host1x refused suffix granted drain authority'),
    ('mark-after-syncpoint', source.replace('            effects_started = true;', '').replace(
        'syncpoint_manager.IncrementSyncpointMaxExt(syncpt_incr.id, syncpt_incr.increments);',
        'syncpoint_manager.IncrementSyncpointMaxExt(syncpt_incr.id, syncpt_incr.increments);\n            effects_started = true;'),
     'host1x syncpoint exception granted drain authority'),
    ('mark-after-read', source.replace('        effects_started = true;\n        session->process', '        session->process').replace(
        '        gpu.PushCommandBuffer(', '        effects_started = true;\n        gpu.PushCommandBuffer('),
     'host1x read exception granted drain authority'),
    ('complete-before-dispatch', source.replace('        gpu.PushCommandBuffer(', '        completed = true;\n        gpu.PushCommandBuffer('),
     'host1x refused suffix granted drain authority'),
]
for name, changed, expected in controls:
    assert changed != source
    mutant = build(name, changed)
    result = subprocess.run([str(mutant)], capture_output=True, text=True, timeout=15)
    log = result.stdout + result.stderr
    (out / (name + '.log')).write_text(log)
    assert result.returncode != 0 and 'FAIL ' + expected in log, (name, log)
    print('PASS host1x Submit control: ' + name, flush=True)
paths = [cpp_path, header_path, 'src/video_core/gpu.cpp', 'src/video_core/cdma_pusher.cpp',
         'src/common/producer_drain.h', 'src/common/scope_exit.h',
         'tools/physical_coherency_tests/run_host1x_submit_drain_tests.py']
(out / 'extraction.json').write_text(json.dumps({
    'sha256': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
    'positive_repeats': a.repeat, 'controls': [c[0] for c in controls],
    'actual': ['Submit, SliceVectors and WriteVectors', 'ioctl structs', 'ProducerDrain and ScopeGuard'],
    'fixtures': ['Kernel, Memory, nvmap, syncpoints and synchronous GPU/CDma work'],
    'boundary': 'Shared synchronous ioctl Submit subset only; no real VIC/decoder, device/native GPU or Guest admission proof.'}, indent=2))
