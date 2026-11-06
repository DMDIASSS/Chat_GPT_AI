# Leave one selector job running

With the older installation, launcher 27 already trains continuously with checkpoints and regression checks. Use 33 first, while paused, to enable adaptive opponents. Keep Fusion frozen as an expert rather than running Fusion and selector training simultaneously on the laptop.

The new unattended workflow uses the existing selector06 and its optimizer state. No new bot or full retraining is required:

1. Pause current training with 28 and wait for saving. Close viewer/game sessions.
2. Copy the ZIP's novaforge and triadbot folders into your existing Chat_GPT_AI, replacing program files. Preserve .venv, assets, runs and exports. No dependency reinstall.
3. Open 35_LEAVE_RUNNING.bat and leave its console open. Stop it with 28 or Ctrl+C. Keep the laptop plugged in and configure Windows to stay awake on AC power.

35 takes a startup backup and resumes one continuous PPO session. If adaptive opponents have never been configured, it enables them; an explicit disabled setting from 34 is respected. The existing goal/potential reward, six-expert roster, Octane body, six/eight-tick expert timing, rollout size, PPO updates, and balanced evaluation schedule remain in place. Frozen experts, including local Fusion, are unchanged.

At each saved 32768-decision segment it creates a shareable research ZIP. Existing automatic W/D/L checks compare latest with the retained champion and require fresh confirmation before promotion. Each distinct retained champion is exported locally for RLBot v5; unchanged champions are not repeatedly exported. The first startup export may still be the Fusion-routing initial champion, which is expected until promotion is earned. Artifact failures are logged and retried at the next save; checkpoint/training failures stop the job rather than starting an unverified replacement.

Find the latest report/export paths in triadbot/runs/selector06/autopilot.json. Reports are under triadbot/reports; exports are under triadbot/exports. Add the exported bot.bot.toml to RLBot v5 on this PC. Final pause/halt also saves a report. Model regression stops remain effective, and autopilot does not clear a recorded model halt or automatically restart a failed job.

Speed work in this version:

- Frozen CPU expert inference uses TorchScript freezing in float32. There is no quantization, half precision or PPO-network rewrite. Native feature/logit fixtures also check compiled action agreement.
- The six-expert simulator skips construction of unused 276-feature observations on its two-tick substeps. Physics, rewards, metadata and the final selector observation still update normally.
- Frozen Fusion identity is hashed on first use and rechecked when its file/metadata signature changes, instead of rereading the same archive every reset.
- Six-expert evaluation reuses loaded opponent controllers across matches and goals. Their reset methods still run for every new episode; this cache belongs to one evaluation call, with no shared live controller across parallel jobs.

The measured cloud environment throughput gain is modest, not 10x–100x. See PERFORMANCE_v1.13.json for three alternating before/after runs, workload and limitations. It measures native environment decisions/s, excludes PPO/evaluation/export, and is not a benchmark of the user's i5-10300H or GTX 1650 Ti. Training now logs throughput/training_decisions_per_second (segment including PPO/save work) and throughput/effective_decisions_per_second (whole session including evaluation/artifacts). These rates distinguish simulation throughput from useful end-to-end training time.

For a local measurement, pause with 28 and run 36_BENCHMARK_SPEED.bat. It warms up then times a fixed 2048-decision workload across six experts and the base opponent mix, without changing checkpoints. Share the selector06_speed_*.json with the progress report. Keep other training jobs/viewers closed during the measurement.

A full native GigaLearn backend is not included. That is a separate integration: port the 240-input selector and option masks, all expert-specific timing/observations and frozen models, the reward/terminal accounting, and regression/export contracts; then compare equal-sized rollouts with batched teacher inference on CPU/GPU. GigaLearn's aggregate SPS must be measured on the same workload and learner-decision definition before comparing it with this serial runner. The next useful experiment is a small parity/throughput pilot, not an expensive full retrain or a checkpoint replacement based only on speed.
