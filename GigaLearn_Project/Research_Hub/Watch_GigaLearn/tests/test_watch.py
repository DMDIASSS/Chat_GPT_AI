import importlib.util
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('watch_core',HERE/'watch_core.py')
wc=importlib.util.module_from_spec(spec);spec.loader.exec_module(wc)

class Tests(unittest.TestCase):
    def test_discovery_read_only_and_reject_1v2(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for name,teams in [('good',(1,1)),('bad',(1,2))]:
                exp=root/'experiments'/name
                cp=exp/'checkpoints'/'500';cp.mkdir(parents=True)
                for filename in ['POLICY.lt','SHARED_HEAD.lt']:(cp/filename).write_bytes(b'weights')
                (exp/'experiment.json').write_text(json.dumps({'settings':{'blue':teams[0],'orange':teams[1]}}))
            self.assertEqual(list(wc.discover(root)),['good'])
            self.assertEqual(wc.latest_checkpoint(root/'experiments'/'good').name,'500')

    def test_select_largest_checkpoint(self):
        with tempfile.TemporaryDirectory() as t:
            exp=Path(t)
            for n in [10,1000,50]:
                cp=exp/'checkpoints'/str(n);cp.mkdir(parents=True)
                (cp/'POLICY.lt').write_text('a');(cp/'SHARED_HEAD.lt').write_text('b')
            self.assertEqual(wc.latest_checkpoint(exp).name,'1000')

    def test_packet_schema(self):
        phys=dict(pos=[0,0,100],vel=[0,0,0],ang_vel=[0,0,0],forward=[1,0,0],right=[0,1,0],up=[0,0,1])
        sample={'type':'frame','ball':phys,'boost_pad_states':[True]*34,
                'cars':[{'team':i,'phys':phys,'boost':42,'on_ground':True,'demoed':False,'has_flip':True}for i in (0,1)]}
        payload=wc.as_rocketsimvis(sample)
        self.assertEqual(payload['cars'][0]['boost_amount'],42)
        self.assertEqual(len(payload['boost_pad_states']),34)
        self.assertEqual(payload['ball_phys']['pos'][2],100)
        self.assertNotIn('checkpoint',payload)
        self.assertEqual(set(payload),{'ball_phys','cars','boost_pad_states'})

    def test_bad_packet_fails_closed(self):
        with self.assertRaises(ValueError):wc.as_rocketsimvis({'type':'frame','cars':[]})

    def test_play_end_to_end_with_mock_native_frames(self):
        # Tests subprocess/stdout parsing/sender lifecycle without Windows/MSVC.
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            (root/'mesh').mkdir()
            cp1=root/'a';cp2=root/'b';cp1.mkdir();cp2.mkdir()
            for cp in (cp1,cp2):
                (cp/'POLICY.lt').write_bytes(b'a');(cp/'SHARED_HEAD.lt').write_bytes(b'b')
            frame={'type':'frame','episode':1,'decision':1,'a_blue':True,'goal':False,
                   'boost_pad_states':[True]*34,
                   'ball':dict(pos=[0,0,92],vel=[0,0,0],ang_vel=[0,0,0],
                               forward=[1,0,0],right=[0,1,0],up=[0,0,1]),
                   'cars':[]}
            for team in (0,1):
                frame['cars'].append(dict(id=team+1,team=team,boost=100,on_ground=True,demoed=False,
                   has_flip=True,ball_touched=False,phys=frame['ball']))
            stub=root/'native_stub'
            stub.write_text('#!/usr/bin/env python3\nimport json\nprint('+repr(json.dumps(frame))+')\n',encoding='utf8')
            stub.chmod(0o755)
            results=[];senders=[]
            class FakeSender:
                def __init__(self,mode,log):self.closed=False;senders.append(self)
                def send(self,frame):results.append(frame)
                def close(self):self.closed=True
            original_root=wc.ROOT
            old=os.environ.get('GIGALEARN_MESHES')
            try:
                wc.ROOT=root;os.environ['GIGALEARN_MESHES']=str(root/'mesh')
                logs=[]
                wc.play(cp1,cp2,viewer='rocketsimvis',speed=5,
                        log=logs.append,executable=stub,sender_factory=FakeSender,
                        stop=threading.Event())
                self.assertEqual(len(results),1)
                self.assertTrue(senders[0].closed)
                self.assertTrue(any('Playback finished' in x for x in logs))
            finally:
                wc.ROOT=original_root
                if old is None:os.environ.pop('GIGALEARN_MESHES',None)
                else:os.environ['GIGALEARN_MESHES']=old

    def test_installer_idempotent(self):
        inspec=importlib.util.spec_from_file_location('installer',HERE/'install_watch_cpp.py')
        installer=importlib.util.module_from_spec(inspec);inspec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);upstream=base/'upstream';(upstream/'src').mkdir(parents=True)
            (upstream/'src/ExampleMain.cpp').write_text('int main(){}')
            cm=upstream/'CMakeLists.txt'
            original='file(GLOB_RECURSE FILES_SRC "src/*.cpp")\nadd_executable(GigaLearnBot ${FILES_SRC})\n'
            cm.write_text(original)
            installer.CMAKE=cm;installer.CPP=upstream/'src/HubWatch.cpp';installer.UPSTREAM=upstream
            a=installer.install();self.assertTrue(a['cmake_changed'])
            self.assertTrue(installer.CPP.read_bytes()==installer.SOURCE.read_bytes())
            self.assertTrue((upstream/'CMakeLists.txt.before_gigalearn_watch_v1.bak').exists())
            cmcontent=cm.read_text()
            self.assertIn('list(FILTER FILES_SRC EXCLUDE REGEX',cmcontent)
            self.assertIn('add_executable(GigaLearnWatch src/HubWatch.cpp)',cmcontent)
            b=installer.install();self.assertFalse(b['cmake_changed'])
            self.assertEqual(cm.read_text(),cmcontent)
            self.assertEqual((upstream/'CMakeLists.txt.before_gigalearn_watch_v1.bak').read_text(),original)

if __name__=='__main__':unittest.main()
