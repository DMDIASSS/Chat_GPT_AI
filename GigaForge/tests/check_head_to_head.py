"""Real frozen native H2H, exact counts, resume and export conversion. No skill claim."""
from pathlib import Path
import importlib.util,sys,tempfile,shutil,torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('h2h_runner',ROOT/'run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
import head_to_head as h,trial_watch

def main():
 torch.set_num_threads(1)
 rows=[dict(seed=710000000+p,side=s,opponent='original_chronos',seconds=100.,goals_for=1,goals_against=0,outcome=1) for p in range(100) for s in (0,1)]
 h.validate(rows,100,710000000,100.,'chronos');result=h.summary(rows)
 assert result['games']==200 and result['wins']==200 and result['score_interval_95'][0]>.5
 for bad in (rows[:-1],rows[:-1]+[rows[0]], [dict(r,seconds=60.) for r in rows]):
  try:h.validate(bad,100,710000000,100.,'chronos')
  except ValueError:pass
  else:raise AssertionError('Invalid rounds accepted')
 tied=[dict(r,goals_for=0,outcome=0) for r in rows];assert h.summary(tied)['draws']==200 and h.summary(tied)['verdict']=='uncertain'
 base=m.create('native_check','cpu')
 with tempfile.TemporaryDirectory(prefix='h2h_check_') as temp:
  run=Path(temp)/'research02';run.mkdir()
  for name in ('config.json','state.json'):shutil.copy2(base/name,run/name)
  for family in ('chronos','galactus'):m.write(run/'champions'/f'{family}.json',dict(path=str(base/'parents'/family)))
  source=run/'branches/chronos/test/checkpoints/1048576';source.mkdir(parents=True)
  for name in trial_watch.FILES:shutil.copy2(base/'parents/chronos'/name,source/name)
  files=trial_watch.identity(m,source)
  m.write(run/'lab_state.json',dict(results=[dict(trial=38,family='chronos',candidate=str(source.relative_to(run))),dict(trial=62,family='chronos',candidate='branches/missing')]))
  for trial,delta,ident in ((38,.0293,files),(62,.0469,{n:'0'*64 for n in trial_watch.FILES})):
   records=[dict(opponent='fixture',seed=710620000+trial,side=s,goals_for=0,goals_against=0,outcome=0,seconds=60.) for s in (0,1)]
   m.write(run/'evaluations'/f'lab_{trial:05d}_chronos_confirmation.json',dict(trials=records,split='confirmation',statistics=dict(delta=delta)))
   m.write(run/'evaluations/jobs'/f'{trial}.json',dict(identity=dict(models=[dict(family='chronos',hitbox='breakout',files=ident)]),result=dict(trials=records)))
  print('SYNTHETIC_PUBLIC_ACTOR_FIXTURE_NOT_USERS_TRAINED_MODEL',flush=True)
  selection=h.select(m,run);assert selection['trial']==38 and selection['attempts'][0]['lookup']=='missing'
  # Training STOP and champion pointers must remain byte-for-byte unchanged.
  (run/'STOP').touch();before={str(p):m.sha(p) for p in [run/'STOP',run/'champions/chronos.json',run/'champions/galactus.json',run/'state.json',run/'lab_state.json']}
  m.folder=lambda name:run
  state=h.run(m,'research02','cpu',rounds=8,seconds=.2,batch_pairs=2,seed=1580000000)
  assert state['status']=='complete' and state['summary']['games']==8 and len(state['chunks'])==2
  assert all(state['by_side'][s]['games']==4 for s in ('blue','orange')) and not state['automatic_promotion']
  assert all(m.sha(p)==sha for p,sha in before.items())
  batch_hashes={c['path']:c['sha256'] for c in state['chunks']}
  state=h.run(m,'research02','cpu',rounds=8,seconds=.2,batch_pairs=2,seed=1580000000)
  assert len(state['games'])==8 and {c['path']:c['sha256'] for c in state['chunks']}==batch_hashes
  # Export-only recovery must load the same logits through the native binary.
  pin=Path(selection['actor']).parent
  for name in trial_watch.FILES:(pin/name).unlink()
  target=run/'export_only';target.mkdir();settings=m.read(run/'config.json');settings['device']='cpu'
  h.native_actor(m,run,selection,settings,target)
  full=h.run(m,'research02','cpu',rounds=2,seconds=100.,batch_pairs=1,seed=1581000000)
  assert full['status']=='complete' and full['summary']['games']==2
  h.validate(full['games'],1,1581000000,100.,'chronos')
  assert all(m.sha(p)==sha for p,sha in before.items())
 print('NATIVE_H2H_COUNTS_SELECTION_RESUME_PAUSED_STATE_AND_EXPORT_PARITY_PASS',flush=True)

if __name__=='__main__':main()
