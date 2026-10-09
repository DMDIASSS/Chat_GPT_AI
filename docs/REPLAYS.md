# Replay imitation learning: important limitations

Rocket League `.replay` files are not a video dataset. They are lossy game-state reconstructions, and not all controller buttons are directly recorded. `rlgym-tools` can infer missing controls from state sequences. Labels are approximate, particularly aerial pitch/yaw/roll and recovery. This is useful *pretraining*, not a shortcut guaranteeing Nexto-level play.

Source: https://rlgym.org/RLGym%20Tools/introduction/

## Fetch publicly shared 1v1 replays

1. Obtain your own Ballchasing API token from https://ballchasing.com/upload (requires an account). Check the website's terms, rate limits and permissions before downloading or redistributing data.
2. Set the token as an environment variable in your own PowerShell session; do not commit it to Git.
3. `python fetch_replays.py --count 50` queries `ranked-duels` and `min-rank=grand-champion` and downloads up to 50 listed public `.replay` files. This is a convenient high-rank filter, **not guaranteed SSL**. Source: https://ballchasing.com/doc/api
4. You can also manually add legally shared 1v1 `.replay` files to `data/replays/`.
5. Install `requirements-extra.txt` and run `python replays_to_dataset.py --max-samples 300000`.
6. Run `python pretrain.py --epochs 12`. It creates `data/bc_policy.pt`.
7. Start a **new** RL PPO run with `python train.py --preset fundamentals --steps 10000000 --fresh --init-policy data/bc_policy.pt`. Move existing checkpoints out of the way first.

### Caveats

- The provided converter accepts only 1v1 states (exactly two cars), because `DefaultObs(zero_padding=None)` yields a different observation width for any other team size.
- Actions are discretized to the same 90-action table the PPO agent uses. Subtle human controls can be lost; data quality varies by replay.
- The 90-action table is not full analog control. This can limit precision at the very top level.
- Our data split is by frames, not match IDs, and can overestimate generalization due to temporal correlation; validation accuracy is a sanity check, not a game-play win rate. For serious studies, split by replay file rather than frames.
- Data reconstruction can be CPU-intensive, and the converter deliberately caps samples to avoid consuming all system memory.
- Do **not** load a third-party pretrained policy merely because its filename says Nexto. The observation space, action indexing and neural architecture must match, and weights must be licensed for reuse.
- Strong human imitation may improve early movement but also impose stylistic errors. Compare against a fresh PPO baseline.

For a more sophisticated inverse-dynamics solution, see https://github.com/Rolv-Arild/replay-pretraining (GPL-3.0; evaluate license compatibility before integrating code).
