from slater_research.replay_engine import split_replay

def test_split_reproducible():
    h='fa12cc07'+'0'*56
    assert split_replay(h)==split_replay(h)
    assert split_replay('0'*64)=='train'
