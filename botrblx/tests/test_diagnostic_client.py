"""Exercise the one-shot executor diagnostic without Roblox or executor APIs."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "JJSploit_Diagnose.lua"
LUAU = os.environ.get("LUAU_BIN") or shutil.which("luau")
MARKER = "__BOTRBLX_DIAGNOSTIC_CONFIG_JSON__"

SETUP = r'''
local config={schema=1,nonce='nonce-current-test',
 control_path='diagnostic_control.json',report_path='diagnostic_report.json',
 cases={
  {id='flat',path='diagnostic_flat.txt',expected='current-marker',kind='file'},
  {id='directory',path='diagnostic_directory',expected='',kind='directory'},
  {id='missing',path='diagnostic_missing.txt',expected='missing-marker',kind='missing'}
 },
 own_tests={{id='rewrite',path='diagnostic_own.txt',first='first-current-marker',second='second-current-marker'}},
 generations={{id=1,expected='generation-current-marker',paths={
  {id='flat',path='diagnostic_generation.txt'},
  {id='nested',path='diagnostic_directory/generation.txt'}
 }}}
}
encoded.TEST_CONFIG=config
local files={['diagnostic_flat.txt']='current-marker'}
local folders={diagnostic_directory=true}
local file_calls=0
local exported=nil
local last_report=nil
local report_encoded=nil
local generation_writes=0
local report_fail=false
local read_override=nil
local publish_override=nil
local original_encode=services.HttpService.JSONEncode
services.HttpService.JSONEncode=function(self,data)
 local body=original_encode(self,data)
 if type(data)=='table' and data.schema==1 and data.nonce==config.nonce and data.capabilities then
  last_report=data;report_encoded=body
 end
 return body
end
local function ui_before_files()
 file_calls=file_calls+1
 assert(playerGui.children.BotrblxDiagnostics,'Diagnostic file call preceded its UI')
end
local function default_publish(control)
 if control.kind=='generation' then
  generation_writes=generation_writes+1
  for _,generation in ipairs(config.generations)do
   if generation.id==control.generation then
    for _,entry in ipairs(generation.paths)do files[entry.path]=generation.expected end
   end
  end
 end
end
local readfile=function(path)
 ui_before_files()
 if read_override then
  local handled,value=read_override(path)
  if handled then return value end
 end
 if folders[path]then error('Expected File But Got Directory')end
 if files[path]==nil then error('file not found: '..path)end
 return files[path]
end
local writefile=function(path,body)
 ui_before_files()
 if path==config.report_path then
  if report_fail then error('report write rejected')end
  exported=assert(encoded[body],'Report was not JSON encoded')
 end
 files[path]=body
 if path==config.control_path then
  local control=assert(encoded[body],'Control was not JSON encoded')
  assert(control.nonce==config.nonce,'Control lost session nonce')
  if publish_override then publish_override(control)else default_publish(control)end
 end
end
local isfile=function(path)ui_before_files();return files[path]~=nil end
local isfolder=function(path)ui_before_files();return folders[path]==true end
local makefolder=function()error('Diagnostic must not create arbitrary folders')end
local request=function()error('Diagnostic must not send HTTP')end
local http_request=request
local keypress=function()error('Diagnostic must not press keys')end
local keyrelease=keypress
local mouse1press=keypress
local mouse1release=keypress
local setthreadidentity=function()error('Diagnostic must not change identity')end
game.HttpGet=request
task.wait=function(dt)now=now+(dt or .01)end
local function record_named(items,id)
 for _,record in ipairs(items or {})do if record.id==id then return record end end
 error('Missing diagnostic record '..tostring(id))
end
local function copyable_output_exists()
 for _,item in ipairs(created)do
  if item.ClassName=='TextBox'and item.Name=='DiagnosticReport'
   and type(item.Text)=='string' and report_encoded
   and string.find(item.Text,report_encoded,1,true)then return true end
 end
 return false
end
'''


class DiagnosticSourceTests(unittest.TestCase):
    def test_diagnostic_has_no_network_input_or_game_module_calls(self):
        source = SOURCE.read_text(encoding="utf-8")
        for name in (
            "request", "http_request", "require", "keypress", "keyrelease",
            "mouse1press", "mouse1release", "setthreadidentity", "setidentity",
        ):
            self.assertNotRegex(source, rf"\b{re.escape(name)}\s*\(", name)
        self.assertNotRegex(source, r":\s*(HttpGet|HttpPost|SendKeyEvent)\s*\(")
        self.assertEqual(source.count(MARKER), 1)


@unittest.skipUnless(LUAU, "Set LUAU_BIN to exercise diagnostic Lua")
class DiagnosticClientTests(unittest.TestCase):
    def run_case(self, overrides, checks):
        fixture = (HERE / "fixtures/roblox_mock.luau").read_text(encoding="utf-8")
        source = SOURCE.read_text(encoding="utf-8").replace(MARKER, "TEST_CONFIG")
        program = fixture + SETUP + overrides + "\nlocal function diagnose()\n" + source
        program += "\nend\ndiagnose()\n" + checks
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagnostic.luau"
            path.write_text(program, encoding="utf-8")
            result = subprocess.run(
                [LUAU, str(path)], capture_output=True, text=True, timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exports_one_shot_report_and_keeps_copyable_ui(self):
        self.run_case("", r'''
assert(file_calls>0,'No file capabilities were exercised')
assert(exported and exported==last_report,'Complete report was not exported')
assert(exported.schema==1 and exported.nonce==config.nonce)
assert(type(exported.capabilities)=='table')
assert(record_named(exported.static,'flat').read.match==true)
local own=record_named(exported.own,'rewrite')
assert(own.write_first.ok and own.read_first.match,'First own write/read failed')
assert(own.write_second.ok and own.read_second.match,'Second own write/read failed')
assert(generation_writes>0,'Generation freshness was not requested')
local generation=record_named(exported.generations,1)
assert(generation.expected=='generation-current-marker')
assert(record_named(generation.results,'flat').match==true)
assert(record_named(generation.results,'nested').match==true)
local function no_raw_probe_body(value)
 if type(value)=='table'then
  for _,item in pairs(value)do no_raw_probe_body(item)end
 else assert(value~='current-marker','Raw probe file contents copied into report')end
end
no_raw_probe_body(exported)
assert(copyable_output_exists(),'No persistent copyable report')
assert(not playerGui.children.BotrblxDiagnostics.destroyed)
assert(now<30,'Diagnostic did not finish within its bounded window')
''')

    def test_directory_read_error_is_recorded_and_remaining_tests_continue(self):
        self.run_case("", r'''
local item=record_named(exported.static,'directory')
assert(item.kind=='directory')
assert(item.read.ok==false)
assert(string.find(item.read.error,'Expected File But Got Directory',1,true),item.read.error)
assert(item.isfile.ok and item.isfile.value==false)
assert(item.isfolder.ok and item.isfolder.value==true)
assert(record_named(exported.static,'missing').read.ok==false)
assert(record_named(exported.own,'rewrite').read_second.match)
assert(record_named(record_named(exported.generations,1).results,'flat').match)
''')

    def test_stale_or_other_session_generation_markers_never_match(self):
        self.run_case(r'''
publish_override=function(control)
 if control.kind=='generation'then
  generation_writes=generation_writes+1
  files.diagnostic_generation='unused'
  files['diagnostic_generation.txt']='generation-previous-nonce'
  files['diagnostic_directory/generation.txt']='generation-current-marker-extra'
 end
end
''', r'''
assert(exported and generation_writes>0)
for _,entry in ipairs(record_named(exported.generations,1).results)do
 assert(entry.match==false,'Stale or prefix marker incorrectly accepted')
 assert(entry.attempts>=1)
end
assert(now<30,'A stale reply caused an unbounded wait')
assert(copyable_output_exists())
''')

    def test_metadata_probes_cannot_suppress_actual_reads(self):
        self.run_case(r'''
isfile=function()ui_before_files();return false end
isfolder=function()ui_before_files();return true end
''', r'''
assert(exported)
local item=record_named(exported.static,'flat')
assert(item.isfile.ok and item.isfile.value==false)
assert(item.isfolder.ok and item.isfolder.value==true)
assert(item.read.match,'An unreliable metadata probe suppressed a valid direct read')
assert(record_named(exported.own,'rewrite').read_second.match)
assert(record_named(record_named(exported.generations,1).results,'flat').match)
''')

    def test_delayed_generation_replaces_stale_values_before_success(self):
        self.run_case(r'''
local pending_control=nil
local published_at=nil
publish_override=function(control)
 if control.kind=='generation'then
  pending_control=control;published_at=now+.2
  files['diagnostic_generation.txt']='old-marker'
  files['diagnostic_directory/generation.txt']='old-marker'
 end
end
task.wait=function(dt)
 now=now+(dt or .01)
 if pending_control and now>=published_at then
  default_publish(pending_control);pending_control=nil
 end
end
''', r'''
assert(exported and generation_writes==1)
local generation=record_named(exported.generations,1)
for _,item in ipairs(generation.results)do
 assert(item.match==true,'Delayed fresh generation was never accepted')
 assert(item.attempts>1,'Old value was accepted before new generation arrived')
end
assert(now<5,'Successful freshness test consumed its entire timeout')
''')

    def test_unsupported_file_apis_still_show_report(self):
        self.run_case("\nreadfile=nil;writefile=nil;isfile=nil;isfolder=nil\n", r'''
assert(exported==nil,'Missing write API unexpectedly wrote report')
assert(last_report and last_report.schema==1 and last_report.nonce==config.nonce)
assert(type(last_report.capabilities)=='table')
assert(copyable_output_exists(),'Unsupported executor silently lost its report')
assert(not playerGui.children.BotrblxDiagnostics.destroyed)
assert(now<30)
''')

    def test_final_export_error_preserves_copyable_report(self):
        self.run_case("\nreport_fail=true\n", r'''
assert(exported==nil)
assert(last_report and record_named(last_report.static,'flat').read.match)
assert(copyable_output_exists(),'Export failure hid the only report')
assert(not playerGui.children.BotrblxDiagnostics.destroyed)
''')

    def test_token_like_error_details_are_redacted(self):
        self.run_case(r'''
read_override=function(path)
 if path=='diagnostic_flat.txt'then
  error('Synthetic failure token=DO_NOT_EXPOSE_TOKEN Authorization: Bearer DO_NOT_EXPOSE_BEARER')
 end
 return false
end
''', r'''
assert(exported,'Report was not exported after read error')
local function inspect(value)
 if type(value)=='table'then
  for key,item in pairs(value)do inspect(key);inspect(item)end
 elseif type(value)=='string'then
  assert(not string.find(value,'DO_NOT_EXPOSE_TOKEN',1,true),'Token leaked into report')
  assert(not string.find(value,'DO_NOT_EXPOSE_BEARER',1,true),'Bearer secret leaked into report')
 end
end
inspect(exported)
assert(record_named(exported.static,'flat').read.ok==false)
assert(record_named(exported.own,'rewrite').read_second.match)
''')


if __name__ == "__main__":
    unittest.main(verbosity=2)
