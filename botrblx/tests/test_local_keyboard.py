"""Keyboard backends must change observable key state, including key releases."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
LUAU=os.environ.get("LUAU_BIN") or shutil.which("luau")


@unittest.skipUnless(LUAU,"Set LUAU_BIN to exercise keyboard backend selection")
class KeyboardTests(unittest.TestCase):
    def run_case(self,setup,checks):
        module=(HERE.parent/"templates/local_keyboard.lua").read_text(encoding="utf-8")
        prefix='''
local now=0
local os={clock=function()return now end}
local task={wait=function(dt)now=now+dt end}
local down={}
local input={IsKeyDown=function(self,key)return down[key]==true end}
local Enum={KeyCode={W='W',A='A',S='S',D='D',Q='Q',E='E',LeftShift='SHIFT'}}
local vk={[0x57]='W',[0x41]='A',[0x53]='S',[0x44]='D',[0x51]='Q',[0x45]='E',[0x10]='SHIFT'}
local scan={[0x11]='W',[0x1E]='A',[0x1F]='S',[0x20]='D',[0x10]='Q',[0x12]='E',[0x2A]='SHIFT'}
local game={GetService=function()error('VirtualInputManager unavailable')end}
local keypress,keyrelease
local cancelled=false
local function cancel()return cancelled end
local reports={}
local function report(s)reports[#reports+1]=s end
'''
        source=prefix+setup+"\nlocal Keyboard=(function()\n"+module+"\nend)()\nlocal keyboard=Keyboard.new(input)\n"+checks
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"keyboard.luau";path.write_text(source,encoding="utf-8")
            result=subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_selects_enum_key_events_when_executor_keyboard_is_silent(self):
        self.run_case('''
keypress=function()end;keyrelease=function()end
game.GetService=function()return {SendKeyEvent=function(self,pressed,key)down[key]=pressed or nil end}end
''','''
assert(keyboard:probe(cancel,report))
assert(keyboard.name=='Roblox key events')
keyboard:event('W',true);keyboard:event('SHIFT',true)
assert(down.W and down.SHIFT)
assert(keyboard:observed()=='W SHIFT')
keyboard:release();assert(next(down)==nil)
''')

    def test_selects_scan_codes_after_vk_calls_silently_fail(self):
        self.run_case('''
keypress=function(code)if scan[code]then down[scan[code]]=true end end
keyrelease=function(code)if scan[code]then down[scan[code]]=nil end end
''','''
assert(keyboard:probe(cancel,report))
assert(keyboard.name=='executor scan')
assert(now>=.18,'Did not reject the silent VK backend')
keyboard:event('W',true);keyboard:event('SHIFT',true)
assert(down.W and down.SHIFT)
keyboard:release();assert(next(down)==nil)
''')

    def test_selects_vk_after_roblox_key_events_are_disallowed(self):
        self.run_case('''
game.GetService=function()return {SendKeyEvent=function()error('API disallowed')end}end
keypress=function(code)down[assert(vk[code])]=true end
keyrelease=function(code)down[assert(vk[code])]=nil end
''','''
assert(keyboard:probe(cancel,report))
assert(keyboard.name=='executor VK')
assert(next(down)==nil)
''')

    def test_noop_keyboard_api_does_not_count_as_working(self):
        self.run_case("keypress=function()end;keyrelease=function()end",'''
local ok,reason=keyboard:probe(cancel,report)
assert(not ok and not keyboard.selected)
assert(string.find(reason,'No keyboard method reached Roblox',1,true))
assert(string.find(reason,'keydown was not observed',1,true))
''')

    def test_rejects_backend_that_cannot_release(self):
        self.run_case('''
keypress=function(code)down[assert(vk[code])]=true end
keyrelease=function()end
''','''
local ok,reason=keyboard:probe(cancel,report)
assert(not ok and not keyboard.selected)
assert(string.find(reason,'Key remained down',1,true))
''')

    def test_f8_during_probe_releases_and_cancels(self):
        self.run_case('''
keypress=function(code)down[assert(vk[code])]=true;cancelled=true end
keyrelease=function(code)down[assert(vk[code])]=nil end
''','''
assert(not keyboard:probe(cancel,report))
assert(next(down)==nil)
assert(not keyboard.selected)
''')

    def test_shift_alone_must_work_before_accepting_backend(self):
        self.run_case('''
keypress=function(code)if code~=0x10 then down[assert(vk[code])]=true end end
keyrelease=function(code)if vk[code]then down[vk[code]]=nil end end
''','''
local ok,reason=keyboard:probe(cancel,report)
assert(not ok and not keyboard.selected)
assert(string.find(reason,'SHIFT: keydown was not observed',1,true))
assert(next(down)==nil)
''')

    def test_live_silent_failure_requires_retest_and_releases_other_keys(self):
        self.run_case('''
keypress=function(code)down[assert(vk[code])]=true end
keyrelease=function(code)down[assert(vk[code])]=nil end
''','''
assert(keyboard:probe(cancel,report))
keyboard:event('W',true);keyboard:event('A',true)
down.W=nil;now=now+.25
local ok,reason=keyboard:verify()
assert(not ok and not keyboard.selected)
keyboard:event('A',false) -- release still works after backend invalidation
keyboard:release();assert(next(down)==nil)
''')
