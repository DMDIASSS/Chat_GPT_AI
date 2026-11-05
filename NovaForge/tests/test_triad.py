import numpy as np
import pytest
from nova.triad import FairSelector


def test_waiting_and_repetition_change_probability_without_excluding_experts():
    selector=FairSelector();np.testing.assert_allclose(selector.probabilities(),[1/3]*3)
    selector.ages[2]=40
    assert selector.probabilities()[2]>selector.probabilities()[0]
    selector.ages[:]=0;selector.recent.extend([0]*30);selector.last=0
    probabilities=selector.probabilities()
    assert 0<probabilities[0]<probabilities[1] and probabilities.sum()==pytest.approx(1)


def test_seeded_selector_balances_experts_and_limits_repeats_over_long_sample():
    a=FairSelector(271);b=FairSelector(271);sequence=[]
    for _ in range(3000):
        value=a.choose();assert value==b.choose();sequence.append(value)
        assert np.isfinite(a.probabilities()).all() and (a.probabilities()>0).all()
    fractions=np.bincount(sequence,minlength=3)/len(sequence)
    assert np.min(fractions)>.28 and np.max(fractions)<.38
    assert np.mean(np.array(sequence[1:])==np.array(sequence[:-1]))<.25


def test_actual_triad_changes_experts_once_per_eight_ticks_and_emits_valid_controls(cfg,request):
    if not request.config.getoption('--teachers'):pytest.skip('Requires all three frozen models')
    from nova.triad import TriadPolicy
    from nova.environment import ArenaEnv
    env=ArenaEnv(cfg,opponent='scorer',scenario='kickoff')
    try:
        env.reset(seed=271);policy=TriadPolicy();policy.reset(env.state,env.agent,np.random.default_rng(271))
        for _ in range(12):
            controls=policy.controls_for_ticks(env.state)
            assert controls.shape==(4,8) and np.isfinite(controls).all() and abs(controls).max()<=1
            env.step_controls(controls)
        assert sum(policy.clock.selector.counts)==6 and (policy.clock.selector.counts>0).all()
    finally:env.close()
