"""Distill Nexto demonstrations with hard-action imitation AND soft KL.

Saves separate student_v2 weights and reports whole-episode validation metrics.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent


def load_data(path: Path):
    files = sorted(path.glob('nexto_rollout_*.npz')) if path.is_dir() else [path]
    if not files or not all(f.is_file() for f in files):
        raise FileNotFoundError(f'No dataset files: {path}')
    ob, pr, ep = [], [], []
    for file in files:
        with np.load(file, allow_pickle=False) as d:
            ob.append(np.asarray(d['obs'], dtype=np.float32))
            pr.append(np.asarray(d['teacher_probs'], dtype=np.float32))
            ep.append(np.asarray(d['replay_ids'], dtype=np.int64))
    obs = np.concatenate(ob)
    probs = np.concatenate(pr)
    episodes = np.concatenate(ep)
    if obs.shape != (len(probs), 92) or probs.shape[1:] != (90,) or episodes.shape != (len(obs),):
        raise ValueError('Dataset must contain (N,92) obs, (N,90) teacher_probs and (N,) replay_ids')
    if not np.isfinite(obs).all() or not np.isfinite(probs).all():
        raise ValueError('Dataset has NaN or infinity')
    if not np.allclose(probs.sum(axis=1), 1, atol=3e-3):
        raise ValueError('Teacher probabilities do not sum to 1')
    return obs, probs, episodes


def split_episodes(ids, fraction=0.15, seed=42):
    uniques = np.unique(ids)
    if len(uniques) < 2:
        raise ValueError('At least 2 complete episodes needed for validation')
    rng = np.random.default_rng(seed)
    rng.shuffle(uniques)
    count = max(1, min(len(uniques) - 1, round(len(uniques) * fraction)))
    valid = np.isin(ids, uniques[:count])
    train_ix = np.flatnonzero(~valid)
    valid_ix = np.flatnonzero(valid)
    assert not np.intersect1d(ids[train_ix], ids[valid_ix]).size
    return train_ix, valid_ix


def combined_loss(preds, teacher_probs, hard_weight):
    import torch
    preds = preds.clamp_min(1e-8)
    kl = torch.nn.functional.kl_div(preds.log(), teacher_probs, reduction='batchmean')
    target = teacher_probs.argmax(-1)
    ce = torch.nn.functional.nll_loss(preds.log(), target)
    return (1-hard_weight) * kl + hard_weight * ce, kl, ce


def train(args):
    import torch
    from rlgym_ppo.ppo.discrete_policy import DiscreteFF
    from chatgpt_ai.config import POLICY_LAYERS
    obs, teacher_p, episodes = load_data(args.dataset)
    tr, va = split_episodes(episodes, args.validation, args.seed)
    device = 'cuda:0' if args.device == 'auto' and torch.cuda.is_available() else args.device
    if device == 'cuda:0' and not torch.cuda.is_available():
        raise RuntimeError('Requested CUDA but it is unavailable')
    torch.set_num_threads(min(4, max(1, torch.get_num_threads())))
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    model = DiscreteFF(92, 90, list(POLICY_LAYERS), device=device)
    if args.init:
        ck = torch.load(str(args.init), map_location='cpu', weights_only=True)
        model.load_state_dict(ck, strict=True)
        print(f'Initialized from {args.init}')
    optim = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    def evaluate():
        model.eval()
        score = np.zeros(3, dtype=np.float64)
        with torch.inference_mode():
            for start in range(0, len(va), args.batch):
                ix = va[start:start+args.batch]
                x = torch.from_numpy(obs[ix]).to(device)
                tar = torch.from_numpy(teacher_p[ix]).to(device)
                pred = model.get_output(x)
                loss, kl, ce = combined_loss(pred, tar, args.hard_weight)
                agreement = int((pred.argmax(-1) == tar.argmax(-1)).sum().item())
                score += [float(kl) * len(ix), float(ce) * len(ix), agreement]
        return score / len(va)
    initial = evaluate()
    print(f'Dataset {len(obs):,} decisions across {len(np.unique(episodes))} episodes | '
          f'train {len(tr):,} / held-out {len(va):,} | device {device}')
    print(f'Initial held-out: KL={initial[0]:.4f}, CE={initial[1]:.4f}, agreement={initial[2]:.2%}')
    best = float('inf')
    best_epoch = None
    since_best = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(1, args.epochs+1):
        rng.shuffle(tr)
        model.train()
        acc = 0.
        for start in range(0, len(tr), args.batch):
            ix = tr[start:start+args.batch]
            X = torch.from_numpy(obs[ix]).to(device)
            T = torch.from_numpy(teacher_p[ix]).to(device)
            pred = model.get_output(X)
            loss, _, _ = combined_loss(pred, T, args.hard_weight)
            optim.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
            optim.step()
            acc += float(loss.detach()) * len(ix)
        metrics = evaluate()
        # Tune for both faithfulness to distribution and the actual favorite action.
        val_score = (1 - args.hard_weight) * metrics[0] + args.hard_weight * metrics[1]
        print(f'Epoch {epoch}/{args.epochs}: train_loss={acc/len(tr):.4f} '
              f'heldout_KL={metrics[0]:.4f} heldout_CE={metrics[1]:.4f} '
              f'agreement={metrics[2]:.2%}', flush=True)
        if val_score < best - 1e-4:
            best = val_score
            best_epoch = epoch
            since_best = 0
            torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, args.output)
        else:
            since_best += 1
            if since_best >= args.patience:
                print(f'Early stopping: {since_best} epochs without held-out score improvement.')
                break
    if best_epoch is not None:
        print(f'BEST checkpoint epoch {best_epoch} saved to {args.output}')
    return best_epoch


def main():
    p = argparse.ArgumentParser(description='Nexto hard+soft distillation with episode-level validation')
    p.add_argument('--dataset', type=Path, default=ROOT/'data/datasets/nexto_rollouts')
    p.add_argument('--init', type=Path, default=ROOT/'data/nexto_student_policy.pt')
    p.add_argument('--output', type=Path, default=ROOT/'data/nexto_student_v2.pt')
    p.add_argument('--epochs', type=int, default=30)
    p.add_argument('--batch', type=int, default=256)
    p.add_argument('--learning-rate', type=float, default=5e-5)
    p.add_argument('--weight-decay', type=float, default=1e-5)
    p.add_argument('--hard-weight', type=float, default=.65)
    p.add_argument('--validation', type=float, default=.15)
    p.add_argument('--patience', type=int, default=6)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--device', choices=['auto', 'cpu', 'cuda:0'], default='auto')
    a = p.parse_args()
    if a.init and not a.init.is_file():
        p.error(f'Missing initialization checkpoint {a.init}')
    if a.epochs < 1 or a.batch < 1 or a.learning_rate <= 0 or a.patience < 1:
        p.error('epochs, batch, patience, lr must be positive')
    if not 0 <= a.hard_weight <= 1 or not 0 < a.validation < 0.5:
        p.error('hard-weight in [0,1] and validation in (0,.5) required')
    train(a)


if __name__ == '__main__':
    main()
