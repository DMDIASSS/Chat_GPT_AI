"""Portable bridge checks; no Windows inputs or private checkpoints are used."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import numpy as np
import torch

HERE = Path(__file__).resolve().parent.parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location("botrblx_bridge", HERE / "bridge271.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
CLIENT = (HERE / "client271.lua").read_text(encoding="utf-8")


def packet(seq=0):
    return {
        "car": {"position": [0,-4608,17], "velocity": [0,100,0],
                "forward": [0,1,0], "up": [0,0,1], "angular_velocity": [0,0,0]},
        "ball": {"position": [0,0,93.15], "velocity": [1,2,3], "angular_velocity": [0,0,0]},
        "boost": 33, "team": 0, "ground_estimate": True, "valid": True,
        "enabled": True, "seq": seq, "account": b.ACCOUNT, "place": b.PLACE,
    }


class FakeOutput(b.Output):
    def __init__(self):
        super().__init__(dry=True)
        self.focus, self.f8 = True, False
        self.events = []

    def focused(self): return self.focus
    def stopped(self): return self.f8
    def event(self, key, down): self.events.append((key,down))


class FixedModel:
    def __call__(self, obs):
        logits = torch.zeros(1,90)
        logits[0,20] = 1
        return logits, None


class TinyActor(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.layer = torch.nn.Linear(32,90)

    def forward(self, obs):
        return self.layer(obs[0].reshape(1,32)), torch.zeros(1)


def save_actor(folder):
    base = folder / "base.pt"
    checkpoint = folder / "update.pt"
    model = torch.jit.trace(TinyActor().eval(), (b.observations(packet(),b.ZERO,True),))
    model.save(str(base))
    torch.save({"actor": model.state_dict()}, checkpoint)
    return base, checkpoint


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): torch.set_num_threads(1)

    def setUp(self):
        self.now = 100.
        self.output = FakeOutput()
        self.bridge = b.Bridge(FixedModel(), self.output, lambda: self.now)

    def test_action_table_matches_existing_agent(self):
        spec = importlib.util.spec_from_file_location("agent", ROOT / "rlbot_v4_template/agent.py")
        agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent)
        np.testing.assert_array_equal(b.lookup_table(), agent.Agent.make_lookup_table())
        self.assertEqual(b.lookup_table().shape, (90,8))

    def test_observation_geometry_inversion_and_unknown_mask(self):
        for team in (0,1):
            p = packet(); p["team"] = team
            previous = np.array([1,-1,0,1,0,0,1,0],dtype=np.float32)
            q, kv, mask = (x.numpy() for x in b.observations(p,previous,True))
            self.assertEqual(q.shape, (1,1,32))
            self.assertEqual(kv.shape, (1,36,24))
            np.testing.assert_allclose(kv[0,1,5:8], [0,4608/2300,(93.15-17)/2300], atol=1e-6)
            np.testing.assert_allclose(kv[0,0,5:8], [0,0,0], atol=1e-6)
            np.testing.assert_array_equal(q[0,0,24:], previous)
            np.testing.assert_array_equal(q[0,0,:3], [1,1,0])
            np.testing.assert_array_equal(mask[0,:2], [0,0])
            np.testing.assert_array_equal(mask[0,2:], np.full(34,-10000))
            self.assertAlmostEqual(float(q[0,0,20]), .33, places=6)

    def test_rejects_missing_boost_and_nonfinite_pose(self):
        p = packet(); p["boost"] = None
        with self.assertRaises((ValueError,TypeError)): b.observations(p,b.ZERO,True)
        p = packet(); p["car"]["velocity"] = [float("nan"),0,0]
        with self.assertRaises(ValueError): b.observations(p,b.ZERO,True)

    def test_observed_pad_positions_and_availability_use_existing_nexto_slots(self):
        p=packet();p["boost_pads"]=[{"position":[111,222,73],"is_big":True,"active":True},
            {"position":[-333,444,70],"is_big":False,"active":False}]
        _,kv,mask=(t.numpy() for t in b.observations(p,b.ZERO,True))
        np.testing.assert_allclose(kv[0,2,5:8],[111/2300,(222+4608)/2300,(73-17)/2300],atol=1e-6)
        np.testing.assert_array_equal(kv[0,2,20:22],[1,1])
        np.testing.assert_allclose(kv[0,3,20:22],[.12,0])
        np.testing.assert_array_equal(mask[0,:4],[0,0,0,0])
        self.assertTrue((mask[0,4:]==-10000).all())
        p["boost_pads"][0]["active"]=None
        with self.assertRaises(ValueError):b.observations(p,b.ZERO,True)

    def test_keyboard_mapping_reports_emitted_axes(self):
        keys, actual = b.mapped_keys([1,1,0,1,0,0,1,1],True)
        self.assertEqual(keys, {"W","D","LMB","SHIFT"})
        np.testing.assert_array_equal(actual, [1,1,-1,0,1,0,1,1])
        keys, actual = b.mapped_keys([1,0,1,1,-1,1,1,1],False)
        self.assertEqual(keys, {"S","D","Q","RMB","LMB"})
        np.testing.assert_array_equal(actual, [-1,1,1,1,-1,1,1,0])

    def test_pause_and_repeated_frame_release_without_repeat_keydown(self):
        self.bridge.frame(packet())
        self.bridge.frame(packet(1))
        self.assertIn("W",self.output.held)
        self.assertEqual(self.output.events.count(("W",True)),1)
        self.bridge.frame(dict(packet(2),enabled=False))
        self.assertFalse(self.output.held)
        self.bridge.frame(packet(1))
        self.assertFalse(self.output.held)

    def test_focus_f8_and_timeout_require_rearming(self):
        for reason in ("focus","f8","timeout"):
            with self.subTest(reason=reason):
                self.setUp(); self.bridge.frame(packet())
                if reason == "focus": self.output.focus = False
                if reason == "f8": self.output.f8 = True
                if reason == "timeout": self.now += .5
                self.bridge.watchdog()
                self.assertFalse(self.output.held)
                self.assertTrue(self.bridge.blocked)
                self.output.focus,self.output.f8 = True,False
                self.bridge.frame(packet(1))
                self.assertFalse(self.output.held)
                self.bridge.frame(dict(packet(2),enabled=False))
                self.bridge.frame(packet(3))
                self.assertTrue(self.output.held)

    def test_goal_reset_waits_and_resumes(self):
        self.bridge.frame(packet())
        reply = self.bridge.frame(dict(packet(1),valid=False,reason="goal/reset"))
        self.assertIn("WAITING",reply["status"])
        self.assertFalse(self.output.held)
        self.assertFalse(self.bridge.blocked)
        self.bridge.frame(packet(2))
        self.assertTrue(self.output.held)

    def test_inflight_inference_cannot_reapply_after_timeout_or_reconnect(self):
        def delayed(obs):
            self.now += .5
            self.bridge.watchdog()
            return FixedModel()(obs)
        self.bridge.model = delayed
        self.bridge.frame(packet())
        self.assertFalse(self.output.held)
        self.setUp()
        def reconnecting(obs):
            self.bridge.epoch += 1
            self.bridge.release("New client")
            return FixedModel()(obs)
        self.bridge.model = reconnecting
        self.bridge.frame(packet())
        self.assertFalse(self.output.held)

    def test_script_and_native_state_checkpoint_loaders(self):
        with tempfile.TemporaryDirectory() as directory:
            base, checkpoint = save_actor(Path(directory))
            first = b.load_model(base,base)
            second = b.load_model(checkpoint,base)
            for key,value in first.state_dict().items():
                self.assertTrue(torch.equal(value,second.state_dict()[key]))
            with torch.inference_mode():
                logits = second(b.observations(packet(),b.ZERO,True))[0]
            self.assertEqual(tuple(logits.shape),(1,90))
            self.assertTrue(torch.isfinite(logits).all())

    @unittest.skipUnless((ROOT / "vendor/nexto/nexto-model.pt").is_file(), "Local Nexto asset unavailable")
    def test_existing_nexto_wrapper_accepts_both_team_observations(self):
        base = ROOT / "vendor/nexto/nexto-model.pt"
        actor = b.load_model(base,base)
        for team in (0,1):
            p = packet(); p["team"] = team
            with torch.inference_mode(): logits = actor(b.observations(p,b.ZERO,True))[0]
            self.assertEqual(tuple(logits.shape),(1,90))
            self.assertTrue(torch.isfinite(logits).all())

    @unittest.skipUnless((ROOT / "vendor/nexto/nexto-model.pt").is_file(), "Local Nexto asset unavailable")
    def test_unknown_pads_are_actually_excluded_by_torchscript_attention(self):
        base = ROOT / "vendor/nexto/nexto-model.pt"
        actor = b.load_model(base,base)
        q,kv,mask = b.observations(packet(),b.ZERO,True)
        with torch.inference_mode():
            full = actor((q,kv,mask))[0]
            trimmed = actor((q,kv[:,:2],mask[:,:2]))[0]
        torch.testing.assert_close(full,trimmed,atol=2e-5,rtol=2e-5)

    def test_cli_selfcheck_and_missing_model_log_before_client(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            base, checkpoint = save_actor(folder)
            command = [sys.executable,str(HERE/"bridge271.py"),"--project-root",str(folder),"--base",str(base),"--model",str(checkpoint),"--self-check"]
            result = subprocess.run(command,capture_output=True,text=True,timeout=30,cwd=directory)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn("SELF_CHECK_OK",result.stderr)
            self.assertNotIn("READY http",result.stderr)
            absent = folder / "missing-update271.pt"
            command[command.index(str(checkpoint))] = str(absent)
            result = subprocess.run(command,capture_output=True,text=True,timeout=30,cwd=directory)
            self.assertEqual(result.returncode,1)
            self.assertIn("Missing model",result.stderr)
            self.assertIn(str(absent),(HERE/"bridge.log").read_text(encoding="utf-8"))

    def test_missing_dependencies_are_logged_before_client(self):
        result = subprocess.run(
            [sys.executable,"-S",str(HERE/"bridge271.py"),"--self-check"],
            capture_output=True,text=True,timeout=15,
        )
        self.assertEqual(result.returncode,1)
        self.assertIn("Project dependencies missing",result.stderr)
        self.assertIn("Project dependencies missing",(HERE/"bridge.log").read_text(encoding="utf-8"))

    def test_default_model_paths_follow_explicit_project_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root/"data/isolated/mechanics_curriculum/selected7_mechanics01/update_000271.pt"
            base = root/"vendor/nexto/nexto-model.pt"
            model.parent.mkdir(parents=True); base.parent.mkdir(parents=True)
            model.touch(); base.touch()
            args = argparse.Namespace(project_root=root,model=None,base=None)
            self.assertEqual(b.resolve_paths(args),(root.resolve(),model,base))

    def test_http_auth_serving_inference_and_invalid_frame_release(self):
        with tempfile.TemporaryDirectory() as directory:
            base,_ = save_actor(Path(directory))
            self.bridge.model = b.load_model(base,base)
            server = b.ThreadingHTTPServer(("127.0.0.1",0),b.make_handler(self.bridge,CLIENT))
            thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            url = f"http://127.0.0.1:{server.server_port}"
            def get(path,headers=None):
                return urllib.request.urlopen(urllib.request.Request(url+path,headers=headers or {}),timeout=3)
            def post(p,token=None):
                return urllib.request.urlopen(urllib.request.Request(url+"/frame",data=json.dumps(p).encode(),headers={"Content-Type":"application/json","X-Bridge-Token":token or self.bridge.token}),timeout=3)
            try:
                with get("/client") as response: self.assertEqual(response.read().decode(),CLIENT)
                with get("/hello") as response: self.assertEqual(json.load(response)["protocol"],1)
                with self.assertRaises(urllib.error.HTTPError) as error: get("/hello",{"Origin":"https://example.test"})
                self.assertEqual(error.exception.code,403)
                with self.assertRaises(urllib.error.HTTPError) as error: post(packet(),"wrong-token")
                self.assertEqual(error.exception.code,401)
                with post(packet()) as response: self.assertIn("RUNNING",json.load(response)["status"])
                with post(dict(packet(1),enabled=False)) as response: self.assertEqual(json.load(response)["keys"],[])
                self.bridge.frame(packet(2))
                with self.assertLogs(level="ERROR"):
                    with self.assertRaises(urllib.error.HTTPError) as error: post(dict(packet(3),boost=None))
                self.assertEqual(error.exception.code,400)
                self.assertFalse(self.output.held)
                self.assertTrue(self.bridge.blocked)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_health_route_is_read_only_and_reports_client_connection(self):
        server = b.ThreadingHTTPServer(("127.0.0.1",0),b.make_handler(self.bridge,CLIENT))
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            with urllib.request.urlopen(url,timeout=3) as response: initial = json.load(response)
            self.assertTrue(initial["model_loaded"])
            self.assertFalse(initial["client_connected"])
            self.bridge.frame(packet())
            token, seq, held = self.bridge.token, self.bridge.seq, set(self.output.held)
            for path in ("/", "/health"):
                with urllib.request.urlopen(url+path,timeout=3) as response: health = json.load(response)
                self.assertTrue(health["client_connected"])
                self.assertEqual(health["service"],"botrblx")
                self.assertNotIn("token",health)
                self.assertEqual((self.bridge.token,self.bridge.seq),(token,seq))
                self.assertEqual(self.output.held,held)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == "__main__": unittest.main(verbosity=2)
