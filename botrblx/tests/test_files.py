"""Real mailbox IO and bridge inference; no executor or Windows input required."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from test_bridge import b, FakeOutput, FixedModel, HERE, packet, save_actor

spec = importlib.util.spec_from_file_location("botrblx_files",HERE / "file_transport.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.now = 100.
        self.output = FakeOutput()
        self.bridge = b.Bridge(FixedModel(),self.output,lambda:self.now)
        self.exchange = f.FileExchange(self.bridge,self.workspace)
        self.request_id = 0
        self.token = ""

    def send(self, route, p=None, session="client-A", token=None):
        self.request_id += 1
        envelope = dict(session=session,id=self.request_id,route=route,file_protocol=3,
                        token=self.token if token is None else token,packet=p)
        self.exchange.request.write_text(json.dumps(envelope),encoding="utf-8")
        self.exchange.poll()
        reply = json.loads(self.exchange.response.read_text(encoding="utf-8"))
        self.assertEqual((reply["session"],reply["id"]),(session,self.request_id))
        return reply

    def hello(self):
        reply = self.send("/hello")
        self.assertEqual(reply["status"],200)
        self.token = reply["data"]["token"]

    def test_roundtrip_inference_duplicate_does_not_refresh_or_repeat(self):
        self.hello()
        reply = self.send("/frame",packet())
        self.assertIn("RUNNING",reply["data"]["status"])
        self.assertIn("W",self.output.held)
        self.now += .5
        for _ in range(5): self.exchange.poll()
        self.assertEqual(self.bridge.frames,1)
        self.bridge.watchdog()
        self.assertFalse(self.output.held)
        self.assertTrue(self.bridge.blocked)
        self.assertEqual([event for event in self.output.events if event[0]=="W"],[("W",True),("W",False)])

    def test_cached_reply_bytes_do_not_hide_the_next_response(self):
        self.hello()
        cache = {}
        def cached_read(path):
            if path not in cache: cache[path] = path.read_bytes()
            return cache[path]
        original_path = self.exchange.response
        original = cached_read(original_path)
        for seq in range(3):
            reply = self.send("/frame",packet(seq))
            visible = json.loads(cached_read(self.exchange.response))
            self.assertEqual(visible["id"],reply["id"])
            self.assertEqual(original_path.read_bytes(),original,"Published reply was overwritten")

    def test_session_tokens_and_new_server_disarm_old_request(self):
        self.assertEqual(self.send("/frame",packet())["status"],401)
        self.hello()
        self.assertEqual(self.send("/frame",packet(),session="old-client")["status"],401)
        self.assertEqual(self.send("/frame",packet(),token="wrong")["status"],401)
        self.send("/frame",packet())
        self.assertTrue(self.output.held)
        self.send("/hello",session="client-B")
        self.assertFalse(self.output.held)
        self.assertEqual(self.send("/frame",packet(1))["status"],401)
        # A fresh process clears owned mailbox contents before accepting IO.
        old_request = self.exchange.request.read_bytes()
        self.exchange = f.FileExchange(self.bridge,self.workspace)
        self.assertEqual(json.loads(self.exchange.request.read_text()),{})
        self.exchange.request.write_bytes(old_request)
        self.exchange.poll()
        self.assertEqual(json.loads(self.exchange.response.read_text())["status"],401)

    def test_stale_frame_and_incomplete_write_never_drive(self):
        self.hello()
        self.exchange.request.write_text('{"session":',encoding="utf-8")
        self.exchange.poll()
        self.assertEqual(self.bridge.frames,0)
        self.exchange.wall_clock = lambda: 1e20
        reply = self.send("/frame",packet())
        self.assertEqual(reply["status"],408)
        self.assertFalse(self.output.held)
        self.assertEqual(self.bridge.frames,0)

    def test_measured_wrd_delay_is_accepted_with_bounded_expiry_and_immediate_stop(self):
        self.bridge.telemetry_timeout = 3.0
        self.hello()
        self.request_id += 1
        self.exchange.request.write_text(json.dumps(dict(session="client-A",id=self.request_id,
            file_protocol=3,route="/frame",token=self.token,packet=packet())))
        written = time.time()-1.3
        os.utime(self.exchange.request,(written,written))
        self.exchange.poll()
        reply = json.loads(self.exchange.response.read_text())
        self.assertEqual(reply["status"],200)
        self.assertIn("W",self.output.held)
        self.now += 1.4
        self.bridge.watchdog()
        self.assertIn("W",self.output.held)
        self.output.f8 = True
        self.bridge.watchdog()
        self.assertFalse(self.output.held)
        self.assertTrue(self.bridge.blocked)
        self.output.f8 = False
        self.bridge.frame(dict(packet(1),enabled=False))
        self.bridge.frame(packet(2))
        self.assertTrue(self.output.held)
        self.output.focus = False
        self.bridge.watchdog()
        self.assertFalse(self.output.held)
        self.output.focus = True
        self.bridge.frame(dict(packet(3),enabled=False))
        self.bridge.frame(packet(4))
        self.now += 3.1
        self.bridge.watchdog()
        self.assertFalse(self.output.held)

    def test_locked_response_retries_without_repeating_inference(self):
        self.hello()
        write_text = Path.write_text
        def locked_write(path,*args,**kwargs):
            if path.parent == self.exchange.replies: raise PermissionError("reply write denied")
            return write_text(path,*args,**kwargs)
        with patch.object(Path,"write_text",locked_write), self.assertLogs(level="WARNING"):
            self.request_id += 1
            self.exchange.request.write_text(json.dumps(dict(session="client-A",id=self.request_id,
                route="/frame",file_protocol=3,token=self.token,packet=packet())),encoding="utf-8")
            self.exchange.poll()
            self.assertIsNotNone(self.exchange.pending)
            self.assertEqual(self.bridge.frames,1)
        self.exchange.poll()
        self.assertIsNone(self.exchange.pending)
        self.assertEqual(self.bridge.frames,1)
        self.assertEqual(json.loads(self.exchange.response.read_text())["id"],self.request_id)

    def test_hello_reply_written_is_logged_without_its_token(self):
        with self.assertLogs(level="INFO") as logs:
            self.hello()
        messages = " ".join(logs.output)
        self.assertIn("FILE_REPLY: hello",messages)
        self.assertIn("reply_client-A_1.json",messages)
        self.assertNotIn(self.token,messages)

    def test_restart_cleans_owned_replies_and_preserves_other_files(self):
        self.hello()
        old_path = self.exchange.response
        other = self.exchange.replies / "notes.txt"
        other.write_text("keep this")
        self.exchange = f.FileExchange(self.bridge,self.workspace)
        self.assertFalse(old_path.exists())
        self.assertEqual(other.read_text(),"keep this")
        self.hello()
        self.assertNotEqual(self.exchange.response,old_path)

    def test_replies_are_bounded_and_replaying_does_not_repeat_inference(self):
        self.hello()
        for seq in range(40): self.send("/frame",packet(seq))
        self.assertEqual(len(list(self.exchange.replies.glob("*.json"))),16)
        self.assertEqual(list(self.exchange.replies.glob("*.tmp")),[])
        frames = self.bridge.frames
        replay = dict(session="client-A",id=self.request_id-1,route="/frame",file_protocol=3,
                      token=self.token,packet=packet(38))
        self.exchange.request.write_text(json.dumps(replay))
        self.exchange.poll()
        self.assertEqual(self.bridge.frames,frames)

    def test_reply_paths_cannot_escape_the_exchange_folder(self):
        self.exchange.request.write_text(json.dumps(dict(session="../../escaped",id=1,route="/hello",file_protocol=3)))
        self.exchange.poll()
        self.assertEqual(list(self.exchange.replies.iterdir()),[])
        self.assertEqual(self.bridge.frames,0)

    def test_true_torchscript_mailbox_and_invalid_packet_release(self):
        base,_ = save_actor(self.workspace)
        self.bridge.model = b.load_model(base,base)
        self.hello()
        reply = self.send("/frame",packet())
        self.assertIn("action",reply["data"])
        with self.assertLogs(level="ERROR"):
            reply = self.send("/frame",dict(packet(1),boost=None))
        self.assertEqual(reply["status"],400)
        self.assertFalse(self.output.held)
        self.assertTrue(self.bridge.blocked)

    def test_workspace_choice_persistence_install_and_generated_source(self):
        config = self.workspace / "connection.json"
        args = argparse.Namespace(workspace=self.workspace,reset_workspace=False,choose_workspace=False)
        self.assertEqual(f.select_workspace(args,config),self.workspace.resolve())
        args.workspace = None
        self.assertEqual(f.select_workspace(args,config),self.workspace.resolve())
        args.reset_workspace = True
        with self.assertRaisesRegex(ValueError,"File mode needs"):
            f.select_workspace(args,config)
        f.install_client(self.workspace,HERE)
        source = (self.workspace / "botrblx_client.lua").read_text(encoding="utf-8")
        self.assertEqual(source,(HERE / "JJSploit_File_Client.lua").read_text(encoding="utf-8"))
        self.assertNotIn("127.0.0.1",source)
        self.assertNotIn("http_request_checked",source)
        self.assertNotIn("HttpGet",source)


if __name__ == "__main__": unittest.main(verbosity=2)
