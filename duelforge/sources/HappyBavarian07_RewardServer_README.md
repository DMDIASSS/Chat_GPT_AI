# RewardServer

A BakkesMod plugin and local server for testing Rocket League reward functions. You play in freeplay or watch a replay; the plugin sends the cars and the ball to the server, and the server runs your reward on them. The overlay lists every reward term with its raw value, weight, and weighted value.

It also:

*   saves the last seconds of play as `.rlpr` clips
*   counts attempts at test shots, with scored, missed and undo
*   plays clips back in the game
*   runs clips through your reward offline

There is no training code in here. You need a GigaLearnCPP/learning framework (or something similar) that can provide a game state, plus RocketSim, the BakkesMod SDK, and MSVC.

***

## Getting Started

1.  Add the server to a CMake project that already has the `GigaLearnCPP` target or a learning framework that can supply RLGymCPP and RocketSim or GameStates:

    ```cmake
    set(RS_FRAMEWORK_ROOT "${CMAKE_SOURCE_DIR}/GigaLearnCPP")
    add_subdirectory(RewardServer/reward_server)
    ```

2.  Put your reward in ([Plugging in your reward](docs/INTEGRATION.md)), or build with the example first.
3.  Build and install the plugin with Rocket League closed:

    ```powershell
    scripts\build_plugin.ps1 -FrameworkRoot <path to GigaLearnCPP>
    ```

4.  Start the server from the folder that contains `collision_meshes`. Start the game, press F2, open Plugins, and select Reward Tester.

    ```powershell
    reward_server.exe --config reward.json --tasks examples/example_tasks.json
    ```

The overlay header says `CONNECTED` when it finds the server. If it doesn't, see the [FAQ](docs/FAQ.md).

***

## Docs

*   [Plugging in your reward](docs/INTEGRATION.md) - the two functions the server calls
*   [Server](docs/SERVER.md) - options, task files, clips, offline replay
*   [Plugin](docs/PLUGIN.md) - tabs, keys, building
*   [Protocol](docs/PROTOCOL.md) - every TCP command
*   [Architecture](docs/ARCHITECTURE.md) - what runs where
*   [FAQ](docs/FAQ.md)
*   [Roadmap](docs/ROADMAP.md)
*   [Bundle](bundle/README.md) - handout for people who only want the prebuilt plugin

