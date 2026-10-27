# RoWorld bot 1.3.0

One **Start bot / Stop bot** button, a decision status line, and F6 to toggle.
Standalone Luau for the supplied RoWorld place `137151641329864`, version 111.
No training, Python, localhost bridge or external AI service is needed to play.

## Install / update

1. Extract the ZIP anywhere, such as Downloads.
2. Open `roworld/RoWorld_Bot.lua` in a text editor and copy **the whole file**.
3. Join a **multiplayer** RoWorld match, paste it into JJSploit, and execute.
4. Press **Start bot**. Re-executing replaces the previous panel and stops its loop.

Start before choosing your territory to let the bot choose a spawn. It cannot
relocate a nation that has already spawned. It does not choose queues or buy shop
items. Stopping prevents new orders; already launched attacks continue normally.

The optional `readfile` loader needs `RoWorld_Bot.lua` directly in your executor
workspace. On the supplied PC that is
`C:\Users\almas\AppData\Roaming\jjsploit\workspace`. Replace the old file there,
then execute `JJSploit_Launch.lua`. Pasting the entire script does not need file
or HTTP functions and does not depend on the extraction location.

## Strategy

Version 1.3 chooses continuous attack percentages from troop budgets instead of
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

The independent multiplayer observer now supports naval units, boats, warship
construction/movement and diplomacy as well as land/economy orders. SAMs, silos
and offensive weapons remain disabled on that route because their full state
is not mirrored. The original live-client route can additionally use those
weapons where its placement and friendly-fire checks permit them.

## Match report

When executor `writefile` is available, the bot saves **`RoWorld_Match_Report.json`**
in the JJSploit workspace every 30 seconds, when stopped, and on an observed
match end/elimination. It includes current troops/gold/land, peak land, order
counts, the last 64 orders, alliances, traitor flags, fleet counts, observed
threats and the latest attack forecast. Nothing is uploaded automatically.
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

**62 offline scenarios** cover policy, adapter and network behavior, plus UI
start/stop/re-injection and standalone Luau compilation. Additional checks against
the supplied game's original modules verify new naval/diplomacy command encoding,
water connectivity, unit paths/health, traitor flags and warship prices. The game
scripts and assets used for these private checks are not redistributed.

**This is a heuristic bot, not a neural model or a guaranteed winner.** Opponent
intent and coalition intervention are estimates. The updated strategy's live
playing strength has not been verified here. A changed game protocol or executor
API can prevent operation; the panel reports connection failures.

## Development

`policy.lua` selects orders; `adapter.lua` revalidates the live observation;
`client.lua` provides the button/reporting. `wire.lua`, `mirror.lua` and
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
