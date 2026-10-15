"""Launcher UI must appear before HTTP and retain readable startup errors."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
LUAU = os.environ.get("LUAU_BIN") or shutil.which("luau")
BASE = r'''
local loaded=false
local loadstring=function(body)
 assert(body=='CLIENT_SOURCE',body)
 return function()loaded=true;return {started=true}end
end
local function panel_exists()
 assert(playerGui.children.Update271Loader,'HTTP started before the launcher UI existed')
end
local function report_text()
 for _,item in ipairs(created)do
  if item.Name=='StartupReport'then return item.Text end
 end
 error('No visible startup report')
end
'''


@unittest.skipUnless(LUAU, "Set LUAU_BIN to exercise launcher UI")
class LauncherTests(unittest.TestCase):
    def run_lua(self, setup, checks):
        prefix = (HERE / "fixtures/roblox_mock.luau").read_text(encoding="utf-8")
        source = (HERE.parent / "JJSploit_Launch.lua").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "launcher.luau"
            path.write_text(prefix + BASE + setup + "\nlocal function launch()\n" + source + "\nend\nlaunch()\n" + checks, encoding="utf-8")
            result = subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_ui_precedes_fetch_and_closes_on_confirmed_start(self):
        self.run_lua(r'''
request=function(options)
 panel_exists()
 assert(string.find(report_text(),'GET http://127.0.0.1:28771/client',1,true))
 return {StatusCode=200,Body='CLIENT_SOURCE'}
end
''',r'''
assert(loaded)
assert(playerGui.children.Update271Loader.destroyed)
''')

    def test_supported_response_formats(self):
        for result in (
            "{StatusCode='200',Body='CLIENT_SOURCE'}",
            "{status_code='200',body='CLIENT_SOURCE'}",
            "'CLIENT_SOURCE'",
        ):
            with self.subTest(result=result):
                self.run_lua("\nrequest=function()panel_exists();return " + result + " end\n", "\nassert(loaded)\n")

    def test_valid_http_request_fallback_when_request_is_not_function(self):
        self.run_lua("\nrequest={}\nhttp_request=function()panel_exists();return {StatusCode=200,Body='CLIENT_SOURCE'}end\n", "\nassert(loaded)\n")

    def test_http_failures_are_visible(self):
        for response, message in (
            ("error('loopback request denied')", "loopback request denied"),
            ("return {StatusCode=404,Body='not found'}", "HTTP 404"),
            ("return {StatusCode=200}", "HTTP response has no Lua body"),
            ("return {StatusCode='unknown',Body='CLIENT_SOURCE'}", "Unrecognized HTTP status"),
        ):
            with self.subTest(message=message):
                self.run_lua("\nrequest=function()panel_exists();" + response + " end\n", "\nassert(not loaded)\nassert(string.find(report_text()," + repr(message) + ",1,true),report_text())\nassert(not playerGui.children.Update271Loader.destroyed)\n")

    def test_missing_http_and_compiler_errors_are_visible(self):
        self.run_lua("\nrequest=nil;http_request=nil\n", "\nassert(not loaded)\nassert(string.find(report_text(),'HTTP request function unavailable',1,true))\n")
        self.run_lua("\nrequest=function()return {StatusCode=200,Body='CLIENT_SOURCE'}end\nloadstring=function()return nil,'synthetic syntax error'end\n", "\nassert(not loaded)\nassert(string.find(report_text(),'compiling downloaded Lua',1,true))\nassert(string.find(report_text(),'synthetic syntax error',1,true))\n")

    def test_runtime_error_is_visible(self):
        self.run_lua("\nrequest=function()return {StatusCode=200,Body='CLIENT_SOURCE'}end\nloadstring=function()return function()error('synthetic client error')end end\n", "\nassert(string.find(report_text(),'starting client',1,true))\nassert(string.find(report_text(),'synthetic client error',1,true))\n")

    def test_close_during_request_prevents_execution(self):
        self.run_lua(r'''
request=function()
 panel_exists()
 click('Close launcher')
 return {StatusCode=200,Body='CLIENT_SOURCE'}
end
''', "\nassert(not loaded)\nassert(playerGui.children.Update271Loader.destroyed)\n")

    def test_older_client_without_confirmation_keeps_explanation_visible(self):
        self.run_lua("\nrequest=function()return {StatusCode=200,Body='CLIENT_SOURCE'}end\nloadstring=function()return function()loaded=true end end\n", "\nassert(loaded)\nassert(not playerGui.children.Update271Loader.destroyed)\nassert(string.find(report_text(),'without startup confirmation',1,true))\n")

    def test_downloaded_real_client_executes_and_streams(self):
        prefix = (HERE / "fixtures/roblox_mock.luau").read_text(encoding="utf-8")
        launcher = (HERE.parent / "JJSploit_Launch.lua").read_text(encoding="utf-8")
        client = (HERE.parent / "client271.lua").read_text(encoding="utf-8")
        setup = r'''
local client_source=[====[__CLIENT__]====]
local transport=request
request=function(options)
 if string.find(options.Url,'/client',1,true)then
  assert(playerGui.children.Update271Loader,'Launcher UI missing before HTTP')
  return {StatusCode='200',Body=client_source}
 end
 return transport(options)
end
task.wait=function(dt)
 move(dt)
 if now>.2 and not startedBot then startedBot=true;click('Start bot / F6')end
 if now>=12 then click('Close')end
end
-- Test-only globals for the newly compiled chunk; the runtime loader does not
-- change execution identity, game modules, or script environments.
local compile=loadstring
local loadstring=function(source)
 local fn,err=compile(source)
 if fn then
  setfenv(fn,setmetatable({game=game,Instance=Instance,UDim2=UDim2,
   Color3=Color3,Enum=Enum,request=request,task=task,os=os,warn=warn},
   {__index=getfenv()}))
 end
 return fn,err
end
'''.replace("__CLIENT__",client)
        checks = r'''
assert(#packets>150,'Downloaded client did not stream')
local running=0
for _,packet in ipairs(packets)do
 if packet.enabled and packet.valid then running=running+1 end
end
assert(running>100,'Downloaded client never enabled')
assert(playerGui.children.Update271Loader.destroyed,'Launcher did not see client confirmation')
assert(packets[#packets].enabled==false,'Close did not send stop')
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "real_download.luau"
            path.write_text(prefix+setup+"\nlocal function launch()\n"+launcher+"\nend\nlaunch()\n"+checks,encoding="utf-8")
            result = subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__ == "__main__": unittest.main(verbosity=2)
