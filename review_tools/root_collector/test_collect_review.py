from pathlib import Path
import importlib.util,json,tempfile,zipfile,hashlib,unittest
root=Path(__file__).resolve().parent
if not (root/'collect_review.py').is_file():root=root.parent
s=importlib.util.spec_from_file_location('collector',root/'collect_review.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class CollectTests(unittest.TestCase):
 def fixture(self,p):
  root=p/'Chat_GPT_AI/gigaforge';root.mkdir(parents=True)
  def put(name,data=b'fixture'):
   q=root/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data);return q
  put('run.py',b'print("fixture")\n');put('src/main.cpp');put('native/src/evaluate.h');put('native/build.json',b'{}')
  put('runs/research04/lab_state.json',b'{"status":"paused"}');put('runs/research04/STOP',b'paused')
  put('runs/research04/h2h/example/test.json',b'{}');put('runs/research04/watch_pins/trial/actor.lt.json',b'{}')
  put('runs/research04/branches/chronos/test/recipe.json',b'{}');put('runs/research04/branches/chronos/test/metrics.jsonl',b'{}\n')
  put('runs/research04/branches/chronos/test/checkpoints/1/POLICY.lt',b'private model')
  put('runs/research04/watch_pins/trial/actor.lt',b'private model');put('native/GigaForge.exe',b'not needed')
  put('.env',b'secret');put('.netrc',b'secret');put('.venv_native/secret.py',b'secret');put('assets/model.pt',b'model')
  put('vendor/GigaLearnCPP/src/private/GigaLearnCPP/PPO/PPOLearner.cpp',b'modified native optimizer')
  put('exports/research04/bot/bot.bot.toml');put('exports/research04/bot/runtime/nova/forge_models.py')
  nova=root.parent/'NovaForge/nova';nova.mkdir(parents=True);(nova/'forge_models.py').write_text('fixture')
  configs=nova.parent/'configs';configs.mkdir();(configs/'forge_league.json').write_text('{}')
  return root
 def test_selection_integrity_and_preservation(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=self.fixture(Path(tmp));before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
   archive=m.collect(root)
   with zipfile.ZipFile(archive) as z:
    names=z.namelist();manifest=json.loads(z.read('REVIEW_MANIFEST.json'))
    for f in manifest['files']:self.assertEqual(hashlib.sha256(z.read(f['path'])).hexdigest(),f['sha256'])
    self.assertIn('chat_gpt_ai/gigaforge/src/main.cpp',names)
    self.assertIn('chat_gpt_ai/NovaForge/nova/forge_models.py',names)
    self.assertIn('chat_gpt_ai/NovaForge/configs/forge_league.json',names)
    self.assertIn('chat_gpt_ai/gigaforge/vendor/GigaLearnCPP/src/private/GigaLearnCPP/PPO/PPOLearner.cpp',names)
    self.assertIn('chat_gpt_ai/gigaforge/exports/research04/bot/runtime/nova/forge_models.py',names)
    self.assertIn('chat_gpt_ai/gigaforge/runs/research04/h2h/example/test.json',names)
    self.assertFalse(any(n.endswith(('.lt','.pt','.exe')) or '.venv_native' in n or '.env' in n or '.netrc' in n for n in names))
   self.assertTrue(all(Path(p).read_bytes()==b for p,b in before.items()))
   self.assertNotEqual(archive,m.collect(root))
 def test_external_symlink_excluded(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);root=self.fixture(p);outside=p/'outside';outside.mkdir();(outside/'private.py').write_text('private')
   (root/'linked').symlink_to(outside,target_is_directory=True);(root/'secret_link.py').symlink_to(outside/'private.py')
   with zipfile.ZipFile(m.collect(root)) as z:self.assertFalse(any('linked' in n or 'secret_link' in n for n in z.namelist()))
 def test_large_file_is_reported(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=self.fixture(Path(tmp));p=root/'oversize.py';p.write_bytes(b'x'*(8*1024*1024+1))
   with zipfile.ZipFile(m.collect(root)) as z:
    d=json.loads(z.read('REVIEW_MANIFEST.json'));self.assertTrue(any(s['file'].endswith('oversize.py') for s in d['skipped']))
 def test_wrong_directory_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaises(FileNotFoundError):m.collect(tmp)
 def test_parent_layout_and_newest_runs(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=self.fixture(Path(tmp))
   for name in ('research05', 'research06', 'research010'):
    run=root/'runs'/name/'evaluations'/'eval_1500_vs_original_chronos';run.mkdir(parents=True)
    (run/'summary_1500g.json').write_text('{}')
    (root/'runs'/name/'research06_summary.json').write_text('{}')
   archive=m.collect(root.parent)
   self.assertEqual(archive.parent,root.parent/'review_uploads')
   with zipfile.ZipFile(archive) as z:
    manifest=json.loads(z.read('REVIEW_MANIFEST.json'))
    self.assertEqual(manifest['research_runs'][:3],['research010','research06','research05'])
    self.assertIn('chat_gpt_ai/gigaforge/runs/research06/evaluations/eval_1500_vs_original_chronos/summary_1500g.json', z.namelist())
    self.assertIn('chat_gpt_ai/gigaforge/runs/research06/research06_summary.json', z.namelist())
if __name__=='__main__':unittest.main()
