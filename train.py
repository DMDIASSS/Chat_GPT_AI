"""Train Chat GPT AI with RocketSim + RLGym-PPO.

Usage: python train.py --preset smoke --steps 100000
       python train.py --preset balanced --steps 100000000
"""
import argparse
import os
from functools import partial

from chatgpt_ai.config import CHECKPOINT_ROOT, POLICY_LAYERS, CRITIC_LAYERS, PRESETS, recommended_workers


def main():
    parser = argparse.ArgumentParser(description="Chat GPT AI / self-play trainer")
    parser.add_argument("--preset", choices=PRESETS, default="balanced")
    parser.add_argument("--steps", type=int, default=100_000_000, help="Total training timesteps, including resumed steps")
    parser.add_argument("--workers", type=int, default=recommended_workers(os.cpu_count()))
    parser.add_argument("--batch", type=int, default=50000)
    parser.add_argument("--minibatch", type=int, default=25000)
    parser.add_argument("--save-every", type=int, default=500000)
    parser.add_argument("--fresh", action="store_true", help="Start from scratch (won't load checkpoints)")
    parser.add_argument("--init-policy", help="Initialize policy weights from BC .pt (only for --fresh)")
    parser.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda:0"])
    parser.add_argument("--wandb", action="store_true")
    parser.add_argument("--seed", type=int, default=123)
    args = parser.parse_args()
    if args.workers < 2 or args.steps < 1 or args.batch < 1000 or not (1 <= args.minibatch <= args.batch):
        parser.error("Need workers>=2, steps>0, batch>=1000, and 1<=minibatch<=batch")
    if args.init_policy and not args.fresh:
        parser.error("--init-policy requires --fresh (don't mix optimizer states)")
    if args.fresh and CHECKPOINT_ROOT.exists() and any(CHECKPOINT_ROOT.glob('*/PPO_POLICY.pt')):
        parser.error("Checkpoint folder exists: move it elsewhere before --fresh to protect old models")

    import torch
    from rlgym_ppo import Learner
    from chatgpt_ai.env import build_env
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 2)))

    print(f"Chat GPT AI | preset={args.preset} | workers={args.workers} | device={args.device}")
    print(f"PPO total timestep target={args.steps:,} | batch={args.batch:,} | save={CHECKPOINT_ROOT}")
    learner = Learner(
        partial(build_env, preset=args.preset),
        n_proc=args.workers,
        min_inference_size=max(1, int(args.workers * .8)),
        metrics_logger=None,
        ppo_batch_size=args.batch,
        ppo_minibatch_size=args.minibatch,
        ts_per_iteration=args.batch,
        exp_buffer_size=args.batch * 3,
        ppo_epochs=2,
        ppo_ent_coef=0.008,
        policy_lr=5e-5,
        critic_lr=5e-5,
        policy_layer_sizes=list(POLICY_LAYERS),
        critic_layer_sizes=list(CRITIC_LAYERS),
        standardize_returns=True,
        standardize_obs=False,
        save_every_ts=args.save_every,
        timestep_limit=args.steps,
        checkpoints_save_folder=str(CHECKPOINT_ROOT),
        checkpoint_load_folder=None if args.fresh else "latest",
        add_unix_timestamp=False,
        n_checkpoints_to_keep=8,
        log_to_wandb=args.wandb,
        device=args.device,
        random_seed=args.seed,
    )
    if args.init_policy:
        state_dict = torch.load(args.init_policy, map_location="cpu", weights_only=True)
        learner.ppo_learner.policy.load_state_dict(state_dict, strict=True)
        print("Loaded BC pretrained policy into new PPO learner.")
    learner.learn()


if __name__ == "__main__":
    # Windows must spawn worker processes from a protected module main.
    import multiprocessing as mp
    mp.freeze_support()
    main()
