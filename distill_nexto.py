"""Train 92->90 student from Nexto soft action targets; output RLGym-PPO state_dict.

Avoid train/validation leakage by splitting entire replay matches, not frames.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent


def split_by_replays(group_ids: np.ndarray, val_fraction: float, seed: int):
    if not (0 < val_fraction < 0.5):
        raise ValueError('val_fraction must be between 0 and 0.5')
    unique=np.unique(group_ids)
    if len(unique) < 2:
        raise ValueError('Need two or more replay matches for a held-out validation match')
    rng=np.random.default_rng(seed)
    unique=rng.permutation(unique)
    n_val=max(1,round(len(unique)*val_fraction))
    valid=np.isin(group_ids,unique[:n_val])
    tr=np.where(~valid)[0]; va=np.where(valid)[0]
    if not len(tr) or not len(va):
        raise ValueError('Could not split whole replay matches into train and validation')
    return tr,va


def train(args):
    import torch
    from rlgym_ppo.ppo.discrete_policy import DiscreteFF
    from chatgpt_ai.config import POLICY_LAYERS

    if args.dataset.is_dir():
        paths=sorted(args.dataset.glob('nexto_rollout_*.npz'))
        if not paths:
            raise FileNotFoundError(f'No Nexto rollout shards in {args.dataset}')
        x_parts=[]; p_parts=[]; g_parts=[]
        group_offset=0
        for path in paths:
            with np.load(path,allow_pickle=False) as d:
                x_parts.append(np.asarray(d['obs'],dtype=np.float32))
                p_parts.append(np.asarray(d['teacher_probs'],dtype=np.float32))
                local=np.asarray(d['replay_ids'],dtype=np.int64)
                # Each shard's matching episode ID appears in other shards too.
                # Preserve identifiers across shards of this same training run.
                g_parts.append(local)
        obs=np.concatenate(x_parts)
        probs=np.concatenate(p_parts)
        groups=np.concatenate(g_parts)
    else:
        if not args.dataset.is_file():
            raise FileNotFoundError(f'Missing {args.dataset}; run BUILD_NEXTO_DATA.bat or COLLECT_NEXTO_ROLLOUTS.bat')
        with np.load(args.dataset,allow_pickle=False) as d:
            obs=np.asarray(d['obs'],dtype=np.float32)
            probs=np.asarray(d['teacher_probs'],dtype=np.float32)
            groups=np.asarray(d['replay_ids'],dtype=np.int64)
    if obs.ndim!=2 or obs.shape[1]!=92 or probs.shape!=(len(obs),90) or groups.shape!=(len(obs),):
        raise ValueError('Expected (N,92) observations, (N,90) teacher probabilities, (N,) replay IDs')
    if not np.isfinite(obs).all() or not np.isfinite(probs).all():
        raise ValueError('Dataset contains NaNs or infinities')
    tr,va=split_by_replays(groups,args.validation_fraction,args.seed)
    dev='cuda:0' if torch.cuda.is_available() and args.device!='cpu' else 'cpu'
    torch.set_num_threads(min(4,max(1,torch.get_num_threads())))
    torch.manual_seed(args.seed)
    rng=np.random.default_rng(args.seed)
    model=DiscreteFF(92,90,list(POLICY_LAYERS),device=dev)
    if args.init:
        if not args.init.is_file():
            raise FileNotFoundError(args.init)
        state=torch.load(str(args.init),map_location='cpu',weights_only=True)
        model.load_state_dict(state,strict=True)
        print(f'Initialized from {args.init}')
    optimizer=torch.optim.Adam(model.parameters(),lr=args.learning_rate)
    def evaluate():
        model.eval(); total_kl=0.; correct=0
        with torch.inference_mode():
            for start in range(0,len(va),args.batch):
                ids=va[start:start+args.batch]
                px=model.get_output(torch.from_numpy(obs[ids]).to(dev)).clamp_min(1e-8)
                tar=torch.from_numpy(probs[ids]).to(dev)
                kl=torch.nn.functional.kl_div(px.log(),tar,reduction='none').sum(-1)
                total_kl+=float(kl.sum())
                correct+=int((px.argmax(-1)==tar.argmax(-1)).sum().item())
        return total_kl/len(va),correct/len(va)
    base_kl,base_ag=evaluate()
    print(f'Nexto teacher dataset: train={len(tr):,} ({len(np.unique(groups[tr]))} replays), '
          f'held-out={len(va):,} ({len(np.unique(groups[va]))} replays), device={dev}')
    print(f'Before training: held-out KL={base_kl:.4f}, top-action agreement={base_ag:.2%}')
    best_kl=base_kl
    saved=False
    args.out.parent.mkdir(parents=True,exist_ok=True)
    for epoch in range(1,args.epochs+1):
        rng.shuffle(tr)
        model.train(); total=0.
        for start in range(0,len(tr),args.batch):
            ids=tr[start:start+args.batch]
            x=torch.from_numpy(obs[ids]).to(dev)
            y=torch.from_numpy(probs[ids]).to(dev)
            preds=model.get_output(x).clamp_min(1e-8)
            loss=torch.nn.functional.kl_div(preds.log(),y,reduction='batchmean')
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
            optimizer.step()
            total+=float(loss.item())*len(ids)
        val_kl,agreement=evaluate()
        print(f'Epoch {epoch}/{args.epochs}: train KL={total/len(tr):.4f} '
              f'held-out KL={val_kl:.4f} top-action agreement={agreement:.2%}',flush=True)
        if val_kl < best_kl:
            best_kl=val_kl
            torch.save({k:v.detach().cpu() for k,v in model.state_dict().items()},args.out)
            saved=True
    if not saved:
        print('Teacher distillation did not beat initial checkpoint on held-out KL; '
              'no new weights saved. Try different hyperparameters or inspect data.')
    else:
        print(f'Saved improved student: {args.out} (held-out KL={best_kl:.4f})')
    return saved


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dataset',type=Path,default=ROOT/'data/datasets/nexto_teacher_1v1.npz')
    p.add_argument('--out',type=Path,default=ROOT/'data/nexto_student_policy.pt')
    p.add_argument('--init',type=Path,default=None,help='Optional initial 92->90 BC or PPO policy weights')
    p.add_argument('--epochs',type=int,default=12)
    p.add_argument('--batch',type=int,default=256)
    p.add_argument('--learning-rate',type=float,default=1e-4)
    p.add_argument('--validation-fraction',type=float,default=0.15)
    p.add_argument('--seed',type=int,default=42)
    p.add_argument('--device',choices=['auto','cpu'],default='auto')
    args=p.parse_args()
    if args.batch<1 or args.epochs<1 or args.learning_rate<=0:
        p.error('batch, epochs, learning-rate must be positive')
    train(args)

if __name__=='__main__':
    main()
