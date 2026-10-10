import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import hub_core
import hub_cpp_patch
import hub_tournament

class TestHub(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory()
    self.root=pathlib.Path(self.tmp.name)
    self.old=hub_core.EXPERIMENTS
    hub_core.EXPERIMENTS=self.root/'experiments'
 def tearDown(self):
    hub_core.EXPERIMENTS=self.old
    self.tmp.cleanup()
 def test_new_isolated_and_no_overwrite(self):
    p=hub_core.new_experiment('Defense Test','Defense Under Pressure 1v2')
    self.assertTrue((p/'checkpoints').is_dir())
    self.assertEqual(hub_core.read_json(p/'experiment.json')['settings']['orange'],2)
    with self.assertRaises(hub_core.HubError):hub_core.new_experiment('Defense Test','Defense Under Pressure 1v2')
 def test_seed_copy_verified_and_incomplete_rejected(self):
    seed=self.root/'4562496';seed.mkdir()
    files=['POLICY.lt','POLICY_OPTIM.lt','SHARED_HEAD.lt','SHARED_HEAD_OPTIM.lt','CRITIC.lt','CRITIC_OPTIM.lt','RUNNING_STATS.json']
    for f in files:(seed/f).write_bytes(f.encode())
    p=hub_core.new_experiment('clone','Balanced 1v1',seed)
    for f in files:self.assertEqual((p/'checkpoints/4562496'/f).read_bytes(),(seed/f).read_bytes())
    self.assertIn('source_read_only',hub_core.read_json(p/'experiment.json')['seed_checkpoint'])
    with self.assertRaises(hub_core.HubError):hub_core.new_experiment('illegal_1v2_seed','Defense Under Pressure 1v2',seed)
    self.assertFalse(hub_core.exp_path('illegal_1v2_seed').exists())
    (seed/'POLICY.lt').unlink()
    with self.assertRaises(hub_core.HubError):hub_core.new_experiment('badclone','Balanced 1v1',seed)
    self.assertFalse((hub_core.exp_path('badclone')).exists())
 def test_safe_stop_flag(self):
    p=hub_core.new_experiment('a','Balanced 1v1')
    self.assertTrue(hub_core.request_safe_stop('a').is_file())
 def test_preset_validity(self):
    for name,cfg in hub_core.PRESETS.items():
      self.assertGreaterEqual(cfg['blue'],1);self.assertLessEqual(cfg['orange'],3)
      self.assertTrue(cfg['mode'] in {'balanced','shooting','defense','air','power','recovery'})
 def test_plan_no_fake_scores(self):
    # redirect plan output to temp without writing in actual user folder
    old=hub_core.HERE;hub_core.HERE=self.root
    try:
        p=hub_core.make_plan(variations=12)
        self.assertEqual(len(p),12)
        self.assertTrue((self.root/'reports/evolution_plan.json').exists())
        self.assertTrue(all(x['status']=='planned' for x in p))
    finally:hub_core.HERE=old
 def test_pairing_and_standings(self):
    p=hub_tournament.pairings(['alpha','beta','gamma','delta'],rounds=3)
    self.assertEqual(len(p),6)
    for n in range(1,4):
      r=[x for x in p if x['round']==n]
      names=[q for x in r for q in [x['a'],x['b']]]
      self.assertEqual(len(names),len(set(names)))
    f=self.root/'results.csv';hub_tournament.save_schedule(f,['alpha','beta'])
    text=f.read_text().replace(',,,' ,',,,')
    with f.open() as infile:
        rows=list(__import__('csv').DictReader(infile))
    self.assertTrue(rows)
    rows[0]['wins_a']='6';rows[0]['wins_b']='4';rows[0]['draws']='0';rows[0]['episodes']='10'
    with f.open('w',newline='') as out:
      import csv
      wr=csv.DictWriter(out,fieldnames=rows[0]);wr.writeheader();wr.writerows(rows)
    standings=hub_tournament.standings_from_csv(f)
    self.assertEqual(standings[0]['score_pct'],60.0)
 def test_env_vars_and_history(self):
    cfg=hub_core.get_preset('Teamplay 2v2')
    env=hub_core.environment_for(cfg,self.root/'env')
    self.assertEqual(env['GL_HUB_BLUE'],'2')
    self.assertEqual(env['GL_HUB_ORANGE'],'2')
    self.assertEqual(env['GL_HUB_HISTORY'],'1')
    self.assertEqual(env['GL_HUB_HEADLESS'],'1')
 def test_log_parser_no_fabrication(self):
    folder=self.root/'log_trial';(folder/'reports').mkdir(parents=True)
    self.assertIsNone(hub_core.parse_metrics(folder)['speed'])
    (folder/'reports/training.log').write_text('Overall Steps/Second: 23,965.3\nTotal Timesteps: 4,562,496\nTotal Iterations: 869\n')
    data=hub_core.parse_metrics(folder)
    self.assertEqual(data['speed'],'23,965.3')
    self.assertEqual(data['total_timesteps'],'4,562,496')
 def test_patched_cpp_verification_accepts_utf8_bom(self):
    old=hub_core.PROJECT
    hub_core.PROJECT=self.root
    try:
        filenames=['upstream/src/ExampleMain.cpp','upstream/GigaLearnCPP/src/public/GigaLearnCPP/Learner.cpp']
        for name in filenames:
            f=self.root/name;f.parent.mkdir(parents=True,exist_ok=True)
            f.write_text('// AFK_RESEARCH_HUB_PATCH_V1\n',encoding='utf-8-sig')
        hub_core._require_patch()
    finally:
        hub_core.PROJECT=old
 def test_cpp_patch_fail_closed(self):
    with self.assertRaises(RuntimeError):hub_cpp_patch.patch_main('int main() { return 0; }')
    with self.assertRaises(RuntimeError):hub_cpp_patch.patch_learner('nothing')
 def test_cpp_representative_snippet(self):
    main='''#include <GigaLearnCPP/Learner.h>\nusing namespace GGL; // GigaLearn\nusing namespace RLGC; // RLGymCPP\nstd::vector<WeightedReward> rewards = {\n{ new GoalReward(), 150 }\n};\nint playersPerTeam = 1;\nfor (int i = 0; i < playersPerTeam; i++) { arena->AddCar(Team::BLUE); arena->AddCar(Team::ORANGE); }\nresult.stateSetter = new KickoffState();\ncfg.deviceType = LearnerDeviceType::GPU_CUDA;\ncfg.numGames = 32;\nint tsPerItr = 5'000;\ncfg.ppo.miniBatchSize = 5'000;\ncfg.ppo.epochs = 1;\ncfg.ppo.entropyScale = 0.035f;\ncfg.ppo.policyLR = 1.5e-4;\ncfg.ppo.criticLR = 1.5e-4;\ncfg.sendMetrics = true;\n'''
    patched,changed=hub_cpp_patch.patch_main(main)
    self.assertTrue(changed)
    self.assertIn('GL_HUB_ORANGE',patched)
    self.assertIn('HubAirControlReward',patched)
    self.assertIn('cfg.sendMetrics = false',patched)
    p,c=hub_cpp_patch.patch_main(patched)
    self.assertFalse(c);self.assertEqual(p,patched)
 def test_learner_patch_inserts_only_in_start(self):
    a='''void GGL::Learner::StartTransferLearn() { if (saveQueued) { exit(0); } }\nvoid GGL::Learner::Start() {\n bool saveQueued;\n std::thread keyPressThread;\n StartQuitKeyThread(saveQueued, keyPressThread);\n if (saveQueued) { Save(); exit(0); }\n}'''
    b,changed=hub_cpp_patch.patch_learner(a)
    self.assertTrue(changed)
    self.assertEqual(b.count('request_safe_stop.flag'),2)
    self.assertIn('GL_HUB_HEADLESS',b)
    self.assertTrue(b.index('request_safe_stop.flag')>b.index('void GGL::Learner::Start()'))

if __name__=='__main__':unittest.main()
