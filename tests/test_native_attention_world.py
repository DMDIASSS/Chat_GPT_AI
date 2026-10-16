"""Real C++/RocketSim migration checks when the optional native build is present."""
from pathlib import Path
import os
import shutil
import subprocess

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def native_toolchain():
    source = Path(os.environ.get("SLATER_GIGA_SOURCE", "/workspace/native-giga-test/upstream-source"))
    libraries = Path(os.environ.get("SLATER_RLGYM_LIB_DIR", "/workspace/native-giga-test/build2/giga/RLGymCPP"))
    include = source / "GigaLearnCPP/RLGymCPP/src"
    compiler = shutil.which("g++") or shutil.which("clang++")
    required = [include / "RLGymCPP/Gamestates/GameState.h", libraries / "libRLGymCPP.a",
                libraries / "RocketSim/libRocketSim.a"]
    if not compiler or not all(p.is_file() for p in required):
        pytest.skip("Optional C++ RocketSim libraries/toolchain unavailable")
    from rlgym.rocket_league.sim import RocketSimEngine
    import inspect
    meshes = Path(inspect.getfile(RocketSimEngine)).parent / "collision_meshes"
    return compiler, include, libraries, meshes


def compile_fixture(native_toolchain, source, output):
    compiler, include, libraries, _ = native_toolchain
    subprocess.run([compiler, "-std=c++20", "-O1", f"-I{ROOT}", f"-I{include}", str(source),
                    str(libraries / "libRLGymCPP.a"), str(libraries / "RocketSim/libRocketSim.a"),
                    "-pthread", "-o", str(output)], check=True, capture_output=True, text=True)


def test_real_world_delay_terminal_timeout_and_frozen_isolation(native_toolchain, tmp_path):
    binary = tmp_path / "world-test"
    compile_fixture(native_toolchain, ROOT / "tests/native_attention_world.cpp", binary)
    proc = subprocess.run([str(binary), str(native_toolchain[3])], check=True, capture_output=True, text=True)
    assert "NATIVE_ATTENTION_WORLD_PASS" in proc.stdout


def test_frozen_clock_matches_python_source_across_script_interruption(native_toolchain, tmp_path):
    source = tmp_path / "clock.cpp"
    source.write_text(r'''
#include "GigaLearn_Project/Native_Attention/AttentionWorld.h"
#include <iomanip>
#include <iostream>
using namespace SlaterAttention;
int main() {
    RLGC::GameState state;
    state.players.resize(2);
    state.players[0].carId = 1; state.players[0].team = RocketSim::Team::BLUE;
    state.players[1].carId = 2; state.players[1].team = RocketSim::Team::ORANGE;
    state.players[0].pos = {-2048,-2560,17}; state.players[1].pos = {2048,2560,17};
    FrozenClock clock;
    int counter = 0;
    std::cout << std::setprecision(9);
    for (int tick=0; tick<190; ++tick) {
        state.ball.pos = {0,tick==80 ? 1.f : 0.f,93};
        const bool kickoff = tick < 169 || tick >= 175;
        Action action = ZeroAction();
        if (clock.updateAction) action = Action((counter++ % 3)-1, .25, 0, 0, .125, 0, 0, 0);
        Action control = clock.Frame(state, 1, kickoff, &action);
        std::cout << clock.ticks << ',' << clock.updateAction << ',' << clock.kickoffIndex;
        for (float v : control) std::cout << ',' << v;
        for (float v : clock.action) std::cout << ',' << v;
        std::cout << '\n';
    }
}''')
    binary = tmp_path / "clock-test"
    compile_fixture(native_toolchain, source, binary)
    actual = np.loadtxt(subprocess.run([str(binary)], check=True, capture_output=True,
                                      text=True).stdout.splitlines(), delimiter=",")
    from slater_nexto_scheduler_v038b import NextoV4Clock
    clock = NextoV4Clock(hardcoded=True, stochastic=False)
    expected = []
    counter = 0

    def infer(previous, beta):
        nonlocal counter
        action = np.array([counter % 3 - 1, .25, 0, 0, .125, 0, 0, 0], dtype=np.float32)
        counter += 1
        return 0, action

    for tick in range(190):
        ball = np.array([0, 1 if tick == 80 else 0])
        frame = clock.frame(is_kickoff_pause=tick < 169 or tick >= 175, ball_xy=ball,
                            positions=np.array([[-2048, -2560], [2048, 2560]]),
                            teams=np.array([0, 1]), index=0, infer=infer)
        expected.append([clock.ticks, clock.update_action, clock.kickoff_index,
                         *frame.controls, *frame.action])
    np.testing.assert_allclose(actual, expected, atol=1e-8, rtol=0)


def test_common_kickoff_short_trajectory_and_reward_match_python(native_toolchain, tmp_path):
    """Shared starts, controls, 64 ticks: bounded check, not full-version parity."""
    import random
    import torch
    from nexto_teacher import nexto_actions
    from slater_versatile_env import VersatileEnv

    action_table = nexto_actions()
    action_index = int(np.flatnonzero(np.all(action_table == [1, 0, 0, 0, 0, 0, 1, 0], axis=1))[0])

    class ConstantActor(torch.nn.Module):
        def forward(self, x):
            logits = torch.zeros((len(x[0]), 90))
            logits[:, action_index] = 10
            return logits

    seed = 9
    order = list(range(5))
    random.Random(seed).shuffle(order)
    source = tmp_path / "trajectory.cpp"
    source.write_text(r'''
#include "GigaLearn_Project/Native_Attention/AttentionWorld.h"
#include <iomanip>
#include <iostream>
using namespace SlaterAttention;
int main(int argc, char** argv) {
    RocketSim::Init(argv[1], false);
    AttentionWorld world(1,1,RocketSim::Team::BLUE,30);
    std::array<int,5> order = {SPAWNS};
    world.Reset(9,&order);
    Action command(1,0,0,0,0,0,1,0);
    std::cout << std::setprecision(12);
    for (int step=0;step<8;++step) {
        world.BeginAction(command);
        while (!world.StepComplete()) {
            std::map<uint32_t,Action> predicted;
            for (auto id: world.ReadyCars()) predicted[id]=command;
            world.Tick(predicted);
        }
        auto us=world.Arena()->GetCar(world.BlueIds()[0])->GetState();
        auto them=world.Arena()->GetCar(world.OrangeIds()[0])->GetState();
        auto ball=world.State().ball;
        std::cout << "TRACE " << world.Reward();
        for (auto vector: {ball.pos,us.pos,us.vel,them.pos,them.vel})
            std::cout << ',' << vector.x << ',' << vector.y << ',' << vector.z;
        std::cout << '\n';
    }
}'''.replace("SPAWNS", ",".join(map(str, order))))
    binary = tmp_path / "trajectory-test"
    compile_fixture(native_toolchain, source, binary)
    proc = subprocess.run([str(binary), str(native_toolchain[3])], check=True, capture_output=True, text=True)
    actual = np.loadtxt([line.removeprefix("TRACE ") for line in proc.stdout.splitlines()
                         if line.startswith("TRACE ")], delimiter=",")
    env = VersatileEnv({"constant": ConstantActor()}, task_name="match", fixed_side="blue", max_seconds=30)
    expected = []
    try:
        env.reset(seed)
        for step in range(8):
            _, reward, done, info = env.step(action_index)
            assert not done
            us = env.state.cars[env.ours].physics
            them = env.state.cars[env.opponent].physics
            expected.append([reward, *env.state.ball.position, *us.position, *us.linear_velocity,
                             *them.position, *them.linear_velocity])
    finally:
        env.close()
    expected = np.array(expected)
    # RocketSim versions differ; quantify a limited no-ball-contact fixture.
    np.testing.assert_allclose(actual[:, 1:], expected[:, 1:], atol=.05, rtol=0)
    np.testing.assert_allclose(actual[:, 0], expected[:, 0], atol=2e-5, rtol=0)
