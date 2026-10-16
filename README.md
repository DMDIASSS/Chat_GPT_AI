# Ranked doubles replay collector (no RL / self-play)

This is an independent, standard-library-only utility to place next to your repo's trainer. It downloads eligible raw 2v2 `.replay` files into `data/replays/ranked-doubles`, uses the official Ballchasing authenticated API, and preserves an auditable manifest. **It does not train the model or reconstruct controller inputs.**

## Windows PowerShell

```powershell
cd 'E:\Downloads\Chat_GPT_AI'
$env:BALLCHASING_TOKEN = 'your_token_from_ballchasing'
python .\fetch_ranked_doubles.py --dry-run --limit 20
python .\fetch_ranked_doubles.py --limit 1000 --output '.\data\replays\ranked-doubles'
python -m unittest -v test_fetch_ranked_doubles.py
```

Store the Ballchasing API token privately (prefer a user-level environment variable or secure secret manager). **Never commit the token.** Limits and 429 errors are handled conservatively. The manifest is append-only and allows resuming after interruption. Raw downloads are written atomically and checksumed.

**Rank caution:** Your website filter `?playlist=11&min-rank=21&max-rank=22` is **not the same query** as the documented public API. The API documents `grand-champion` as its highest *named* filter. That may include ranks outside GC3–SSL; this collector therefore sets `rank_verified_gc3_ssl=false`. Do not advertise the dataset as GC3–SSL until rank/MMR metadata is checked via a separate validated method. The collector also requires exactly two players per team.

## What the imitation pipeline must do next

1. Parse real game state per physics tick and reconstruct actions with RocketSim; reject clips when one-step and full-chunk forward reconstructions exceed thresholds calibrated against known-good control traces.
2. Split data **by entire replay identity**, keeping all perspectives, duplicate uploads, overlapping chunks and TAS variants in the same split. Use 1v1 and 2v2 held-out sets separately.
3. Train behavioral-cloning/chunk prediction from *verified* controls; store state, control alignment, confidence and source metadata. Keep uncertain labels masked rather than rewarding a network for copying them.
4. Train the value head using observed future game events/outcomes and split-safe targets. Avoid leaking future action/state into model inputs. The fact that PPO reward is absent does not eliminate label leakage or data bias.
5. Run a blind held-out evaluation with action classification/calibration, forward-simulation physics error, long-horizon rollout tests, meaningful gameplay scenarios, and inference latency/throughput. Compare direct policy and candidate-planning performance under identical conditions.
6. Log dataset version/hash, seed, train/val/test replay IDs, rank confidence, reconstruction rejects, teacher-forcing versus open-loop errors, metrics by playlist and checkpoint/artifact hashes. W&B `offline` mode is useful until the pipeline is trusted.

This standalone collector deliberately does not pretend it can access the local Windows replay directory from a separate cloud environment.

## W&B integration for the *new* imitation trainer

`imitation_metrics.py` is a small optional logger. It logs to a local JSONL file regardless of W&B availability, validates steps/metrics, and can use W&B offline until you are satisfied with replay reconstruction. It is deliberately **not wired into legacy `train.py`**, which still runs PPO on the currently published GitHub branch; hook it into the uncommitted replay-imitation trainer after its metrics are computed.

```python
from imitation_metrics import ImitationMetrics

with ImitationMetrics('runs/imitation_v1', wandb_mode='offline',
                      config={'seed': 123, 'data': 'verified-replay-only'}) as logger:
    # This is illustrative; integrate in the real training loop.
    logger.log(step=0, metrics={'train/chunk_nll': 1.2, 'val/chunk_nll': 1.5,
                                'reconstruction/chunk_pass_rate': 0.9})
```

For online sync, install W&B with `pip install wandb`, run `wandb login` on your PC, and set `wandb_mode='online'`. For offline upload later use `wandb sync runs/imitation_v1/wandb/offline-run-*` (after actual offline runs exist). Avoid logging individual players' identifying information, API keys, or full private replays. Always make W&B charts label **measured** values rather than claiming improvement from declining loss alone.
