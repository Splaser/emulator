# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual CPU PageTable snapshots and cold Memory/HostMemory preparation; stores remain legacy."""
import argparse
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--cxx', default=os.environ.get('CXX', 'g++'))
p.add_argument('--boost-include', type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
out = root / '.diagnostics/m3b-cpu-mapping'
out.mkdir(parents=True, exist_ok=True)
fmt = out / 'stubs/fmt'
fmt.mkdir(parents=True, exist_ok=True)
(fmt / 'format.h').write_text('''#pragma once
#include <string>
namespace fmt {
template<class T> struct formatter;
struct format_parse_context {constexpr const char* begin() const {return nullptr;}};
template<class Out,class... T> Out format_to(Out out,const char*,T&&...) {return out;}
template<class... T> std::string format(const char* text,T&&...) {return text;}
}
''')
source = (root / 'src/core/memory.cpp').read_text()

def method(marker):
    start = source.index(marker)
    return source[start:source.index('\n    }', start) + 6]

prepare = method('    std::optional<PreparedCpuPage> PrepareControlledCpuPage(')
checkpoint = '        if (!physical || current_page_table != table || !mapping->IsCurrent())'
assert prepare.count(checkpoint) == 1
prepare = prepare.replace(checkpoint, '        ObservePrepared();\n' + checkpoint)
mapping = method('    void MapPages(')
head = r'''
#include <cassert>
#include <future>
#include <functional>
#include <iostream>
#include <latch>
#include <thread>
#include "core/controlled_cpu_page.h"
#include "common/host_memory.h"
#define LOG_DEBUG(...) ((void)0)
constexpr u64 CITRON_PAGEBITS=12,CITRON_PAGESIZE=4096;
namespace DramMemoryMap {constexpr u64 Base=0x80000000;}
using Core::Memory::PreparedCpuPage;
std::function<void()> prepared;
void ObservePrepared() {if(prepared) prepared();}
struct Device {
    Common::HostMemory buffer{8ULL<<20,2ULL<<20};
    template<class T> T* GetPointer(Common::PhysicalAddress p) {
        return reinterpret_cast<T*>(buffer.BackingBasePointer()+GetInteger(p)-DramMemoryMap::Base);
    }
};
struct System {
    Device device;
    Device& DeviceMemory() {return device;}
    bool IsShuttingDown() const {return false;}
};
struct Cpu {
    System& system;
    Common::PageTable* current_page_table;
'''
tail = r'''
};
int main() {
    System system;Common::PageTable table;table.Resize(16,12);Cpu cpu{system,&table};
    constexpr u64 B=DramMemoryMap::Base,P=4096;
    cpu.MapPages(table,1,1,B,Common::PageType::Memory);
    cpu.MapPages(table,2,1,B,Common::PageType::Memory);
    auto first=cpu.PrepareControlledCpuPage(P),alias=cpu.PrepareControlledCpuPage(2*P);
    assert(first && alias && first->mapping.IsCurrent());
    assert(first->physical.GateIdentity()==alias->physical.GateIdentity());
    assert(first->mapping.physical_page==B);
    assert(!cpu.PrepareControlledCpuPage(P+1) && !cpu.PrepareControlledCpuPage(16*P));
    prepared=[&]{cpu.MapPages(table,1,1,B+P,Common::PageType::Memory);};
    auto raced=cpu.PrepareControlledCpuPage(P);prepared={};
    if(raced) {std::cerr<<"cold CPU preparation accepted remap after pin\n";return 51;}
    assert(!first->mapping.IsCurrent());
    auto fresh=cpu.PrepareControlledCpuPage(P);assert(fresh && fresh->mapping.physical_page==B+P);
    assert(first->physical.PhysicalOffset()==0 && fresh->physical.PhysicalOffset()==P);
    auto token=table.SnapshotMapping(P);assert(token);
    {
        const auto mutation=table.MutateMappings();
        table.entries[1].pointer.Store(0,Common::PageType::RasterizerCachedMemory);
    }
    assert(!token->IsCurrent());
    auto cached=table.SnapshotMapping(P);assert(cached && cached->type==Common::PageType::RasterizerCachedMemory);
    cpu.MapPages(table,1,1,0,Common::PageType::Unmapped);
    assert(!cached->IsCurrent() && !cpu.PrepareControlledCpuPage(P));
    auto before_resize=table.SnapshotMapping(2*P);assert(before_resize);
    table.Resize(17,12);assert(!before_resize->IsCurrent());
    auto dying=std::make_unique<Common::PageTable>();dying->Resize(16,12);
    cpu.MapPages(*dying,1,1,B,Common::PageType::Memory);
    auto dead=dying->SnapshotMapping(P);assert(dead);dying.reset();assert(!dead->IsCurrent());
    // Actual mutator must exclude cold snapshot reads even between its PTE field writes.
    cpu.MapPages(table,1,1,B,Common::PageType::Memory);
    auto live=table.SnapshotMapping(P);assert(live);
    std::latch locked{1},release{1};
    std::thread mutator([&]{
        const auto mutation=table.MutateMappings();
        table.entries[1].pointer.Store(0,Common::PageType::DebugMemory);
        locked.count_down();release.wait();
        table.entries[1].backing_addr=B+P-P;
    });
    locked.wait();
    const bool wrongly_unlocked=live->domain->mutex.try_lock_shared();
    if(wrongly_unlocked) live->domain->mutex.unlock_shared();
    std::thread releaser([&]{release.count_down();});
    auto consistent=table.SnapshotMapping(P);mutator.join();releaser.join();
    assert(!wrongly_unlocked && consistent && consistent->physical_page==B+P);
    assert(consistent->type==Common::PageType::DebugMemory);
    std::cout<<"PASS actual CPU PageTable/cold Memory preparation: physical aliases, post-pin remap, tag/unmap/resize/retirement invalidation and consistent locked snapshot; ordinary stores unchanged\n";
}
'''
cpp = out / 'cpu_mapping.cpp'
cpp.write_text(head + prepare + '\n' + mapping + tail)
cmd = [a.cxx, '-std=c++23', '-O1', '-pthread', '-Wall', '-Wextra', '-Werror',
       '-Wno-unused-parameter', '-I', str(out / 'stubs'),
       '-I', str(root / '.diagnostics/m3b-physical-pin/stubs'),
       '-I', str(root / 'src'), '-I', str(root / 'externals/fmt/include')]
if a.boost_include:
    cmd += ['-I', str(a.boost_include)]
cmd += [str(root / 'src/common/host_memory.cpp'), str(root / 'src/common/page_table.cpp'),
        str(root / 'src/common/virtual_buffer.cpp')]
if os.name == 'nt':
    cmd += [str(root / 'src/common/dynamic_library.cpp')]
exe = out / ('cpu_mapping.exe' if os.name == 'nt' else 'cpu_mapping')
subprocess.run(cmd + [str(cpp), '-o', str(exe)], check=True)
subprocess.run([str(exe)], check=True, timeout=30)
control = out / 'cpu_mapping_control.cpp'
control.write_text((head + prepare + '\n' + mapping + tail).replace(
    ' || !mapping->IsCurrent()', ''))
subprocess.run(cmd + [str(control), '-o', str(exe)], check=True)
result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
if result.returncode != 51 or 'accepted remap after pin' not in result.stderr:
    raise RuntimeError('Missing post-pin validation negative control did not fail')
print('PASS negative control: cold CPU preparation accepted remap after pin')
