import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def load_module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

R=load_module(ROOT/'extended_rotation.py','extended_rotation_test')
P=load_module(ROOT/'extended_frozen_cli_patch.py','extended_frozen_cli_patch_test')


def dummy_cp(folder, ts=0):
    cp=folder/'checkpoints'/str(ts)
    cp.mkdir(parents=True,exist_ok=True)
    for name in ('POLICY.lt','SHARED_HEAD.lt','CRITIC.lt'):
        (cp/name).write_bytes(b'test weights')
    (cp/'RUNNING_STATS.json').write_text(json.dumps({'total_timesteps':ts,'total_iterations':ts//4096}))
    return cp


class ExtendedRotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.original_exps=R.EXPERIMENTS
        R.EXPERIMENTS=self.root/'experiments'
    def tearDown(self):
        R.EXPERIMENTS=self.original_exps
        self.tmp.cleanup()

    def test_checkpoint_checks_integrity(self):
        exp=R.EXPERIMENTS/'old'
        cp=dummy_cp(exp,100)
        self.assertEqual(R.latest(exp),cp)
        (cp/'POLICY.lt').unlink()
        with self.assertRaisesRegex(RuntimeError,'Incomplete checkpoint'):R.latest(exp)

    def test_teacher_log_count_and_incomplete_rotation(self):
        log='[FrozenNexto] PPO cycle=1 teacher=nexto\n[FrozenNexto] PPO cycle=2 teacher=cycle9\n[FrozenNexto] PPO cycle=3 teacher=wavedash\n'
        self.assertEqual(R.audit_teachers(log),{'nexto':1,'cycle9':1,'wavedash':1})
        self.assertEqual(R.audit_teachers('teacher=nexto'),dict.fromkeys(R.TEACHERS,0))

    def test_journal_rejects_other_experiment(self):
        exp=R.EXPERIMENTS/'tri_teacher_challenger_01'
        dummy_cp(exp)
        R.atomic_json(exp/R.STATE_FILE,{'kind':'something-else'})
        with self.assertRaisesRegex(RuntimeError,'not our protected'):R.verify_journal()

    def test_init_creates_isolated_branch_from_latest_successful(self):
        old=R.EXPERIMENTS/'nexto_rotation_01'
        cp=dummy_cp(old,4320)
        target=R.EXPERIMENTS/'tri_teacher_challenger_01'
        def fake_create(ns):
            self.assertEqual(ns.seed,cp)
            dummy_cp(target,0)
            (target/'experiment.json').write_text('{"name":"tri_teacher_challenger_01"}')
        mock=types.SimpleNamespace(create=fake_create)
        with patch.dict(sys.modules,{'frozen_cli':mock}):
            journal=R.init_challenger()
        self.assertEqual(journal['completed_rounds'],0)
        self.assertEqual(R.latest(target).name,'0')
        self.assertEqual(R.init_challenger.__name__,'init_challenger')

    def test_existing_unknown_branch_fails_closed(self):
        dummy_cp(R.EXPERIMENTS/'tri_teacher_challenger_01',0)
        with self.assertRaisesRegex(RuntimeError,'without our journal'):R.init_challenger()

    def test_safe_stop_writes_flag_only_if_running_lock(self):
        exp=R.EXPERIMENTS/'tri_teacher_challenger_01'
        dummy_cp(exp,0)
        state={'kind':R.OWN_MARK,'experiment':exp.name,'opponents':list(R.TEACHERS),
               'last_checkpoint_step':0,'completed_rounds':0,'history':[],'status':'running'}
        R.atomic_json(exp/R.STATE_FILE,state)
        R.stop()
        self.assertFalse((exp/'request_safe_stop.flag').exists())
        (exp/'extended_rotation.lock').write_text('lock')
        R.stop()
        self.assertTrue((exp/'request_safe_stop.flag').exists())

    def test_atomic_json_no_temp_residue(self):
        f=self.root/'sub'/'j.json'
        R.atomic_json(f,{'v':1})
        R.atomic_json(f,{'v':2})
        self.assertEqual(json.loads(f.read_text()),{'v':2})
        self.assertFalse((f.parent/'j.json.new').exists())

    def test_script_rejects_bad_save_intervals(self):
        for val in (1000,4096,30000,262145):
            with self.assertRaises(ValueError):R.training(rounds=1,save_every=val)

    def test_progress_without_promoting_models(self):
        old=R.EXPERIMENTS/'nexto_rotation_01'
        dummy_cp(old,13000)
        exp=R.EXPERIMENTS/'tri_teacher_challenger_01'
        def fake_create(ns):
            dummy_cp(exp,0)
            (exp/'experiment.json').write_text('{"name":"tri_teacher_challenger_01"}')
        core=types.SimpleNamespace(create=fake_create)
        def fake_process(experiment,state,rotation,games,save_every,round_ix,seed):
            start=int(R.latest(experiment).name)
            end=start+rotation*3
            dummy_cp(experiment,end)
            return {'started_utc':R.now(),'round':round_ix,'old_checkpoint':start,'new_checkpoint':end,
                    'teachers_ppo_iterations':{'nexto':12,'cycle9':13,'wavedash':12},
                    'elapsed_seconds':0.1,'return_code':0,'fatal':False,'success':True,'paused':False,
                    'full_requested_steps_saved':True}
        with patch.dict(sys.modules,{'frozen_cli':core}),\
             patch.object(R,'validate_setup',return_value={'nexto':'a','cycle9':'b','wavedash':'c'}),\
             patch.object(R,'_process_round',side_effect=fake_process):
            R.training(rounds=2)
            _,st,cp=R.verify_journal()
            self.assertEqual(st['completed_rounds'],2)
            self.assertEqual(st['status'],'finished')
            self.assertEqual(cp.name,str(2*196608))
            self.assertFalse((exp/'extended_rotation.lock').exists())
            R.training(rounds=3)
            _,st,cp=R.verify_journal()
            self.assertEqual(st['completed_rounds'],3)
            self.assertEqual(cp.name,str(3*196608))
            self.assertTrue((old/'checkpoints'/'13000'/'POLICY.lt').exists())

    def test_pause_does_not_claim_completed_round(self):
        old=R.EXPERIMENTS/'nexto_rotation_01'
        dummy_cp(old,13000)
        exp=R.EXPERIMENTS/'tri_teacher_challenger_01'
        def fake_create(ns):
            dummy_cp(exp,0)
            (exp/'experiment.json').write_text('{"name":"tri_teacher_challenger_01"}')
        def fake_process(experiment,state,rotation,games,save_every,round_ix,seed):
            dummy_cp(experiment,4320)
            return {'started_utc':R.now(),'round':round_ix,'old_checkpoint':0,'new_checkpoint':4320,
                    'teachers_ppo_iterations':{'nexto':1,'cycle9':0,'wavedash':0},
                    'elapsed_seconds':0.1,'return_code':1,'fatal':False,'success':False,'paused':True,
                    'full_requested_steps_saved':False}
        with patch.dict(sys.modules,{'frozen_cli':types.SimpleNamespace(create=fake_create)}),\
             patch.object(R,'validate_setup',return_value={'nexto':'a','cycle9':'b','wavedash':'c'}),\
             patch.object(R,'_process_round',side_effect=fake_process):
            R.training(rounds=5)
        _,state,cp=R.verify_journal()
        self.assertEqual(state['status'],'paused')
        self.assertEqual(state['completed_rounds'],0)
        self.assertEqual(cp.name,'4320')

    def test_fail_does_not_claim_completed_round(self):
        old=R.EXPERIMENTS/'nexto_rotation_01'
        dummy_cp(old,13000)
        exp=R.EXPERIMENTS/'tri_teacher_challenger_01'
        def fake_create(ns):
            dummy_cp(exp,0)
            (exp/'experiment.json').write_text('{"name":"tri_teacher_challenger_01"}')
        def fake_process(experiment,state,rotation,games,save_every,round_ix,seed):
            return {'started_utc':R.now(),'round':round_ix,'old_checkpoint':0,'new_checkpoint':0,
                    'teachers_ppo_iterations':{'nexto':0,'cycle9':0,'wavedash':0},
                    'elapsed_seconds':0.1,'return_code':2,'fatal':True,'success':False,'paused':False,
                    'full_requested_steps_saved':False}
        with patch.dict(sys.modules,{'frozen_cli':types.SimpleNamespace(create=fake_create)}),\
             patch.object(R,'validate_setup',return_value={'nexto':'a','cycle9':'b','wavedash':'c'}),\
             patch.object(R,'_process_round',side_effect=fake_process):
            with self.assertRaisesRegex(RuntimeError,'did not complete'):
                R.training(rounds=1)
        _,state,_=R.verify_journal()
        self.assertEqual(state['status'],'error')
        self.assertEqual(state['completed_rounds'],0)
        self.assertFalse((exp/'extended_rotation.lock').exists())

class PatchTests(unittest.TestCase):
    def test_patch_against_real_prior_version(self):
        # The distribution includes only our patcher. This anchor fixture mirrors v1's CLI.
        original='''def run(args):
    pass
# FROZEN_WORKER_SUBPROCESS_V1
# FROZEN_DLL_BUILD_GUARD_V1
foo={
    'GL_HUB_SAVE_EVERY':'4096',
    'GL_HUB_SEED':'734891',
}
def make_parser():
    p.add_argument('--games',type=int,default=4)
'''
        code=P.modify(original)
        self.assertEqual(P.modify(code),code)
        self.assertIn("'GL_HUB_SAVE_EVERY':str(args.save_every)",code)
        self.assertIn("'GL_HUB_SEED':str(args.seed)",code)
        with self.assertRaises(RuntimeError):P.modify(original.replace("'4096'","'8192'"))

    def test_patch_file_idempotent_and_backup(self):
        with tempfile.TemporaryDirectory() as t:
            src=Path(t)/'frozen_cli.py'
            src.write_text('''def run(args):
    pass
# FROZEN_WORKER_SUBPROCESS_V1
# FROZEN_DLL_BUILD_GUARD_V1
foo={
    'GL_HUB_SAVE_EVERY':'4096',
    'GL_HUB_SEED':'734891',
}
def make_parser():
    p.add_argument('--games',type=int,default=4)
''')
            backup=Path(t)/'before.bak'
            with patch.object(P,'TARGET',src),patch.object(P,'BACKUP',backup):
                P.install()
                after=src.read_bytes()
                P.install()
                self.assertEqual(src.read_bytes(),after)
                self.assertIn("'GL_HUB_SAVE_EVERY':'4096'",backup.read_text())

if __name__=='__main__':unittest.main()
