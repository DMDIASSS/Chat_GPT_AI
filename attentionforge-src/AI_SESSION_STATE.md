# AttentionForge Skills handoff

Current task: user explicitly requested a complete reward-based attention training project, with measured early improvement, watch, export and unattended checks. Historical replay-only scope in the linked code-review repo is a separate older task.

Implemented: analytic ground-driving BC warm start, physical contact gate, protected PPO continuation, varied curriculum resets, established touch/acceleration rewards, goal-gated distinct-event combos, periodic validation and bounded archive/restore recovery. Separate `attention_skills` project preserves existing runs.

Evidence: 41 tests passed, one CUDA-only test skipped; Windows native build passed. After 327,680 PPO transitions, fresh contact tests reached 84.375% stationary and 99.21875% moving, both colors combined. A 100x60-second parent panel yielded 23W/68D/9L and goals 35:14; conservative interval crosses 50%, so match advantage remains unconfirmed. The rejected first continuation pilot and full results are recorded in SKILLS_VALIDATION.json.

Export: real TorchScript PT and LT readers, SDK-tested v5 adapter/delay clock, unique agent IDs, v4 wrapper; actual Rocket League connection and user-GPU throughput remain unverified. No external strong-bot evaluation or current user actor was available.

Next local action: SKILLS.bat, choose 1. It learns ground approaches then starts PPO and monitors contact. Menu 4 packages reports. No private logs, user model files, API keys or game assets are distributed.
