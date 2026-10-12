"""Export a v031 kickoff specialist to a NEW RLBot TorchScript file.

Does not alter original Cycle9, u60, Nexto, or your existing Bot_Dias package.
This exports only the 90-action policy: NO speedflip macro controller added yet.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import torch
import slater_cycle9_native_ppo_v025 as base
import slater_cycle9_paired_eval_v026_fixed as paired

EXPECTED_U60_SHA='5f9bf7cb6a0bcfb3bcf801ade021b11499181d80fb36b0cfad827e2648936c74'


def guarded_export(cp,source,out,root):
    allowed=(root/'data'/'isolated').resolve()
    if not cp.is_relative_to(allowed) or not cp.is_file():raise ValueError('Not an isolated candidate')
    from slater_research.checkpoint import CYCLE9,CYCLE9_SHA
    if base.sha256(root/CYCLE9)!=CYCLE9_SHA or base.sha256(source)!=paired.EXPECTED_NEXTO_SHA256:
        raise RuntimeError('Original model hash mismatch')
    doc=torch.load(cp,map_location='cpu',weights_only=True)
    if not (isinstance(doc,dict) and doc.get('stage')=='slater_kickoff_v031'
       and doc.get('source_sha')==CYCLE9_SHA
       and doc.get('meta',{}).get('nexto_sha')==paired.EXPECTED_NEXTO_SHA256
       and doc.get('meta',{}).get('u60_sha')==EXPECTED_U60_SHA
       and isinstance(doc.get('actor'),dict)):
        raise ValueError('Not a verified v031 kickoff checkpoint derived from expected u60')
    module=torch.jit.load(str(source),map_location='cpu')
    module.load_state_dict(doc['actor'],strict=True)
    module.eval()
    for param in module.parameters():param.requires_grad_(False)
    created=False
    try:
        out.parent.mkdir(parents=True,exist_ok=True)
        with out.open('xb') as f:
            created=True;torch.jit.save(module,f)
        reread=torch.jit.load(str(out),map_location='cpu')
        if any(not torch.equal(module.state_dict()[k],reread.state_dict()[k]) for k in module.state_dict()):
            raise RuntimeError('Round trip check failed')
        if base.sha256(root/CYCLE9)!=CYCLE9_SHA or base.sha256(source)!=paired.EXPECTED_NEXTO_SHA256:
            raise RuntimeError('Protected source changed')
        return base.sha256(out)
    except BaseException:
        if created:out.unlink(missing_ok=True)
        raise


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--checkpoint',required=True)
    ap.add_argument('--out',required=True)
    args=ap.parse_args()
    from slater_research.checkpoint import CYCLE9, CYCLE9_SHA
    root=Path.cwd().resolve()
    out=base.check_output(args.out,root)
    result=guarded_export(Path(args.checkpoint).resolve(),root/'vendor'/'nexto'/'nexto-model.pt',out,root)
    print('EXPORTED_KICKOFF_RLBOT',out,'SHA256',result)
    print('Copy into a SEPARATE copy of the RLBot package as nexto-model.pt. Original files untouched.')

if __name__=='__main__':main()
