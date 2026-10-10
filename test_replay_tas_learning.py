"""No RocketSim required; run: python -m unittest -v test_replay_tas_learning"""
import importlib.util
import json
import pathlib
import struct
import tempfile
import unittest
from unittest.mock import patch
import sys
import numpy as np

HERE=pathlib.Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location('afk_replay_tas_learning',HERE/'afk_replay_tas_learning.py')
L=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(L)

class SafetyTests(unittest.TestCase):
    def test_expand_quoted_windows_style_glob_on_os(self):
        with tempfile.TemporaryDirectory() as tmp:
            t=pathlib.Path(tmp)
            (t/'a.data').write_bytes(b'abc');(t/'b.data').write_bytes(b'def')
            (t/'c.txt').write_bytes(b'X')
            paths=L.expand_files([str(t/'*.data')],'.data')
            self.assertEqual([x.name for x in paths],['a.data','b.data'])

    def test_tas_record_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'a.data'
            payload=struct.pack('<II',1,2)+2*struct.pack('<I7f',3,1,0,0,0,0,0,0)+bytes(128)
            path.write_bytes(payload)
            r=L.inspect_tas(path)
            self.assertEqual(r['frame_count'],2)
            self.assertFalse(r['training_ready'])
            self.assertEqual(r['raw_flag_counts'][3],2)
            self.assertEqual(path.read_bytes(),payload)

    def test_bad_tas_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/'bad.data';p.write_bytes(struct.pack('<II',1,4)+bytes(128))
            with self.assertRaises(ValueError):L.inspect_tas(p)

    def test_action_exact_and_invalid(self):
        table=np.zeros((90,8),np.float32)
        table[5]=[1,0,0,0,0,1,0,1]
        r=L.action_options(table[5],table)
        self.assertEqual(r[0],5)
        self.assertEqual(r[1],0)
        self.assertIsNone(L.action_options(np.array([np.nan]*8),table))
        self.assertIsNone(L.action_options(np.array([2.0]*8),table))

    def test_replay_hash_split_stability(self):
        h='12345678'+('0'*56)
        a=L.replay_split(h,20)
        self.assertEqual(a,L.replay_split(h,20))
        self.assertIn(a,['train','val'])

    def test_atomic_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/'m.json'
            L.write_json(p,{'foo':'bar'})
            self.assertEqual(json.loads(p.read_text())['foo'],'bar')

    def test_no_overwrite_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/'original.pt';p.write_bytes(b'model')
            with patch.object(L,'BASE',pathlib.Path(tmp)):
                archived=L.archive_existing(p)
                self.assertEqual(archived.read_bytes(),b'model')
                self.assertEqual(p.read_bytes(),b'model')
                self.assertEqual(archived,L.archive_existing(p))

    def test_dataset_format_and_group_leakage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'data.npz'
            man=pathlib.Path(tmp)/'manifest.json'
            n=12
            d=dict(q=np.zeros((n,1,32),np.float32),kv=np.zeros((n,37,24),np.float32),
                   mask=np.zeros((n,37),np.float32),action=np.zeros(n,np.int64),
                   weight=np.ones(n,np.float32),is_val=np.array([False]*8+[True]*4),
                   bucket=np.zeros(n,np.uint8),source_id=np.array([0]*8+[1]*4,np.int32))
            np.savez_compressed(path,**d)
            man.write_text(json.dumps({'dataset_sha256':L.sha(path)}))
            with patch.object(L,'DATA',path),patch.object(L,'MANIFEST',man):
                data,_=L.dataset_load();self.assertEqual(len(data['action']),n)
                d['source_id'][-1]=0
                np.savez_compressed(path,**d);man.write_text(json.dumps({'dataset_sha256':L.sha(path)}))
                with self.assertRaises(ValueError):L.dataset_load()

if __name__=='__main__':unittest.main()

class ReplayBuildSmoke(unittest.TestCase):
    def test_replay_converts_to_native_and_reuses_cache(self):
        from types import SimpleNamespace,ModuleType
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);replays=root/'replays';replays.mkdir()
            paths=[]
            for i in range(16):
                path=replays/f'{i}.replay';path.write_bytes(bytes([i])*60);paths.append(path)
            mock_replays=ModuleType('rlgym_tools.rocket_league.replays')
            parsed=ModuleType('rlgym_tools.rocket_league.replays.parsed_replay')
            convert=ModuleType('rlgym_tools.rocket_league.replays.convert')
            nteacher=ModuleType('nexto_teacher')
            actionpick=ModuleType('rlgym_tools.rocket_league.replays.pick_action')
            actionpick.get_best_action_options=lambda car,control,table,greedy:np.concatenate(([1.],np.zeros(89)))
            loads={'count':0}
            def load(path):loads['count']+=1;return str(path)
            parsed.ParsedReplay=SimpleNamespace(load=load)
            class T:
                def __init__(self,*args,**kwargs):pass
                def observe(self,state,past):
                    return [(aid,np.zeros((1,32),np.float32),np.zeros((37,24),np.float32),
                             np.zeros((37,),np.float32)) for aid in state.cars]
            nteacher.NextoTeacher=T
            table=np.zeros((90,8),np.float32)
            nteacher.nexto_actions=lambda:table
            class Car:
                def __init__(self,orange):
                    self.is_orange=orange;self.is_demoed=False;self.boost_amount=50
                    self.physics=SimpleNamespace(position=np.zeros(3))
            state=SimpleNamespace(cars={0:Car(False),1:Car(True)},ball=SimpleNamespace(position=np.array([0,0,100.])))
            def frames(_):
                for _ in range(20):
                    yield SimpleNamespace(state=state,actions={0:np.zeros(8),1:np.zeros(8)},
                              update_age={0:0.,1:0.})
            convert.replay_to_rlgym=frames
            mods={'rlgym_tools':ModuleType('rlgym_tools'),
                'rlgym_tools.rocket_league':ModuleType('rlgym_tools.rocket_league'),
                'rlgym_tools.rocket_league.replays':mock_replays,
                'rlgym_tools.rocket_league.replays.parsed_replay':parsed,
                'rlgym_tools.rocket_league.replays.convert':convert,
                'rlgym_tools.rocket_league.replays.pick_action':actionpick,
                'nexto_teacher':nteacher}
            args=SimpleNamespace(inputs=[str(replays)],every=1,max_replays=16,max_samples=1000,
                per_replay=20,max_age=.1,max_cost=.65,validation_pct=30,
                min_samples=60,min_train_replays=1,min_val_replays=1,seed=817249,strict=True,replace=False)
            with patch.dict(sys.modules,mods),patch.object(L,'ROOT',root),patch.object(L,'BASE',root/'learning'),\
                patch.object(L,'DATA',root/'learning'/'dataset.npz'),\
                patch.object(L,'MANIFEST',root/'learning'/'manifest.json'),\
                patch.object(L,'PAUSE',root/'learning'/'learning.pause'):
                L.build(args)
                d,m=L.dataset_load()
                self.assertEqual(d['q'].shape[1:],(1,32))
                self.assertGreater(len(d['action']),60)
                self.assertGreater(m['train_replays'],0)
                self.assertGreater(m['val_replays'],0)
                before=loads['count']
                args.replace=True
                L.build(args)
                self.assertEqual(loads['count'],before)
                self.assertEqual(json.loads(L.MANIFEST.read_text())['cache_hits'],m['unique_replays'])

