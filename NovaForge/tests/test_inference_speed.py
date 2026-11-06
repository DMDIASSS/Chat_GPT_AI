import json
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
import torch
from nova.inference import frozen_inference


@pytest.mark.parametrize('name',['chronos','galactus','ducky','rain','megabyte'])
def test_compiled_frozen_network_keeps_native_logits_and_actions(request,name):
    if not request.config.getoption('--teachers'):pytest.skip('Requires pinned teacher assets')
    from nova.giga_teachers import GigaNetwork
    from nova.six_experts import ExtraNetwork
    from nova.teachers import verify_teacher
    kind='giga' if name in ('chronos','galactus') else 'six'
    data=json.loads((Path(__file__).parent/'fixtures'/f'{kind}_reference.json').read_text())
    eager=GigaNetwork(verify_teacher(name),name) if kind=='giga' else ExtraNetwork(verify_teacher(name),name)
    optimized=frozen_inference(eager)
    for row in data['cases']:
        x=torch.tensor(row['reference'][name]['features'],dtype=torch.float32)[None,:]
        with torch.inference_mode():a=eager(x);b=optimized(x)
        torch.testing.assert_close(a,b,atol=3e-5,rtol=2e-5)
        assert int(a.argmax())==int(b.argmax())
        from rlgym_tools.rocket_league.misc.serialize import deserialize_game_state
        from nova.six_experts import action_mask
        state=deserialize_game_state(np.array(row['state'],np.float32))
        car=next(c for c in state.cars.values() if c.team_num==row['side'])
        mask=torch.tensor(action_mask(car,name))[None,:]
        assert int(a.masked_fill(~mask,-torch.inf).argmax())==int(b.masked_fill(~mask,-torch.inf).argmax())


def test_unused_observation_can_be_skipped_without_changing_simulation(cfg):
    from nova.environment import ArenaEnv
    from rlgym_tools.rocket_league.misc.serialize import serialize_game_state
    a=ArenaEnv(cfg,opponent='scripted',scenario='kickoff',side=0)
    b=ArenaEnv(cfg,opponent='scripted',scenario='kickoff',side=0)
    try:
        a.reset(seed=82);b.reset(seed=82);controls=np.zeros((2,8),np.float32);controls[:,0]=1
        for _ in range(16):
            x=a.step_control_ticks(controls,2);y=b.step_control_ticks(controls,2,observation=False)
            assert x[0] is not None and y[0] is None and x[1:]==y[1:]
            np.testing.assert_array_equal(serialize_game_state(a.state),serialize_game_state(b.state))
    finally:a.close();b.close()


def test_fusion_verification_is_cached_and_invalidates_when_file_changes(tmp_path,monkeypatch):
    from nova.environment import ArenaEnv
    import nova.core as core
    p=tmp_path/'fusion.pt';p.write_bytes(b'weights');Path(str(p)+'.json').write_text('{}')
    calls=[]
    def check(path,contract):calls.append(path);return {'sha256':'original'}
    monkeypatch.setattr(core,'check_model',check)
    env=ArenaEnv.__new__(ArenaEnv);env.cfg={'env':{'fusion_opponent':str(p)},'fusion_teacher':{'sha256':'original'}}
    env.forced_opponent='fusion';env.forced_snapshot=None;env.cache={('chronos_snapshot',str(p)):NS()}
    env._choose_opponent();env._choose_opponent();assert len(calls)==1
    p.write_bytes(b'changed weights')
    env._choose_opponent();assert len(calls)==2
    monkeypatch.setattr(core,'check_model',lambda *a:{'sha256':'wrong'})
    p.write_bytes(b'changed again to different content')
    with pytest.raises(ValueError,match='changed'):env._choose_opponent()
