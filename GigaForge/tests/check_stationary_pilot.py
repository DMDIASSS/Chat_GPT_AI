"""Actual native updates, bounded pause/resume, cached evaluation, and exact export. No strength claim."""
from pathlib import Path
from types import SimpleNamespace
import sys,tempfile,torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import stationary_pilot as p
from stationary_jobs import PilotPaused

def main():
    torch.set_num_threads(1);m=p.runtime();binary=m.binary()
    with tempfile.TemporaryDirectory(prefix='stationary_integration_') as temp:
        m.ROOT=Path(temp)/'GigaForge';m.ROOT.mkdir();m.binary=lambda:binary
        m.write(m.ROOT/'active_research.json',dict(run='research04'))
        old=m.ROOT/'runs/research04/STOP';old.parent.mkdir(parents=True);old.write_text('keep paused')
        protected={str(f):f.read_bytes() for f in (old,m.ROOT/'active_research.json')}
        args=SimpleNamespace(device='cpu',decisions=1024,rollout=512,games=4,warmup=1,pairs=1,seconds=.2,minutes=5.,no_resource_guard=True)
        original_launch=p.launch;count=0
        def interrupt_second_arm(*a,**kw):
            nonlocal count
            count+=1
            if count==2:raise PilotPaused('Synthetic user pause between arms')
            return original_launch(*a,**kw)
        p.launch=interrupt_second_arm
        try:state=p.train(m,'pilot_fixture',args)
        finally:p.launch=original_launch
        assert state['status']=='paused' and list(state['arms'])==['goal_only']
        first=state['arms']['goal_only'];policy_sha=m.sha(Path(first['pin'])/'POLICY.lt')
        state=p.train(m,'pilot_fixture',args);assert state['status']=='pilot_complete'
        assert m.sha(Path(state['arms']['goal_only']['pin'])/'POLICY.lt')==policy_sha
        for arm in p.ARMS:
            checks=state['arms'][arm]['checks']
            assert checks['logged_collected']==checks['logged_used']==1024
            assert checks['actor_steps']>0 and checks['frozen_trunk_verified']
        assert all(Path(f).read_bytes()==b for f,b in protected.items())
        study=m.folder('pilot_fixture');actor=p.actor(m,study)
        from nova.giga_teachers import GigaNetwork
        network=GigaNetwork(Path(state['arms'][state['selected_preview']]['pin']),'chronos')
        x=torch.linspace(-1,1,4*228).reshape(4,228)
        with torch.inference_mode():torch.testing.assert_close(torch.jit.load(str(actor))(x),network(x[:,:225]),rtol=0,atol=0)
        completed=list((study/'evaluation_jobs').glob('*/completed.json'));before={str(f):m.sha(f) for f in completed}
        state=p.train(m,'pilot_fixture',args)
        assert state['status']=='pilot_complete' and all(m.sha(f)==h for f,h in before.items())
        # An invocation cannot clear the pilot STOP while another invocation holds its lock.
        from filelock import Timeout
        stop=study/'STOP';stop.touch()
        with p.study_lock(m,'pilot_fixture'):
            try:p.train(m,'pilot_fixture',args)
            except Timeout:pass
            else:raise AssertionError('Concurrent trainer was accepted')
            assert stop.exists()
        print('STATIONARY_NATIVE_TRAIN_PAUSE_RESUME_CACHE_FROZEN_TRUNK_EXPORT_AND_ISOLATION_PASS',flush=True)
if __name__=='__main__':main()
