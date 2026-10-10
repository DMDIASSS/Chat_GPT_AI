import io
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.request import urlopen
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from balance_core import goal_threat, boost_waste, BalanceTracker
from rl_camera_server import serialize, Store, make_handler


def obj(**kwargs):return SimpleNamespace(**kwargs)
def car(pos,boost=30,speed=0,orange=False):
    return obj(is_orange=orange,boost_amount=boost,physics=obj(
        position=np.array(pos,dtype=float),linear_velocity=np.array([0,speed,0],dtype=float),
        rotation_mtx=np.eye(3)),on_ground=True)
def state(ball,vel,cars=None):
    cars={0:car([0,-1000,17]),1:car([0,1500,17],orange=True)} if cars is None else cars
    return obj(ball=obj(position=np.array(ball,dtype=float),linear_velocity=np.array(vel,dtype=float)),
               cars=cars,boost_pad_timers=np.zeros(34))

class BalanceTests(unittest.TestCase):
    def test_ball_goal_threat_blue(self):
        s=state([0,-2200,180],[0,-1800,0]);self.assertGreater(goal_threat(s,False),.5)
        self.assertEqual(goal_threat(s,True),0)
    def test_ball_goal_threat_orange(self):
        s=state([0,2500,170],[0,1500,0]);self.assertGreater(goal_threat(s,True),.5)
        self.assertEqual(goal_threat(s,False),0)
    def test_missed_net_isnt_danger(self):
        self.assertEqual(goal_threat(state([3200,-2200,100],[0,-1900,0]),False),0)
    def test_boost_penalty_only_when_wasted(self):
        self.assertTrue(boost_waste(70,65,2250,3000,0))
        self.assertFalse(boost_waste(70,65,2250,800,0))
        self.assertFalse(boost_waste(70,65,2250,3000,.7))
    def test_pickup_cooldown(self):
        b=BalanceTracker(False)
        before=state([0,0,95],[0,0,0],{0:car([0,-1300,17],10),1:car([0,1200,17],orange=True)})
        after=state([0,0,95],[0,0,0],{0:car([0,-1300,17],24),1:car([0,1200,17],orange=True)})
        self.assertGreater(b.step(before=before,after=after,ours=0,opponent=1),0)
        self.assertEqual(b.step(before=before,after=after,ours=0,opponent=1),0)
    def test_save_bonus_requires_our_touch(self):
        before=state([0,-2200,160],[0,-1700,0]);after=state([0,-2350,160],[0,850,0]);b=BalanceTracker(False)
        self.assertEqual(b.step(before=before,after=after,ours=0,opponent=1,our_touch=False),0)
        self.assertGreater(b.step(before=before,after=after,ours=0,opponent=1,our_touch=True),0)
    def test_own_touch_creating_goal_threat_is_bad(self):
        before=state([0,-2300,95],[0,650,0])
        after=state([0,-2400,95],[0,-1900,0])
        tracker=BalanceTracker(False)
        self.assertLess(tracker.step(before=before,after=after,ours=0,opponent=1,our_touch=True),0)
        self.assertEqual(BalanceTracker(False).step(before=before,after=after,ours=0,opponent=1,our_touch=False),0)
    def test_serialized_state(self):
        d=serialize(state([0,0,90],[0,100,0]));self.assertEqual(len(d['cars']),2);self.assertEqual(len(d['pads']),34)
        self.assertEqual(d['cars'][1]['team'],'orange')
    def test_http_loopback(self):
        s=Store();s.put({'cars':[]});http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(s));th=threading.Thread(target=http.serve_forever,daemon=True);th.start()
        try:
            with urlopen(f'http://127.0.0.1:{http.server_address[1]}/state',timeout=2) as res:
                self.assertIn(b'"cars": []',res.read())
        finally:http.shutdown();http.server_close();th.join(timeout=3)

class ExportTests(unittest.TestCase):
    def test_export_actor_torchscript(self):
        import torch
        import export_rlbot_v4 as ex
        with tempfile.TemporaryDirectory() as d:
            tmp=Path(d)
            original=ex.SOURCE
            self.assertTrue(original.exists(),'Test requires original Nexto TorchScript')
            actor=torch.jit.load(str(original),map_location='cpu')
            chk=tmp/'fake_native.pt';torch.save({'actor':actor.state_dict(),'timesteps':1},chk)
            prev=ex.OUTPUT
            try:
                ex.OUTPUT=tmp/'exports'
                result=ex.export(chk,'IntegrationTest')
                out=torch.jit.load(str(result/'nexto-model.pt'),map_location='cpu')
                self.assertEqual(len(out.state_dict()),len(actor.state_dict()))
                self.assertTrue((result/'bot.cfg').exists())
                self.assertIn('hardcoded_kickoffs=False',(result/'bot.py').read_text())
                with self.assertRaises(FileExistsError): ex.export(chk,'IntegrationTest')
            finally:ex.OUTPUT=prev

if __name__=='__main__':unittest.main()
