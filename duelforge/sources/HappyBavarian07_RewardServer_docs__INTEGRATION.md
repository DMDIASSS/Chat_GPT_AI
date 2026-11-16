# Plugging in Your Reward

### Introduction

On this page I want to show you how to get your own reward into the server. At the end the overlay rows are your terms.

You write one source file with two functions. The server calls them.

***

## What You Need

*   A CMake project that builds the `GigaLearnCPP` target.
*   MSVC with C++20.
*   Your reward classes, or a config format you can load yourself.

***

## The Source File

**First Step**: Copy `examples/user_reward_example.cpp` next to your reward code.

**Second Step**: Implement `IRewardSource` around your reward.

```cpp
#include "user_reward.h"

namespace {
using namespace RLGC;

class MySource : public rs::IRewardSource {
public:
    const std::vector<std::string>& Names() const override { return names_; }

    void PreStep(const GameState& state) override {}

    void Evaluate(const GameState& state, int focus, rs::RewardTerms& out) override {
        const Player& p = state.players[focus];
        out.names = names_;
        out.values = {p.vel.Length() / 2300.f};
        out.weights = {1.f};
        out.weighted = {out.values[0] * out.weights[0]};
        out.total = out.weighted[0];
    }

private:
    std::vector<std::string> names_ = {"Speed"};
};
}

namespace rs {
std::unique_ptr<IRewardSource> CreateUserReward(const std::string& configPath, std::function<uint64_t()> getTimestep) {
    return std::make_unique<MySource>();
}
std::unique_ptr<IEvalExtension> CreateEvalExtension() { return nullptr; }
}
```

**What happens here**:

*   `CreateUserReward` runs on every `load` and `reload`. `configPath` is the overlay's config box. Load a file with it or ignore it.
*   `getTimestep` returns the training step the overlay is set to. Use it if your terms fade in over training.
*   `PreStep` runs once per tick before `Evaluate`. Track state there.
*   `Evaluate` fills one row per term. Leave `weights` and `weighted` empty for terms without a weight.
*   Use the names your trainer uses, so the rows match your metrics.

**Third Step**: Call your real reward classes inside `Evaluate`, one row per class.

***

## Evaluation Hooks

`CreateEvalExtension` can return an `IEvalExtension`. Its hooks see the same `GameState` the reward sees. Return null if you don't need them.

| Hook | Runs | Use |
|---|---|---|
| `OnLoad(source)` | after a reward was loaded | reset detectors |
| `OnReset()` | on goals and freeplay resets | clear per-episode state |
| `BeforeEvaluate(gs)` | before `PreStep` | fill caches, attach `gs.userInfo` |
| `AfterEvaluate(gs)` | after `Evaluate` | collect labels |
| `TickReport(focus)`, `ReplayReport()` | during `--replay --json --extra` | add fields to the output |

***

## Building

**First Step**: Set the variables before adding the server.

```cmake
set(RS_FRAMEWORK_ROOT "${CMAKE_SOURCE_DIR}/GigaLearnCPP")
set(RS_INTEGRATION_SOURCES "${CMAKE_SOURCE_DIR}/my_reward.cpp")
set(RS_EXTRA_SOURCES ${MY_REWARD_SOURCES})
add_subdirectory(RewardServer/reward_server)
```

**Second Step**: Build the `reward_server` target in Release. All variables are in [Server](SERVER.md#build-variables).

***

## Checking That It Works

Start the server from the folder that contains `collision_meshes`:

```powershell
reward_server.exe --config reward.json
```

The console should print:

```text
[server] RocketSim arena mirror enabled (meshes: collision_meshes)
[server] preloaded config 'reward.json' (N terms)
[server] listening on 127.0.0.1:42069
```

Then run the protocol check from another terminal:

```powershell
python tests/smoke_client.py --config reward.json
```

`SMOKE OK (N terms)` means the server and your reward agree on the row count.

**Note**: Changing reward code means rebuilding and restarting the server. The plugin reconnects by itself. A config change only needs **Reload config** in the overlay.

And done. Next: [Server](SERVER.md).

