import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys

HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE))
import hub_eval
import hub_eval_cpp
from hub_core import HubError

class TestGameplayEval(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.root=Path(self.tmp.name)
    self.exp=self.root/'experiments';self.exp.mkdir()
    self.folder=self.root/'results'
    self.fakebin=self.root/'GigaLearnEval.exe'
    self.fakebin.write_text('fake',encoding='utf8')
    self.saved=(hub_eval.EXPERIMENTS,hub_eval.EVAL_BINARY,hub_eval.REPORT_ROOT,hub_eval.check_runtime)
    hub_eval.EXPERIMENTS=self.exp
    hub_eval.EVAL_BINARY=self.fakebin
    hub_eval.REPORT_ROOT=self.folder
    hub_eval.check_runtime=lambda:{'meshes':str(self.root)}
    self.addCleanup(self.reset)

 def reset(self):
    hub_eval.EXPERIMENTS,hub_eval.EVAL_BINARY,hub_eval.REPORT_ROOT,hub_eval.check_runtime=self.saved

 def make(self,name,teams=(1,1),step=2398176):
    p=self.exp/name;cp=p/'checkpoints'/str(step);cp.mkdir(parents=True)
    (cp/'POLICY.lt').write_bytes(b'policy-'+name.encode())
    (cp/'SHARED_HEAD.lt').write_bytes(b'shared')
    (cp/'RUNNING_STATS.json').write_text('{}')
    (p/'experiment.json').write_text(json.dumps({'settings':{'blue':teams[0],'orange':teams[1]},'preset':'test'}))
    return p,cp

 def test_only_complete_one_v_one(self):
    self.make('base');self.make('defense',teams=(1,2));self.make('shoot')
    self.assertEqual([x['name'] for x in hub_eval.candidates()],['base','shoot'])

 def test_reject_duplicate_and_nonexistent(self):
    self.make('base');self.make('shoot')
    with self.assertRaises(HubError):hub_eval._selected(['base','base'])
    with self.assertRaises(HubError):hub_eval._selected(['base','bad'])

 def test_reject_active_experiment(self):
    p,_=self.make('base');self.make('shoot')
    (p/'running.json').write_text('{"pid":123}')
    with patch.object(hub_eval,'is_alive',return_value=True):
        with self.assertRaisesRegex(HubError,'currently training'):
            hub_eval._selected(['base','shoot'])

 def test_round_robin_writes_read_only_reports(self):
    names=['base','shoot','defense']
    before={}
    for n in names:
        _,cp=self.make(n)
        before[n]=(cp/'POLICY.lt').read_bytes()
    fake={'kind':'gigalearn_head_to_head_first_goal_v1','wins_a':3,'wins_b':1,'draws':0,
          'score_a':0.75,'a_shot_events':4,'b_shot_events':2,'a_save_events':1,'b_save_events':0}
    def simulate(cmd,**kwargs):
        out=Path(cmd[cmd.index('--out')+1]);out.write_text(json.dumps(fake))
        kwargs['stdout'].write(b'RUN OK\n')
        return subprocess.CompletedProcess(cmd,0)
    with patch.object(hub_eval.subprocess,'run',side_effect=simulate):
        report=hub_eval.run(names,pairs=2,decisions=180)
    self.assertTrue(report.is_file())
    data=json.loads(report.read_text())
    self.assertEqual(len(data['pairings']),3)
    self.assertEqual(data['standings']['base']['games'],8)
    self.assertIn('shoot',hub_eval.show_summary(report))
    for n in names:
        self.assertEqual(before[n],(self.exp/n/'checkpoints'/'2398176'/'POLICY.lt').read_bytes())

 def test_failure_preserves_partial_report_without_promoting(self):
    self.make('base');self.make('shoot')
    with patch.object(hub_eval.subprocess,'run',return_value=subprocess.CompletedProcess([],5)):
        with self.assertRaises(HubError):hub_eval.run(['base','shoot'],pairs=1,decisions=180)
    self.assertEqual(len(list(self.folder.glob('*/FAILED.txt'))),1)

 def test_ui_installer_preserves_unrelated_lines(self):
    import INSTALL_GAMEPLAY_EVAL as ui
    app=self.root/'hub_app.py';app.write_text('before\n'+ui_marker+'\nafter\n')
    old=ui.APP
    try:
        ui.APP=app
        self.assertIn('installed',ui.install().lower())
        self.assertIn('install_evaluation_tab(self)',app.read_text())
        self.assertIn('already installed',ui.install().lower())
        self.assertIn('before\n',app.read_text())
    finally:ui.APP=old

 def test_cpp_patch_repeat_no_double_main(self):
    src=self.root/'upstream';(src/'src').mkdir(parents=True)
    (src/'src'/'ExampleMain.cpp').write_text('int main(){}')
    cmake=src/'CMakeLists.txt';cmake.write_text('file(GLOB_RECURSE FILES_SRC "src/*.cpp")\nadd_executable(GigaLearnBot ${FILES_SRC})\n')
    saved=hub_eval_cpp.SRC,hub_eval_cpp.CPP_TARGET,hub_eval_cpp.CMAKE
    try:
        hub_eval_cpp.SRC=src;hub_eval_cpp.CPP_TARGET=src/'src/HubEvaluate.cpp';hub_eval_cpp.CMAKE=cmake
        self.assertTrue(hub_eval_cpp.patch_source()['cmake_patched'])
        self.assertFalse(hub_eval_cpp.patch_source()['cmake_patched'])
        text=cmake.read_text()
        self.assertEqual(text.count('add_executable(GigaLearnEval'),1)
        self.assertIn('EXCLUDE REGEX',text)
        self.assertIn('add_executable(GigaLearnBot',text)
    finally:hub_eval_cpp.SRC,hub_eval_cpp.CPP_TARGET,hub_eval_cpp.CMAKE=saved

ui_marker='self.create_overview();self.create_experiments();self.create_evolution();self.create_replays();self.create_bridge();self.create_logs()'

if __name__=='__main__':unittest.main()
