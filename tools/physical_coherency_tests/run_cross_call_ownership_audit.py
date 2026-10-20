#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reproduce OPEN cross-call ownership gaps using extracted production bodies.

Injected PTE, allocator and tree collaborators; not native process acceptance.
Passing means the documented defect still reproduces, NOT that ownership is safe.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
out = root / '.diagnostics/m4-cross-call-audit'
out.mkdir(parents=True, exist_ok=True)
paths = ['src/core/hle/kernel/k_page_table_base.cpp',
         'src/core/hle/kernel/k_page_group.h', 'src/core/memory.cpp',
         'src/core/controlled_mapping_publication.h', 'src/common/producer_drain.h',
         'src/core/hle/kernel/k_memory_block_manager.cpp',
         'tools/physical_coherency_tests/run_cross_call_ownership_audit.py']


def extract(path, marker):
    text = (root / path).read_text()
    start = text.index(marker)
    opening = text.index('{', start)
    depth, end = 1, opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


operate = extract(paths[0], 'Result KPageTableBase::Operate(PageLinkedList* page_list, KProcessAddress virt_addr,\n                               size_t num_pages, const KPageGroup&')
scoped = extract(paths[1], 'class KScopedPageGroup {') + ';'
wrapper = extract(paths[2], 'void Memory::MapMemoryRegion(')
finalize = extract(paths[5], 'void KMemoryBlockManager::Finalize(')
source = r'''
#include <array>
#include <cassert>
#include <functional>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <utility>
#include <vector>
#include "common/alignment.h"
#include "core/controlled_mapping_publication.h"
using Result=int;
constexpr u64 PageSize=4096;
constexpr u64 GetInteger(u64 value) {return value;}
#define R_SUCCEED() return 0
namespace Common {
using ProcessAddress=u64;
using PhysicalAddress=u64;
enum class MemoryPermission {ReadWrite};
struct PageTable {std::array<bool,2> mapped{};};
}
struct Impl {
    unsigned calls{};
    bool throw_after_effect{};
    void MapMemoryRegion(Common::PageTable& table,u64,u64,u64 phys,
                         Common::MemoryPermission,bool) {
        ++calls;table.mapped.at(phys/PageSize)=true;
        if(throw_after_effect) throw std::runtime_error("injected uncertain map");
    }
};
namespace Core::Memory {
struct Memory {
    Impl* impl;
    ControlledMappingPublication mapping_publications;
    Memory(Impl* target,bool controlled):impl{target},mapping_publications{controlled} {}
    void MapMemoryRegion(Common::PageTable&,Common::ProcessAddress,u64,u64,
                         Common::MemoryPermission,bool);
};
// @WRAPPER@
}
namespace Kernel {
using KProcessAddress=u64;
struct PageLinkedList {};
struct KPageProperties {unsigned perm{};};
enum class OperationType {MapGroup,MapFirstGroup,MapFirstGroupPhysical};
Common::MemoryPermission ConvertToMemoryPermission(unsigned) {return Common::MemoryPermission::ReadWrite;}
struct Node {
    unsigned index;
    Core::Memory::ControlledMappingPublication* close_before{};
    size_t GetNumPages() const {
        // Deterministic closure BETWEEN completed Memory calls; no shared-lock recursion.
        if(close_before) close_before->Retire();
        return 1;
    }
    u64 GetAddress() const {return index*PageSize;}
};
struct KPageGroup {
    std::array<Node,2> nodes{{{0, nullptr},{1, nullptr}}};
    mutable std::array<unsigned,2> refs{};
    mutable unsigned opens{},first_opens{},closes{};
    size_t GetNumPages() const {return 2;}
    auto begin() const {return nodes.begin();}
    auto end() const {return nodes.end();}
    void Open() const {++opens;for(auto& ref:refs) ++ref;}
    void OpenFirst() const {++first_opens;for(auto& ref:refs) {assert(ref==0);++ref;}}
    void Close() const {++closes;for(auto& ref:refs) {assert(ref);--ref;}}
};
// @SCOPED@
struct KPageTableBase {
    Common::PageTable* m_impl;
    Core::Memory::Memory* m_memory;
    bool IsLockedByCurrentThread() const {return true;}
    Result Operate(PageLinkedList*,u64,size_t,const KPageGroup&,KPageProperties,OperationType,bool);
};
// @OPERATE@
struct KMemoryBlock {
    u64 address;
    u64 GetAddress() const {return address;}
    u64 GetSize() const {return PageSize;}
};
struct Tree {
    std::vector<KMemoryBlock*> nodes;
    struct Iterator {
        Tree* tree;size_t index;
        KMemoryBlock& operator*() const {return *tree->nodes.at(index);}
        bool operator!=(const Iterator& other) const {return index!=other.index;}
    };
    Iterator begin() {return {this,0};}
    Iterator end() {return {this,nodes.size()};}
    Iterator erase(Iterator it) {nodes.erase(nodes.begin()+it.index);return it;}
    bool empty() const {return nodes.empty();}
};
struct KMemoryBlockSlabManager {
    unsigned freed{};
    void Free(KMemoryBlock*) {++freed;}
};
using BlockCallback=std::function<void(u64,u64)>;
struct KMemoryBlockManager {
    Tree m_memory_block_tree;
    void Finalize(KMemoryBlockSlabManager*,BlockCallback&&);
};
// @FINALIZE@
}
int main() {
    using O=Kernel::OperationType;
    for(auto operation:{O::MapGroup,O::MapFirstGroup,O::MapFirstGroupPhysical}) {
        // Success, refusal before first node, close between nodes, uncertain first node,
        // and ordinary untracked control.
        for(unsigned mode=0;mode<5;++mode) {
            Common::PageTable pte;Impl impl;
            Core::Memory::Memory memory{&impl,mode!=4};
            Kernel::KPageTableBase table{&pte,&memory};Kernel::KPageGroup pg;
            if(mode==1) memory.mapping_publications.Retire();
            if(mode==2 || mode==4) pg.nodes[1].close_before=&memory.mapping_publications;
            impl.throw_after_effect=mode==3;
            bool threw=false;
            try {assert(table.Operate(nullptr,PageSize,2,pg,{},operation,false)==0);}
            catch(const std::runtime_error&) {threw=true;}
            assert(pg.opens==(operation==O::MapGroup ? 1u : 0u));
            assert(pg.first_opens==(operation==O::MapGroup ? 0u : 1u));
            if(mode==0 || mode==4) {
                assert(!threw && impl.calls==2 && pte.mapped[0] && pte.mapped[1]);
                assert(pg.refs[0]==1 && pg.refs[1]==1 && pg.closes==0);
            } else if(mode==1) {
                assert(threw && impl.calls==0 && !pte.mapped[0] && !pte.mapped[1]);
                assert(pg.refs[0]==0 && pg.refs[1]==0 && pg.closes==1);
            } else {
                assert(threw && impl.calls==1 && pte.mapped[0] && !pte.mapped[1]);
                assert(pg.refs[0]==0 && pg.refs[1]==0 && pg.closes==1 &&
                       "OPEN defect: published prefix lost group ownership");
            }
        }
    }
    for(unsigned failure=0;failure<5;++failure) {
        Kernel::KMemoryBlock a{PageSize},b{2*PageSize};
        Kernel::KMemoryBlockManager manager{{{&a,&b}}};
        Kernel::KMemoryBlockSlabManager slab;unsigned callbacks=0;bool threw=false;
        std::array<bool,2> effects{};
        const unsigned fail_at=failure<=2 ? 1 : 2;
        try {manager.Finalize(&slab,[&](u64 addr,u64) {
            ++callbacks;
            assert(manager.m_memory_block_tree.nodes.front()->address==addr &&
                   "Finalize must retain current record during callback");
            if(failure && callbacks==fail_at && failure%2==1)
                throw std::runtime_error("injected before effects");
            effects.at(addr/PageSize-1)=true;
            if(failure && callbacks==fail_at)
                throw std::runtime_error("injected after effects");
        });} catch(const std::runtime_error&) {threw=true;}
        if(failure) {
            assert(threw && callbacks==fail_at && slab.freed==fail_at-1 &&
                   manager.m_memory_block_tree.nodes.size()==3-fail_at &&
                   manager.m_memory_block_tree.nodes[0]==(fail_at==1 ? &a : &b) &&
                   "Finalize must retain failed and untouched records");
            assert(effects.at(fail_at-1)==(failure%2==0));
            // Explicitly idempotent collaborator: this is NOT arbitrary callback rollback.
            manager.Finalize(&slab,[&](u64 addr,u64) {effects.at(addr/PageSize-1)=true;});
            assert(slab.freed==2 && effects[0] && effects[1] && manager.m_memory_block_tree.empty());
        } else assert(!threw && callbacks==2 && slab.freed==2 && manager.m_memory_block_tree.empty());
    }
    std::cout<<"PASS cross-call audit: MapGroup still OPEN, Finalize records retained; injected collaborators only\n";
}
'''
for marker, body in [('WRAPPER', wrapper), ('SCOPED', scoped), ('OPERATE', operate), ('FINALIZE', finalize)]:
    source = source.replace('// @' + marker + '@', body)
cpp = out / 'audit.cpp'
cpp.write_text(source)
exe = out / ('audit.exe' if os.name == 'nt' else 'audit')
command = [os.environ.get('CXX', 'g++'), '-std=c++23', '-O1', '-pthread',
           '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-I', str(root / 'src')]
subprocess.run(command + [str(cpp), '-o', str(exe)], check=True)
for repeat in range(1, 4):
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
    (out / f'audit-{repeat}.txt').write_text(result.stdout + result.stderr)
    assert result.returncode == 0 and 'PASS cross-call audit:' in result.stdout, result
    print(result.stdout.strip(), flush=True)
# Sensitivity controls are deliberately incomplete counterfactuals, not proposed repairs.
retained = operate.replace('for (const auto& node : page_group) {',
                          'size_t completed=0; try { for (const auto& node : page_group) {')
retained = retained.replace('virt_addr += size;', 'virt_addr += size; ++completed;')
retained = retained.replace('// We succeeded! We want to persist',
                            '} catch (...) { if(completed) spg.CancelClose(); throw; }\n'
                            '        // We succeeded! We want to persist')
reordered = finalize.replace('        it = m_memory_block_tree.erase(it);\n', '')
reordered = reordered.replace('        block_callback(block->GetAddress(), block->GetSize());',
                              '        it = m_memory_block_tree.erase(it);\n'
                              '        block_callback(block->GetAddress(), block->GetSize());')
controls = [('retain-prefix', source.replace(operate, retained),
             'OPEN defect: published prefix lost group ownership'),
            ('erase-before-callback', source.replace(finalize, reordered),
             'Finalize must retain current record during callback')]
for name, changed, expected in controls:
    assert changed != source, name
    control_cpp = out / (name + '.cpp')
    control_cpp.write_text(changed)
    control_exe = out / (name + ('.exe' if os.name == 'nt' else ''))
    subprocess.run(command + [str(control_cpp), '-o', str(control_exe)], check=True)
    result = subprocess.run([str(control_exe)], capture_output=True, text=True, timeout=15)
    log = result.stdout + result.stderr
    (out / (name + '.txt')).write_text(log)
    assert result.returncode != 0 and 'assert' in log.lower() and expected in log, (name, log)
    print('PASS audit sensitivity control: ' + name, flush=True)
(out / 'extraction.json').write_text(json.dumps({
    'status': 'mapgroup-open-finalize-bookkeeping-fixed',
    'repeats': 3,
    'sensitivity_controls': [name for name, _, _ in controls],
    'sha256': {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in paths},
}, indent=2) + '\n')
