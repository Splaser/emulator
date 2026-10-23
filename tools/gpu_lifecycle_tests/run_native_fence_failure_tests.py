# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual MasterSemaphore fence completion bodies with controlled Vulkan results."""
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
out = (a.output_dir or root / '.diagnostics/m4-native-fence-failure').resolve()
out.mkdir(parents=True, exist_ok=True)
path = 'src/video_core/renderer_vulkan/vk_master_semaphore.cpp'
production = (root / path).read_text()


def method(marker):
    start = production.index(marker)
    pos = production.index('{', start)
    depth, end = 1, pos + 1
    while depth:
        depth += (production[end] == '{') - (production[end] == '}')
        end += 1
    return production[start:end].replace('MasterSemaphore::', '')


wait = method('void MasterSemaphore::Wait(u64 tick)')
worker = method('void MasterSemaphore::WaitThread(')
source = r'''
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <deque>
#include <future>
#include <iostream>
#include <mutex>
#include <optional>
#include <queue>
#include <thread>
using u64=unsigned long long;
using VkResult=int;
constexpr int VK_SUCCESS=0,VK_TIMEOUT=2,VK_ERROR_DEVICE_LOST=-4;
using namespace std::chrono_literals;
void Require(bool value,const char* reason) {
    if(!value) {std::cerr<<"FAIL "<<reason<<"\n";std::cerr.flush();std::_Exit(91);}
}
namespace vk {
struct Exception {int result;explicit Exception(int r):result{r} {}};
struct Fence {
    int id=0,result=0;inline static std::atomic<int> resets=0;
    Fence()=default;Fence(int i,int r):id{i},result{r} {}
    Fence(Fence&& other) noexcept:id{std::exchange(other.id,0)},result{other.result} {}
    Fence& operator=(Fence&& other) noexcept {id=std::exchange(other.id,0);result=other.result;return *this;}
    int Wait() {return result;}void Reset() {++resets;}
};
}
namespace Common {
template<class CV,class Lock,class Pred>
void CondvarWait(CV& cv,Lock& lock,std::stop_token token,Pred pred) {cv.wait(lock,token,pred);}
}
struct FakeTimeline {
    explicit operator bool() const {return false;}
    bool Wait(u64) {throw vk::Exception(-9);}
};
struct Master {
    using Waitable=std::pair<u64,vk::Fence>;
    FakeTimeline semaphore;std::atomic<u64> gpu_tick{0};
    std::atomic<VkResult> completion_failure{VK_SUCCESS};std::optional<Waitable> failed_wait;
    std::mutex wait_mutex,free_mutex;std::condition_variable free_cv;
    std::condition_variable_any wait_cv;
    std::queue<Waitable> wait_queue;std::deque<vk::Fence> free_queue;
    bool IsFree(u64 tick) {return gpu_tick.load()>=tick;}void Refresh() {}
''' + wait + '\n' + worker + r'''
};
void Check(int result) {
    Master master;vk::Fence::resets=0;
    master.wait_queue.emplace(7,vk::Fence{17,result});
    // Later submissions must not leap over an unknown earlier completion.
    if(result!=VK_SUCCESS)master.wait_queue.emplace(8,vk::Fence{18,VK_SUCCESS});
    auto first=std::async(std::launch::async,[&] {
        try {master.Wait(7);return VK_SUCCESS;}catch(const vk::Exception& e) {return e.result;}
    });
    auto second=std::async(std::launch::async,[&] {
        try {master.Wait(7);return VK_SUCCESS;}catch(const vk::Exception& e) {return e.result;}
    });
    std::jthread worker([&](std::stop_token token) {master.WaitThread(token);});
    Require(first.wait_for(3s)==std::future_status::ready && second.wait_for(3s)==std::future_status::ready,
            "native fence failure stranded completion waiters");
    const auto first_result=first.get(),second_result=second.get();
    worker.request_stop();master.wait_cv.notify_all();worker.join();
    if(result==VK_SUCCESS) {
        Require(first_result==VK_SUCCESS && second_result==VK_SUCCESS && master.gpu_tick==7 &&
                vk::Fence::resets==1 && master.free_queue.size()==1,"successful native fence failed to retire");
    } else {
        Require(first_result==result && second_result==result,"failed native fence reported completion");
        Require(master.gpu_tick==0 && vk::Fence::resets==0 && master.free_queue.empty(),
                "failed native fence advanced tick or recycled resource");
        Require(master.failed_wait && master.failed_wait->second.id==17 && master.wait_queue.size()==1,
                "unknown native fence or queued suffix lost ownership");
        master.Wait(0); // already completed history remains available
        std::cout<<"PASS native fence failure wakes waiters and retains unknown prefix/suffix\n";
    }
}
int main() {Check(VK_SUCCESS);Check(VK_ERROR_DEVICE_LOST);Check(VK_TIMEOUT);}
'''
source = '#include <utility>\n' + source
flags = [a.cxx, '-std=c++23', '-O1', '-pthread', '-Wall', '-Wextra', '-Werror']


def build(name, text):
    cpp = out / (name + '.cpp')
    cpp.write_text(text)
    exe = out / (name + ('.exe' if os.name == 'nt' else ''))
    subprocess.run(flags + [str(cpp), '-o', str(exe)], check=True)
    return exe


exe = build('native-fence', source)
for i in range(a.repeat):
    result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=12)
    log = result.stdout + result.stderr
    (out / f'positive-{i}.log').write_text(log)
    assert result.returncode == 0 and log.count('PASS native fence failure') == 2, log
print(f'PASS actual native fence completion bodies ({a.repeat} repetitions)', flush=True)
controls = [
    ('ignore-wait-result', source.replace('if (result != VK_SUCCESS) {', 'if (false) {'),
     'failed native fence reported completion'),
    ('recycle-unknown-fence', source.replace('failed_wait.emplace(host_tick, std::move(fence));',
        'fence.Reset();free_queue.push_back(std::move(fence));'),
     'failed native fence advanced tick or recycled resource'),
]
for name, changed, expected in controls:
    assert changed != source
    mutant = build(name, changed)
    result = subprocess.run([str(mutant)], capture_output=True, text=True, timeout=12)
    log = result.stdout + result.stderr
    (out / (name + '.log')).write_text(log)
    assert result.returncode != 0 and 'FAIL ' + expected in log, (name, log)
    print('PASS native fence control: ' + name, flush=True)
paths = [path, 'src/video_core/renderer_vulkan/vk_master_semaphore.h',
         'tools/gpu_lifecycle_tests/run_native_fence_failure_tests.py']
(out / 'extraction.json').write_text(json.dumps({
    'sha256': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths},
    'positive_repeats': a.repeat, 'controls': [c[0] for c in controls],
    'actual': ['MasterSemaphore Wait and WaitThread'],
    'fixtures': ['Vulkan fence results, timeline-disabled facade and resource queues'],
    'boundary': 'No native device run, visibility, backing ownership or Guest admission proof.'
}, indent=2))
