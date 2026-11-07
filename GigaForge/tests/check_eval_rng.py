"""Identical actors must agree over full matches, including demo respawns."""
from pathlib import Path
import importlib.util,json,sys,tempfile,torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('rng_runner',ROOT/'run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def main():
 torch.set_num_threads(1);run=m.create('native_check','cpu');settings=m.read(run/'config.json');settings['device']='cpu'
 results=[]
 with tempfile.TemporaryDirectory(prefix='paired_rng_') as temp:
  temp=Path(temp)
  for family in ('chronos','galactus'):
   actor=m.descriptor(run/'parents'/family,family)
   panel=[dict(m.descriptor(run/'parents'/f,f),name='original_'+f) for f in ('chronos','galactus')]
   recipe=m.base_recipe(run,family,settings,mode='self');out=temp/(family+'.json')
   recipe['evaluation']=dict(candidate=actor,baseline=actor,opponents=panel,pairs=8,seconds=60,seed=410000000,output=str(out),stop_file=str(temp/'STOP'))
   m.launch(recipe,log=temp/(family+'.log'));data=m.read(out)
   assert data['evaluation_protocol']=='arena-rng-v4'
   key=lambda r:(r['opponent'],r['seed'],r['side'])
   old={key(r):r for r in data['baseline_trials']}
   mismatched=[r for r in data['trials'] if r!=old[key(r)]]
   assert not mismatched,f'{family}: identical actor comparisons diverged: {mismatched[:2]}'
   results.append(dict(family=family,games_per_actor=len(old),mismatched_pairs=0,seconds_per_game=60))
   print('NATIVE_IDENTICAL_ACTOR_FULL_MATCH_RNG_PASS',json.dumps(results[-1]),flush=True)
 print('NATIVE_PAIRED_ARENA_RNG_V4_PASS',flush=True)


if __name__=='__main__':main()
