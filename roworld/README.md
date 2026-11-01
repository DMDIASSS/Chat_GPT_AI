# RoWorld bot 2.4.0

A **Start bot / Stop bot** button, live strategy dashboard, **Save match report**, **Help Roblox friends: ON/OFF**, and F6 to toggle.
Standalone Luau for the supplied RoWorld place `137151641329864`, version 111.
No training, Python, localhost bridge or external AI service is needed to play.

## Install / update

1. Extract the ZIP anywhere, such as Downloads.
2. Open `roworld/RoWorld_Bot.lua` in a text editor and copy **the whole file**.
3. Join a **multiplayer** RoWorld match, paste it into JJSploit, and execute.
4. Press **Start bot**. Re-executing replaces the previous panel and stops its loop.

Start before choosing your territory to let the bot choose a spawn. It cannot
relocate a nation after active play begins; during the countdown it can reselect its spawn. It does not choose queues or buy shop
items. Stopping prevents new orders; already launched attacks continue normally.

The optional `readfile` loader needs `RoWorld_Bot.lua` directly in your executor
workspace. On the supplied PC that is
`C:\Users\almas\AppData\Roaming\jjsploit\workspace`. Replace the old file there,
then execute `JJSploit_Launch.lua`. Pasting the entire script does not need file
or HTTP functions and does not depend on the extraction location.

## Strategy

Version 2.4 adds reactive counterattacks against overcommitted attackers:

- A live bordering attacker is eligible when its observed army attacking us is
  over 1.5x its remaining home bank. Allies, protected friends and pending peace
  proposals are excluded; this is a visible overcommitment test, not intent detection.
- Reassesses at most once per second. Amounts scale with the target bank and
  estimated recruitment, subtracting our troops already attacking that target.
- Each counter order retains at least **ceil(42% of current troop capacity)**,
  the existing strategic reserve and 1.5x observed incoming threats, whichever is
  largest. It can retain more than 42% when proportionate reinforcement requires
  less or defensive risk requires more. Game minimum order size still applies.
- Requires a viable forecast and enough spare troops; holds below the floor or
  during a critical core emergency. The floor and active attacker are rechecked
  immediately before sending. Valid counter campaigns get a short continuation
  window to avoid immediate recall/relaunch churn, with a bounded deadline.

192 offline scenarios, dashboard/lifecycle and compilation passed. This controls
our counterattack spending; it cannot prevent combat losses from reducing the
bank below 42%, create missing troops, or promise that retaliation wins. Other
ordinary expansion retains its existing recruitment-aware budgets.

Version 2.3 addresses the early betrayal loss:

- A corridor cannot complete after only a one-to-three-second gain. It requires
  at least eight seconds, retained own land and (for countries) at least a 25%
  decrease from that country's initial territory. Unrelated own expansion no
  longer resets campaign progress unless the target also loses territory.
- An active affordable country corridor or asset raid may be promoted to an
  elimination objective without resetting money/troop spending or adding an
  unlimited fresh deadline. Cheap local countries obstructing the core buffer
  may qualify for clearance even without a treasury; their estimated gold reward
  remains zero. Army, invasion, reserve and budget checks still apply.
- A neighboring treaty ally with more than 1.5x our home bank produces a visible
  warning, recorded history and a bounded reserve adjustment (45%, or 60% at 2x).
  The planner increases the value of productive investment. This is uncertainty
  management, not proof of hostile intent: it does not break the alliance, declare
  war or enter recovery solely because an ally is strong. Permanent teammates
  and balanced or distant allies are exempt.

188 offline scenarios plus dashboard/lifecycle/compilation passed. Both original
country-AI smoke seeds survived; land was similar/slightly lower, with larger home
banks. These worlds do not replay the human betrayal or prove the supplied loss
would have been prevented. The report includes `ally_warning_history` and current
warnings/reserves in the strategic board.

Version 2.2 prioritizes valuable country conquests and adds visible missile alerts:

- Country targets are ranked by current treasury, productive building kinds,
  levels, readiness, missing production in our economy, defense and army cost.
  Defense posts do not inflate the useful-asset score.
- Weak, manageable countries with assets or money can become **elimination**
  objectives. These continue after the first building capture instead of banking
  that raid immediately. Finishing remains subject to home defense, route/front
  feasibility, counterattack forecasts, spending limits and a 90-second deadline.
- A finishing allocation is capped at 40% of the current home bank and existing
  reserves can reduce it further. Reinforcement accounts for troops already
  attacking, has a three-second country campaign interval and cannot exceed the
  remaining campaign allocation. An adequate live army is not fed duplicate sends.
- Inspected rules pay a country's remaining treasury to the credited conqueror.
  The displayed amount is an estimate: spending and another player's finishing
  attack can change or remove our reward. Elimination does not guarantee that we
  captured every building or that all surviving territory is reachable.
- Visible incoming missile flights trigger dashboard warnings with estimated
  impact time, own/allied assets in the possible blast and SAM coverage at the
  target. Alerts scan at up to 5 Hz, retain the latest 32 observations and are
  exposed as `missile_alerts` / `missile_alert_history` in the report. Unrelated
  distant launches do not create a local warning. Asset checks are exact point
  checks against conservative radii; bounded unbuilt-land probes may miss thin
  holdings. Interception, actual damage and last-second target changes are unknown.
- Threatened own assets feed the existing SAM construction consideration. A
  warning cannot supply missing money, instantly finish a SAM or cancel missiles.

182 offline scenarios, UI lifecycle and compilation passed. Country conquest-gold
math also matched the supplied original Rules. Two three-minute country-AI smoke
seeds survived; results were mixed for land and do not establish faster credited
eliminations or a live strength gain. The supplied v2.0 report confirms a betrayer
committed most of its bank, but does not retain enough impact information to
attribute each lost asset to a specific missile; the new alert history improves
that evidence for subsequent matches.

Version 2.1 adds team detection and optional Roblox-friend cooperation:

- Detects any number of teams from snapshot team names and observed team IDs.
  The dashboard shows team count and your team; a partial observed roster is
  reported as potentially incomplete. Matching positive team IDs remain allies.
- **Help Roblox friends** defaults ON and can be switched OFF at any time. Its
  setting survives reinjection in the same client session. New Roblox sessions
  start ON. Turning it off removes friend-specific protection and priority; it
  does not break existing alliances or disable normal teammate support.
- Uses the live Roblox player roster and friendship API (asynchronous API with
  legacy fallback). Friendship checks are cached for 60 seconds and the roster
  refreshed about every 15 seconds, outside the decision loop.
- The game sends display names rather than account IDs for nations. Only unique
  live player/nation name matches are used; duplicates are skipped. The Roblox
  friendship is checked by UserId, but the nation binding is an inference, not
  authenticated account ownership. API failures and unmatched/renamed players
  receive no friend priority. Reports expose this limitation and lookup status.
- Eligible friends receive alliance acceptance/offer/renewal priority. New land,
  boat and missile attacks avoid them; existing land campaigns are recalled and
  missile blast checks protect their land. Already launched missiles or boats
  cannot necessarily be cancelled. Friends on opposing teams receive no special
  treatment, preserving the game's team rules.
- Actual allies who are eligible friends or teammates can receive limited troop
  support when threatened or depleted. No support is sent while we have an
  incoming land invasion or a core invasion/recovery warning. Each send is at
  most 8% of our home bank, with a 45-second policy cooldown and further reserve,
  recipient capacity and alliance checks immediately before sending. The bot
  cannot control whether another player reciprocates.

173 offline behavior scenarios plus dashboard/toggle/export/reinjection and
compilation passed. Donation encoding also matched the supplied original game
protocol. Live friendship lookup and cooperative strength remain unverified.
No account friend requests, chat messages or external messages are sent.

Version 2.0 integrates all five proposed planning extensions:

1. **Strategic map:** incremental connected holdings, economic centers, exposure,
   public neighbor graph and sampled growth frontiers, with explicit snapshot age.
2. **Strategic planner:** compares defense, investment, expansion, negotiation and
   relocation; prolonged quiet guard mode can consider small reserve-safe growth.
3. **Investment evaluator:** compares marginal recruitment, productive links,
   price and exposure; city levels drive production targets and concentration risk.
4. **Campaign objectives:** asset capture/consolidation, corridors and tribe
   elimination, with spending/time limits, progress checks and recorded exits.
5. **Opponent profiles:** observed attacks, naval sightings and lasting betrayal
   penalties; bounded local JSON persistence when file functions are available.

The dashboard shows the current strategic objective. Reports now include
`atlas`, `planner`, `campaigns`, `campaign_history`, `opponent_profiles` and ranked
investment candidates. Profiles are stored in `RoWorld_Opponent_Profiles.json`
in the executor workspace; keep that file when updating. Cross-match identities
are based on ambiguous display names, not verified accounts.

See [PLANNING.md](PLANNING.md) for behavior, resource limits, persistence details
and the complete verification scope. **161 offline scenarios passed.** In four
paired nine-minute country-AI simulations, the new version finished with more
land in three seeds and a larger average building base, but often expanded more
slowly in the three-minute checks. This does not establish a live win rate.
Complete comparisons are in [the benchmark](benchmarks/planning_v2.0.json).

Version 1.9 addresses the supplied loss. See [the analysis](LOSS_ANALYSIS_v1.8.md)
for evidence, limitations and the learning path.

- Emergency defense uses the same three-post limit as routine decisions, plus a
  rolling three-purchase/minute budget to prevent endless replacement spending.
- Quiet productive cores save for SAM coverage against ready hostile silos.
- Distant human landings need a useful visible asset and substantial third-party
  pressure; only one expedition can be at sea. Escape scoring avoids dominant
  human centers and favors neutral expansion room.
- A destroyed economic core can trigger relocation despite residual 'clearable'
  tiles. Fresh recovery growth resets the stall timer.
- Public opponent summaries/events and bounded early/recent samples support
  future analysis. They are not exact action labels, hidden intent or an already
  trained neural network.
- The dashboard shows economy, incoming troops, core risk, savings and measured
  policy decision time. That time excludes networking, UI rendering and report
  writing. Reports also include blocked-order counts/reason and runtime errors.
- **Save match report** writes `RoWorld_Match_Report.json` and a timestamped
  archive `RoWorld_Match_Report_<timestamp>_<clock>.json` in the executor workspace.
  Stop, match end and reinjection also archive the current report when file
  writing works. Periodic saves update the latest file every 30 seconds.
  Save a report immediately after an important incident if possible. Nothing is
  uploaded automatically. Each fresh Start begins a new observation session.

139 offline scenarios plus dashboard export/lifecycle and compilation passed.
Live competitive improvement is **not verified**. No server exploits, money
creation or automatic-win mechanism is included.

Version 1.8 expands diplomacy and emergency responses:

- Requests, offers and renewals use a scored assessment with recorded reasons.
  Humans receive preference over tribes/countries; nearby weak countries carry
  an expansion-opportunity cost. Shared active enemies and compatible ports add
  value. Strength, recent aggression, betrayal history, nearby warships, rapid
  expansion and alliances with our enemies alter the score.
- Dominant bordering countries are normally rejected because of future betrayal
  risk. During an already overwhelming invasion, last-resort peace can outweigh
  that normal rule. Agreement is voluntary; a positive score cannot force peace.
- The first two minutes of known match age reduce the value of an otherwise
  quiet country alliance. The exact country grace depends on hidden difficulty,
  jitter, distance and other state; it is **not immunity from retaliation**.
- Formal alliances are reassessed in the actual final 30-second renewal window.
  The bot may request/accept extension for a useful partner or let an unhelpful
  alliance expire. It checks the two-party extension bits and expiry again
  before sending, avoiding duplicate requests. Permanent teams need no renewal.
- Heavy incoming armies trigger emergency decisions before routine industry:
  recall, useful peace proposals, affordable safe missile targets, then a possible
  small neutral survival expedition or defensive construction. Survival boats
  require incoming troops above 125% of the home bank, no other transport, a safe
  observed destination and a retained 90% bank. Ordinary reserve rules remain for
  every other order. A rejected peace offer or unavailable weapon is not a fix
  for a lost military position; the report records when no safe option exists.
- During the spawn countdown it reassesses approximately twice per second and
  may move to a materially better location, at most once every two seconds.
  This is permitted by the inspected game. It never relocates an already-spawned
  nation after play begins. Future player marks remain unknown.
- The UI/observation loop polls at up to **10 Hz**; heavy core scans are capped
  at **5 Hz** and outgoing orders at **5/second**, with separate action cooldowns.
  Repeated unchanged ticks are skipped. These are nominal limits, not measured
  guarantees on a particular PC, network or game update rate.

Reports add `diplomacy_candidates` with score/reasons, renewal decisions in the
order log, emergency state/reason, and nominal runtime limits.


Version 1.7 addresses income, alliance changes and trapped-core recovery:

- Factory/city site scoring favors partners within 15–90 full map units with a
  clear owned/allied land corridor. This improves the chance of a usable income
  network, but does not guarantee that the game's rail planner connects it.
  Cities primarily provide troop capacity; factories and port trade matter for
  additional income. Production targets now permit more factories and ports as
  the city base expands.
- Routine warship purchases preserve funds for a first factory/port. A visible
  transport invasion can override that saving priority. Reports include the
  advertised income rate, economic building counts, live trade/cargo units and
  the current production reserve. The advertised rate is not a full ledger of
  every shipment, donation, conquest or loss.
- Multiplayer alliance-end events record the breaker and expiry flag. Confirmed
  betrayers are distrusted for three minutes, pending peace grace is cleared,
  and a nearby betrayal triggers a short defensive reassessment. Expiry and
  unknown native-client endings are not claimed as proven betrayal. Repeated
  outgoing proposals to the same nation back off for two minutes.
- A core stranded without local expansion for 20 seconds can enter relocation
  mode despite a distant/nearby naval guard warning. It requires no incoming
  land or transport invasion and sends at most 10% of the bank to neutral coast,
  preserving at least 75% reserves. Only one such transport may be outstanding;
  the possible destination gets a temporary five-minute expansion anchor.
  This is a recovery attempt, not proof that the sea journey is safe.


Version 1.6 protects the **original home and an economic core**:

- Chooses a stable center from the concentration and levels of owned buildings,
  rather than following whichever distant port was encountered first. The owned
  spawn remains a secondary objective when the economic center moves elsewhere.
- Performs a bounded local ownership scan around those anchors, supplemented by
  exact radial probes. This finds home-front expansion even when the rotating
  global border scan is busy with distant outposts. Neutral buffer growth and
  affordable nearby enemy clearance receive priority over distant opportunities.
- Pauses new distant wars and landings while the home buffer needs consolidation.
  Useful nearby coastal landings remain possible when the area is not threatened.
- Raises reserves and recalls distant raids when hostile troops or ships threaten
  the core. Sudden loss of local buffer territory triggers emergency recovery.
  Enemy transports are treated as potential invasions, not certain future inputs.
- Favors core locations for new economic construction and defense/SAM coverage.
  Patrol construction and interception prioritize core ports; healthy available
  warships nearest the chosen threat are considered first. Damaged ships retain
  the game's retreat/repair behavior.
- If the original spawn is lost, the bot protects remaining owned assets instead
  of blindly pursuing an empty enemy-held location. Center selection has
  hysteresis so small building upgrades do not constantly move its objective.

RoWorld troops are a **global bank**, not separate local garrisons. Gold is also
global; the center uses building importance as an estimate of economic value.
The bot cannot guarantee that a buffer is safe or clear: local scans are bounded,
water bodies and intervening terrain matter, and opponents can change direction.
It keeps the existing cost, alliance, fallout and incoming-strike checks.

Version 1.5 adds a board review before choosing new military orders:

- Distinguishes humans (kind 2), AI countries (kind 0), and tribes (kind 1).
  Human invasions need a larger advantage, smaller first commitments and slower
  reinforcement. Nearby human armies, multiple fronts, reachable remote human
  ports and potentially unreliable dominant country allies raise reserves.
- An outgoing alliance proposal blocks land attacks, boats and nuclear launches
  against that nation while pending. A 45-second policy grace period also avoids
  immediately attacking after a proposal is declined or expires.
- Compares affordable opponents and visible asset opportunities each decision;
  neutral growth competes with war. A clearly better opportunity can end a
  stalled front first. It does not open a second war just to change targets.
- Stops feeding stalled campaigns, pauses after recalls, and enters recovery
  after recent territory loss. A bank drop caused by its own troop dispatch is
  not automatically treated as battlefield damage.
- Looks for shallow, visible country buildings worth capturing. After captures,
  it can recall and bank the gain when human pressure or campaign cost warrants
  it; it does not abandon every successful conquest after the first building.
  Attacks and recalls still cost troops. It does not assume it can force the
  country AI to construct a desired building.
- Saves for the first city instead of buying repeated defense posts under
  moderate pressure. Emergency defense can still take precedence when necessary.
- Spawn scoring counts nearby **humans separately from countries**, penalizes
  multiple/opposing player directions, and prefers flat expansion space backed
  by water over a cramped island or an exposed crowded start. It is a bounded
  sample of known current positions; future player spawns are unknown.

[Country AI notes](./COUNTRY_AI_NOTES.md) describe the inspected rules and limits.

Version 1.3 introduced continuous attack percentages from troop budgets instead of
fixed 10/22/25/55% settings. The game's minimum is **1% of the current home army**;
smaller orders are held rather than letting the server silently increase them.
The bot can send above 55% when its retained recruitment/defense budget permits.

Recruitment follows `(home^.73 / 4 + 10) * (1 - home / capacity)`. Its peak is
computed again when capacity changes, generally around **41–42%** for large
armies. This is a preferred economic level, not a mandatory ceiling: danger can
require banking more, and early expansion can justify investing below it. The
bot never attacks merely to dump surplus troops when there is no suitable target.

Enemy attacks compare three troop budgets using the existing cost/risk forecast.
Real third-party attacks give a bounded opportunity bonus and can relax the army
advantage requirement; our own attacks, retreating armies and the target's allies
do not count as outside pressure. The target's remaining home troops and nearby
coalition counterattacks still count. This is a heuristic, not a victory promise.

- Scores 160 spawn candidates for flat unclaimed land, distance from established
  players, nearby weak tribes, and some water access. This is a bounded search,
  not proof of a globally optimal spawn.
- Preserves recruitment and defensive reserves while expanding. Tracks actual
  attacks and troop spending over time; spending alone is not treated as proof
  of hostile intent.
- Compares terrain and defense-post costs under several counterattack assumptions.
  Counts nearby allies of a target as possible additional opposition and avoids
  opening another enemy war while a land attack against a different enemy runs.
- Uses current alliances and teams when choosing targets. Accepts suitable
  requests, declines marked traitors, and can request a safer frontier alliance.
  Betraying a marked traitor requires an exceptionally large defensive margin:
  breaking any alliance also marks **you** as a traitor and weakens your defense.
  Team alliances are never deliberately broken.
- Requires an owned-land setback around construction sites: **18 map distance
  units** for economic buildings, **8** for defense/SAM sites. Ports permit water
  inside this radius but still require a land setback. The bot waits if there is
  no safe site and rechecks the setback immediately before sending an order.
- Builds cities, factories, ports and defenses when affordable. Uses warships
  for coastal patrol/interception, tracks ship counts and health, and leaves
  damaged or retreating ships to the game's repair logic.
- Uses connected-water observations for transport landings and warship patrols;
  avoids destinations near observed hostile warships. Enemy actions and fleet
  movement can still change after an order is sent.

Both the independent multiplayer observer and the original live-client route now
support **SAMs, missile silos, atom bombs, hydrogen bombs and MIRVs**, in addition
to the land/naval/economy features above. Weapon prices, silo reload slots,
in-flight missiles and MIRV escalation are tracked from server observations.

## Nuclear strategy and SAMs

- Visible enemy silos, including construction sites, trigger preparation. Two
  ready hostile silos increase the desired SAM coverage to two layers.
- SAM placement prioritizes uncovered cities, factories and silos. It retains
  the 8-unit land setback, considers range gained by upgrades, and builds ahead
  of threats: a new SAM takes 30 seconds to finish. It cannot erase an already
  imminent impact. Silo construction retains enough gold for an atom bomb.
- Fallout flags are tracked from snapshots and updates: the bot skips those
  tiles for spawning, expansion and construction, and avoids nuking ruined
  targets. It avoids new construction inside visible incoming strike footprints
  and skips expansion targets threatened by impacts within three seconds.
- The bot compares up to 12 valuable structure targets per weapon, prefers
  worthwhile damage for the cost, retains a gold reserve, and avoids overlapping
  strikes. Hydrogen is useful against clusters; atom can be cheaper for a single
  valuable target. An unused nuclear capability is preferable to a poor launch.
- Atom/hydrogen launch checks screen their curved trajectories against observed
  nonallied SAMs, including third-party defenses and coverage near our silo.
  The check is conservative: a SAM reloading or still under construction can
  become ready before arrival. It may decline a shot that could have succeeded.
- **MIRV carriers bypass SAM interception; individual warheads do not.** MIRV
  damage is discounted when selecting a weapon, not treated as guaranteed.
- Atom costs **750K**, hydrogen **5M**, and MIRV starts at **25M**, increasing by
  **15M for each MIRV launched anywhere in the match**. A ready own silo is
  required. Observed shot stamps and silo level determine ready slots.
- Atom and hydrogen use their different 30/100-unit blast radii. MIRV checks the
  full 1500-unit spread plus its 18-unit warhead blast for friendly territory,
  because the landing points are random. This deliberately rules out many
  MIRV launches near our own or allied countries. The bot also declines new
  alliances endangered by our missiles already in flight.
- Ownership, alliances, silo readiness and SAM coverage are checked again before
  sending a launch. Future construction, captures and alliance changes during
  flight remain uncertain; safe impact cannot be guaranteed.

This update implements the requested nuclear/SAM arsenal. Other unlock-based
arsenal items (artillery, airfields, railguns, mega/scatter weapons and reinforce)
are not automated; the bot does not purchase or unlock account items.

## Match report

When executor `writefile` is available, the bot saves **`RoWorld_Match_Report.json`**
in the JJSploit workspace every 30 seconds, when stopped, and on an observed
match end/elimination. It includes current troops/gold/land, peak land, order
counts, the last 64 orders, alliances, traitor flags, fleet counts, observed
threats, enemy silo construction/readiness, own SAM counts, fallout tile count,
and the latest attack forecast. Version 1.5 also records the board mode, nearby
human pressure, alternative military candidates, spawn assessment, target owner
IDs/types and a bounded five-second timeline of territory, reserves and incoming
attacks. Version 1.6 adds `strategy.core`: center/home tiles, retained home
ownership, anchor radii, estimated building importance, up to 32 protected
building locations/types/levels, sampled buffer ownership, local incoming armies
and naval threat counts. Timeline samples also record core risk and buffer share.
Territory changes do not identify which attacker caused every loss. Nothing is uploaded automatically.
Send that file after a completed match to investigate its decisions. It covers
the current observer snapshot onward; a fresh snapshot or re-execution resets
its history. It records orders sent, not server confirmation of success.

If file writing is unavailable, the same report is returned by
`getgenv().__RoWorldBot.report()`. Access failures also print diagnostics in F9
and try to save `RoWorld_Diagnostics.txt` in the executor workspace.

## Compatibility and verification

The original route reuses the game's running `Main.session` / `Main.ui.ctx`.
When JJSploit blocks module access, an independent observer listens to the
existing multiplayer `AirfrontNet` snapshot/delta stream, requests the normal
resync, downloads terrain, and sends ordinary own-nation orders. It does not
start another simulation, replace callbacks, impersonate another nation, or
send JOIN/LEAVE commands. Solo needs working live-client access; the independent
observer cannot read a private local solo simulation.

Incomplete, stale or corrupt observations prevent orders and request resync.
Match changes invalidate earlier decisions. Terrain water components are built
once per download with cooperative yields; strategy scans are bounded.

**128 offline scenarios** cover policy, adapter, network, weapons, strategy and core behavior, plus UI
start/stop/re-injection and standalone Luau compilation. Additional checks against
the supplied game's original modules verify new naval/diplomacy command encoding,
water connectivity, unit paths/health, traitor flags and warship prices. Nuclear checks also match
command encoding, missile/shot observations, all five construction/weapon prices,
trajectory coordinates and MIRV carrier/warhead interception constants. The game
scripts and assets used for these private checks are not redistributed.

During version 1.5 development, four paired three-minute worlds also ran with the supplied game
simulator. Both versions survived all four; version 1.5 retained more troops
in all four, but held less territory in three. These are small synthetic worlds
against built-in country/tribe AI, not tests against humans or proof of a higher
win rate. The full results and setup are in
[the development comparison](./benchmarks/strategy_v1.5.json).

A further three-minute simulator smoke test of v1.6 survived with ongoing
expansion/construction. It is a synthetic country/tribe world and provides no
human-opponent win-rate evidence.

**This is a heuristic bot, not a neural model or a guaranteed winner.** Opponent
intent and coalition intervention are estimates. The updated strategy's live
playing strength has not been verified here. A changed game protocol or executor
API can prevent operation; the panel reports connection failures.

## Development

`diplomacy.lua` scores alliance value/risk and renewal candidates;
`core.lua` tracks owned building clusters, the home buffer and local threats;
`strategy.lua` tracks campaigns, diplomacy grace periods and board conditions;
`policy.lua` selects orders; `adapter.lua` revalidates the live observation;
`client.lua` provides the button/reporting. `weapons.lua` shares nuclear
readiness, blast and SAM coverage checks between planning and order validation. `wire.lua`, `mirror.lua` and
`network.lua` implement the independent read-only multiplayer observer.

```sh
python roworld/build.py
python roworld/tests/run.py --luau /path/to/luau --compiler /path/to/luau-compile
```

Strategy reference: [OpenFront Solo AggroBot](https://greasyfork.org/en/scripts/599445)
(the supplied userscript declares MIT). This is an independent Luau adaptation,
not its browser DOM/EventBus code or optional neural models. No executor binary,
game assets, payment/ad scripts, private diagnostics or Rocket League models are
included.
