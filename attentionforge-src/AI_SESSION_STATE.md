# AttentionForge Offense 0.6 handoff

Current user objective: keep existing ball control, improve precise scoring, jump/flip use and half-flip-like recovery. User reports most goals arise from a center kickoff boost mismatch.

Implemented: preserve skills01 and fork exact trained state into attack01; native attack_v1 goal/aim/movement rewards; diverse finishing/elevated/recovery and all-five-kickoff resets; temporary legal mechanics rehearsal from successful physical trajectories; separate context panels, early/later goal logs, isolated skill probes, immutable snapshot-safe actor pins and exact pinned watch/export.

Limits: user actor at 13M was not uploaded. Server pilots use an earlier server-trained model. Short continuation preserved contact but did not establish learned flips/aerials or overall strength. One pilot lost diagonal kickoffs; new reporting exposes this instead of hiding it in an aggregate.

Next local action: pause/exit Python, merge the update into attention_skills, OFFENSE.bat -> 1. Source weights/optimizer/history are inherited; old run stays intact. Menu 4 reports diagnostics, 6 runs longer context panels, 8/9 watch/export the unverified open-play pin.

No private Discord exports, API keys, game assets or user weights are distributed. Source, validation and installation details: OFFENSE_GUIDE.md and OFFENSE_VALIDATION.json.
