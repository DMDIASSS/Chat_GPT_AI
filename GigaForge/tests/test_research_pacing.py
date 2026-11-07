import copy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import research as r
import research_pacing as p
from test_research_eval import fake_runner
import pytest


def state(n=30):return dict(trial=n,results=[dict(decision='uncertain') for _ in range(n)])


def test_no_upgrade_without_evidence(tmp_path):
 m=fake_runner(tmp_path);s=state(2)
 assert p.configure(m,tmp_path,s,r.DEFAULT)==r.DEFAULT and 'pacing' not in s


def test_pacing_keeps_objectives_and_checkpoints_but_is_persistent_and_sealed(tmp_path):
 m=fake_runner(tmp_path);m.write(tmp_path/'lab.json',r.DEFAULT)
 m.write(tmp_path/'evaluations/lab_0.json',dict(invocation_wall_seconds=300))
 metric=tmp_path/'branches/chronos/control/abc/metrics.jsonl';metric.parent.mkdir(parents=True);metric.write_text('{"Collection Time":10,"Consumption Time":20}\n')
 s=state();effective=p.configure(m,tmp_path,s,r.DEFAULT)
 assert effective['block']==262144 and effective['max_branch_decisions']==2097152
 assert all(effective[k]==r.DEFAULT[k] for k in ('arms','minimum_delta','confirmation_pairs','goal_rate_tolerance','seconds'))
 assert m.read(tmp_path/'lab.json')==r.DEFAULT
 assert p.configure(m,tmp_path,s,r.DEFAULT)==effective
 policy=tmp_path/s['pacing']['path'];m.write(policy,dict(tampered=True))
 with pytest.raises(ValueError,match='configuration changed'):p.configure(m,tmp_path,s,r.DEFAULT)


def test_focus_preserves_control_and_regular_exploration():
 s=state();s['arms']={'chronos/attack':dict(n=3,score=.1),'chronos/possession':dict(n=4,score=.5)}
 chosen=[]
 for trial in (32,34,36,38):
  s['trial']=trial;chosen.append(p.choose(s,'chronos',r.ARMS,lambda *a:dict(name='exploration'))['name'])
 assert chosen==['control','possession','control','exploration']
