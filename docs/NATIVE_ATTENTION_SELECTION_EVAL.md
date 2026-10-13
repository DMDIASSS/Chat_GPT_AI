# Native batched checkpoint evaluation

`AttentionEval.h` supplies an inference-only evaluator for portable copies of
original Nexto attention actors. It keeps one candidate-controlled slot per
arena. In team matches, every other car is frozen: teammates use the same
reference actor, and opponents use the selected rival actor. These results
measure the candidate slot in a fixed team context; they do not measure a team
made entirely of copies of the candidate.

The native entry point is:

```cpp
nlohmann::json slater_attention_eval::run_batched_evaluation(
    const std::filesystem::path& manifest,
    const std::filesystem::path& meshes,
    const std::filesystem::path& out,
    torch::Device device,
    const std::filesystem::path& pause_file,
    int batch_worlds = 8,
    int sim_threads = 2);
```

It initializes RocketSim, runs bounded independent arenas, and returns the same
summary written to `out/evaluation.json`. The caller configures Torch thread
counts and verifies all portable actor SHA-256 values before and after native
invocation. Actors load lazily, and immutable loaded modules are retained only
while active arenas need them. The module contract is 44 parameter tensors,
444,032 parameters, tuple input `(q, kv, mask)`, and a tuple containing 90 logits.
A LibTorch MLP `.lt` checkpoint cannot be passed as an attention actor.

## Manifest contract

The schema is version 1. Paths may be absolute or relative to the manifest.
`protocol_sha` pins the overall Python experiment protocol. Actor IDs and job
IDs consist of ASCII letters, digits, underscores, or hyphens. Each manifest
includes at least one job controlled by the protected reference.

```json
{
  "schema": 1,
  "protocol_sha": "<64 lowercase hex characters>",
  "reference_id": "baseline180",
  "actors": [
    {"id": "baseline180", "path": "actors/baseline180.pt", "sha256": "<digest>"},
    {"id": "candidate278", "path": "actors/candidate278.pt", "sha256": "<digest>"},
    {"id": "nexto", "path": "actors/nexto.pt", "sha256": "<digest>"}
  ],
  "jobs": [
    {
      "id": "<stable per-game digest>",
      "candidate_id": "candidate278",
      "rival_id": "nexto",
      "reference_id": "baseline180",
      "format": [2, 2],
      "seed": 10001,
      "learner_team": "orange",
      "seconds": 60,
      "learner_scripted_kickoff": false,
      "frozen_scripted_kickoff": true
    }
  ]
}
```

The abbreviated example must also include a matching baseline180 job. A
format `[2, 1]` means two cars on the candidate's team and one on the opposing
team, independently of learner color. All side sizes from 1 through 3 work.
There is exactly one candidate slot. Optional `cache_dir` selects a shared
record directory; its default is `out/records`.

Inference is greedy over the original unmasked 90-action lookup table. Learner
kickoff defaults OFF. If enabled, the learner uses the exact per-packet frozen
Nexto kickoff clock; teammates and opponents always use it. Scripted and learned
learner modes use distinct cache identities. Every job runs the full requested
physics duration. A goal credits its scorer and restarts a kickoff; it does not
end the allotted match early. Post-goal seeds use `seed + 7919 * episode_index`,
so matching candidate/reference jobs share their kickoff sequence.

## Cache and interruption behavior

The scheduler batches learner rows by candidate policy and ready frozen-car
rows by fixed policy across active arenas. Physics advances at 120 Hz, with one
old-control tick plus seven new-control ticks per learner action. Independent
arena ticks can execute in the simulation thread pool.

Each complete game is written through a temporary file to
`cache_dir/<job.id>.json`. The saved descriptor includes actor weight hashes,
fixed teammate/rival hashes, format, seed, color, duration in ticks, kickoff
settings, device, batch limit, action/clock contract, and compiled backend
identity. A reused record must match this descriptor exactly. A stale record,
different configuration, malformed completion marker, or concurrent writer
causes a clear failure instead of silent reuse. Job IDs should therefore include
these per-game settings, rather than the complete candidate inventory, to allow
reference games to be reused across selection stages.

`out/native_protocol.json` pins the manifest and native runtime settings for a
resumed invocation. A pause file stops new game scheduling and lets the active
bounded set finish. Resume skips complete records. An abrupt interruption
restarts only unfinished games; physical arena snapshots are not serialized.
No actor weights, original checkpoints, or source replays are modified.

## Output contract

Each record preserves its job fields and adds:

- `model_id` and `candidate_id`, `rival_id`, `reference_id`, `is_reference`;
- `goals_for`, `goals_against`, aliases `gf`/`ga`, and `goal_diff`;
- exact simulated `seconds`, `physics_ticks`, and `episodes`;
- `learner_touch_ticks`, `goalward_touch_ticks`;
- `early_goal_concessions`, `early_goals_for`, measured within the first 10
  seconds of each kickoff episode (a timing diagnostic, not proof of overcommit);
- `learner_script_ticks`, `frozen_script_ticks`;
- `policy_sampling: false`, `finish: "COMPLETE"`, `game_complete: true`;
- `descriptor` for cache verification.

Touch counts are physics ticks with contact, not unique touch events. A summary
has `status: "FINITE_EVALUATION_COMPLETE"` or `"PAUSED"`, `completed`, `planned`,
`cached`, `records`, wall time, inference-row and physics-tick counts, maximum
simultaneously loaded actor count, device, and backend/protocol identities.
`promoted` and `confirmed` remain false: selection, fresh-seed confirmation, and
mode-specific ranking belong to the Python campaign layer.

The executable emits one `SLATER_SELECTION_GAME` line per newly finished game.
Its caller emits `SLATER_SELECTOR_COMPLETE` with the returned summary.
