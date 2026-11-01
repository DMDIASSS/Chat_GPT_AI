# Findings from the supplied Discord exports

The useful direction is to retain the strong policy, verify its observation/action interface, improve the training objective, and then optimize measured bottlenecks. The exports contain useful native-framework leads. They do not establish that changing programming language alone produces a stronger bot.

## What was inspected

The supplied `Discord.rar` contains 54 regular HTML files totaling 480,145,927 decompressed bytes. The archive SHA-256 is `54fcd2ffd7f8f7510823969f2f5cad2056196e2e37abf0fd51daee44de263169`. It was read without executing embedded code or downloading attachments. Every member path was checked; extraction accepted only regular HTML/text/JSON files within size limits. The original archive and uploads were preserved.

The complete local scan covered **73 HTML paths**, including the archive and 19 separate HTML uploads. Hash deduplication leaves **56 distinct files**, and channel/message ID deduplication leaves **577,620 messages**. There were zero parser errors. Eleven distinct files contain no message containers, including several restricted-channel exports. An empty exported file does not provide access to the conversations that might have existed in that channel.

Every available message body and message link was indexed. Targeted searches scanned the whole index; relevant hits were then inspected with neighboring messages. This is an automated complete-text scan plus a contextual review of the technical matches, not a claim that every conversation was read manually. Author names and account IDs are not indexed as metadata. The raw files, searchable text, context excerpts, and source inventory remain in ignored local `data/isolated/discord_research/`; they are not included in public updates.

The material is a set of **partial channel histories**, not live Discord access. Some useful coverage:

| Exported channel | Indexed messages | Export timestamp range |
| --- | ---: | --- |
| RLGym / rlgym-learn | 9,500 | August 2024–January 2026 |
| RLGym / imitation-learning | 6,900 | June 2022–January 2023 |
| RLGym / ml-lounge | 9,000 | September 2021–March 2022 |
| RLGym / rocketsim | 4,300 | February–March 2023 |
| RLGym / general | 4,600 | September 2021 |
| RLBot / machine-learning | 68,700 | November 2017–July 2021 |

Dates above describe the exported timestamps; their timezone is not inferred. Older advice may refer to removed APIs, old RocketSim behavior, or RLGym v1.

## Framework and speed findings

**GigaLearn is a useful candidate for an efficient training backend.** Discussions distinguish its threading, trajectory processing, batching, action masking, and league infrastructure from merely translating Python into C++. The public [GigaLearn source](https://github.com/ZealanL/GigaLearnCPP-Leak) is directly linked in the supplied January 2026 rlgym-learn messages. However, this does not imply that a different network can load an existing attention checkpoint without architecture and interface work.

The supplied text does **not corroborate an achieved 30-million end-to-end training steps/second benchmark**. Searches for `30M`, `30 million`, numeric equivalents, speed units, GGL, and custom frameworks found several references to total training steps and a 30-million-parameter network. Those are different measurements.

The closest unusually high throughput discussion is December 29, 2024 in rlgym-learn. It separately mentions approximately 600 million RocketSimCUDA physics ticks/second and 20 million batched policy inferences/second. The same conversation describes inaccurate car-ball collisions, incomplete implementation, and an aspiration for about two million overall steps/second. These are contextual community claims, not independently reproduced results. Multiplying simulation speed by network inference speed would be invalid.

Relevant local evidence IDs:

- `1269505204936507423:1322751110699552840`: separate CUDA physics and batched-inference claims.
- `1269505204936507423:1322750888325943297`: desired overall throughput.
- `1269505204936507423:1322751301666213909` and `1322751450765590568` in the same channel: collision-accuracy limitation.
- `1269505204936507423:1397401847874191360`: proposal for a comparable setup across several frameworks.
- `1269505204936507423:1463459394493743188`: public GigaLearn masked inference and normalized-entropy source.

For a meaningful comparison, report **environment decisions/second, agent decisions/second, physics ticks/second, collection time, optimization time, and total elapsed time** separately. Also record hardware, number of cars/environments, tick skip, network size, batch size, precision, and whether gradients/evaluation run. The final criterion is match strength gained per hour with the same starting policy and evaluation conditions.

## Public leads worth investigating

These links were found in the exports. A link in chat is a research lead, not proof of compatibility, current maintenance, or strong training results. Public-source inspection is recorded separately in [FRAMEWORK_RESEARCH.md](FRAMEWORK_RESEARCH.md).

| Lead | Why it matters | Context and qualification |
| --- | --- | --- |
| [GigaLearnCPP](https://github.com/ZealanL/GigaLearnCPP-Leak) and [RLGymPPO_CPP](https://github.com/ZealanL/RLGymPPO_CPP) | Native rollout/PPO implementations; compare batching and model loading | Inspect pinned source and preserve existing actor semantics before switching. |
| [rlgym-learn](https://github.com/JPK314/rlgym-learn) and [rlgym-learn-algos](https://github.com/JPK314/rlgym-learn-algos) | Separate environment collection from learning algorithms; Rust-backed processing discussions | More flexible Python-facing components can introduce overhead; profile the actual workload. |
| [rlgymppo_rs](https://github.com/VirxEC/rlgymppo_rs) and [rocketsim-rs](https://github.com/VirxEC/rocketsim-rs) | Rust learner and simulator bindings | The July 2025 learner link appears in a discussion requesting fixes because it was not learning. Its present source must be checked; the historical link is not a success benchmark. |
| [Prism](https://github.com/AechPro/Prism) and [LeanRL](https://github.com/pytorch-labs/LeanRL) | Trajectory-processing, logging, and PyTorch optimization patterns | Techniques are candidates for isolated tests, not a requirement to replace the whole project. |
| [rlgym-tools](https://github.com/RLGym/rlgym-tools) | Team-spirit rewards, variable team-size mutators, replay conversion and reset rewards | Verify installed-version behavior and test state transitions; copied chat snippets contain mistakes. |
| [rlgym-learn-trueskill](https://github.com/ericle85/rlgym-learn-trueskill) | League evaluation and rating examples | Ratings need consistent opponents and enough matches; a screen is not independent certification. |
| [RLCarInputSolver](https://github.com/ZealanL/RLCarInputSolver) | Reconstructing missing aerial controls from replay dynamics | The tools conversation explicitly compares reconstruction errors; these are inferred controls. |
| [replay-pretraining](https://github.com/Rolv-Arild/replay-pretraining) | Supervised replay imitation design | Its November 2022 announcement explicitly calls it old RLGym v1 code to use as a reference. |
| [RocketLeagueGym-Rewards](https://github.com/Aiden-Frost/RocketLeagueGym-Rewards) | Interactive human input with RLViser | The linked message recommends its human-controller example, not its rewards as a proven best recipe. |

## Rewards and mechanics

The strongest practical warning is that a reward correlating with winning in human replays can still produce exploitable bot behavior. An October 2024 rlgym-tools discussion gives an example where a large irrelevant reward does not appear in professional play, but a learner can exploit it. More speed makes a flawed objective fail faster.

Use actual goals, concessions, useful touches and useful progress as primary outcomes. Track each reward component separately, including its total contribution per episode. Watch policies for farming contact, circling for speed, hoarding boost, or continuously jumping. A policy that drives and earns shaping reward while never scoring needs an objective/behavior audit before additional overnight compute.

For air dribbles and resets, distinguish a **contact event**, an acquired flip, a consumed flip, a useful follow-up touch, and a scored finish. Repeated wheel contact is not proof of a reset; a reset is not proof of a successful attack. Use simulator state transitions and physically checked episodes rather than copying a visual condition from chat. A July 2024 C++ flip-reset snippet in the supplied tools export has state/bookkeeping defects and should not be transplanted.

Evidence: `887306841745420288:1291028416505843813` (reward correlation warning), `887306841745420288:1257139661848182805` (compute shared touch/velocity information once per step), and `887306841745420288:1265302255159218187` (example reset snippet).

## Replay imitation

The imitation-learning and tools exports consistently separate replay states from player inputs. Aerial axes may be reconstructed with inverse dynamics; quantized/sparse recorded throttle and steer still require alignment. A long sequence of low imitation loss does not establish that the same policy can execute the sequence successfully in closed-loop physics.

Before adding more imitation, verify raw field coverage, time alignment, button transitions, team perspective, previous-action convention, and action projection. Split training/validation/test **by replay**, so adjacent states from the same match cannot leak across splits. Compare behavior-cloning-only, PPO-only, and mixed branches starting from the same strong policy. Check fresh match performance as well as replay loss.

Evidence: `887306841745420288:1251598878487085198` and `1251599030245523457` in the same channel discuss single-replay flip-cancel reconstruction errors. `990780700644999168:1047239659702464616` identifies replay-pretraining as historical reference code.

## Multiple team sizes

A May 2024 tools discussion specifically proposes a team-spirit wrapper, variable team-size mutator, random branch mutator, and non-padded observations for multiple modes. This supports pursuing mixed team sizes deliberately, rather than assuming a 1v1 policy becomes a good teammate by adding cars.

For 1v1 through 3v3 and uneven teams, preserve entity identity and masks, check orange-team transformations, apply rewards to the correct learner team, and keep experience from frozen opponents separate. Log results by team configuration. Train even-team modes alongside selected numerical advantages/disadvantages, then evaluate each mode independently. A 1v1 improvement can conceal a teamwork regression.

Evidence: `887306841745420288:1237701495592325120` and `1237703959204859924` in the same channel.

## What the user can supply if a lead is inaccessible

The current exports are already useful; another token-based export is unnecessary. For an inaccessible benchmark or custom framework, the useful missing evidence is the **exact public repository/commit or public benchmark page**, hardware, game/player counts, tick skip, network architecture, and the metric definition. For a claim visible only in a screenshot/video, share that screenshot or the short timestamped passage. Do not supply login tokens or private account credentials.

For this project specifically, actual local continuation logs, match-evaluation JSON, and behavior reports for update180 and its selected successor are more useful than another generic reward list. Cloud access does not provide control of the user's Windows computer or its running training process.

## Reproduce the local research

The tool is offline and uses only the Python standard library for HTML indexing and searching. RAR extraction is optional and requires trusted `libarchive-c` plus a system libarchive library. No Discord login is performed.

```bat
.venv\Scripts\python.exe slater_discord_research.py index "PATH_TO_YOUR_EXPORTED_HTML_FOLDER"
.venv\Scripts\python.exe slater_discord_research.py topics
.venv\Scripts\python.exe slater_discord_research.py search "gigalearn|ggl|rocketsimcuda" --out data\isolated\discord_research\framework_hits.json
```

`inventory.json` records file hashes, counts, empty exports and date coverage. `index.sqlite3` holds author-free message metadata and original body text. Topic/search JSON includes bounded excerpts and neighboring-message context. Keep these files local: message bodies can still contain mentions or private information even when author metadata is omitted. Evidence IDs are `<channel-id>:<message-id>` and can be located in the original HTML or the index.
