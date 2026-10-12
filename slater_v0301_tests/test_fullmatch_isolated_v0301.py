from __future__ import annotations
import sys
import types
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pytest
import slater_fullmatch_eval_v0301 as fm


class FakeMatch:
    instances = []

    def __init__(self, actions, observer, opponent, max_steps, device='cpu'):
        self.init_max_steps = max_steps
        self.max_steps = max_steps
        self.t = 0
        self.device = device
        self.previous = {}
        self._seed = 0
        self._closed = False
        self.state = SimpleNamespace()
        self.id = len(self.instances)
        self.instances.append(self)

    def reset(self, seed):
        self._seed = seed
        self.t = 0
        return (self._seed,)

    def step(self, act):
        self.t += 1
        return (self._seed,), 0., self.t >= self.max_steps, {
            'student_touches':self.t,'opponent_touches':self.t//2,
            'outcome':0, 'timeout': self.t >= self.max_steps,
        }

    def close(self): self._closed = True


def fixture_fake(monkeypatch):
    FakeMatch.instances.clear()
    monkeypatch.setattr(fm.base, 'Native1v1', FakeMatch)
    monkeypatch.setattr(fm.paired, 'RoleSwap1v1', FakeMatch)
    monkeypatch.setitem(sys.modules, 'afk_team_research',
                        types.SimpleNamespace(TeamObserver=lambda: object()))
    monkeypatch.setattr(fm, 'detailed_kickoff_signature', lambda env: str(env.inner._seed))
    monkeypatch.setattr(fm.paired, 'greedy_action', lambda *a, **k: 0)


def test_isolated_reset_recreates_engine_and_observer(monkeypatch):
    fixture_fake(monkeypatch)
    env = fm.IsolatedKickoffEnv('blue', None, None, 10)
    env.reset(321)
    first = env.inner
    env.max_steps=5
    env.step(0)
    assert first.t == 1 and env.max_steps == 5
    env.reset(654)
    assert first._closed and env.inner is not first
    assert env.t == 0 and env.max_steps == 10
    env.close()
    assert env.inner is None
    assert len(FakeMatch.instances) == 2


def test_match_repeated_isolated_and_no_persistent_state(monkeypatch):
    fixture_fake(monkeypatch)
    env=fm.IsolatedKickoffEnv('orange',None,None,11)
    a=fm.one_full_match(env,object(),5,'orange',10,0)
    b=fm.one_full_match(env,object(),5,'orange',10,0)
    assert fm.match_equal(a,b)
    assert len(FakeMatch.instances)==2
    assert FakeMatch.instances[0]._closed
    assert a['first_kickoff_signature']==b['first_kickoff_signature']
    env.close()


def test_fullmatch_aggregation_still_works():
    a=[{'goals_for':0,'goals_against':2,'goal_diff':-2,'outcome':-1,
        'touches':10,'opponent_touches':4,'overtime':False},
       {'goals_for':3,'goals_against':1,'goal_diff':2,'outcome':1,
        'touches':5,'opponent_touches':5,'overtime':False}]
    r=fm.aggregate(a)
    assert r['matches']==2 and r['win_rate']==.5 and r['avg_goal_diff']==0.


def test_validation_rejects_bad_side():
    with pytest.raises(ValueError):
        fm.IsolatedKickoffEnv('green',None,None,10)


def test_new_file_must_live_in_isolated(tmp_path):
    root=tmp_path
    (root/'data'/'isolated').mkdir(parents=True)
    with pytest.raises(ValueError):
        fm.base.check_output(root/'bad.json',root,'.json')


def test_kickoff_rebuilds_after_goal(monkeypatch):
    fixture_fake(monkeypatch)
    class FakeGoal(FakeMatch):
        def step(self, action):
            self.t += 1
            outcome = 1 if self.t == 2 and self.id == 0 else 0
            done = bool(outcome or self.t >= self.max_steps)
            return (self._seed,), 0., done, {
                'student_touches':self.t,'opponent_touches':self.t,
                'outcome':outcome, 'timeout':bool(done and not outcome),
            }
    FakeGoal.instances=FakeMatch.instances
    monkeypatch.setattr(fm.base, 'Native1v1', FakeGoal)
    env=fm.IsolatedKickoffEnv('blue',None,None,8)
    row=fm.one_full_match(env,object(),11,'blue',7,0)
    assert row['goals_for']==1 and row['decisions']==7
    assert len(FakeMatch.instances)==2
    assert FakeMatch.instances[0]._closed
    assert row['kickoffs']==2
    env.close()
