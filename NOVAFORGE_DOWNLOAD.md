# NovaForge v1.10 / TriadBot v1.3: selected/refined Fusion as a fourth expert

[Download the full combined source ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-Triad-four-experts-v1.10.0.zip)

Adds an isolated workflow: compare available saved Fusion students with fresh confirmation, refine a copy toward 131072 new decisions with self-play and a regression guard, then freeze the retained champion for a separate four-choice selector04. Original selector01/fusion01 runs are preserved. Corrects learned watch/runtime probability logs; those previously showed the unused random scheduler's probabilities.

Pause old training, wait for saving, and stop watch consoles. Copy chat_gpt_ai/novaforge and chat_gpt_ai/triadbot from the ZIP into the existing Chat_GPT_AI, replacing program files. Keep .venv/assets/runs/exports. No dependency reinstall or model reset.

In triadbot: 14 compares saved Fusion candidates; 15 prepares isolated refinement; 16 runs/resumes bounded refinement; 17 creates the four-expert run; 18 trains it. 19 pauses, 20 watches latest, 21 diagnoses, 22 exports champion, 23 reports, and 24 pauses refinement. The initial four-way champion routes to Chronos until a student earns promotion.

[Full workflow and limitations](NovaForge/FOUR_EXPERTS_v1.10.md) · [Candidate audit and 2v2 roadmap](NovaForge/EXPERT_AND_TEAM_PLAN_v1.10.md) · [Corrected learned telemetry](NovaForge/SELECTOR_TELEMETRY_v1.10.md) · [Validation](NovaForge/VALIDATION.md)

The working runtime remains 1v1. Extra bot sources are audited, not silently installed as unverified headless policies. The new original scripted demochaser is a small stress opponent, not a port of Adversity. These changes do not prove a stronger bot.

Individual source ZIPs: [NovaForge v1.10.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.10.0.zip) and [TriadBot v1.3.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/TriadBot-v1.3.0.zip).

Source only: no weights or private reports. Personal model exports bundle locally downloaded/frozen teachers with matching metadata and notices. Published on codex/novaforge-v1; main is unchanged.
