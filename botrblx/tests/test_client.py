"""Execute the real Lua client under deterministic Roblox API mocks."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from client_cases import CASES

HERE = Path(__file__).resolve().parent
LUAU = os.environ.get("LUAU_BIN") or shutil.which("luau")


@unittest.skipUnless(LUAU, "Set LUAU_BIN to exercise the mocked Roblox client")
class ClientTests(unittest.TestCase):
    def run_case(self, name, extra="", extra_checks="", filename="client271.lua", checks_override=None):
        _, behaviour, checks = next(case for case in CASES if case[0] == name)
        if checks_override is not None: checks = checks_override
        prefix = (HERE / "fixtures/roblox_mock.luau").read_text(encoding="utf-8")
        source = (HERE.parent / filename).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / (name + ".luau")
            wrapped = "\nlocal function start_client()\n" + source + "\nend\nlocal client_state=start_client()\n"
            path.write_text(prefix + extra + behaviour + wrapped + checks + extra_checks, encoding="utf-8")
            result = subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_live_frames_buttons_and_close(self): self.run_case("live_frames_and_close")
    def test_goal_respawn_resumes(self): self.run_case("goal_respawn_resumes")
    def test_teleport_invalidates_frame(self): self.run_case("teleport_invalidates_frame")
    def test_missing_boost_never_fabricates_state(self): self.run_case("missing_boost_no_fake_state")

    def test_alternate_http_response_formats(self):
        formats = {
            "string_status": "return {StatusCode='200',Body=response.Body}",
            "lowercase_fields": "return {status_code='200',body=response.Body}",
            "empty_uppercase": "return {StatusCode=200,Body='',body=response.Body}",
            "second_return": "return true,response",
            "raw_body": "return response.Body",
        }
        for name, result in formats.items():
            with self.subTest(format=name):
                extra = "\nlocal original_request=request\nrequest=function(options)\nlocal response=original_request(options)\n" + result + "\nend\n"
                self.run_case("live_frames_and_close", extra)

    def test_live_client_falls_back_and_caches_working_http_api(self):
        extra = r'''
local original_request=request
local failed_calls=0
request=function()failed_calls=failed_calls+1;return nil end
http_request=original_request
'''
        self.run_case("live_frames_and_close",extra, "\nassert(failed_calls==1,'Repeated the failed API on every frame')\n")

    def test_file_client_streams_without_http_and_rejects_unrelated_replies(self):
        extra = r'''
local mock_server=request
request=function()error('File client attempted HTTP')end
http_request=request
services.HttpService.GenerateGUID=function()return 'fresh-file-session'end
local files={}
local read_attempt=0
local writefile=function(path,body)
 assert(path=='botrblx_exchange/request.json')
 local r=services.HttpService:JSONDecode(body)
 assert(r.session=='fresh-file-session')
 local reply=mock_server({Url=r.route,Method=r.packet and 'POST'or 'GET',
  Headers={['X-Bridge-Token']=r.token},Body=r.packet and services.HttpService:JSONEncode(r.packet)})
 files['botrblx_exchange/response.json']=services.HttpService:JSONEncode({
  session=r.session,id=tostring(r.id),server='file-server',status='200',data=services.HttpService:JSONDecode(reply.Body)})
 read_attempt=0
end
local readfile=function(path)
 read_attempt=read_attempt+1
 if read_attempt==1 then return services.HttpService:JSONEncode({session='old-session',id=1,status=200,data={}})end
 if read_attempt==2 then return 'partial JSON'end
 return string.char(239,187,191)..assert(files[path],'missing file')
end
'''
        for name,_,_ in CASES:
            with self.subTest(case=name):
                self.run_case(name,extra,filename="JJSploit_File_Client.lua")

    def test_file_client_missing_functions_stays_visible(self):
        extra = "\nservices.HttpService.GenerateGUID=function()return 'test-session'end\nlocal readfile=nil\nlocal writefile=nil\n"
        checks = r'''
assert(#packets==0,'Attempted HTTP fallback')
local visible=false
for _,item in ipairs(created)do
 if item.ClassName=='TextLabel'and string.find(item.Text or '',
  'File mode needs both readfile and writefile',1,true)then visible=true end
end
assert(visible,'Missing APIs did not produce a visible explanation')
'''
        self.run_case("live_frames_and_close",extra=extra,filename="JJSploit_File_Client.lua",checks_override=checks)

    def test_file_client_wrong_workspace_times_out_visibly(self):
        extra = r'''
services.HttpService.GenerateGUID=function()return 'test-session'end
local writefile=function()end
local readfile=function()error('missing reply')end
'''
        checks = r'''
assert(#packets==0)
local visible=false
for _,item in ipairs(created)do
 if item.ClassName=='TextLabel'and string.find(item.Text or '',
  'No matching file reply: readfile failed: ',1,true)then visible=true end
end
assert(visible,'Wrong workspace did not show a timeout')
'''
        self.run_case("live_frames_and_close",extra=extra,filename="JJSploit_File_Client.lua",checks_override=checks)

    def test_file_client_explains_why_a_readable_reply_was_rejected(self):
        for body,expected in (
            ("'partial JSON'", "JSON decode failed"),
            ("services.HttpService:JSONEncode({session='other-client',id=1})", "reply belongs to another client"),
            ("services.HttpService:JSONEncode({session='test-session',id=0})", "reply id=0, waiting for id="),
            ("false", "readfile returned boolean"),
        ):
            with self.subTest(detail=expected):
                extra = "\nservices.HttpService.GenerateGUID=function()return 'test-session'end\nlocal writefile=function()end\nlocal readfile=function()return " + body + " end\n"
                checks = "\nassert(#packets==0)\nlocal visible=false\nfor _,item in ipairs(created)do\n if item.ClassName=='TextLabel'and string.find(item.Text or ''," + repr(expected) + ",1,true)then visible=true end\nend\nassert(visible,'Missing specific reply diagnostic')\n"
                self.run_case("live_frames_and_close",extra=extra,filename="JJSploit_File_Client.lua",checks_override=checks)


if __name__ == "__main__": unittest.main(verbosity=2)
