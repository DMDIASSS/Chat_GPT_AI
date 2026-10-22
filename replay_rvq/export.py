"""Export the separately trained RVQ model and optional all-car search to RLBot."""
from pathlib import Path
from importlib.metadata import version
import re,json,shutil,tempfile
import torch
from replay_rvq.inference import load,freeze
from replay_rvq.train import ROOT
from slater_v041_core import sha256,read_json


def export(root,name='ReplayRVQ01',output=None):
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,59}',name):raise ValueError('Invalid export name')
    root=Path(root);output=Path(output or ROOT/'data/rlbot_exports');target=output/name
    if target.exists():raise FileExistsError('Export exists; choose a new --name to preserve it')
    digest=sha256(root/'policy/best.pt');model=load(root);torch.set_num_threads(2)
    output.mkdir(parents=True,exist_ok=True);temp=Path(tempfile.mkdtemp(prefix='.'+name+'_',dir=output))
    try:
        kernel=freeze(model);torch.jit.save(kernel,str(temp/'policy.pt'));kernel=torch.jit.load(str(temp/'policy.pt')).eval()
        checks=[];rng=torch.Generator().manual_seed(20261022)
        with torch.inference_mode():
            for batch in (1,3,8):
                obs=(torch.randn(batch,1,32,generator=rng),torch.randn(batch,41,24,generator=rng),torch.zeros(batch,41))
                expected=model.encode(obs);actual=kernel.encode(obs);torch.testing.assert_close(expected,actual,atol=3e-5,rtol=3e-5)
                for method in ('greedy','propose','value'):
                    before=getattr(model,method)(expected);after=getattr(kernel,method)(actual)
                    for a,b in zip(before,after) if isinstance(before,tuple) else [(before,after)]:
                        torch.testing.assert_close(a,b,atol=3e-5,rtol=3e-5)
                checks.append({'batch':batch,'encode_max_error':float((expected-actual).abs().max())})
        files={'bot.py':ROOT/'replay_rvq/agent.py','rvq_runtime.py':ROOT/'replay_rvq/runtime.py',
            'rvq_packet.py':ROOT/'replay_rvq/packet.py','rvq_search.py':ROOT/'replay_rvq/search.py',
            'replay_rlbot_core.py':ROOT/'replay_rlbot_core.py','replay_nexto_obs.py':ROOT/'vendor/nexto/nexto_obs.py',
            'NEXT0_UPSTREAM_LICENSE.txt':ROOT/'rlbot_v4_template/NEXT0_UPSTREAM_LICENSE.txt',
            'appearance.cfg':ROOT/'rlbot_v4_template/appearance.cfg'}
        for filename,source in files.items():shutil.copy2(source,temp/filename)
        (temp/'runtime.json').write_text(json.dumps({'device':'auto','mode':'search','candidates':16,
            'adaptive':True,'scripted_kickoff':True},indent=2),encoding='utf8')
        versions=read_json(root/'protocol.json').get('runtime',{})
        versions={name:versions.get(name,version(name)) for name in ('torch','numpy','rlgym','rlgym-rocket-league','rocketsim')}
        # CUDA wheel suffixes use a separate index; preserve a portable base
        # Torch version while pinning the actual tested simulator API versions.
        requirements='rlbot==1.*\n'+''.join(name+'=='+number.split('+')[0]+'\n' for name,number in versions.items())
        (temp/'requirements.txt').write_text(requirements,encoding='utf8')
        (temp/'bot.cfg').write_text('[Locations]\nlooks_config = ./appearance.cfg\npython_file = ./bot.py\nrequirements_file = ./requirements.txt\n'
            f'name = {name}\nmaximum_tick_rate_preference = 120\n\n[Details]\ndeveloper = Chat GPT AI project\n'
            'description = Offline human-replay residual VQ policy with value-guided all-car search\nlanguage = python\ntags = 1v1, 2v2, 3v3\n',encoding='utf8')
        runtime=['policy.pt','bot.py','rvq_runtime.py','rvq_packet.py','rvq_search.py','replay_rlbot_core.py','replay_nexto_obs.py']
        info={'format':'replay-rvq-rlbot-v4-v1','name':name,'checkpoint_sha256':digest,'model_config':model.config,
            'parameters':sum(p.numel() for p in model.parameters()),'input':'current_state_only','codebooks':4,'codes_per_level':64,
            'horizon_ticks':128,'execute_first_ticks':8,'mode':'search','numerical_checks':checks,
            'runtime_sha256':{n:sha256(temp/n) for n in runtime},'learning':'offline human replay only; no runtime training',
            'validation':read_json(root/'policy/selected.json').get('validation',{}),'training_runtime':versions,
            'live_game_verified':False,'limitations':'Standard Soccar only. Jump/flip, demolition and pad respawn timers are estimates. '
                'Unknown hitboxes default to Octane only when packet dimensions are absent. No score/time features in cached inputs. '
                'Basic scripted kickoff, not a pro replay book. Reference search may exceed laptop budget; adaptive counts are a soft limit.'}
        (temp/'EXPORT_INFO.json').write_text(json.dumps(info,indent=2),encoding='utf8')
        (temp/'README_IMPORT.txt').write_text('Load bot.cfg in RLBot v4. RLBot Python needs Torch, NumPy and rlgym[rl-sim].\n'
            'The export is self-contained and never trains. Search defaults to an adaptive maximum of 16 candidates.\n'
            'runtime.json mode can be policy for a direct-policy comparison. Benchmark the trained model before raising the budget.\n'
            +info['limitations']+'\n',encoding='utf8')
        if sha256(root/'policy/best.pt')!=digest:raise RuntimeError('Source checkpoint changed during export')
        temp.rename(target);print('RVQ_EXPORTED:',target/'bot.cfg',flush=True);return target
    except BaseException:shutil.rmtree(temp,ignore_errors=True);raise
