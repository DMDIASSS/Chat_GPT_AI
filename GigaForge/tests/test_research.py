import copy,random,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
nova=Path(__file__).resolve().parents[2]/'novaforge'
if not nova.exists():nova=Path(__file__).resolve().parents[2]/'NovaForge'
sys.path.insert(0,str(nova))
import research as r


def test_reward_population_explores_and_preserves_fixed_control():
 state=dict(arms={},population={'chronos':copy.deepcopy(r.ARMS)},trial=8)
 assert r.choose_arm(state,'chronos',r.ARMS)['name']=='control'
 for arm in r.ARMS:state['arms']['chronos/'+arm['name']]=dict(n=3,score=.2 if arm['name']=='attack' else -.2)
 before=copy.deepcopy(state['population']['chronos'][0]);r.evolve(state,r.DEFAULT)
 assert len(state['population']['chronos'])==4 and state['population']['chronos'][0]==before
 child=next(a for a in state['population']['chronos'] if a['name'].startswith('evolved'))
 assert all(0<=x<=.6 for x in child['potential']) and 5e-7<=child['lr']<=5e-6


def test_prioritizes_hard_opponents_while_retaining_easy_ones():
 entries=[dict(name='easy'),dict(name='hard')];payoff={'easy':dict(points=99,games=100),'hard':dict(points=1,games=100)}
 rng=random.Random(271);selected=[r.choose_opponent(entries,payoff,rng)['name'] for _ in range(3000)]
 assert selected.count('hard')>selected.count('easy')*4 and selected.count('easy')>100


def test_uncertain_and_bad_goal_difference_do_not_promote():
 stats=dict(lower=-.1,upper=.2,delta=.05,by_opponent={'a':.05,'b':.05})
 result=dict(statistics=stats,summary=dict(goals_for=4,goals_against=6),baseline_summary=dict(goals_for=5,goals_against=5))
 assert r.decision(result,r.DEFAULT)=='uncertain'
 stats.update(lower=.01);assert r.decision(result,r.DEFAULT)=='uncertain'
 result['summary']=dict(goals_for=7,goals_against=5);assert r.decision(result,r.DEFAULT)=='improved'
 stats.update(lower=-.4,upper=-.01,delta=-.2);assert r.decision(result,r.DEFAULT)=='regressed'


def test_paired_identical_models_are_never_declared_improved():
 rows=[dict(opponent=o,seed=i,side=s,outcome=0,goals_for=1,goals_against=1) for o in ('c','g') for i in range(8) for s in (0,1)]
 stat=r.stats(rows,copy.deepcopy(rows));assert stat['delta']==0 and stat['lower']<0<stat['upper']


def test_population_never_changes_goal_reward_or_exports():
 for arm in r.ARMS:
  assert set(arm)=={'name','potential','lr','anchor','freeze_shared'}
  assert len(arm['potential'])==5
