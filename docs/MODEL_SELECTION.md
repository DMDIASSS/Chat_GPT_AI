# Staged checkpoint selection

`slater_model_selection.py` finds promising attention actors without a huge all-versus-all tournament. It preserves every source file, deduplicates equal **actor weights** across checkpoint containers and families, and exports independent portable actors into its own run folder. A different optimizer, critic or filename does not make identical actor weights a different competitor.

The default inventory reads only these exact families:

| Family | Sources |
| --- | --- |
| Mechanics | `data/isolated/mechanics_curriculum/selected7_mechanics01/update_*.pt` and `accepted*.pt` |
| Team | `data/isolated/team_campaigns/update180_teams01/update_*.pt` |
| Native attention | `data/isolated/native_attention/runs/update180_attention02/checkpoints/checkpoint_*` |

Native attention directories need their completion marker and every checkpoint component. Incomplete native directories are reported and excluded. Original update180 and update278 are mandatory protected anchors by default. Missing anchors fail explicitly instead of silently substituting Nexto. An incompatible optional family checkpoint is listed in the inventory with its reason. These tools evaluate the original 44-tensor / 444,032-parameter attention architecture; the older native MLP `.lt` checkpoints need their separate evaluator.

## What runs

1. **Screen:** every distinct family actor, 20-second 1v1 games, one shared seed, both colors, against Nexto and update180. This is a cheap exploratory screen, not a best-model verdict.
2. **Refine:** retain the first eight per family, **all exact cutoff ties**, up to four additional uncertain neighbors and all protected anchors. Test fresh seeds, 30-second games, fixed rivals, and 1v1/2v2/3v3.
3. **Finalists:** retain four per family, additional mode leaders and anchors. Test fresh seeds and 45-second games against the fixed pool and one leading candidate per family as extra rivals. The candidate policy controls its own squad. This samples useful head-to-head contests rather than all checkpoint pairs.
4. **Confirm:** overall leaders, mode leaders and anchors receive eight fresh seeds, 60-second games, both colors and the fixed pool, again using candidate-policy squads.

Every candidate and original update180 receives matched opponents, seeds, colors and match durations. Reference games are cached and reused. Ranking uses the change in goal difference per simulated minute relative to matched reference games; raw scores, win/draw/loss counts, worst seed performance and early concessions are retained too. Early concessions count goals shortly after a kickoff; they help locate fragile starts but do not by themselves diagnose overcommitment. Intervals cluster all colors and opponents by seed and apply a conservative comparison-count adjustment. A single seed has **no confidence interval**. Exact score ties are retained in later stages and mode specialist pools, so a shortlist may exceed four when the evidence cannot distinguish the models. Use a bounded game budget to pause a large unresolved pool; the report marks unresolved ties rather than claiming a verified top four. Even a positive held-out result is not a guarantee of the best model or a competitive rank.

**Refinement evaluates one candidate car beside fixed update180 teammates. Finalists and confirmation also evaluate the candidate's whole squad.** Opponents use the selected rival policy. Every frozen-policy car has scripted kickoff ON, including the candidate's teammates. The selected candidate car's kickoff script is OFF by default. These are explicit team-composition tests, not a claim of fully unscripted team performance. Mode-specific rankings remain separate, so a promising duelist or teammate is not discarded just because its overall score is lower. Custom per-stage `team_policy` can be `fixed_reference` or `candidate_squad`.

## Windows commands

Pause training first if you want the selector to use your laptop's full resources. Existing source checkpoints can be read without changing them. Build the updated native attention executable once:

```cmd
cd /d E:\Downloads\Chat_GPT_AI
ATTENTION_NATIVE.bat build
```

Run inventory and selection together. CUDA is useful only if its parity/smoke checks have passed on this laptop:

```cmd
.venv\Scripts\python.exe -u slater_model_selection.py run --run best_models01 --device cuda
```

For an initial bounded experiment, screen at most 400 new games in this invocation:

```cmd
.venv\Scripts\python.exe -u slater_model_selection.py run --run best_models01 --device cuda --until screen --max-games 400
```

Use only **one** of the two start commands for a given run name. `--max-games` counts additional completed games in that invocation; it does not delete or exclude other candidates. Later, continue the same saved settings and caches:

```cmd
.venv\Scripts\python.exe -u slater_model_selection.py resume --run best_models01 --max-games 400
```

From another CMD window, inspect or pause it:

```cmd
.venv\Scripts\python.exe slater_model_selection.py status --run best_models01
.venv\Scripts\python.exe slater_model_selection.py pause --run best_models01
```

Pause stops launching new games and lets active games complete and save their records. A sudden shutdown can lose the active games, but already completed records remain reusable. Resume removes the pause request. It rechecks source/private model hashes, code, native binary, device, batch settings and runtime; changed protocols require a new run name. Do not edit config or run files to force a resume.

For inventory alone, use `inventory` instead of `run`; afterward use `resume` to start its games. Inventory progress is saved per checkpoint, so a resumed interrupted pass does not reload already inventoried actors. File size, modification time and SHA are recorded; actual SHA checks protect the source models before evaluation.

## Where results go

`data/isolated/model_selection/runs/best_models01/` contains:

- `inventory.json`: supported actors, every original path/alias, rejected files and protected anchors.
- `SHORTLIST.md` and `shortlist.json`: the latest completed-stage ranking, top four per family and per-mode leaders. Early rankings are provisional.
- `stages/<stage>/ranking.json`: complete paired statistics, seed means and intervals.
- `cache/records/<game-id>.json`: one durable complete native game per content-derived identity.
- `selection.json`: a verified portable `actor_path` for an **isolated continuation experiment**, its original source aliases, evidence and source hashes.
- `progress.json`, group manifests and logs: progress, exact game settings and diagnostics.

`selection.json` can recommend an exploratory leader even when the evidence is inconclusive. It sets `auto_promotion: false` and keeps `playing_model` pointing at protected update180. Do not treat “latest checkpoint”, high teacher KL, or the first screen's winning row as proof of superiority. Keep several shortlisted actors and compare their actual play.

Rebuild human-readable rankings from saved complete records without running extra matches:

```cmd
.venv\Scripts\python.exe slater_model_selection.py rank --run best_models01
```

## Custom pools and modes

Use `--config path.json` for exact settings. `families`, `rivals` and `anchors` maps replace their defaults. Adding named rivals such as cycle9, wavedash or v60 requires their **actual checkpoint paths**; a label does not invent a play style. Unsupported architectures fail explicitly. Example structure (replace the placeholder before running):

```json
{
  "rivals": {
    "nexto": "vendor/nexto/nexto-model.pt",
    "update180": "data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt",
    "update278": "data/isolated/mechanics_curriculum/selected7_mechanics01/update_000278.pt",
    "cycle9": "YOUR_ACTUAL_CYCLE9_CHECKPOINT.pt"
  },
  "stages": {
    "screen": {"rivals": ["nexto", "update180"]},
    "confirm": {"seconds": 120, "formats": ["1v1", "2v2", "3v3", "1v2", "2v1"]}
  }
}
```

Every stage must use distinct seed namespaces. The default four-stage plan is finite; its duration depends on the number of distinct actors, opponents, game length and hardware. The progress files show the exact planned game count. These measured budgets are much smaller than evaluating every pair of hundreds of checkpoints 50 times, but no laptop-independent completion time or strength improvement is promised.

Cloud integration tests explicitly replace the missing Windows anchors and family paths with local Nexto-derived fixtures. That is test configuration, not a fallback in real runs.
