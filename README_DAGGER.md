# Chat GPT AI — Nexto DAgger Recovery (experimental)

Your original 30,000-example Nexto imitation student scored 0/10 against Nexto and made 4 contacts vs Nexto's 289. **Do not start long PPO from this student yet.** These files keep existing replay datasets and checkpoints intact.

## Why this exists

The teacher dataset was produced in states Nexto itself visited. In matches, the student reaches different, harder states due to its own mistakes (*covariate shift*). DAgger (Dataset Aggregation) fixes part of this by asking Nexto to label **states visited by the student**, not only perfect teacher states. Because student-only rollouts may collapse immediately, the collector mixes teacher actions into student play with `--teacher-probability 0.5`. The opponent is always Nexto.

The new trainer also balances teacher **soft** probabilities (KL) with the single **most likely teacher action** (CE), measured on complete held-out episodes. The 92-input observation may still be too weak to clone Nexto reliably; evaluation tells us whether this is worth scaling.

## Windows quick start

Unzip **all files directly** into `E:\Downloads\Chat_GPT_AI`, beside `train.py`. Do NOT delete your `data` directory.

0. `STEP_0_BENCHMARK_AUDIT.bat` — Run Nexto versus itself to catch a side-bias or fairness bug in the benchmark before attributing every loss to the student. Over 20 matches it need not be perfectly balanced, but a systematic advantage is suspicious.
1. `STEP_1_DAGGER.bat` — Collect 15,000 additional decisions from the existing student/Nexto mixture; saves new `nexto_rollout_*.npz` shards, without overwriting earlier data.
2. `STEP_2_DISTILL_V2.bat` — Train a new policy, saving `data\nexto_student_v2.pt`; the original `nexto_student_policy.pt` is untouched.
3. `STEP_3_BENCHMARK_V2.bat` — Compare v1 and v2 against Nexto with the same seed, side swaps and 20 first-goal episodes.

Interpretation: if v2 gets more touches or goals, repeat DAgger with v2 checkpoint, gradually reducing teacher control. If it remains near zero, **stop and investigate observation fidelity and capacity**; don't waste GPU/CPU hours in generic PPO.

## Manual options

```powershell
cd E:\Downloads\Chat_GPT_AI
.\.venv\Scripts\python.exe collect_dagger.py --checkpoint data\nexto_student_policy.pt --decisions 15000 --teacher-probability 0.5 --scenarios grounded
.\.venv\Scripts\python.exe distill_v2.py --init data\nexto_student_policy.pt --output data\nexto_student_v2.pt --epochs 30 --hard-weight 0.65
.\.venv\Scripts\python.exe benchmark_vs_nexto.py --checkpoint data\nexto_student_v2.pt --games 20 --seed 123
```

To try a second DAgger round **only after benchmarking v2**, gather new states using `--checkpoint data\nexto_student_v2.pt --teacher-probability 0.25` and save distillation to `data\nexto_student_v3.pt` with `--init data\nexto_student_v2.pt`. The collector does not overwrite earlier shards.

## Training context

- Your GTX 1650 Ti can distill these small datasets quickly; closed-loop teacher collection is primarily limited by CPU/Nexto inference on your i5-10300H.
- `--teacher-probability` determines how frequently the teacher controls the **student car** in the environment, not the label source. All labels are always Nexto.
- No replay token or internet connection required for this experiment.
- The model is still an experimental 92-feature student. It is **not Nexto-quality**, does not implement specialist mechanics, and no C++ conversion is claimed.
- The baseline benchmark is first-to-score only, excludes Nexto's scripted RLBot kickoff, and should be repeated across many seeds and scenarios if improvement looks promising.
- Nexto upstream model and related assets remain under their upstream CC BY-NC-SA 4.0 licensing conditions (noncommercial/share-alike); see `vendor/nexto/LICENSE.txt`.
