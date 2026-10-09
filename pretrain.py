"""Imitation pretraining on reconstructed human actions from 1v1 replays.

Outputs a policy state_dict loadable by train.py --init-policy <path> --fresh.
"""
import argparse
from pathlib import Path
import numpy as np
from chatgpt_ai.config import DATASET_PATH, POLICY_LAYERS, ROOT


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--dataset', type=Path, default=DATASET_PATH)
    p.add_argument('--out', type=Path, default=ROOT / 'data' / 'bc_policy.pt')
    p.add_argument('--epochs', type=int, default=12)
    p.add_argument('--batch', type=int, default=1024)
    p.add_argument('--learning-rate', type=float, default=3e-4)
    args = p.parse_args()
    if not args.dataset.is_file():
        p.error(f'Dataset missing: {args.dataset}; run replays_to_dataset.py first')

    import torch
    from rlgym_ppo.ppo.discrete_policy import DiscreteFF
    data = np.load(args.dataset, allow_pickle=False)
    x = np.asarray(data['obs'], dtype=np.float32)
    y = np.asarray(data['actions'], dtype=np.int64)
    if x.ndim != 2 or x.shape[1] != 92 or y.shape != (len(x),) or len(x) < 100:
        p.error('Expected at least 100 samples with obs shape (N, 92) and actions (N,)')
    if y.min() < 0 or y.max() >= 90:
        p.error('Action label outside RLGym LookupTableAction 0..89')
    device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
    model = DiscreteFF(92, 90, list(POLICY_LAYERS), device=device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    rng = np.random.default_rng(123)
    # Hold out samples, don't just report training accuracy.
    perm = rng.permutation(len(x))
    split = max(1, int(len(x) * .9))
    if split == len(x):
        split -= 1
    tr, va = perm[:split], perm[split:]
    print(f'Imitation pretraining: {len(tr)} train | {len(va)} validation | {device}')
    best_accuracy = -1.0
    for epoch in range(args.epochs):
        model.train()
        np.random.shuffle(tr)
        running = 0.0
        for start in range(0, len(tr), args.batch):
            ids = tr[start:start+args.batch]
            obs = torch.from_numpy(x[ids]).to(device)
            target = torch.from_numpy(y[ids]).to(device)
            output = model.get_output(obs).clamp_min(1e-10)
            loss = torch.nn.functional.nll_loss(output.log(), target)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            running += float(loss.item()) * len(ids)
        model.eval()
        correct = 0
        with torch.no_grad():
            for start in range(0, len(va), args.batch):
                ids = va[start:start+args.batch]
                pred = model.get_output(torch.from_numpy(x[ids]).to(device)).argmax(-1).cpu().numpy()
                correct += int((pred == y[ids]).sum())
        accuracy = correct / len(va)
        print(f'Epoch {epoch+1}/{args.epochs}: train CE {running/len(tr):.3f}, val acc {accuracy:.3%}')
        if accuracy > best_accuracy:
            best_accuracy = accuracy
            args.out.parent.mkdir(parents=True, exist_ok=True)
            torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, args.out)
    print('Best validation accuracy:', f'{best_accuracy:.1%}', '| saved', args.out)


if __name__ == '__main__':
    main()
