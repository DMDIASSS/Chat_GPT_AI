# RoWorld bot

One **Start bot / Stop bot** button and a status line describing its current
decision. Runs inside Roblox through JJSploit, without Python, localhost HTTP,
an external AI service, or a second simulation.

## Run

1. Download [the standalone script](./RoWorld_Bot.lua) using GitHub's **Raw / Download raw file** button.
2. Join **RoWorld World PvP** and enter the solo or multiplayer match you want.
3. Open `RoWorld_Bot.lua` in a text editor, copy **all its contents** into
   JJSploit, and execute. It starts stopped.
4. Press **Start bot**. The same button stops new orders. F6 also toggles it.

Extract the ZIP **anywhere**, such as Downloads. Pasting the complete script
does not depend on where you extracted it. Only the optional `readfile` loader
below needs the file in the executor workspace.

You can instead put `RoWorld_Bot.lua` directly in your JJSploit workspace
(`C:\Users\almas\AppData\Roaming\jjsploit\workspace` on your PC) and execute:

```lua
local run, err = loadstring(readfile("RoWorld_Bot.lua"))
assert(run, err)
run()
```

That file loader needs `readfile` and `loadstring`; pasting the complete script
does not need executor file or HTTP functions. Re-executing replaces the old
panel and stops its decision loop. Stopping prevents new orders; attacks already
sent remain ordinary game attacks and continue until resolved or recalled.

## What it does

- Chooses an unclaimed starting position if you have not spawned.
- Expands into clean neutral land while retaining a troop reserve.
- Compares bordering armies and attacks weaker nonallied neighbours.
- Holds troops when threatened and recalls outgoing attacks during heavy pressure.
- Builds cities, factories, ports, defense posts, SAMs and a missile silo when
  the observed resources, available space and game rules permit them.
- Accepts incoming alliance requests when it is not attacking that nation.
- Attempts reachable coastal landings when land expansion stalls.
- Can launch affordable atom strikes at enemy structures after checking the
  surrounding area for your own or allied land.

The status distinguishes an **order sent** from waiting or defending. It does
not claim that a sent order was accepted or that an attack succeeded. It follows
the local owner's ID from the live session, including changes after a new match.
It waits in menus, while spectating, while loading, on a paused solo game, or
when game ticks stop updating. It does not choose queues or buy shop items.

If client access is blocked, version 1.0.1 tries requiring the game module at
ordinary client thread identity (restoring the prior identity afterward), then
looks for the already-running client tables when `getgc(true)` is available.
It never boots a second client. Access failures automatically write
`RoWorld_Diagnostics.txt` to the JJSploit workspace if `writefile` is available,
and also print the same capability/error report to F9. That report contains no
session tokens or account information. No additional place files are needed
for the module-permission error; that diagnostic is useful if both routes fail.

## Compatibility and verification

Adapted to the supplied place `137151641329864`, version **111**, whose client is
named `AirfrontClient`. It reads the existing `Main.session` and `Main.ui.ctx`
and calls `session:send_intent`, the same command path used by the game's UI.
Solo uses the existing local command queue. Joined multiplayer clients use the
existing network route; server validation still applies and hosting is not
required by this adapter.

This is a Lua strategy adaptation of the supplied **OpenFront Solo AggroBot**,
not a byte-for-byte port of its browser code or bundled optional neural models.
The source JS's DOM, EventBus and OpenFront object APIs do not exist in Roblox.
RoWorld-specific state, ownership, terrain, placements and prices are used here.
Browser screenshots, ads, payments, hCaptcha and other unrelated uploaded assets
are not needed or included. There is no Rocket League model in this bot.

Offline tests cover strategy decisions, solo/joined-client routing, updated
alliances/targets, reserves, stale state, pause/stop, and duplicate injection.
The standalone script is compiled with Luau. **A live JJSploit session and playing
strength have not been verified here.** A changed game API or an executor that
cannot access cached game modules can prevent operation; the panel reports the
problem rather than silently sending guessed commands.

## Development

`policy.lua` contains strategy, `adapter.lua` reads and validates the live API,
and `client.lua` contains the one-button UI. After changes, regenerate the file:

```sh
python roworld/build.py
python roworld/tests/run.py --luau /path/to/luau --compiler /path/to/luau-compile
```

Credit: [OpenFront Solo AggroBot on Greasy Fork](https://greasyfork.org/en/scripts/599445)
(supplied userscript declares the MIT license). The provided RoWorld scripts
were inspected to establish the adapter API; game code and assets are not
redistributed in this folder.
