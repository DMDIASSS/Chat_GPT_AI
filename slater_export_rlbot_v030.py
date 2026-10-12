"""Export verified Slater v027 actor weights to a TorchScript RLBot v4 model file.

For original Bot_Dias v4 package using agent.py -> nexto-model.pt. Creates a
NEW TorchScript file under data/isolated and never alters source/candidate.
After export, user may copy file INTO a separate copy of their RLBot bot folder
as nexto-model.pt. Does not install or launch RLBot.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import torch
import slater_cycle9_native_ppo_v025 as base
import slater_nexto_heldout_eval_v028 as heldout
import slater_cycle9_paired_eval_v026_fixed as paired


def export_model(checkpoint: Path, native_source: Path, destination: Path, cycle_sha: str, nexto_sha: str, root: Path):
    cp,doc=heldout.checked_candidate(str(checkpoint),root,cycle_sha,nexto_sha)
    if doc.get('meta', {}).get('nexto_sha') != nexto_sha:
        raise ValueError('Candidate Nexto provenance missing or incorrect')
    if base.sha256(native_source)!=nexto_sha:
        raise RuntimeError('Vendor Nexto source changed')
    original=torch.jit.load(str(native_source),map_location='cpu')
    # Load ALL 44 parameter tensors by strict name/shape; no partial weights.
    original.load_state_dict(doc['actor'],strict=True)
    original.eval()
    for p in original.parameters():p.requires_grad_(False)
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Create-only even on Windows: 'xb' refuses existing file.
    created = False
    try:
        with destination.open('xb') as stream:
            created = True
            torch.jit.save(original,stream)
        checked=torch.jit.load(str(destination),map_location='cpu')
        a=original.state_dict()
        b=checked.state_dict()
        if set(a)!=set(b) or any(not torch.equal(a[k],b[k]) for k in a):
            raise RuntimeError('TorchScript round-trip did not preserve weights')
        # checkpoint actor shape and values verified; original source unchanged.
        if base.sha256(cp)!=base.sha256(checkpoint) or base.sha256(native_source)!=nexto_sha:
            raise RuntimeError('Source changed unexpectedly')
        return {'checkpoint_sha256':base.sha256(cp),'export_sha256':base.sha256(destination),
                'parameters':len(b),'global_updates':doc['global_updates']}
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',required=True)
    p.add_argument('--out',required=True)
    args=p.parse_args()
    root=Path.cwd().resolve()
    out=base.check_output(args.out,root,'.pt')
    from slater_research.checkpoint import CYCLE9, CYCLE9_SHA
    cycle=root/CYCLE9
    nexto=root/'vendor'/'nexto'/'nexto-model.pt'
    if base.sha256(cycle)!=CYCLE9_SHA:
        raise RuntimeError('Protected Cycle9 checkpoint modified')
    result=export_model(Path(args.checkpoint).resolve(),nexto,out,CYCLE9_SHA,paired.EXPECTED_NEXTO_SHA256,root)
    if base.sha256(cycle)!=CYCLE9_SHA:
        raise RuntimeError('Protected Cycle9 changed')
    print('EXPORTED_RLBOT_TORCHSCRIPT',out)
    print('EXPORT_INFO',result)
    print('NEXT: copy exported .pt into a COPY of Bot_Dias RLBot v4 bot folder as nexto-model.pt')
    print('NOT_FOR_PUBLIC_MATCHMAKING. NO_ORIGINAL_CHECKPOINT_MODIFICATIONS')

if __name__=='__main__':main()
