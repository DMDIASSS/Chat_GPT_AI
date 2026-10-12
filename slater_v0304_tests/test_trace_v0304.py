import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import slater_determinism_trace_v0304 as m


def fake():
    r={k:(0 if k in ('student_action','student_touches','opponent_touches','outcome') else 'same') for k in m.FIELDS}
    return {'side':'blue','mode':'greedy','match_seed':123,'start_state':'start','start_obs':'obs','records':[{'step':1,**r}]}


def test_equal_records_no_difference():
    x=fake();assert m.first_divergence(x,x) is None
    assert 'reproducible' in m.classify_divergence(None)


def test_earliest_physics_divergence():
    x=fake(); y=fake();y['records'][0]['after_state']='other'
    d=m.first_divergence(x,y)
    assert d['step']==1 and d['first_unmatched_field']=='after_state'
    assert 'RocketSim' in m.classify_divergence(d)


def test_opponent_command_diagnostic():
    x=fake(); y=fake();y['records'][0]['opponent_command']='different'
    d=m.first_divergence(x,y)
    assert 'opponent' in m.classify_divergence(d)


def test_initial_mismatch_and_length():
    x=fake(); y=fake();y['start_state']='different'
    assert m.first_divergence(x,y)['stage']=='initial'
    y=fake(); y['records'].append(dict(y['records'][0],step=2))
    assert m.first_divergence(x,y)['stage']=='length'


def test_hash_has_shape_and_content():
    import numpy as np
    assert m.hash_numpy(np.ones((2,2))) != m.hash_numpy(np.ones((4,1)))
    assert m.hash_numpy([np.ones((2,)),np.ones((2,))]) == m.hash_numpy([np.ones((2,)),np.ones((2,))])


def test_args_rejected():
    with pytest.raises(ValueError):m.child_command(Path('trace.py'),'yellow','greedy',123,30)
    cmd=m.child_command(Path('trace.py'),'blue','greedy',123,30)
    assert '--child' in cmd and '--seed' in cmd
