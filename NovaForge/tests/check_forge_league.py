"""Actual native networks, optimizer resume, pilot, new league, reports, exports.

Tiny budgets verify mechanics of the system; they are not strength experiments.
"""
from pathlib import Path
import json
import shutil
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import torch

from nova import forge_league as league
from nova.forge_league import read
from nova.forge_models import contract
from nova.core import ROOT,atomic_json,check_model,sha256


def main():
    torch.set_num_threads(1)
    with tempfile.TemporaryDirectory() as temp:
        league.PROJECT=Path(temp)/'forgeleague'
        cfg=read(ROOT/'configs/forge_league.json')
        cfg.update(match_seconds=.2,warmup_rollouts=1,checkpoint_decisions=8,pilot_decisions=16,
            specialist_decisions=16,block_decisions=16)
        cfg['ppo'].update(n_steps=8,batch_size=8,n_epochs=1)
        cfg['evaluation'].update(pairs=1,confirmation_pairs=1,seconds=.2,test_pairs=1,test_seconds=.2)
        config=Path(temp)/'config.json';atomic_json(config,cfg)
        run=league.create('native_ci',config)
        initial={f:sha256(league.champion(run,f)) for f in league.FAMILIES}
        league.run('native_ci',wandb='off',max_tasks=1)
        state=read(run/'state.json');assert state['total_decisions']==16 and len(state['done'])==1
        full=run/'tasks/pilot_chronos_control/checkpoints/000000000016.zip'
        model=league.ChronosPPO.load(full,device='cpu')
        assert model.num_timesteps==16 and model.chronos_updates==2 and len(model.policy.optimizer.state)>0
        del model
        league.run('native_ci',wandb='off',max_tasks=3)
        # Critical boundary: queue is empty but the pilot has not been judged.
        assert read(run/'state.json')['phase']=='pilot'
        league.run('native_ci',wandb='off',once=True)
        state=read(run/'state.json');assert state['phase']=='league' and state['cycle']==1
        assert state['selected_critic']=={'chronos':False,'galactus':False}
        assert all(sha256(league.champion(run,f))==initial[f] for f in league.FAMILIES)
        # Resume the actual optimizer into a main block, not a fresh model.
        league.run('native_ci',wandb='off',once=True)
        state=read(run/'state.json');assert state['cycle']==2 and len(state['history'])==2
        assert state['total_decisions']==128
        p=read(run/'tasks/cycle0001_chronos/progress.json')
        full=run/'tasks/cycle0001_chronos'/p['checkpoint'];model=league.ChronosPPO.load(full,device='cpu')
        assert model.num_timesteps==32 and model.chronos_updates==4
        assert all(sha256(league.champion(run,f))==initial[f] for f in league.FAMILIES)
        del model
        from nova.forge_export import export_actor_bundle
        for family in league.FAMILIES:
            folder=export_actor_bundle(league.champion(run,family),Path(temp)/'exports')
            import subprocess
            result=subprocess.run([sys.executable,'run_forge.py','--diagnose'],cwd=folder,capture_output=True,text=True)
            assert result.returncode==0,(result.stdout,result.stderr)
            assert sha256(folder/'actor.lt')==sha256(folder/'actor.pt')==initial[family]
            check_model(folder/'actor.lt',contract(family,cfg.get('hitboxes',{}).get(family,'octane')))
        with __import__('zipfile').ZipFile(league.report('native_ci')) as z:
            assert 'state.json' in z.namelist() and not any(n.endswith(('.lt','.pt','.zip')) for n in z.namelist())
        forked=league.fork('native_ci','fresh_from_retained',config)
        assert all(sha256(league.champion(forked,f))==initial[f] for f in league.FAMILIES)
        assert read(forked/'state.json')['total_decisions']==0
        assert all(sha256(league.champion(run,f))==initial[f] for f in league.FAMILIES)
        print('FORGE_NATIVE_PILOT_OPTIMIZER_RESUME_FROZEN_LEAGUE_REPORT_EXPORT_PASS')


if __name__=='__main__':main()
