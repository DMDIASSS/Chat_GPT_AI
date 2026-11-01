#include "GigaLearn_Project/Native_Attention/AttentionTasks.h"
#include <cassert>
#include <iostream>

using namespace SlaterAttention;

static RLGC::GameState State(int teamSize = 1) {
    RLGC::GameState state;
    state.players.resize(teamSize * 2);
    state.ball.pos = {0, 0, 93.15f};
    for (int i = 0; i < teamSize * 2; ++i) {
        auto& p = state.players[i];
        p.carId = uint32_t(i + 1); p.team = i < teamSize ? RocketSim::Team::BLUE : RocketSim::Team::ORANGE;
        p.ballTouchedTick = p.ballTouchedStep = false;
        p.pos = {float(i * 700), 0, 17}; p.boost = 20;
        p.rotMat = TaskYaw(1.5707963267948966f); p.updateCounter = 1;
    }
    return state;
}

static void TestStarts() {
    for (auto routine : {PracticeRoutine::Match, PracticeRoutine::Defense, PracticeRoutine::Recovery,
                         PracticeRoutine::Boost, PracticeRoutine::Bump, PracticeRoutine::BumpEvasion}) {
        assert(ParsePracticeRoutine(PracticeRoutineName(routine)) == routine);
        for (int ours = 1; ours <= 3; ++ours) for (int theirs = 1; theirs <= 3; ++theirs)
        for (auto team : {RocketSim::Team::BLUE, RocketSim::Team::ORANGE}) {
            auto start = CreateTaskStart(67, .7, routine, ours, theirs, team);
            auto repeat = CreateTaskStart(67, .7, routine, ours, theirs, team);
            assert(start.cars.size() == size_t(ours + theirs));
            assert(start.learnerIndex == (team == RocketSim::Team::BLUE ? 0u : size_t(theirs)));
            assert(start.ball.pos.Dist(repeat.ball.pos) == 0);
            for (size_t i = 0; i < start.cars.size(); ++i) {
                const auto& car = start.cars[i];
                assert(car.pos.Dist(repeat.cars[i].pos) == 0);
                assert(std::isfinite(car.pos.x) && std::isfinite(car.pos.y) && std::isfinite(car.pos.z));
                assert(std::abs(car.pos.x) < 4096 && std::abs(car.pos.y) < 5120);
                assert(car.boost >= 0 && car.boost <= 100);
                assert(std::abs(car.rotMat.up.Length() - 1) < 1e-5);
                assert(std::abs(car.rotMat.up.Dot(car.rotMat.forward)) < 1e-5);
            }
        }
    }
    bool rejected = false;
    try { ParsePracticeRoutine("invented-mechanic"); } catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);
    rejected = false;
    try { CreateTaskStart(0, 0, PracticeRoutine::Boost, 0, 3, RocketSim::Team::BLUE); }
    catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);
}

static void TestDefenseRecovery() {
    auto before = State(), after = before;
    before.ball.pos = after.ball.pos = {0, -4000, 93.15f};
    before.ball.vel = {0, -1200, 0}; after.ball.vel = {0, 1400, 0};
    before.players[0].pos = after.players[0].pos = {0, -4300, 17};
    after.players[0].ballTouchedTick = true;
    TaskTracker defense(PracticeRoutine::Defense);
    auto paid = defense.Tick(before, after, 1);
    assert(paid.reward > .7 && paid.success && paid.events & TaskClear);
    assert(defense.Tick(after, after, 1).reward == 0); // Persistent contact/idle cannot farm.
    auto wall = before, wallAfter = before;
    wall.ball.pos.x = wallAfter.ball.pos.x = 3900;
    wallAfter.players[0].ballTouchedTick = true;
    wallAfter.ball.vel.x = -400; // A side-wall touch with no threatened goal is not a save.
    TaskTracker falseSave(PracticeRoutine::Defense);
    assert(falseSave.Tick(wall, wallAfter, 1).reward == 0);
    TaskTracker noContact(PracticeRoutine::Defense);
    after.players[0].ballTouchedTick = false;
    assert(noContact.Tick(before, after, 1).reward == 0);

    before = State(); after = before;
    before.players[0].isOnGround = false; before.players[0].rotMat.up = {0, 1, 0};
    after.players[0].isOnGround = true; after.players[0].rotMat.up = {0, 0, 1};
    TaskTracker recovery(PracticeRoutine::Recovery);
    assert(recovery.Tick(before, after, 1).reward == 0); // Landing motionless is not useful recovery.
    after.players[0].vel = {0, 1000, 0};
    assert(recovery.Tick(before, after, 1).reward > .5);
    assert(recovery.Tick(after, after, 1).reward == 0);
    recovery.Tick(before, after, 1);
    assert(recovery.Tick(before, after, 1).reward == 0); // Episode milestone cap.
}

static void TestBoost() {
    auto before = State(), after = before;
    const auto pad = RLGC::CommonValues::BOOST_LOCATIONS[7];
    before.players[0].pos = {pad.x, pad.y - 100, 17};
    after.players[0].pos = {pad.x, pad.y - 90, 17};
    before.ball.pos = after.ball.pos = {pad.x, pad.y + 1000, 93.15f};
    after.players[0].vel = {0, 600, 0}; after.players[0].boost = 32;
    after.boostPads[7] = false;
    TaskTracker boost(PracticeRoutine::Boost);
    assert(boost.Tick(before, after, 1).reward > .2);
    assert(boost.Tick(after, after, 1).reward == 0);
    auto fake = after; fake.boostPads[7] = true;
    TaskTracker noPad(PracticeRoutine::Boost);
    assert(noPad.Tick(before, fake, 1).reward == 0);
    auto respawn = before; respawn.players[0].isDemoed = true;
    assert(noPad.Tick(respawn, after, 1).reward == 0);
    auto reset = before; reset.players[0].updateCounter = 25;
    assert(noPad.Tick(reset, after, 1).reward == 0);
    for (int i = 0; i < 100; ++i) boost.Tick(before, after, 1);
    assert(boost.Summary().usefulPickups == 4 && boost.Summary().reward <= 1.5);

    for (int size : {2, 3}) {
        before = State(size); after = before;
        before.players[0].pos = after.players[0].pos = {pad.x, pad.y - 350, 17};
        before.players[0].boost = after.players[0].boost = 60;
        before.players[1].pos = {pad.x, pad.y - 90, 17};
        after.players[1].pos = {pad.x, pad.y - 75, 17};
        before.players[1].boost = 0; after.players[1].boost = 12;
        before.ball.pos = after.ball.pos = {pad.x, pad.y + 1000, 93.15f};
        after.boostPads[7] = false;
        TaskTracker sharing(PracticeRoutine::Boost);
        auto shared = sharing.Tick(before, after, 1);
        assert(shared.reward > .1 && shared.events & TaskSharedPickup);
        assert(sharing.Tick(after, after, 1).reward == 0);

        before.players[0].pos = {pad.x, pad.y - 180, 17};
        after.players[0].pos = {pad.x, pad.y - 160, 17};
        before.players[1].pos = after.players[1].pos = {pad.x, pad.y - 60, 17};
        before.players[1].boost = after.players[1].boost = 0;
        after.players[0].boost = 72;
        TaskTracker stealing(PracticeRoutine::Boost);
        assert(stealing.Tick(before, after, 1).reward < 0);
    }
}

static void TestBumpEvasion() {
    auto before = State(), after = before;
    before.ball.pos = after.ball.pos = {0, 1800, 93.15f};
    before.ball.vel = after.ball.vel = {0, 1200, 0};
    before.players[1].pos = after.players[1].pos = {0, 3000, 17};
    after.players[0].carContact.otherCarID = 2;
    after.players[0].carContact.cooldownTimer = .25f;
    TaskTracker bump(PracticeRoutine::Bump);
    assert(bump.Tick(before, after, 1).reward > .6);
    assert(bump.Tick(before, after, 1).reward == 0); // Same victim never repeat-paid.
    TaskTracker pointlessDemo(PracticeRoutine::Bump);
    before.ball.vel = after.ball.vel = {};
    after.players[1].isDemoed = true;
    assert(pointlessDemo.Tick(before, after, 1).reward == 0);

    TaskTracker evasion(PracticeRoutine::BumpEvasion), stationary(PracticeRoutine::BumpEvasion);
    auto prior = State();
    prior.players[0].pos = {0, 0, 17}; prior.players[0].vel = {};
    prior.players[1].pos = {0, -700, 17}; prior.players[1].vel = {0, 2200, 0};
    auto idlePrior = prior;
    for (int tick = 1; tick <= 70; ++tick) {
        auto next = prior;
        next.players[0].pos = {12.f * tick, 0, 17}; next.players[0].vel = {1440, 0, 0};
        next.players[1].pos = {0, -700.f + 2200.f * tick / 120.f, 17};
        evasion.Tick(prior, next, 1); prior = next;
        auto idleNext = idlePrior; idleNext.players[1].pos = next.players[1].pos;
        stationary.Tick(idlePrior, idleNext, 1); idlePrior = idleNext;
    }
    assert(evasion.Summary().evasions == 1 && evasion.Summary().reward > .4);
    assert(stationary.Summary().evasions == 0 && stationary.Summary().reward == 0);
    auto death = prior; death.players[0].isDemoed = true;
    auto demo = evasion.Tick(prior, death, 1);
    assert(demo.reward == -.5 && demo.events & TaskDemoed);
    assert(evasion.Tick(death, death, 1).reward == 0);
}

static void TestActualRocketSimPickup(const char* meshes) {
    RocketSim::Init(meshes, false);
    auto* arena = RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR);
    auto* ours = arena->AddCar(RocketSim::Team::BLUE);
    auto* theirs = arena->AddCar(RocketSim::Team::ORANGE);
    auto start = CreateTaskStart(2, 0, PracticeRoutine::Boost, 1, 1, RocketSim::Team::BLUE);
    ours->SetState(start.cars[0]); theirs->SetState(start.cars[1]); arena->ball->SetState(start.ball);
    ours->controls.throttle = 1;
    std::vector<RLGC::Action> actions(2);
    RLGC::GameState state;
    state.UpdateFromArena(arena, actions, nullptr);
    TaskTracker tracker(PracticeRoutine::Boost);
    for (int tick = 0; tick < 160; ++tick) {
        RLGC::GameState old = state; old.prev = nullptr;
        arena->Step(1);
        state.ResetBeforeStep(); state.UpdateFromArena(arena, actions, &old);
        tracker.Tick(old, state, ours->id);
    }
    assert(tracker.Summary().usefulPickups >= 1 && tracker.Summary().reward > 0);
    delete arena;
}

int main(int argc, char** argv) {
    if (argc != 2) throw std::invalid_argument("Pass collision meshes directory");
    TestStarts(); TestDefenseRecovery(); TestBoost(); TestBumpEvasion(); TestActualRocketSimPickup(argv[1]);
    std::cout << "NATIVE_ATTENTION_TASKS_PASS starts=108 farm_caps=1 actual_boost=1 share_2s3s=1 useful_bump=1 evade=1\n";
}
