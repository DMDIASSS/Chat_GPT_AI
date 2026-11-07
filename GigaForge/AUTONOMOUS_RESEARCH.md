# Autonomous research02

Current update: [paired evaluation repair and automatic training focus](PAIRED_REPAIR.md).
This update includes a NEW prebuilt native executable. Replace the native program
files while preserving models, optimizer checkpoints and the selected runtime.

Pause older trainers with their 4_PAUSE button and wait for them to finish. Merge
the update's chat_gpt_ai/gigaforge into your existing Chat_GPT_AI/gigaforge.
Your models, runs and environments are preserved. No new CUDA download or local
build is required for an existing working install.

Run **17_START_AUTONOMOUS_RESEARCH.bat once**. It creates research02 and selects it
for the other buttons. Thereafter **3_START_OR_RESUME** resumes the active study.
If you only run 3 while research01 is active, it resumes research01 unchanged.
An existing research02 is resumed, never reinitialized or silently reconfigured.

The five-hour session budget remains. Send 8_REPORT after the first hour, then
after a full session. 4_PAUSE safely pauses, 5/6 watch retained champions, 10/11
watch unverified latest candidates and 7 exports retained .pt/.lt + v5 TOML
bundles. Viewer behavior is unchanged. Research01 can be resumed explicitly with
`python run.py research --run research01` using the selected project runtime.
Do not run competing trainers together on the laptop.

## Decisions made by the coordinator

- Two independent full-size pretrained actors: Chronos on Breakout and Galactus
  V2 on Octane. New initialization uses approved research01 champions if that
  predecessor is stopped, otherwise protected native01 champions or originals.
  Experimental candidates are never chosen as parents.
- Four reward/learning-rate profiles, hard-opponent sampling with a uniform
  exploration floor, original opponents, accepted opponents/history and periodic
  self-play. PPO/reward physics, original feature contracts, FP32 and epochs are
  unchanged. No private opponent controls enter the exported actor.
- Train 65,536 decisions between screens. Branches can reach 524,288 decisions
  before restarting, versus 131,072 previously. Branch optimizer state resumes.
  Coefficient mutation waits until every current profile has three measurements;
  a single lucky first screen no longer replaces a profile.
- Screen on 32 fresh seed pairs per opponent, both colors. With two opponents
  this is 128 candidate and 128 baseline games, each 60 simulated seconds.
  Positive point estimates of at least 3 percentage points can be nominated even
  when the development confidence interval crosses zero.
- Confirm on a separate fixed budget of 128 fresh seed pairs per opponent:
  512 candidate and 512 baseline games with two opponents. Stages finish their
  fixed budgets before a decision. Three opponents increase these totals.
- Promotion requires a positive paired match-score interval and at least a
  3-point estimated gain, plus per-opponent match-score noninferiority within
  10 points, and scoring/conceding/goal-difference noninferiority within 0.25
  goals per simulated minute. These are confidence-bound guards, not just point
  estimates. Conceding improvement is positive when the candidate concedes less.
  Small tolerated changes are not claims of improvement in every aspect.
- Later champions also pass an extra fresh comparison against the study's
  starting actor, not only their immediately preceding champion.
- Confirmation uses summable error budgets alpha_n = .05 / (n*(n+1)), shared
  across the study; a paused confirmation reuses its index. All guards must pass.
  Approximate paired Student-t intervals assume independent seed blocks within
  fixed opponent strata; this is not an exact lifetime statistical guarantee.
- Two best positive-screen actors per family are copied into shortlist outside
  checkpoint rotation. They remain UNVERIFIED and are never champion exports.
  Reports include their identities/statistics but omit weights. Active branch
  optimizer checkpoints remain separate from these actor-only snapshots.

## Evaluation speed and resume

Native physics already runs in parallel and inference is batched. The new default
packs 32 seed pairs per opponent into each native job (256 games including both
actors with two opponents), instead of eight. This increases useful GPU batches;
there is no promised laptop speed multiplier. Larger confirmation runs are split
into bounded jobs so memory use does not grow with the whole tournament.

Each completed job is cached using both actor files for every model, native
executable, evaluation controller, meshes, Torch/runtime/device, thread settings,
opponent names, seeds and match duration. Partial jobs are rerun. Completed jobs
are reused only for the same experiment request; different checkpoints do not
share old results. This avoids replaying completed work after a pause. Progress
appears at each job boundary and every ten wall seconds during native execution.
Native errors have saved per-job logs in reports.

Current native-compatible opponents are Chronos and Galactus families. Match
statistics measure this simulator panel, not aerial/recovery success in isolation,
team play, all available RLBot opponents, or live Rocket League strength. Those
claims require separate tests. Longer 60-second suites and more games can reject
noise; they cannot guarantee that training discovers a better policy.
