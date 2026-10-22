#include "GigaLearn_Project/Native_Attention/AttentionWorld.h"
#include <cassert>
#include <iostream>

using namespace SlaterAttention;

static void Packet(AttentionWorld& world, const Action& prediction = ZeroAction()) {
    std::map<uint32_t, Action> actions;
    for (auto id : world.ReadyCars()) actions[id] = prediction;
    world.Tick(actions);
}

int main(int argc, char** argv) {
    if (argc != 2) throw std::invalid_argument("Pass collision meshes directory");
    RocketSim::Init(argv[1], false);
    const std::array<int, 5> spawns = {0, 1, 2, 3, 4};
    AttentionWorld world(1, 1, RocketSim::Team::BLUE, 30);
    world.Reset(9, &spawns);
    const Action forward(1, 0, 0, 0, 0, 0, 0, 0);
    assert(world.ReadyCars().empty());
    world.BeginAction(forward);
    assert(world.ReadyCars().size() == 1);
    const float oldSpeed = world.State().players[world.LearnerIndex()].vel.Length2D();
    Packet(world);
    // First physics packet used the previous zero action, not forward.
    assert(world.State().players[world.LearnerIndex()].vel.Length2D() == oldSpeed);
    assert(world.PreviousActions().at(world.LearnerId()).throttle == 1);
    assert(world.ReadyCars().size() == 1); // Source's initial second inference.
    assert(world.StepInfo().scriptPhysicsTicks == 1);
    Packet(world);
    assert(world.State().players[world.LearnerIndex()].vel.Length2D() > oldSpeed);
    while (!world.StepComplete()) Packet(world);
    assert(world.StepInfo().physicsTicks == 8 && !world.Done());
    assert(world.StepInfo().scriptPhysicsTicks == 8);
    // Raw learner never appears among policy-clock requests, including teammates.
    AttentionWorld uneven(3, 2, RocketSim::Team::ORANGE, 30);
    uneven.Reset(4, &spawns);
    uneven.BeginAction(ZeroAction());
    assert(uneven.ReadyCars().size() == 4);
    for (auto id : uneven.ReadyCars()) assert(id != uneven.LearnerId());
    while (!uneven.StepComplete()) Packet(uneven);
    assert(uneven.State().players.size() == 5);

    AttentionWorld timed(1, 1, RocketSim::Team::BLUE, 2.0 / 120.0);
    timed.BeginAction(ZeroAction());
    while (!timed.StepComplete()) Packet(timed);
    assert(timed.Done() && timed.StepInfo().timeout && !timed.StepInfo().terminal);
    assert(timed.StepInfo().physicsTicks == 2 && timed.StepInfo().outcome == 0);

    // Physical goal terminates and is attributed to the learner's team only.
    AttentionWorld goal(1, 1, RocketSim::Team::ORANGE, 30);
    RocketSim::BallState ball;
    ball.pos = {0, 5200, 93.15f}; ball.vel = {0, 3000, 0};
    std::vector<RocketSim::CarState> cars(2);
    cars[0].pos = {-3000, -3000, 17}; cars[1].pos = {3000, 3000, 17};
    for (auto& car : cars) car.isOnGround = true;
    goal.ResetFromStates(ball, cars);
    goal.BeginAction(ZeroAction());
    while (!goal.StepComplete()) Packet(goal);
    assert(goal.Done() && goal.StepInfo().terminal && !goal.StepInfo().timeout);
    assert(goal.StepInfo().outcome == -1);
    assert(goal.Reward() < -9);

    const double phi = MatchPotential({0, 1000, 93}, {0, 0, 17}, 1);
    assert(std::abs(phi - (.4 * 1000 / 5120 - .12 * std::sqrt(1000.0 * 1000 + 76 * 76) / 5000)) < 1e-8);
    assert(std::abs(MatchPotentialReward(.2, .1) - (std::pow(.995, 1.0 / 8) * .2 - .1 - .02 / 120)) < 1e-12);
    std::cout << "NATIVE_ATTENTION_WORLD_PASS delay=1old7new timeout_bootstrap=caller goal_team_correct frozen_only_script=1\n";
}
