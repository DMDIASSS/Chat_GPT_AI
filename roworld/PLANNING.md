# RoWorld 2.0: five integrated planning features

This release implements the five proposed extensions together. It remains a
standalone strategy bot using public game observations and normal orders. The
planner compares explicit heuristic alternatives; it is not a trained network
or a full prediction of human responses.

## 1. Strategic map

`atlas.lua` takes a frozen copy of public ownership and incrementally scans it.
It identifies four-neighbour connected holdings, their land and building value,
the main economic component, sampled neutral frontiers, coastal edges and the
public adjacency graph between nations. It supplements the rotating frontier
scan with neutral frontiers and component construction sites. New nearby threats
from a recent complete graph feed the reserve calculation. Placement scoring
penalizes exposed locations and small detached components.

The default work allowance is 16,384 scan/flood steps per fresh tick. Completion
is asynchronous with respect to decisions: the bot keeps acting while a scan
runs. A new scan starts at least five seconds after completion. Reports include
the snapshot tick, age and scan status; topology over 30 seconds old does not
supply component lookups or frontier/neighbor hints. Every proposed order is
still checked against current ownership, resources, hazards and alliances.

The graph describes ownership connectivity, not troop pathfinding or guaranteed
military access. Only the largest 32 holdings are included in the report and
frontier augmentation. Ownership, labels and flood queue require about 24 MB
for a two-million-cell map, excluding component metadata and existing game state.
Copying the initial ownership snapshot is not split into scan steps.

## 2. Strategic alternatives and the cost of waiting

`planner.lua` compares defend, invest, expand, negotiate and relocate. It records
their scores/reasons, recent objective changes, feasible actions and selected
action. Realistic alternatives are passed to one selector instead of always
returning the first available purchase before considering expansion.

Stalled growth and observed growth of rival leaders raise the cost of waiting.
After 30 quiet seconds without material growth, a guard position may consider a
small expedition. This exception requires available troops and no current land
or local naval invasion/recovery warning. It retains the existing reserve,
limits maritime expeditions to at most 12% of the home bank and excludes new
human landing targets. Weak nonhuman land opportunities may also be considered
within their remaining campaign budget. Existing commitments, route checks,
peace requests and ownership constraints continue to apply.

The planner does not make a weak army strong, guarantee a safe destination or
force a plan to have a feasible action. Incoming invasions and recalls retain
priority over the ordinary alternative selector.

## 3. Investment evaluation

`investment.lua` ranks feasible purchases using marginal benefit, price,
placement exposure and asset concentration. City value includes the change in
recruitment from another 250K of capacity at the current troop bank. High-level
concentration carries a penalty. Factory and port values use observed potential
production links and allied water-body access; production targets now depend on
city levels, not only the number of separate city structures.

Factories and ports can therefore compete with repeated upgrades of one city.
Proactive SAM coverage remains valuable and savings are no longer disabled just
because a quiet core has a static threat flag. Imminent invasions retain their
separate construction priorities. The existing post count and replacement
purchase limits still apply.

Production payback numbers are explicitly marked as proxies. The bot cannot
promise that a proposed rail/trade route will be created, survive or deliver a
particular income. Reports expose the candidate costs, scores, risks and reasons
so those assumptions can be checked against actual matches.

## 4. Campaign objectives and exits

Enemy campaigns identify a capturable asset, a limited territorial corridor, or
the defeat of a tribe. They retain an allocation, cumulative spending, deadline,
progress and objective status. Proposed reinforcements are limited to the
remaining allocation. The initial allocation accommodates the first approved
order, avoiding immediate withdrawal just because that order exceeded a fixed
fraction of the bank.

An asset capture allows a brief consolidation interval: withdraw when nearby
probes show a buffer or after eight seconds, rather than instantly recalling on
the first captured frame. This is a bounded banking rule, not proof the entire
area is safe. Tribe objectives do not stop merely because the first border tile
was captured. The bot recalls when the objective is complete, an asset is gone,
the budget/deadline is reached, the front stalls or home defense requires it.
Another player's reduction of enemy land does not reset our progress timer.

Reports include current campaigns and up to 32 recent closed/recalled campaign
records. Neutral growth still uses recruitment-aware expansion budgets; enemy
campaign history is not a claim of causal attribution for every captured tile.

## 5. Persistent opponent evidence

`profiles.lua` stores observed attack sizes, attacks against us, naval sightings
and confirmed betrayals. A confirmed betrayal keeps a diplomacy penalty beyond
the temporary quarantine. Repeated observations of larger attack fractions can
increase the threat estimate used for reserves. No inferred intention is stored
as an observed fact.

Up to 128 profiles are kept, with old entries evicted to admit new opponents.
The available client state exposes display names, not a verified stable account
identity, so cross-match matching is uncertain and its betrayal penalty is
capped more tightly than confirmed betrayal within the current session.

Profiles survive Start/Stop and reinjection through memory. When the executor
supports files, saves write `RoWorld_Opponent_Profiles.json` beside the match
report and a later execution can read it back. Loading uses bounded JSON and
validates counters; it never executes file contents. Without file functions,
profiles remain in memory. Runtime diagnostics report storage mode and write
errors. Nothing is automatically uploaded. To clear all remembered profiles,
close Roblox and remove that JSON file before a new session.

## Verification and limits

- 161 offline behavior scenarios, dashboard/report export/profile handoff,
  reinjection cleanup, generated-source equality and Luau compilation passed.
- Four paired seeds at three and nine simulation minutes used the supplied
  original simulator with built-in country/tribe AI, a synthetic 128x96 coastal
  world and decisions every six ticks. All runs survived. v2.0 generally gained
  land more slowly at three minutes. At nine minutes it had more land in three
  of four seeds and more buildings on average. The complete metrics, including
  unfavorable seeds and host timings, are in `benchmarks/planning_v2.0.json`.
- A two-million-cell ownership scan with 100K owned cells completed in 129
  updates on the development host; median update about 1.05 ms, p95 6.61 ms and
  maximum 14.69 ms. This is an isolated atlas measurement, not the complete bot
  frame time and not a benchmark on the user's laptop.

These are engineering checks, not human-opponent win-rate measurements. No
claim of an unbeatable bot, hidden-information access or competitive strength
verification is made. No neural-network training is required to use this ZIP.
