import numpy as np
import pytest
import torch
from nova.triad_selector import Gate
from nova.triad import FairSelector,TriadClock


def gate(logits):
    obj=Gate.__new__(Gate);obj.body='breakout';obj.names=('chronos','galactus','ripple');obj.n=3;obj.reset()
    obj.network=lambda x:torch.tensor([logits],dtype=torch.float32)
    return obj


def test_reported_probabilities_are_learned_free_choices_and_stay_cached_during_hold():
    obj=gate([0.,1.,0.]);x=np.zeros(225,np.float32)
    assert obj.choose(x)==1
    before=dict(obj.status()['last_free_choice_probabilities'])
    assert before['galactus']==pytest.approx(.57611688)
    obj.network=lambda x:torch.tensor([[10.,0.,0.]])
    for _ in range(7):
        assert obj.choose(x)==1
        assert obj.status()['last_free_choice_probabilities']==before
    assert obj.choose(x)==0 and obj.status()['last_free_choice_probabilities']['chronos']>.999
    obj.reset();assert obj.status()['last_free_choice_probabilities'] is None


def test_learned_clock_never_labels_unused_fair_scheduler_probabilities_as_its_choice():
    obj=TriadClock.__new__(TriadClock);obj.selector=FairSelector()
    for _ in range(834):obj.selector.record(0)
    obj.gate=gate([1.,0.,0.]);obj.gate.choose(np.zeros(225,np.float32))
    status=obj.status()
    assert status['mode']=='learned' and status['last']=='chronos'
    assert status['selections']['chronos']==834
    assert 'next_probabilities' not in status and 'waiting_decisions' not in status
    assert status['last_free_choice_probabilities']['chronos']>.57
    obj.gate=None;status=obj.status()
    assert status['mode']=='random' and status['next_probabilities']['chronos']<.001
