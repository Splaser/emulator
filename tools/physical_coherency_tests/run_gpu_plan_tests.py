# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual GMMU resolver/pin adapters plus real HostMemory; device PTE storage is a fixture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

p = argparse.ArgumentParser()
p.add_argument('--cxx', default=os.environ.get('CXX', 'g++'))
p.add_argument('--boost-include', type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[2]
setup = [sys.executable,str(Path(__file__).with_name('run_physical_pin_tests.py')),'--cxx',a.cxx]
if a.boost_include:
    setup += ['--boost-include',str(a.boost_include)]
subprocess.run(setup,check=True)
out = root / '.diagnostics/m3b-physical-pin'

def function(text, marker, template=False, inline=False):
    pos = text.index(marker)
    start = text.rfind('template <',0,pos) if template else text.rfind('\n',0,pos)+1
    end = '\n    }' if inline else '\n}'
    return text[start:text.index(end,pos)+len(end)]+'\n'

gpu = (root/'src/video_core/memory_manager.cpp').read_text()
gpu_h = (root/'src/video_core/memory_manager.h').read_text()
device = (root/'src/core/device_memory_manager.h').read_text()
fixture = (root/'tools/physical_resolver_tests/tests.cpp').read_text().split('int main() {')[0]
start = fixture.index('namespace Common {')
end = fixture.index('namespace Core {',start)
fixture = fixture[:start]+fixture[end:]
fixture = '#include "common/alignment.h"\n'+fixture
fixture = fixture.replace('/* DEVICE_TRANSLATION */',function(device,'PAddr GetPhysicalRawAddressFromDAddr(',inline=True))
fixture = fixture.replace('/* DEVICE_SNAPSHOT */',function(device,'auto ReadPhysicalMappingSnapshot(',True,True))
fixture = fixture.replace('    ~DeviceFixture() {', '''
    std::unique_ptr<Common::HostMemory> real_backing;
    const Common::HostMemory* guest_backing{};
    DeviceFixture() : real_backing{std::make_unique<Common::HostMemory>(8ULL<<20,2ULL<<20)},
                      guest_backing{real_backing.get()} {
        backing_epoch=real_backing->BackingEpoch();
        physical_backing_size=real_backing->backing_size;
    }
''' + function(device,'std::optional<Common::PinnedPhysicalMemory> PinGuestPhysicalRange(',inline=True)+
                          '    ~DeviceFixture() {')
fixture = fixture.replace('/* GPU_INDEX */',function(gpu_h,'std::size_t PageEntryIndex(',True,True))
parts = []
for name,templated in [('GetEntry',True),('SetEntry',True),('IsBigPageContinuous',False),
                       ('SetBigPageContinuous',False),('NotifyMappingChange',True),
                       ('PageTableOp',True),('BigPageTableOp',True),('Map',False),
                       ('Unmap',False),('GpuToCpuAddress',False),('ResolvePhysicalRanges',False),
                       ('PinPhysicalRanges',False)]:
    parts.append(function(gpu,'MemoryManager::'+name+'(',templated))
fixture = fixture.replace('/* GPU_FUNCTIONS */',''.join(parts))
fixture = fixture.replace('    PhysicalResolveResult ResolvePhysicalRanges(',
    '    std::optional<PhysicalAccessPlan> PinPhysicalRanges(u64,u64) const;\n    PhysicalResolveResult ResolvePhysicalRanges(')
head = r'''
#include <functional>
#include "common/host_memory.h"
#include "video_core/physical_access_plan.h"
namespace Tegra {
std::function<void()> plan_ready;
void ObservePlanReady() {if(plan_ready) plan_ready();}
}
'''
tail = r'''
int main() {
    constexpr u64 P=4096,G=0x10000,D=0x20000;
    std::optional<Tegra::PhysicalAccessPlan> retained;
    {
        DeviceFixture dev;Tegra::MemoryManager memory{dev};
        dev.Map(D,0);dev.Map(D+P,3*P);
        memory.Map(G,D,2*P);
        retained=memory.PinPhysicalRanges(G+10,P+10);
        assert(retained && retained->Size()==P+10 && retained->Segments().size()==2);
        assert(retained->Segments()[0].logical_offset==0 && retained->Segments()[0].storage.PhysicalOffset()==10);
        assert(retained->Segments()[0].storage.Bytes().size()==P-10);
        assert(retained->Segments()[1].logical_offset==P-10 && retained->Segments()[1].storage.PhysicalOffset()==3*P);
        retained->Segments()[0].storage.Bytes()[0]=77;
        assert(dev.real_backing->BackingBasePointer()[10]==77);
        assert(!memory.PinPhysicalRanges(G+2*P,1));
        assert(!memory.PinPhysicalRanges(G,0));
        bool changed=false;
        Tegra::plan_ready=[&] {
            memory.Unmap(G,2*P);memory.Map(G,D+P,P);changed=true;
        };
        auto rejected=memory.PinPhysicalRanges(G+10,4);
        assert(changed && !rejected);
        Tegra::plan_ready={};
        auto remapped=memory.PinPhysicalRanges(G+10,4);
        assert(remapped && remapped->Segments()[0].storage.PhysicalOffset()==3*P+10);
        assert(retained->Segments()[0].storage.PhysicalOffset()==10);
        assert(retained->Segments()[0].storage.Bytes()[0]==77);
        dev.Map(D+P,5*P);
        auto replaced=memory.PinPhysicalRanges(G+10,4);
        assert(replaced && replaced->Segments()[0].storage.PhysicalOffset()==5*P+10);
        assert(remapped->Segments()[0].storage.PhysicalOffset()==3*P+10);
        // Real GMMU big-page path, not a contiguous-physical assumption.
        dev.Map(D+16*P,16*P,16*P);
        memory.Map(G+16*P,D+16*P,16*P,Tegra::PTEKind::INVALID,true);
        auto big=memory.PinPhysicalRanges(G+16*P+P-2,8);
        assert(big && big->Size()==8 && big->Segments()[0].storage.PhysicalOffset()==17*P-2);
    }
    assert(!retained->Segments()[0].storage.OwnerAlive());
    assert(retained->Segments()[0].storage.Bytes()[0]==77);
    retained.reset();
    std::cout<<"PASS actual GPU plan resolver: noncontiguous/split/big-page translation, holes, GPU remap during pin, device remap, retained physical allocation after owner exit\n";
}
'''
cpp = out/'gpu_plan.cpp'
cpp.write_text(head+fixture+tail)
exe = out/('gpu_plan.exe' if os.name=='nt' else 'gpu_plan')
cmd = [a.cxx,'-std=c++23','-O1','-pthread','-Wall','-Wextra','-Werror',
       '-Wno-unused-parameter','-Wno-missing-field-initializers',
       '-I',str(out/'stubs'),'-I',str(root/'src')]
if a.boost_include:
    cmd += ['-I',str(a.boost_include)]
cmd += [str(root/'src/common/host_memory.cpp')]
if os.name=='nt':
    cmd += [str(root/'src/common/dynamic_library.cpp')]
subprocess.run(cmd+[str(cpp),'-o',str(exe)],check=True)
subprocess.run([str(exe)],check=True,timeout=30)
(out/'gpu_plan_extraction.json').write_text(json.dumps({
    'sha256': {path:hashlib.sha256((root/path).read_bytes()).hexdigest() for path in [
        'src/video_core/memory_manager.cpp','src/video_core/memory_manager.h',
        'src/core/device_memory_manager.h','src/video_core/physical_access_plan.h']},
    'real': ['extracted GPU map/unmap/translation/resolver/pin methods',
             'device translation/snapshot/physical pin methods', 'HostMemory/OS allocations'],
    'fixtures': ['GPU/device page-table storage and manager shells', 'rasterizer invalidation sink',
                 'submapped range enumeration', 'post-pin mapping rendezvous'],
},indent=2))
