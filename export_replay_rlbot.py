"""Export the selected replay-only chunk policy to a separate RLBot v4 folder."""
from pathlib import Path
import argparse
import json
import re
import shutil
import tempfile
import numpy as np
import torch
from replay_il.planner import load
from replay_il_inference import InferenceKernel,freeze_kernel
from slater_v041_core import sha256

ROOT=Path(__file__).resolve().parent


def export(folder,name='ReplayScratch01',output=None,*,scripted_kickoff=False):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,59}',name):raise ValueError('Invalid export name')
    folder=Path(folder).resolve();output=Path(output or ROOT/'data/rlbot_exports').resolve();target=output/name
    if target.exists():raise FileExistsError('Export already exists. Choose another --name; existing exports are preserved.')
    identity={n:sha256(folder/n) for n in ('best.pt','tokens.npy','selected.json','tokenizer.json')}
    model,book=load(folder,device='cpu')
    if book.shape!=(model.config['vocabulary'],32,8) or not np.isfinite(book).all() or np.any(np.abs(book)>1.001) or not np.isin(book[:,:,5:],[0,1]).all():
        raise ValueError('Action vocabulary is not the trained 32-tick replay chunk format')
    if not all(torch.isfinite(p).all() for p in model.parameters()):raise ValueError('Non-finite model weights')
    output.mkdir(parents=True,exist_ok=True);temp=Path(tempfile.mkdtemp(prefix='.'+name+'_',dir=output))
    try:
        with torch.inference_mode():
            kernel=freeze_kernel(InferenceKernel(model));torch.jit.save(kernel,str(temp/'policy.pt'))
            restored=torch.jit.load(str(temp/'policy.pt'),map_location='cpu').eval()
            errors=[];generator=torch.Generator().manual_seed(271)
            for batch,players in ((1,2),(3,4),(8,6)):
                observations=(torch.randn(batch,1,32,generator=generator),torch.randn(batch,41,24,generator=generator),torch.zeros(batch,41))
                observations[2][:,players:6]=-10000.
                expected=model.encoder(observations);actual=restored.encode(observations)
                torch.testing.assert_close(actual,expected,atol=3e-5,rtol=3e-5)
                features=torch.randn(batch,model.history,128,generator=generator)
                before=InferenceKernel(model).decode(features);after=restored.decode(features)
                for a,b in zip(before,after):torch.testing.assert_close(a,b,atol=3e-5,rtol=3e-5)
                if not torch.equal(before[0].argmax(-1),after[0].argmax(-1)):raise ValueError('Export changed a validation action')
                errors.append({'batch':batch,'players':players,'feature_max_error':float((expected-actual).abs().max()),
                    'logits_max_error':float((before[0]-after[0]).abs().max()),'values_max_error':float((before[1]-after[1]).abs().max())})
        shutil.copy2(folder/'tokens.npy',temp/'tokens.npy')
        shutil.copy2(ROOT/'replay_rlbot_agent.py',temp/'bot.py');shutil.copy2(ROOT/'replay_rlbot_core.py',temp/'replay_rlbot_core.py')
        shutil.copy2(ROOT/'vendor/nexto/nexto_obs.py',temp/'replay_nexto_obs.py')
        shutil.copy2(ROOT/'rlbot_v4_template/NEXT0_UPSTREAM_LICENSE.txt',temp/'NEXT0_UPSTREAM_LICENSE.txt')
        shutil.copy2(ROOT/'rlbot_v4_template/appearance.cfg',temp/'appearance.cfg')
        (temp/'runtime.json').write_text(json.dumps({'device':'auto','scripted_kickoff':bool(scripted_kickoff)},indent=2),encoding='utf8')
        (temp/'requirements.txt').write_text('rlbot==1.*\nnumpy\ntorch\n',encoding='utf8')
        (temp/'bot.cfg').write_text('[Locations]\nlooks_config = ./appearance.cfg\npython_file = ./bot.py\nrequirements_file = ./requirements.txt\n'
            f'name = {name}\nmaximum_tick_rate_preference = 120\n\n[Details]\ndeveloper = Chat GPT AI project\n'
            'description = Offline human-replay action-chunk imitation policy\nlanguage = python\ntags = 1v1, 2v2, 3v3\n',encoding='utf8')
        limitations='RLBot v4 standard Soccar only. Jump/flip timers and ground/contact flags are packet estimates. '
        limitations+='Direct policy inference; RocketSim search is not included. Optional basic scripted kickoff is not learned/pro-replay behavior. Live-game parity and playing strength unverified.'
        runtime_files=('policy.pt','tokens.npy','bot.py','replay_rlbot_core.py','replay_nexto_obs.py')
        metadata={'format':'replay-chunk-rlbot-v4-v1','name':name,'checkpoint_sha256':identity['best.pt'],
            'book_sha256':identity['tokens.npy'],'parameters':sum(p.numel() for p in model.parameters()),
            'history':model.history,'vocabulary':len(book),'chunk_ticks':32,'execute_first_ticks':8,'physics_hz':120,
            'learning':'offline imitation; no training during export/deployment','mode':'policy','torch':torch.__version__,
            'runtime_sha256':{n:sha256(temp/n) for n in runtime_files},'numerical_validation':errors,
            'scripted_kickoff':bool(scripted_kickoff),'live_game_verified':False,'limitations':limitations}
        (temp/'EXPORT_INFO.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
        (temp/'README_IMPORT.txt').write_text('Import bot.cfg using RLBot v4 (Add/Load bot). Use a Python environment with Torch and NumPy.\n'
            'This directory is self-contained; moving it does not require the training project.\n'
            'Set runtime.json device to cpu if your RLBot Python has no compatible CUDA build.\n'+limitations+'\n',encoding='utf8')
        if identity!={n:sha256(folder/n) for n in identity}:raise RuntimeError('Training source artifacts changed during export')
        if sha256(temp/'tokens.npy')!=identity['tokens.npy']:raise RuntimeError('Export action vocabulary changed')
        temp.rename(target)
        print('EXPORTED:',target/'bot.cfg',flush=True);print('Mode: policy | temporal history retained | no retraining',flush=True)
        return target
    except BaseException:shutil.rmtree(temp,ignore_errors=True);raise


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',default='replay_scratch01');parser.add_argument('--name',default='ReplayScratch01')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--scripted-kickoff',action='store_true',help='Enable an explicitly scripted basic kickoff; model weights remain unchanged')
    args=parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',args.run):parser.error('Invalid run name')
    torch.set_num_threads(2)
    export(ROOT/'data/isolated/replay_imitation/runs'/args.run,args.name,args.output,scripted_kickoff=args.scripted_kickoff)


if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError) as error:print('STOPPED:',str(error),flush=True);raise SystemExit(1)
