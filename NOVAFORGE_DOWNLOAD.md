# NovaForge v1.7.0 and TriadBot downloads

[Download NovaForge v1.7.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.7.0.zip)

[Download TriadBot v1.0.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/TriadBot-v1.0.0.zip)

Extract both into the parent of chat_gpt_ai. NovaForge contains chat_gpt_ai/novaforge; TriadBot contains chat_gpt_ai/triadbot. Preserve environments, assets and runs.

NovaForge: pause with 36, merge, run 1_CHECK, then 35 to upgrade/resume chronos01 with backed-up settings, eight-tick rewards, longer credit horizon, W&B, automatic timed W/D/L/confirmation and substantial-regression stops. 38 still watches latest; 51 watches the protected champion. 40 exports the champion as both .pt/.cfg and .lt/.toml; 41 reports; 50 compares latest with original Chronos. 43 starts the separate fusion01 probability-distillation/PPO experiment, with 44 pause, 46 W/D/L, 47 export and 48 report.

[Current instructions, safeguards, fusion pilot and exports](NovaForge/FINISH_AND_FUSION.md) · [Validation](NovaForge/VALIDATION.md)

TriadBot is a separate frozen three-model random router. Waiting experts gain probability; frequent/repeated choices lose probability. Run its 0 check, 1 watch, 2 portable v5 export or 3 W/D/L comparison. The generated personal export contains the three local models; the downloadable source ZIP does not.

[TriadBot instructions](TriadBot/README.md)

The small fusion pilot did not establish an improvement: original Chronos 6 W / 2 D / 0 L, raw ensemble 4 / 1 / 3, short single-student distillation 4 / 3 / 1 across eight matched 30-second simulator games. Experiments do not replace the user's existing good Chronos run. No reward guarantees stronger play; the export champion is protected by separate comparisons. Windows live games and laptop CUDA performance still require user testing. Native GigaLearn throughput is not claimed.

[Upstream review](NovaForge/UPSTREAM_REVIEW.md) · [Further plan](NovaForge/PLAN.md) · [Attribution](NovaForge/THIRD_PARTY.md)

Published on codex/novaforge-v1; main and the original project files are unchanged.
