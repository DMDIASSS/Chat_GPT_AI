import sys,copy,json,shutil,time
from pathlib import Path
import argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def main():
    p=argparse.ArgumentParser(description='Reproducible small CPU acquisition/control pilot; no user weights opened')
    p.add_argument('--steps',type=int,default=500000);p.add_argument('--output',type=Path,default=ROOT/'runs/contact_reward_pilot')
    a=p.parse_args()
    if not 4096<=a.steps<=2000000:raise ValueError('Pilot step budget must be 4096..2000000')
    from duelforge.runtime import config,load,save,atomic_json,sha,actor_sha
    from duelforge.train import train
    from duelforge.acquisition_experiment import fork_stage,probe_checkpoint
    from duelforge.export import export
    from duelforge.watch import watch
    root=a.output;root.mkdir(parents=True,exist_ok=False)
    c=config();c.update(width=64,n_envs=32,device='cpu',torch_threads=1)
    c['ppo'].update(steps=64,epochs=2,batch_size=256);c['wandb']['enabled']=False
    c['auto_evaluate_every']=10**9
    parent=root/'parent';train(parent,c,minutes=2,max_updates=0)
    identity=sha(parent/'latest.pt')
    results={'scope':'Small random-model CPU matched-control sanity experiment, not the user 57M policy and not playing-strength validation.','initial_model_seed':c['seed'],'parameter_width':64,'stage':'contact_velocity_KL_controller_v4','requested_learning_steps_per_arm':a.steps,'arms':{}}
    for label in ('contact','same_drills_goal_only'):
     folder=root/label
     fork_stage(parent/'latest.pt',folder,parent/'latest.pt','contact',0)
     ck=load(folder/'latest.pt')
     if label=='same_drills_goal_only':
      ck['config']['acquisition']['contact_approach_weight']=0
      ck['config']['acquisition']['contact_first_touch_bonus']=0
      save(folder/'latest.pt',ck);atomic_json(folder/'config.json',ck['config'])
     results['arms'][label]={'initial_model_sha256':actor_sha(ck['model'])}
     results['arms'][label]['before']=probe_checkpoint(folder/'latest.pt',parent/'latest.pt',0x80001111,pairs=32,seconds=6.)
     start=time.perf_counter();steps=train(folder,minutes=90,stop_at_transitions=a.steps)
     results['arms'][label].update(learning_steps=steps,wall_seconds=time.perf_counter()-start)
     results['arms'][label]['after']=probe_checkpoint(folder/'latest.pt',parent/'latest.pt',0x80002222,pairs=32,seconds=6.)
    assert len({x['initial_model_sha256'] for x in results['arms'].values()})==1
    assert sha(parent/'latest.pt')==identity
    folder=root/'contact';before=sha(folder/'latest.pt')
    out=export(folder)
    results['export']=json.loads((out/'identity.json').read_text())
    watch(folder,seconds=1,scene=-2,headless=True,frames=15)
    assert sha(folder/'latest.pt')==before
    results['parent_unchanged']=True
    atomic_json(root/'pilot_results.json',results)
    for label,r in results['arms'].items():
     print('PILOT_RESULT',label,r['learning_steps'],r['before']['success_rate'],r['after']['success_rate'],r['after']['median_contact_seconds'])
    print('EXPORT_WATCH_PASS',out)

if __name__=='__main__':main()
