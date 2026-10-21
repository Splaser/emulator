#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Production cohort/roster/core bodies; injected kernel/backend/Memory collaborators."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[2]
out=root/'.diagnostics/m4-process-cohort-stop'
out.mkdir(parents=True,exist_ok=True)
prerequisite=root/'.diagnostics/m4-process-execution-stop/production.cpp'
assert prerequisite.exists(), 'Run run_process_execution_stop_tests.py first'
head=prerequisite.read_text().split('int main() {',1)[0]
head='#include "core/hle/kernel/process_cohort_stop.h"\n#include "core/controlled_mapping_publication.h"\n'+head
path='src/core/hle/kernel/process_cohort_stop.cpp'
methods=(root/path).read_text()
methods=methods[methods.index('namespace Kernel {'):]
factory_text=(root/'src/core/hle/kernel/k_process.cpp').read_text()
start=factory_text.index('std::optional<ProcessCohortStop> KProcess::TryStopProcessCohort(')
opening=factory_text.index('{',start)
end=opening+1;depth=1
while depth:
    depth+=(factory_text[end]=='{')-(factory_text[end]=='}');end+=1
factory='namespace Kernel {\n'+factory_text[start:end]+'\n}\n'
test='tools/physical_coherency_tests/process_cohort_stop_tests.cpp.in'
source=head+methods+factory+(root/test).read_text()
capture = methods[methods.index('    if (!owners) {'):methods.index('    if (!execution) {')]
late_capture = source.replace(capture, '').replace('    const auto result = execution->Poll();',
    '    const auto result = execution->Poll();\n' + capture)
variants=[('production',source,None),
    ('halt-before-cohort-capture',late_capture,
        'entire owner cohort must be retained before halt request'),
    ('omit-publication-drain',source.replace('    const auto published = publication.Poll();',
        '    const auto published = D::DrainedSubset;'),None)]
# The publication mutant must reach an early halt assertion, before producer exit.
variants[2]=(variants[2][0],variants[2][1], 'writer.backend.requests==0')
variants += [
    ('omit-creation-closure', source.replace('    if (state->creation_owner) throw CreationRefused{};', ''),
     'held creation closure must refuse new owners'),
    ('detach-publication-closure', source.replace(
        '    auto publication = m_kernel.ProcessPublicationDomain()->TryClose(poll_budget);',
        '    static Common::ProducerDrain unrelated;\n    auto publication = unrelated.TryClose(poll_budget);'),
     'held publication closure must refuse ordinary mappings'),
]
command=[os.environ.get('CXX','g++'),'-std=c++23','-O1','-pthread','-Wall','-Wextra','-Werror',
         '-Wno-unused-parameter','-I',str(root/'.diagnostics/m4-process-execution-stop/stubs'),'-I',str(root/'src')]
for name,text,expected in variants:
    assert expected is None or text!=source
    cpp=out/(name+'.cpp');cpp.write_text(text)
    exe=out/name
    subprocess.run(command+[str(cpp),'-o',str(exe)],check=True)
    for repeat in range(1,4 if expected is None else 2):
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
        log=result.stdout+result.stderr;(out/f'{name}-{repeat}.txt').write_text(log)
        if expected:
            assert result.returncode!=0 and expected in log and 'assert' in log.lower(),log
        else:
            assert result.returncode==0 and 'PASS sustained process cohort:' in log,log
    print('PASS '+name,flush=True)
paths=[path,'src/core/hle/kernel/process_cohort_stop.h','src/core/hle/kernel/k_process.cpp',
       'src/core/hle/kernel/k_process.h','src/core/hle/kernel/kernel.h',
       'src/core/hle/kernel/k_page_table_base.h','src/core/hle/kernel/k_process_page_table.h',
       'src/common/producer_drain.h','src/core/hle/kernel/process_execution_stop.cpp',
       'src/core/hle/kernel/process_execution_stop.h','src/tests/core/controlled_cpu_scheduler.cpp',
       'src/tests/CMakeLists.txt','.github/workflows/pr375-pr380-integration.yml',
       'src/core/hle/kernel/k_slab_heap.h','src/core/hle/kernel/process_owner_roster.cpp',
       'src/core/hle/kernel/process_owner_roster.h','src/core/controlled_mapping_publication.h',
       'src/core/memory.cpp','src/core/hle/kernel/kernel.cpp','src/core/hle/service/os/process.cpp',
       'tools/physical_coherency_tests/run_process_execution_stop_tests.py',
       'tools/physical_coherency_tests/process_execution_stop_fixture.cpp.in',test,
       'tools/physical_coherency_tests/run_process_cohort_stop_tests.py']
(out/'extraction.json').write_text(json.dumps({'positive_repeats':3,
    'assertion_mutants':[x[0] for x in variants[1:]],
    'sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths},
    'boundary':'Sustained creation/init/cold mapping cohort plus backend stop; injected collaborators; no Guest admission'},indent=2)+'\n')
