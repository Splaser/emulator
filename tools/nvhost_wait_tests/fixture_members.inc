// SPDX-License-Identifier: GPL-3.0-or-later
std::array<InternalEvent, MaxNvEvents> events;
FakeSystem system;
FakeNvSyncpoints syncpoint_manager{system.host.manager};
std::mutex mutex;
std::unique_lock<std::mutex> NvEventsLock() { return std::unique_lock{mutex}; }
u32 FindFreeNvEvent(u32) { return 0; }
NvResult IocCtrlEventWait(IocCtrlEventWaitParams&, bool);
NvResult IocCtrlClearEventWait(IocCtrlEventClearParams&);
