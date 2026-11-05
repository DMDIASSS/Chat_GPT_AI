# Learned-selector telemetry correction in v1.10

The v1.9.1 watch output mixed two sources: `last` and `selections` tracked the
learned selector, while `next_probabilities` and `waiting_decisions` came from
the unused fair-random scheduler. This could show Chronos always chosen alongside
a tiny displayed probability for it. The learned selector never used those
random-scheduler probabilities. This was a display bug, not a routing override.

## Install

Stop the watch console with Ctrl+C and pause training if running. Install the
full v1.10 source ZIP over the existing novaforge/triadbot folders, replacing
program files while retaining environments, assets, runs and exports. Restart
5_WATCH_SELECTOR.bat for the original selector or 20_WATCH_FOUR_SELECTOR.bat for
the new four-expert run after it has a checkpoint.

No dependency reinstall, checkpoint reset, retraining or diagnostic rerun is
needed. The fix changes telemetry only. The actor weights, expert weights,
argmax choice rule, option duration, rewards and champion remain unchanged.

Learned mode now prints `mode: learned`, the most recently chosen expert in
`last`, control-decision counts in `selections`, and:

- `last_free_choice_probabilities`: the actual learned actor's probabilities
  at its most recent free choice. These sum to one and describe choosing an
  expert, not the probability of winning.
- `decisions_until_free_choice`: remaining eight-tick decisions in the current
  commitment. Cached free-choice probabilities stay visible while committed;
  a forced one-hot mask is not presented as model confidence.

The values are null before the first free choice or after a reset until a new
choice. Counts include held control decisions, so 834 Chronos decisions do not
mean 834 independent opportunities to switch. Console refresh is still about
three seconds; this correction does not add a graphical HUD.

Random mode still reports its applicable `next_probabilities` and waiting ages,
with `mode: random`. Learned mode omits those unused scheduler fields. RLBot
v5 runtime logs use the corrected status too; re-export a personal bot if you
want an existing standalone export to contain the updated runtime source.

The new tests reproduce the misleading 834-Chronos-decision example, distinguish
learned from random probabilities, preserve a learned choice under its option
mask, update probabilities at the next free choice and clear them on reset.
