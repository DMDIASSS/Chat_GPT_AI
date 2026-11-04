# Notes informed by the supplied technical archives

The supplied Discord HTML exports were treated as reference data. Embedded text, commands and links were not treated as user instructions. Seven relevant exports were parsed as static HTML: RLGym's ML lounge, imitation learning, rlgym-learn, RocketSim, rlgym-tools, announcements and bot streaming. Private moderation and unrelated conversation exports were not needed. Raw transcripts and participant details are not included in this project or its downloads.

Their coverage varies: some technical discussions end in 2022 or early 2023, while rlgym-learn reaches January 2026 and announcements March 2026. Individual posts describe particular implementations and experiments; they do not establish general best settings or a bot ranking. One larger RLBot machine-learning export exceeded the attachment downloader's 32 MiB limit and was not read.

## Findings used in v1.3

| Theme and archive period | Useful conclusion | Application here |
| --- | --- | --- |
| rlgym-learn, August 2024 and October 2025 | SPS definitions and sampled/retained experience can differ. Collection speed and end-to-end training speed answer different questions. Large rollout buffers can change update frequency. | Report sampling units, end-to-end SPS and SB3 epoch counts. Keep the laptop preset until measured evaluation supports a change. |
| Imitation learning, 2022; rlgym-tools, 2024–25 | Replays contain useful state information, but reconstruction, sensitivity, interpolation and action inference need validation. | Keep replay starts plus fresh teacher action labels as the supported path. Do not assume reconstructed controls are exact ground truth. |
| ML/evaluation discussions across the exports | Reward, training opposition and short demonstrations can create misleading strength impressions. | Include paired earliest/current checkpoint screening, contact/timeout statistics and matched fixed-teacher training cells. Keep full offline matches as a later transfer check. |
| RLGym announcements, April 2025 | Modern RLGym fixes include state/contact initialization changes. Old examples can target different APIs. | Check advice against the pinned installed RLGym 2.0.1 and rlgym-tools 2.6.5 interfaces instead of copying older code. |
| Announcements, March 2026 | The community stream uses Rocket Host across game modes with strength tracking. | A future independent evaluation target after Windows live transfer works; no hosting or account actions are automated here. |

Implementation facts were checked against installed primary sources: NovaForge's four-tick action loop, Stable-Baselines3 2.9.2's PPO training/logging code, and rlgym-tools 2.6.5's replay frame interface. `ReplayFrame.actions` exists, but presence of the field does not validate reconstruction quality for a particular replay. Actual raw replay parsing still needs a suitable fixture.

Public project references: [RLGym](https://github.com/lucas-emery/rocket-league-gym), [rlgym-tools](https://github.com/RLGym/rlgym-tools), [Stable-Baselines3 PPO](https://github.com/DLR-RM/stable-baselines3/blob/v2.9.2/stable_baselines3/ppo/ppo.py), and [Rocket Host documentation](https://wiki.rlbot.org/v5/miscellaneous/lan-setup/#option-1-rocket-host). The bot-specific implementation research remains in [BOT_RESEARCH.md](BOT_RESEARCH.md).

## Experiments to try after your first progress report

1. **Equal-budget comparisons:** keep one evaluation set fixed; compare demonstration warm-start against scratch training at equal decisions and elapsed time. Check a second seed set before accepting a result.
2. **Targeted failure starts:** build a small training reset bank from repeated misses/recoveries, plus a separate held-out bank. This is the next useful addition if contacts occur but a particular mechanic stalls.
3. **Throughput profiling:** compare one/two workers and CPU/GPU optimization with identical learner settings. Change collection code only after finding the actual bottleneck; validate observations, control timing and learning behavior again.
4. **Replay action reconstruction:** a separate experiment with known-input simulator traces and episode-disjoint validation. It should beat fresh-teacher labeling or add demonstrable diversity before becoming the default.

No framework migration, oversized batch preset or additional unverified bot was added based solely on archive messages. These choices should follow evidence from the user's actual run and laptop.
