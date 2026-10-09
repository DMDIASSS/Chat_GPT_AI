# Chat GPT AI: concrete route to Nexto+ with mechanics

## Important baseline

- `data/nexto_student_v2.pt` is not Nexto-strength (latest 20-game first-goal benchmark: 0/20 versus Nexto). It is a 92-input imitation student. **Do not assume more DAgger data automatically fixes it.**
- `vendor/nexto/nexto-model.pt` is the original Nexto learned policy. It already plays at a substantially higher level in offline RocketSim first-goal tests.
- `data/native_nexto/last.pt`, if it exists, is an **experimental fine-tuned Nexto actor**. It may be better or worse than original; only use it after evaluation against the original over multiple seeds and both sides.

## Development milestones (each requires measured pass/fail)

1. **Native baseline**: verify original Nexto plays correctly with its original attention observations. Record win/loss, touches per 1000 decision ticks, shots, and errors in a seed-controlled 1v1 test. Existing native viewer shows baseline but does not evaluate skill.
2. **Native PPO no-forgetting**: keep frozen original Nexto as anchor and regularization reference; ensure no drop in 1v1 strength across several random seeds. Avoid claiming improvement based on one reward number.
3. **Kickoff specialist**: create stable mirrored kickoff scenarios for multiple spawn positions; record time-to-ball, first touch, ball exit speed/direction, possession at 1.5s, and goal conceded. Start with a *verified* scripted baseline or trained policy; speed flip and wavedash should only count if actions and motion are correct, not if jump happened.
4. **Ground and wall specialists**: diverse starting states (facing away, low boost, wall entry, recovery). Track measured touch success, shot speed, grounded recovery duration, dribble possession and saves. Randomize sides, velocities, and starting yaw.
5. **Air dribble / flip reset / ceiling / double tap**: spawn varied ball-car states, not generic 1v1 kickoffs. Define success from physical events (sustained air control, flip availability regained after roof contact, successful second touch off backboard, shot accuracy). Mix failures and successful demonstrations; avoid rewards for spinning or jump count.
6. **Integration**: a mode-choosing controller routes a small subset of states to mechanical specialists while general Nexto/native policy handles the rest; later distill to unified architecture. Train on replay and self-play data as supplementary guidance, not proof of skill.
7. **Competitive evaluation**: 100s of offline games with both sides swapped and fixed/randomized seeds, then separately scored specialized drills. New policies replace the champion only after statistically meaningful improvement. Never deploy to online ranked.

## Optimization after correctness

Port *the trainer*, not necessarily the native Nexto model, to a fast C++ experience collection backend after equivalence tests for state encoding, action lookup, tick skip, and policy outputs. A 10x faster broken input adapter is worse than a correct slower adapter. On i5-10300H / GTX 1650 Ti Mobile, avoid expensive CUDA sync on every 15Hz decision; first profile CPU sim and batched inference.

The viewer in this add-on measures touchdowns/goals only as coarse observation. It **does not** implement specialist training, add mechanical skill, or prove Nexto superiority.
