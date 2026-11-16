# GigaLearn archive GAE audit

Source: ZealanL/GigaLearnCPP-Leak, commit **86e11c3881a21225a43c36b14af40f0b3c87e7dd**. [GAE.cpp](https://github.com/ZealanL/GigaLearnCPP-Leak/blob/86e11c3881a21225a43c36b14af40f0b3c87e7dd/GigaLearnCPP/src/private/GigaLearnCPP/PPO/GAE.cpp) SHA256 `8c1c8d622457ab9c6488edefa96c039474ba00f5fd0e2e08752afa1ff80c8459`.

## Tests actually executed

The exact original GAE.cpp was compiled unchanged against the installed real LibTorch 2.9.1 CPU runtime. A thin header supplied the same terminal enum, function declaration and logging/helper macros instead of building the full framework. The harness does not replace Tensor arithmetic with a mock. AddressSanitizer was enabled.

1. Two independent truncated transitions, zero rewards/values, gamma=1, lambda=0, timeout values appended in forward order `[10,100]`. Correct advantages are `[10,100]`; original function returned `[100,10]`. Its reverse loop consumes the forward timeout array from index zero. Learner.cpp appends the timeout states in forward terminal order, so this tests the actual caller's ordering contract.
2. One truncated transition followed by an ordinary goal terminal, with two value predictions as supplied by Learner.cpp. AddressSanitizer reported a **heap-buffer-overflow** at original GAE.cpp line 80: it reads `values[step+1]` at the terminal tail before multiplying by `(1-done)`. Multiplying an already invalid read by zero does not make the read valid.

Raw logs and structured results are in `results/ggl_*`. The normal terminal's next value should be zero without a read; a nonterminal tail needs an explicit valid bootstrap. The minimal patch also indexes timeout values from the end during the reverse scan.

The patched function was compiled and both isolated fixtures run: returned `[10,100]` and `[10,0]`, without an ASan error. See `ggl_gae_minimal_fix.patch`.

## Scope and limits

This is a reproducible source-level runtime audit, not a full GigaLearn trainer build or a statistical learning experiment. The patch does not implement a fixed-horizon collector, solve all historical-opponent switching problems, establish target-device performance or certify every checkpoint path. It does not establish why any previous user project played poorly, since those projects may already have different patched kernels.

Further native-training gates include synthetic fixtures across multiple arenas/players, rollout tails, several timeouts and goals in one rollout, manual TD targets, masked frozen rows and optimizer-update continuity. The collector should finish a bounded fixed rollout with the same actor weights; carry-over trajectories spanning policy updates must be eliminated or explicitly handled.

## Optional reproduction

On Linux with an existing matching PyTorch installation and g++/AddressSanitizer:

```
python tools/ggl_gae_audit/reproduce.py --build results/new_gae_audit
```

The script downloads only the pinned source file, verifies its hash, builds original and patched isolated harnesses and writes logs. It refuses an existing output directory. It does not train a bot, install compilers or modify the upstream checkout. The original failures are expected audit outcomes, not training crashes. This optional tool is not part of the Windows benchmark launcher.
