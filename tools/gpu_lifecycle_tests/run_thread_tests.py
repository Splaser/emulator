# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual ThreadManager, RunThread and bounded queue; shim only engine/renderer/platform."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--cxx', default=os.environ.get('CXX', 'g++'))
p.add_argument('--repeat', type=int, default=10)
p.add_argument('--sanitize', choices=['address', 'thread'])
p.add_argument('--handoff-controls', action='store_true')
args = p.parse_args()
if args.repeat < 1:
    p.error('--repeat must be positive')
root = Path(__file__).resolve().parents[2]
out = root / '.diagnostics/gpu-lifecycle' / ('windows' if os.name == 'nt' else 'linux')
out.mkdir(parents=True, exist_ok=True)
shim = out/'shims/video_core'
shim.mkdir(parents=True, exist_ok=True)
(shim/'framebuffer_config.h').write_text('''#pragma once
#include <vector>
#include "common/common_types.h"
namespace Tegra { struct CommandList { std::vector<int> entries; }; }
''')
production = (root/'src/video_core/gpu_thread.cpp').read_text()
gpu_source=(root/'src/video_core/gpu.cpp').read_text()
direct_cpu=gpu_source.index('    bool OnCPUWrite(DAddr addr, u64 size) {')
direct_cpu=gpu_source[direct_cpu:gpu_source.index('\n    }',direct_cpu)+len('\n    }')]
body = production[production.index('namespace VideoCommon::GPUThread {'):]
# Rendezvous signals only: the copied production wait and cancellation still run.
assert body.count('state.cv.wait(lk);') == 1
body = body.replace('state.cv.wait(lk);', 'if(queue_wait) { queue_wait->Set(); }\n        state.cv.wait(lk);')
assert body.count('thread.request_stop();') == 1
body = body.replace('thread.request_stop();', 'thread.request_stop(); if(stop_requested) stop_requested->Set();')
assert body.count('thread.join();') == 1
body = body.replace('thread.join();', 'thread.join(); if(worker_joined) worker_joined->Set();')
accepted='    const u64 fence{++state.last_fence};'
assert body.count(accepted)==1
body=body.replace(accepted,accepted+'\n    if(command_queued) command_queued->Set();')
terminal_header=(root/'src/common/terminal_ingress.h').read_text()
join='    void Join() noexcept {'
enter='        const auto old = value.fetch_add(1, std::memory_order_acq_rel);'
assert terminal_header.count(join)==1 and terminal_header.count(enter)==1
terminal_header=terminal_header.replace('#pragma once','#pragma once\nvoid ObserveDirectJoin();\nvoid ObserveDirectEnter();')
terminal_header=terminal_header.replace(join,join+'\n        ::ObserveDirectJoin();')
terminal_header=terminal_header.replace(enter,'        ::ObserveDirectEnter();\n'+enter)
(out/'shims/common').mkdir(parents=True,exist_ok=True)
(out/'shims/common/terminal_ingress.h').write_text(terminal_header)
callback_header = (root/'src/video_core/acknowledged_callback.h').read_text()
assert callback_header.count('completion.get();') == 1
(shim/'acknowledged_callback.h').write_text(callback_header.replace(
    'completion.get();', 'if(callback_wait) { callback_wait->Set(); }\n        completion.get();'))
head = r'''
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <functional>
#include <future>
#include <iostream>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <vector>
#include "video_core/gpu_thread.h"
#include "video_core/buffer_cache/gather_alias.h"
#include "video_core/buffer_cache/controlled_conflict.h"
#define LOG_ERROR(category, format, reason) ((void)(reason))
#define CITRON_PROFILE_SCOPE(...) ((void)0)
#define VK_ERROR_OUT_OF_DEVICE_MEMORY -2
#define VK_ERROR_OUT_OF_HOST_MEMORY -1
using namespace std::chrono_literals;
void Require(bool b,const char* why) { if(!b) throw std::runtime_error(why); }
struct Event {
    std::mutex mutex; std::condition_variable cv; bool set=false;
    void Set() { std::lock_guard lock{mutex}; set=true; cv.notify_all(); }
    void Wait() { std::unique_lock lock{mutex}; Require(cv.wait_for(lock,5s,[&]{return set;}),"rendezvous timeout"); }
};
template<class T> T Ready(std::future<T>& f) {
    Require(f.wait_for(5s)==std::future_status::ready,"operation timeout"); return f.get();
}
Event* queue_wait=nullptr;
Event* stop_requested=nullptr;
Event* callback_wait=nullptr;
Event* worker_joined=nullptr;
Event* command_queued=nullptr;
std::function<void()> direct_join_observer, direct_enter_observer;
void ObserveDirectJoin() {if(direct_join_observer)direct_join_observer();}
void ObserveDirectEnter() {if(direct_enter_observer)direct_enter_observer();}
#include "video_core/acknowledged_callback.h"
namespace Common {
enum class ThreadPriority { Critical };
void SetCurrentThreadName(const char*) {}
void SetCurrentThreadPriority(ThreadPriority) {}
}
namespace Settings { bool IsGPULevelExtreme() { return false; } }
namespace VideoCommon { struct InvalidImageSize : std::runtime_error { using runtime_error::runtime_error; }; }
namespace Vulkan::vk { struct Exception : std::runtime_error {
using runtime_error::runtime_error; int GetResult() const { return -2; }
}; }
namespace Core {
enum class SystemResultStatus { ErrorVideoCore };
struct System {
    struct Gpu {
        std::atomic<int> ticks=0; void NotifyShutdown() {} void TickWork() { ++ticks; }
        bool HasControlledProducerConflict() const { return false; }
        u64 RequestFlush(DAddr,u64) { return 0; } void WaitForSyncOperation(u64) {}
    } gpu;
    void RegisterHostThread() {} Gpu& GPU() { return gpu; }
    void Exit(SystemResultStatus) {}
};
namespace Frontend { struct GraphicsContext { int Acquire() { return 0; } }; }
}
namespace VideoCore {
struct RasterizerInterface {
    std::atomic<unsigned> invalidations{};
    std::function<void()> invalidate;
    void FlushRegion(DAddr,u64) {}
    void OnCacheInvalidation(DAddr,u64) {++invalidations;if(invalidate)invalidate();}
    bool OnCPUWrite(DAddr,u64) {++invalidations;return false;}
};
struct RendererBase { RasterizerInterface rasterizer; RasterizerInterface* ReadRasterizer() { return &rasterizer; } };
}
namespace Tegra::Control {
struct Scheduler {
    Event* retry_entered=nullptr; Event* retry_release=nullptr;
    std::atomic<bool> suspended=false, retry_finished=false;
    bool HasSuspendedChannels() { return suspended; }
    void RetrySuspended(bool) {
        if(retry_entered) { retry_entered->Set(); retry_release->Wait(); }
        retry_finished=true; suspended=false;
    }
    void Push(s32,Tegra::CommandList) {}
};
}
'''
head+='\nstruct UnmanagedGpuFacade { VideoCore::RasterizerInterface* rasterizer;\n'+direct_cpu+'\n};\n'
tail = r'''
using VideoCommon::GPUThread::ThreadManager;
void full_queue_stop() {
    Core::System system; VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context; Tegra::Control::Scheduler scheduler;
    ThreadManager manager{system,true}; manager.StartThread(renderer,context,scheduler);
    auto entered=std::make_shared<Event>(), release=std::make_shared<Event>();
    auto active=std::async(std::launch::async,[&] {
        manager.RunOnGpuThread([entered,release] { entered->Set(); release->Wait(); });
    });
    entered->Wait();
    for(int i=0;i<4096;++i) manager.TickGPU(); // exact production queue capacity
    Require(!manager.TryQueueCpuWrite([] {return true;}),"full queue admitted nonblocking CPU handoff");
    Event waiting,stopping; queue_wait=&waiting; stop_requested=&stopping;
    std::atomic<int> cancelled_executions=0;
    auto producer=std::async(std::launch::async,[&] {
        manager.RunOnGpuThread([&] { ++cancelled_executions; });
    });
    waiting.Wait(); // producer is inside the real full-queue wait, not a timing guess
    auto stop=std::async(std::launch::async,[&] { manager.Stop(); });
    stopping.Wait(); Ready(producer); Ready(active);
    Require(stop.wait_for(0ms)!=std::future_status::ready,"Stop failed to join active callback");
    release->Set(); Ready(stop); manager.Stop();
    manager.RunOnGpuThread([&] { ++cancelled_executions; });
    manager.TickGPU(); manager.Synchronize();
    Require(cancelled_executions==0 && system.gpu.ticks==0,"queued or post-stop work executed");
    queue_wait=nullptr; stop_requested=nullptr;
}
void suspended_stop() {
    Core::System system; VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context; Tegra::Control::Scheduler scheduler;
    Event entered,release,stopping; scheduler.retry_entered=&entered; scheduler.retry_release=&release;
    scheduler.suspended=true; stop_requested=&stopping;
    ThreadManager manager{system,true}; manager.StartThread(renderer,context,scheduler);
    entered.Wait(); auto stop=std::async(std::launch::async,[&] { manager.Stop(); });
    stopping.Wait(); Require(!scheduler.retry_finished,"retry unexpectedly escaped latch");
    release.Set(); Ready(stop); Require(scheduler.retry_finished,"scheduler outlived worker use");
    stop_requested=nullptr;
}
void execution_and_ownership(bool async) {
    Core::System system; VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context; Tegra::Control::Scheduler scheduler;
    ThreadManager manager{system,async};
    int calls=0; manager.RunOnGpuThread([&] { ++calls; }); // before Start: rejected
    manager.StartThread(renderer,context,scheduler);
    manager.RunOnGpuThread([&] {
        Require(manager.IsGpuThread(),"GPU thread identity lost");
        manager.RunOnGpuThread([&] { ++calls; }); manager.Synchronize();
    });
    Require(calls==1 && !manager.IsGpuThread(),"nested callback self-wait or incorrect identity");
    manager.Stop(); manager.RunOnGpuThread([&] { ++calls; }); Require(calls==1,"stop admitted callback");
}
void acknowledged_preservation() {
    using VideoCommon::CallbackOutcome;
    Core::System system; VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context; Tegra::Control::Scheduler scheduler;
    ThreadManager manager{system,true};
    auto dispatch=[&](auto callback) { manager.RunOnGpuThread(std::move(callback)); };
    Require(VideoCommon::RunAcknowledgedCallback(dispatch,[] {})==CallbackOutcome::Cancelled,"pre-start success");
    manager.StartThread(renderer,context,scheduler);
    Require(VideoCommon::RunAcknowledgedCallback(dispatch,[] {})==CallbackOutcome::Completed,"normal callback not acknowledged");
    Event entered,release,stopping,wait;
    stop_requested=&stopping;callback_wait=&wait;
    auto request=std::async(std::launch::async,[&] {
        return VideoCommon::RunAcknowledgedCallback(dispatch,[&] {entered.Set();release.Wait();});
    });
    entered.Wait();auto stop=std::async(std::launch::async,[&] {manager.Stop();});
    stopping.Wait();wait.Wait();
    Require(request.wait_for(0ms)!=std::future_status::ready,"active callback prematurely acknowledged");
    release.Set();Require(Ready(request)==CallbackOutcome::Completed,"active callback lost completion");
    Ready(stop);stop_requested=nullptr;callback_wait=nullptr;
    Require(VideoCommon::RunAcknowledgedCallback(dispatch,[] {})==CallbackOutcome::Cancelled,"post-stop success");
}
void failed_worker_acknowledgement() {
    using VideoCommon::CallbackOutcome;
    Core::System system;VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context;Tegra::Control::Scheduler scheduler;
    ThreadManager manager{system,true};manager.StartThread(renderer,context,scheduler);
    auto dispatch=[&](auto callback) {manager.RunOnGpuThread(std::move(callback));};
    auto failed=VideoCommon::RunAcknowledgedCallback(dispatch,[] {throw VideoCommon::UnsupportedGatherMapping("injected");});
    Require(failed==CallbackOutcome::Failed,"preservation exception reported success");
    int calls=0;
    Require(VideoCommon::RunAcknowledgedCallback(dispatch,[&] {++calls;})==CallbackOutcome::Cancelled,
            "failed-mode queue fence reported preservation success");
    Require(calls==0,"failed worker executed preservation");manager.Stop();
}
void nonblocking_cpu_continuation() {
    Core::System system;VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context;Tegra::Control::Scheduler scheduler;
    ThreadManager manager{system,true};manager.StartThread(renderer,context,scheduler);
    Event entered,release,polled;
    auto blocked=std::async(std::launch::async,[&] {
        manager.RunOnGpuThread([&] {entered.Set();release.Wait();});
    });entered.Wait();
    std::atomic<bool> produced=false;std::atomic<int> stores=0;
    auto enqueue=std::async(std::launch::async,[&] {
        return manager.TryQueueCpuWrite([&] {polled.Set();if(!produced) return false;++stores;return true;});
    });
    const bool nonblocking=enqueue.wait_for(100ms)==std::future_status::ready;
    release.Set();Ready(blocked);Require(Ready(enqueue),"handoff queue refused unexpectedly");
    Require(nonblocking,"CPU handoff waited for a GPU worker waiting on that CPU producer");
    polled.Wait();
    manager.RunOnGpuThread([&] {produced=true;}); // later normal queue work must break the dependency
    manager.Synchronize();Require(stores==1,"continuation failed or replayed store");
    for(int i=0;i<8;++i) {manager.TickGPU();}
    manager.Synchronize();
    Require(stores==1,"retired continuation was resumed again");manager.Stop();
    Require(!manager.TryQueueCpuWrite([] {return true;}),"post-stop CPU handoff accepted");
    ThreadManager synchronous{system,false};
    Require(!synchronous.TryQueueCpuWrite([] {return true;}),"unsupported synchronous handoff accepted");
}
void direct_invalidation_lifetime(bool flush) {
    Core::System system;VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context;Tegra::Control::Scheduler scheduler;
    ThreadManager manager{system,true};
    auto invoke=[&] {if(flush)manager.FlushAndInvalidateRegion(4096,4096);else manager.InvalidateRegion(4096,4096);};
    invoke();Require(renderer.rasterizer.invalidations==0,"pre-start direct invalidation accepted");
    Event entered,release,joined;worker_joined=&joined;
    renderer.rasterizer.invalidate=[&] {entered.Set();release.Wait();};
    manager.StartThread(renderer,context,scheduler);
    auto direct=std::async(std::launch::async,invoke);entered.Wait();
    auto stop=std::async(std::launch::async,[&] {manager.Stop();});joined.Wait();
    const bool early=stop.wait_for(100ms)==std::future_status::ready;
    release.Set();Ready(direct);Ready(stop);worker_joined=nullptr;
    Require(!early,"Stop failed to join direct invalidation");
    const auto before=renderer.rasterizer.invalidations.load();invoke();
    Require(renderer.rasterizer.invalidations==before,"post-stop direct invalidation accepted");
}
void direct_count_contention_and_exception() {
    Core::System system;VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context;Tegra::Control::Scheduler scheduler;
    ThreadManager manager{system,true};manager.StartThread(renderer,context,scheduler);
    std::vector<std::thread> callers;
    for(unsigned i=0;i<8;++i)callers.emplace_back([&] {
        for(unsigned n=0;n<1000;++n)manager.InvalidateRegion(4096,4096);
    });
    for(auto& caller:callers)caller.join();
    Require(renderer.rasterizer.invalidations==8000,"healthy direct entry count contention lost invalidation");
    renderer.rasterizer.invalidate=[] {throw std::runtime_error("direct callback exception");};
    bool threw=false;try {manager.FlushAndInvalidateRegion(4096,4096);}catch(const std::runtime_error&) {threw=true;}
    Require(threw,"direct exception disappeared");manager.Stop();
}
void entered_owner_invalidation_during_stop() {
    Core::System system;VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context;Tegra::Control::Scheduler scheduler;
    ThreadManager manager{system,true};manager.StartThread(renderer,context,scheduler);
    Event entered,release,stopping;stop_requested=&stopping;
    auto active=std::async(std::launch::async,[&] {manager.RunOnGpuThread([&] {
        entered.Set();release.Wait();manager.InvalidateRegion(4096,4096);
        manager.FlushAndInvalidateRegion(4096,4096);
    });});
    entered.Wait();auto stop=std::async(std::launch::async,[&] {manager.Stop();});
    stopping.Wait();release.Set();Ready(active);Ready(stop);stop_requested=nullptr;
    Require(renderer.rasterizer.invalidations==2,"Stop rejected invalidation from an already entered GPU owner");
}
void unmanaged_cpu_write_negative() {
    Core::System system;VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context;Tegra::Control::Scheduler scheduler;
    ThreadManager manager{system,true};manager.StartThread(renderer,context,scheduler);manager.Stop();
    UnmanagedGpuFacade facade{&renderer.rasterizer};facade.OnCPUWrite(4096,4096);
    Require(renderer.rasterizer.invalidations==1,"unmanaged GPU OnCPUWrite bypass counterexample disappeared");
}
void direct_join_after_capture_cancellation() {
    Core::System system;VideoCore::RendererBase renderer;
    Core::Frontend::GraphicsContext context;Tegra::Control::Scheduler scheduler;
    ThreadManager manager{system,true};manager.StartThread(renderer,context,scheduler);
    Event running,release,queued,stopping,retired;
    auto active=std::async(std::launch::async,[&] {manager.RunOnGpuThread([&] {running.Set();release.Wait();});});
    running.Wait();command_queued=&queued;stop_requested=&stopping;
    std::atomic<bool> capture_retired=false;
    renderer.rasterizer.invalidate=[&] {
        auto capture=std::shared_ptr<int>(new int{1},[&](int* p) {delete p;capture_retired=true;retired.Set();});
        manager.RunOnGpuThread([keep=std::move(capture)] {});
        retired.Wait(); // An unexecuted capture can release an entered producer.
    };
    auto direct=std::async(std::launch::async,[&] {manager.InvalidateRegion(4096,4096);});queued.Wait();
    direct_join_observer=[&] {
        assert(capture_retired && "queued captures must retire before the direct-call join");
    };
    auto stop=std::async(std::launch::async,[&] {manager.Stop();});stopping.Wait();release.Set();
    Ready(active);Ready(direct);Ready(stop);
    direct_join_observer={};command_queued=nullptr;stop_requested=nullptr;
    Require(capture_retired,"cancelled capture outlived direct join");
}
void delayed_direct_entry() {
    Common::TerminalIngress ingress;ingress.Open();Event loaded,release;
    direct_enter_observer=[&] {loaded.Set();release.Wait();};
    auto late=std::async(std::launch::async,[&] {return bool(ingress.TryEnter());});
    loaded.Wait();ingress.Close();ingress.Join();release.Set();
    const bool admitted=Ready(late);direct_enter_observer={};
    Require(!admitted,"late external invalidation entry bypassed Close");ingress.Join();
}
int main() {
    try {
        full_queue_stop(); suspended_stop(); execution_and_ownership(true); execution_and_ownership(false);
        acknowledged_preservation();failed_worker_acknowledgement();
        nonblocking_cpu_continuation();
        direct_invalidation_lifetime(false);direct_invalidation_lifetime(true);
        direct_count_contention_and_exception();direct_join_after_capture_cancellation();delayed_direct_entry();
        entered_owner_invalidation_during_stop();unmanaged_cpu_write_negative();
        std::cout<<"PASS actual ThreadManager: full-queue cancellation, active join, suspended retry, sync/async inline, pre/post-start rejection\n";
    } catch(const std::exception& e) { std::cerr<<"FAIL "<<e.what()<<"\n"; return 1; }
}
'''
cpp=out/'gpu_thread.cpp'; cpp.write_text(head+body+tail)
exe=out/('gpu_thread.exe' if os.name=='nt' else 'gpu_thread')
flags=[args.cxx,'-std=c++23','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-variable','-pthread',
       '-I',str(out/'shims'),'-I',str(root/'src')]
if args.sanitize:
    flags+=['-fsanitize='+('address,undefined' if args.sanitize=='address' else 'thread'),'-fno-omit-frame-pointer']
subprocess.run(flags+[str(cpp),'-o',str(exe)],check=True)
manifest={
    'source_sha256': hashlib.sha256(production.encode()).hexdigest(),
    'instrumentation': ['signal immediately before queue-space wait', 'signal after request_stop',
                        'signal before acknowledged callback future wait',
                        'signal after worker join and command enqueue',
                        'observer before terminal join and direct-entry RMW'],
    'sha256': {path: hashlib.sha256((root/path).read_bytes()).hexdigest() for path in [
        'src/video_core/gpu_thread.cpp','src/video_core/gpu_thread.h','src/video_core/gpu.cpp','src/common/terminal_ingress.h',
        'src/common/bounded_threadsafe_queue.h','tools/gpu_lifecycle_tests/run_thread_tests.py']},
    'production': ['ThreadManager class', 'RunThread and all ThreadManager definitions', 'MPSCQueue/SPSCQueue', 'stop-token wait'],
    'fixtures': ['renderer/engine/scheduler/platform/Core/System'],
    'boundary': 'Terminal worker and two direct invalidation entries only; no live GPU freeze or Vulkan completion',
    'positive_repeats': args.repeat,
}
for i in range(args.repeat):
    result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
    (out/f'thread-{i}.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        print(result.stdout+result.stderr,end=''); raise SystemExit(result.returncode)
    assert 'PASS actual ThreadManager:' in result.stdout
print(f'PASS actual ThreadManager ({args.repeat} repetitions)')
guard=('    const bool owner = IsGpuThread();\n'
       '    auto entry = owner ? std::optional<Common::TerminalIngress::Entry>{}\n'
       '                       : direct_invalidations.TryEnter();\n'
       '    if (!owner && !entry) return;\n')
assert body.count(guard)==2
join_block=('    // An entered invalidation can be waiting for a queued preservation callback.\n'
            '    // Cancel unexecuted captures first, outside write_lock, so it can leave.\n'
            '    direct_invalidations.Join();\n')
assert body.count(join_block)==1
early_join=body.replace(join_block,'').replace('    CommandDataContainer cancelled;',
    '    direct_invalidations.Join();\n    CommandDataContainer cancelled;')
legacy=body.replace('    direct_invalidations.Close();\n','').replace(
    '        direct_invalidations.Join();\n','').replace('    direct_invalidations.Join();\n','')
closed='        if (old & Closed) { Leave(); return {}; }'
assert terminal_header.count(closed)==1
direct_controls=[
    ('direct-entry-released-early',body.replace(guard,'    {\n'+guard+'    }\n'),None,
     'Stop failed to join direct invalidation'),
    ('direct-stop-skips-ingress',legacy,None,'Stop failed to join direct invalidation'),
    ('direct-join-before-capture-cancel',early_join,None,'queued captures must retire before the direct-call join'),
    ('direct-late-entry-bypasses-close',body,terminal_header.replace(closed,''),
     'late external invalidation entry bypassed Close'),
    ('direct-rejects-entered-owner',body.replace('const bool owner = IsGpuThread();','const bool owner = false;'),None,
     'Stop rejected invalidation from an already entered GPU owner'),
]
for name,changed,override,expected in direct_controls:
    assert changed!=body or override is not None
    control=out/(name+'.cpp');control.write_text(head+changed+tail)
    mutant=out/(name+('.exe' if os.name=='nt' else ''))
    injected=out/'shims/common/terminal_ingress.h'
    try:
        if override is not None: injected.write_text(override)
        subprocess.run(flags+[str(control),'-o',str(mutant)],check=True)
        result=subprocess.run([str(mutant)],capture_output=True,text=True,timeout=30)
        log=result.stdout+result.stderr;(out/(name+'.log')).write_text(log)
        assert result.returncode!=0 and expected in log and ('FAIL ' in log or 'assert' in log.lower()),(name,log)
    finally: injected.write_text(terminal_header)
    print('PASS terminal direct invalidation control: '+name,flush=True)
manifest['direct_control_mutants']=[entry[0] for entry in direct_controls]
if args.handoff_controls:
    admission = '++state.last_fence;\n    return true;'
    assert body.count(admission) == 1
    control = out / 'blocking_handoff.cpp'
    control.write_text(head + body.replace(admission,
        '++state.last_fence;\n    lock.unlock();\n    Synchronize();\n    return true;') + tail)
    mutant = out / ('blocking_handoff.exe' if os.name == 'nt' else 'blocking_handoff')
    subprocess.run(flags + [str(control), '-o', str(mutant)], check=True)
    result = subprocess.run([str(mutant)], capture_output=True, text=True, timeout=30)
    if result.returncode != 1 or 'handoff waited for a GPU worker waiting on that CPU producer' not in result.stderr:
        raise RuntimeError(f'Blocking handoff control failed incorrectly: {result.returncode} {result.stderr}')
    print('PASS negative topology control: synchronous queue acknowledgement recreates the CPU/GPU dependency cycle')
(out/'thread-extraction.json').write_text(json.dumps(manifest,indent=2))
