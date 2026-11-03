# TurboBall Chronos V2.1

`downloads/TurboBall_Chronos.lua` contains the actual public Chronos V2.1 shared
head and actor. It runs locally in Luau with the existing botrblx v6.8 window,
keyboard controls, telemetry, measured goal calibration and bounded recovery.
There is no Python server to keep running and no model download during play.

## Run

Close the old bot panel first. The adapter still targets `Deadline_coolgun` and
Turbo Soccer place `101880234193261` with the original keyboard/mouse bindings.

For the GitHub branch containing this change:

```lua
loadstring(game:HttpGet("https://raw.githubusercontent.com/DMDIASSS/Chat_GPT_AI/refs/heads/botrblx-chronos/downloads/TurboBall_Chronos.lua"))()
```

For a downloaded file, put `TurboBall_Chronos.lua` in the JJSploit workspace:

```lua
loadstring(readfile("TurboBall_Chronos.lua"))()
```

Wait for **Chronos V2.1 LOCAL ready**, then press **F6** to start. **F8** stops;
**F4** minimizes the window. A focus loss or open chat pauses inputs. Physics
assist starts off; goal safety starts on, as in the supplied Nexto loader.
The startup self-test checks the embedded network against PyTorch reference
outputs before enabling Start.

The old `37ff849...` URL names an immutable commit. A different filename at that
commit cannot serve a newly added bot. Use the branch above or the commit SHA
containing this release. Publication must finish before the GitHub loader works.

## Choice and evidence

Chronos was located through the official RLBot botpack's `Chronos` submodule:
https://github.com/KingJake3113/Chronos/tree/4f8fdd27e4802d977b33b9ade4759ff6aeaca5aa

The pinned model identifies itself as `KingJake/ChronosV2.1.1` and displays
`ChronosV2.1` upstream. Its configuration uses 225 observations, two shared layers
of 960 neurons, four actor layers (960/800/640/640), LayerNorm, ReLU and 90 actions.
The port includes its X reflection, padded teammate/opponent slots and action
masks. It does not reuse Nexto's 32/24 attention inputs or Nexto's weights.

In the saved **32-episode RocketSim 1v1 first-goal comparison**, Chronos won
**30**, original Nexto won **2**, and there were **0 draws**. Both team assignments
were used for each of 16 seeds; 8 episodes started at kickoff and 24 from grounded
states. Each episode had at most 750 decisions (50 simulated seconds). Both
actors used tick skip 8 with a 7-tick action delay, without scripted kickoff
overrides. See `reports/chronos_vs_nexto.json` and `benchmark_chronos.py`.

This establishes a stronger actor than Nexto in that experiment. It does not
establish the strongest of every linked release, superiority in 2s/3s, or a
Turbo Soccer win rate. No reliable, current, version-matched public ranking
covering all those releases was found. The other supplied repositories were
reviewed for their advertised variants and inputs; their actors were not run in
this comparison. Chronos is the tested upgrade selected here, not a claim of a
universal champion.

## Runtime limits

- The network contains about 3.8 million float32 parameters. The standalone file
  is about 20.6 MB. CLI Luau parity testing measured approximately 50 ms per
  inference on this cloud CPU; this is not a JJSploit performance measurement.
- The existing scheduler targets 15 decisions per second. Startup rejects a
  model inference over 200 ms, and the panel reports actual cadence. A larger
  model can run more slowly than Nexto on the user's computer.
- Roblox observations still come from rendered poses and UI. Opponent boost,
  remote jump/flip state and first-seen pad cooldowns are estimates. Unknown
  pads use zero features, rather than claiming all pads are active. Pad slots
  match the standard arena; observed active-to-inactive transitions estimate
  cooldowns. All 34 known pad slots are available to Chronos.
- The local keyboard scheduler and the existing kickoff/recovery/goal guards
  remain adapter behavior. They do not exactly reproduce RLBot's timing or the
  simulator benchmark. Live Roblox/JJSploit play has not been tested here.

## Rebuild and verify

From the repository root, with the project's Python environment:

```text
python botrblx/build_chronos.py --download
```

Or supply a folder already containing the two pinned `.lt` assets:

```text
python botrblx/build_chronos.py --assets PATH_TO_CHRONOS_RLBOT
```

`chronos_manifest.json` pins the public source revision, both weight SHA256s and
the upstream observation/action source hashes. Other/private checkpoints and
architecture changes are rejected. Downloaded build assets are ignored by Git;
only their public inference values are embedded in the Lua artifact.

Set `LUAU_BIN` to the Luau CLI and `CHRONOS_ASSETS` to that model folder, then run:

```text
python -m pytest botrblx/tests/test_chronos.py botrblx/tests/test_arena.py -q
python botrblx/benchmark_chronos.py --assets PATH_TO_CHRONOS_RLBOT --pairs 16 --decisions 750 --output work/chronos_vs_nexto.json
```

The benchmark additionally needs the existing RLGym/RocketSim dependencies.
Ready-to-run users need only the Lua file. Attribution and licenses are recorded
in `CHRONOS_NOTICE.md` and the accompanying license files.
