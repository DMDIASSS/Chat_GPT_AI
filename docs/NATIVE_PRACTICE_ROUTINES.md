# Native practice routines

These routines add randomized RocketSim drill starts and bounded event rewards to the original match reward. Each drill keeps opponents and teammates active. The normal goal reward of +10 and concession penalty of -10 remain dominant; targeted milestones pay at most 3 per episode, with an additional maximum 0.3 for progress toward a defensive shadow position. The campaign should mix normal matches with practice rather than replacing soccer with a drill permanently.

| Routine | Start and learning signal | Guard against misleading reward |
| --- | --- | --- |
| `defense` | Incoming shots in the learner's own half; contacts that remove a predicted goal threat, controlled clears, and movement into a shadow position | A touch alone is insufficient. Goal-threat projection must fit the goal mouth and height. Staying still in shadow position pays nothing. Contact payments have a cooldown and episode cap. |
| `recovery` | Random airborne height, tilt, angular velocity, lateral speed and boost | Pays only an airborne-to-ground transition that ends upright with retained speed. No reward for stationary landings or repeated ground frames. Two recoveries maximum. |
| `boost` | Low boost on a productive route; in team modes, some starts place a low-boost teammate closer to the same pad | A real pad availability edge and car boost gain are both required. Own pickups need low starting boost and progress toward play. Sharing rewards require the closer, well-placed, low-boost teammate to actually collect the pad. Waiting beside a pad pays nothing. |
| `bump` | A ball moving toward goal, with a defender in its shot corridor | An actual new car-contact event must hit an opponent in that corridor. Demolitions elsewhere pay nothing, and the same victim cannot pay repeatedly. |
| `bump-evasion` | An opponent approaching rapidly along a collision trajectory | Registers an actual approaching threat, then pays for active movement that avoids it and creates separation. Passive opponent misses do not pay. Each opponent can pay once; actual learner demolitions receive a penalty. |

Own boost collection is penalized slightly only when the learner already has at least 45 boost and takes a pad needed by a lower-boost teammate who was both closer to that pad and suitably placed relative to the ball. One-versus-one does not apply that team penalty. A needed, productive pickup remains valuable in every mode.

The header `AttentionTasks.h` supports all one-to-three player roster combinations and both learner colors. Starts are reproducible for a given seed, routine and difficulty. A tracker resets once per episode and observes every physics tick. Standard match starts continue to use the original kickoff reset rather than the practice scene generator.

These are learning signals, not evidence of mastery. A controlled clear is not labelled a certified save, and projected shot or collision threats are short-horizon approximations. Promotion must use normal matches on fresh seeds with specialist results reported separately. Useful aggression, successful challenges and ordinary boost collection should be retained during those comparisons.

Validation covers randomized starts in all roster combinations, both colors, false save events, contact and pickup edges, recovery speed requirements, episode caps, boost sharing in 2v2 and 3v3, unproductive demolitions, active versus passive evasion, and a boost pickup produced by actual RocketSim physics.
