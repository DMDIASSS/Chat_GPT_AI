"""Exercise startup pacing and delayed/failed downloads with a real scheduler model."""
import unittest
import test_performance as performance


class LoadingTests(unittest.TestCase):
    run_lua=performance.PerformanceTests.run_lua

    def test_loading_work_does_not_wait_after_every_worker_slice(self):
        self.run_lua({'Startup':'local_startup.lua'},'''
local time,waits=0,0
local loader=Startup.new({clock=function()return time end,
 spawn=function()error('Unexpected HTTP request')end,
 wait=function()waits+=1;time+=.1 end})
for i=1,1000 do time+=.0005;loader:checkpoint()end
assert(waits>=58 and waits<=63,'Startup waited once per small work unit')
assert(time<7,'Half a second of CPU work took too many frames at 10 FPS')
''')

    def test_delayed_download_reports_progress_and_returns_exact_bytes(self):
        self.run_lua({'Startup':'local_startup.lua'},'''
local time,worker,renders=0,nil,{}
local loader=Startup.new({clock=function()return time end,
 spawn=function(fn)worker=coroutine.create(fn);assert(coroutine.resume(worker))end,
 fetch=function(url)assert(url=='pinned');coroutine.yield();return 'FP32'end,
 wait=function(dt)time+=dt;assert(coroutine.resume(worker))end,
 render=function(stage,done,total,elapsed)renders[#renders+1]={stage,done,total,elapsed}end})
assert(loader:download('pinned',4)=='FP32')
assert(#renders>0 and string.find(renders[1][1],'Downloading',1,true))
assert(renders[1][2]==nil and renders[1][3]==nil,'Invented a download percentage')
''')

    def test_timeout_cancel_and_late_reply_cannot_finish_loading(self):
        self.run_lua({'Startup':'local_startup.lua'},'''
for _,mode in ipairs({'timeout','cancel'})do
 local time,worker,active=0,nil,true
 local loader=Startup.new({clock=function()return time end,downloadTimeout=.3,
  alive=function()return active end,
  spawn=function(fn)worker=coroutine.create(fn);assert(coroutine.resume(worker))end,
  fetch=function()coroutine.yield();return 'FP32'end,
  wait=function(dt)time+=dt;if mode=='cancel'then active=false end end})
 local ok,err=pcall(function()loader:download('pinned',4)end)
 assert(not ok and string.find(err,mode=='cancel'and 'cancelled'or 'timed out',1,true),tostring(err))
 assert(coroutine.resume(worker),'Late reply raised an error')
 assert(coroutine.status(worker)=='dead','Cancelled HTTP work remained active')
end
''')

    def test_http_errors_and_truncated_model_fail_clearly(self):
        self.run_lua({'Startup':'local_startup.lua'},'''
for _,mode in ipairs({'http','short'})do
 local loader=Startup.new({spawn=function(fn)fn()end,wait=function()error('Unexpected wait')end,
  fetch=function()if mode=='http'then error('HTTP 404')end;return 'bad'end})
 local ok,err=pcall(function()loader:download('pinned',4)end)
 assert(not ok and string.find(err,mode=='http'and 'HTTP 404'or 'Incomplete model',1,true),tostring(err))
end
''')

    def test_preparation_timeout_and_close_stop_cpu_work(self):
        self.run_lua({'Startup':'local_startup.lua'},'''
local time,alive=0,true
local loader=Startup.new({clock=function()return time end,alive=function()return alive end,
 spawn=function()error('Unexpected HTTP request')end,
 wait=function()alive=false end})
time=.01
local ok,err=pcall(function()loader:checkpoint()end)
assert(not ok and string.find(err,'cancelled',1,true))
alive=true;time=121
ok,err=pcall(function()loader:checkpoint()end)
assert(not ok and string.find(err,'timed out',1,true))
''')
