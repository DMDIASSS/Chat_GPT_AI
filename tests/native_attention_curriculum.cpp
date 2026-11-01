#include "GigaLearn_Project/Native_Attention/AttentionCurriculum.h"
#include "GigaLearn_Project/Native_Attention/AttentionWorld.h"
#include <cassert>
#include <iostream>
#include <set>

using namespace SlaterAttention;

static void Packet(AttentionWorld& world) {
    if (world.StepComplete()) world.BeginAction(ZeroAction());
    std::map<uint32_t, Action> actions;
    for (auto id : world.ReadyCars()) actions[id] = ZeroAction();
    world.Tick(actions);
}

static RLGC::GameState Fixture(RocketSim::Team team = RocketSim::Team::BLUE) {
    RLGC::GameState state;
    state.deltaTime = 1.f / 120;
    state.players.resize(1);
    auto& car = state.players[0];
    car.carId = 1; car.team = team;
    car.ballTouchedStep = car.ballTouchedTick = false;
    car.pos = {0, 0, 600}; car.vel = {0, team == RocketSim::Team::BLUE ? 500.f : -500.f, 0};
    car.rotMat = CurriculumBasis({0, team == RocketSim::Team::BLUE ? 1.f : -1.f, 0}, {0, 0, 1});
    car.isOnGround = false; car.hasFlipped = true; car.hasJumped = true;
    car.airTimeSinceJump = 1;
    state.ball.pos = car.pos + RocketSim::Vec(0, team == RocketSim::Team::BLUE ? 130.f : -130.f, 65);
    state.ball.vel = car.vel;
    return state;
}

static void RealWheelReset() {
    AttentionWorld world(1, 1, RocketSim::Team::BLUE, 12);
    RocketSim::BallState ball;
    ball.pos = {0, 0, 950}; ball.vel = {0, 400, 0};
    std::vector<RocketSim::CarState> cars(2);
    cars[0].pos = {0, 0, 840}; cars[0].vel = {0, 400, 150};
    cars[0].rotMat = CurriculumBasis({0, 1, 0}, {0, 0, -1});
    cars[0].isOnGround = false; cars[0].hasFlipped = cars[0].hasJumped = true;
    cars[0].airTimeSinceJump = 1;
    cars[1].pos = {3000, 4000, 17}; cars[1].rotMat = RocketSim::RotMat::GetIdentity();
    world.ResetFromStates(ball, cars);
    assert(!world.State().players[world.LearnerIndex()].HasFlipOrJump());
    CurriculumTracker tracker(CurriculumStage::ResetAcquire, 0, CurriculumStage::ResetAcquire);
    bool detected = false;
    double acquisitionReward = 0;
    for (int tick = 0; tick < 80; ++tick) {
        auto before = world.State(); Packet(world);
        const auto event = tracker.tick(before, world.State(), world.LearnerId());
        if (event.events & ResetAcquireEvent) {
            const auto& car = world.State().players[world.LearnerIndex()];
            assert(car.HasFlipOrJump());
            assert(FourWheelBallContact(car, world.State().ball));
            assert(event.success && tracker.summary().resetsAcquired == 1);
            detected = true; acquisitionReward = event.reward;
        }
    }
    assert(detected && acquisitionReward > .65);
    assert(tracker.summary().resetsAcquired == 1); // Sustained contact never farms resets.
    assert(tracker.summary().resetsUsed == 0);
    assert(!tracker.summary().fullChain); // No fabricated wall/carry prefix.
}

static void RealWallRollBothSides() {
    for (int side : {-1, 1}) {
        AttentionWorld world(1, 1, RocketSim::Team::BLUE, 12);
        RocketSim::BallState ball;
        ball.pos = {side * 4002.85f, 0, 400}; ball.vel = {0, 0, 500};
        std::vector<RocketSim::CarState> cars(2);
        cars[0].pos = {side * 4078.f, 0, 270}; cars[0].vel = {0, 0, 600};
        cars[0].rotMat = CurriculumBasis({0, 0, 1}, {-float(side), 0, 0});
        cars[0].isOnGround = true;
        for (bool& contact : cars[0].wheelsWithContact) contact = true;
        cars[1].pos = {3000, 4000, 17}; cars[1].rotMat = RocketSim::RotMat::GetIdentity();
        world.ResetFromStates(ball, cars);
        CurriculumTracker tracker(CurriculumStage::WallRoll);
        bool detected = false;
        for (int tick = 0; tick < 180 && !detected; ++tick) {
            if (world.StepComplete()) world.BeginAction(Action(1, 0, 0, 0, 0, 0, 1, 0));
            auto before = world.State();
            std::map<uint32_t, Action> actions;
            for (auto id : world.ReadyCars()) actions[id] = ZeroAction();
            world.Tick(actions);
            const auto result = tracker.tick(before, world.State(), world.LearnerId());
            detected = result.events & WallRollEvent;
        }
        assert(detected && tracker.summary().wallRise >= 120 && tracker.summary().success);
        assert(!(tracker.summary().earnedEvents & WallPopEvent));
    }
}

static void FalseResetsAndProximity() {
    // A statesetter may make HasFlipReset true without any ball-wheel event.
    auto old = Fixture(); auto next = old;
    next.players[0].hasFlipped = next.players[0].hasJumped = false;
    assert(next.players[0].HasFlipReset());
    CurriculumTracker falseReset(CurriculumStage::ResetAcquire, 0, CurriculumStage::ResetAcquire);
    assert(!(falseReset.tick(old, next, 1).events & ResetAcquireEvent));

    // Even fabricated four contact wheels are rejected at the side wall.
    old = Fixture(); next = old;
    old.players[0].pos = {4000, 0, 600};
    next.players[0].pos = {4000, 0, 600};
    next.players[0].rotMat = CurriculumBasis({0, 1, 0}, {1, 0, 0});
    next.ball.pos = {3890, 0, 600};
    next.players[0].hasFlipped = next.players[0].hasJumped = false;
    next.players[0].isOnGround = true;
    for (bool& contact : next.players[0].wheelsWithContact) contact = true;
    assert(!FourWheelBallContact(next.players[0], next.ball));
    assert(!(falseReset.tick(old, next, 1).events & ResetAcquireEvent));

    // Matching velocity/proximity alone, however long, never earns air carry.
    CurriculumTracker proximity(CurriculumStage::AirCarry, 0, CurriculumStage::AirCarry);
    old = Fixture();
    for (int tick = 0; tick < 500; ++tick) {
        next = old; next.ball.pos.y += 4; next.players[0].pos.y += 4;
        auto result = proximity.tick(old, next, 1);
        assert(!(result.events & AirCarryEvent) && !result.success && result.reward <= 0);
        old = next;
    }
    assert(proximity.summary().bestCarrySeconds == 0 && proximity.summary().carryProgress == 0);

    // Real ground contact can restore the flip; it must not earn a ball reset.
    AttentionWorld ground(1, 1, RocketSim::Team::BLUE, 12);
    RocketSim::BallState ball; ball.pos = {0, 0, 93.15f};
    std::vector<RocketSim::CarState> cars(2);
    cars[0].pos = {1000, 0, 80}; cars[0].vel = {0, 0, -150};
    cars[0].rotMat = RocketSim::RotMat::GetIdentity();
    cars[0].isOnGround = false; cars[0].hasFlipped = cars[0].hasJumped = true;
    cars[1].pos = {3000, 4000, 17}; cars[1].rotMat = RocketSim::RotMat::GetIdentity();
    ground.ResetFromStates(ball, cars);
    CurriculumTracker landing(CurriculumStage::ResetAcquire, 0, CurriculumStage::ResetAcquire);
    bool landed = false;
    for (int tick = 0; tick < 100; ++tick) {
        auto before = ground.State(); Packet(ground);
        const auto result = landing.tick(before, ground.State(), ground.LearnerId());
        assert(!(result.events & ResetAcquireEvent));
        landed |= ground.State().players[ground.LearnerIndex()].isOnGround;
    }
    assert(landed && landing.summary().resetsAcquired == 0);
}

static void UsefulResetShotsAreCapped() {
    // A flip touching the ball almost sideways is not a useful reset shot even
    // if its small forward component increases.
    auto sidewaysOld = Fixture(); auto sidewaysNext = sidewaysOld;
    sidewaysOld.players[0].hasFlipped = sidewaysOld.players[0].hasJumped = false;
    sidewaysNext.players[0].hasFlipped = true;
    sidewaysNext.players[0].isFlipping = true;
    sidewaysNext.players[0].ballTouchedStep = true;
    sidewaysNext.ball.vel = {5000, 750, 0};
    CurriculumTracker sideways(CurriculumStage::ResetShot, 0, CurriculumStage::ResetShot);
    assert(!(sideways.tick(sidewaysOld, sidewaysNext, 1).events & ResetShotEvent));

    auto state = Fixture();
    state.players[0].rotMat = CurriculumBasis({0, 1, 0}, {0, 0, -1});
    state.players[0].pos = {0, 0, 700}; state.ball.pos = {0, 0, 810};
    state.players[0].hasFlipped = true;
    CurriculumTracker tracker(CurriculumStage::ResetShot, 0, CurriculumStage::ResetAcquire);
    // Causal state fixtures test repeated flip use independently of the actual
    // wheel-physics fixture above. Each acquisition is a spent->regained edge.
    for (int repetition = 0; repetition < 5; ++repetition) {
        auto next = state;
        next.players[0].hasFlipped = next.players[0].hasJumped = false;
        next.players[0].isOnGround = false;
        for (bool& contact : next.players[0].wheelsWithContact) contact = true;
        auto acquired = tracker.tick(state, next, 1);
        assert(bool(acquired.events & ResetAcquireEvent) == (repetition < 3));
        state = next;
        next.players[0].hasFlipped = true; next.players[0].hasJumped = true;
        next.players[0].isFlipping = true;
        for (bool& contact : next.players[0].wheelsWithContact) contact = false;
        next.players[0].ballTouchedStep = true;
        next.ball.vel.y = state.ball.vel.y + 200;
        auto used = tracker.tick(state, next, 1);
        assert(bool(used.events & ResetShotEvent) == (repetition < 3));
        state = next; state.players[0].ballTouchedStep = false;
        state.players[0].isFlipping = false;
        for (int tick = 0; tick < 25; ++tick) {
            auto held = tracker.tick(state, state, 1);
            assert(!(held.events & (ResetAcquireEvent | ResetShotEvent)));
        }
    }
    assert(tracker.summary().resetsAcquired == 3 && tracker.summary().resetsUsed == 3);
    assert(tracker.summary().success);
    assert(tracker.summary().reward < 6); // Diminishing, bounded repeated bonuses.
}

static void WallAndCarryRequireActualProgress() {
    auto old = Fixture(); auto next = old;
    old.ball.pos = {3990, 0, 150}; next.ball.pos = {3990, 0, 275};
    old.players[0].pos = {4050, 0, 100}; next.players[0].pos = {4050, 0, 200};
    next.players[0].rotMat = CurriculumBasis({0, 0, 1}, {-1, 0, 0});
    next.players[0].vel.z = 200; next.ball.vel.z = 500;
    next.players[0].ballTouchedStep = true;
    for (bool& contact : next.players[0].wheelsWithContact) contact = true;
    CurriculumTracker wall(CurriculumStage::WallRoll);
    auto rolled = wall.tick(old, next, 1);
    assert((rolled.events & WallRollEvent) && rolled.success);
    // No outward pop reward for a wall-normal zero-speed contact.
    old = next; next.ball.pos.x = 3800; next.ball.vel.x = 0;
    assert(!(wall.tick(old, next, 1).events & WallPopEvent));
    old = next; old.ball.pos.x = 3950; old.ball.vel.x = 0;
    next.ball.pos.x = 3860; next.ball.pos.z = 350; next.ball.vel.x = -500;
    auto popped = wall.tick(old, next, 1);
    assert(popped.events & WallPopEvent);
    assert(wall.summary().earnedEvents & WallRollEvent);

    CurriculumTracker carry(CurriculumStage::AirCarry, 0, CurriculumStage::AirCarry);
    old = Fixture();
    bool qualified = false;
    for (int tick = 0; tick < 80; ++tick) {
        next = old; next.ball.pos.y += 5; next.players[0].pos.y += 5;
        next.players[0].ballTouchedStep = true;
        auto result = carry.tick(old, next, 1);
        qualified |= result.events & AirCarryEvent;
        old = next;
    }
    assert(qualified && carry.summary().success && carry.summary().bestCarrySeconds > .45);
    assert(!(carry.summary().earnedEvents & (WallRollEvent | WallPopEvent)));
}

static void DeadlineStopsMechanicRewardsButKeepsGoals() {
    auto state = Fixture();
    CurriculumTracker tracker(CurriculumStage::WallRoll);
    int expiryEvents = 0;
    for (int tick = 0; tick < 900; ++tick) {
        auto result = tracker.tick(state, state, 1);
        expiryEvents += bool(result.events & DeadlineEvent);
        assert(!(result.events & WallRollEvent));
    }
    assert(expiryEvents == 1 && tracker.summary().expired && !tracker.summary().success);
    // A qualifying wall transition after expiration earns no skill reward;
    // the episode's later team goal remains valuable exactly once.
    auto next = state;
    next.ball.pos = {3990, 0, 400}; next.ball.vel = {0, 0, 500};
    next.players[0].pos = {4050, 0, 300}; next.players[0].vel = {0, 0, 500};
    next.players[0].ballTouchedStep = true;
    for (bool& contact : next.players[0].wheelsWithContact) contact = true;
    assert(!(tracker.tick(state, next, 1).events & WallRollEvent));
    state = next; next.goalScored = true; next.ball.pos = {0, 5250, 93.15f};
    const auto goal = tracker.tick(state, next, 1);
    assert((goal.events & GoalEvent) && goal.scored && !goal.success);
    assert(goal.reward > .49 && goal.reward < .51);
    assert(tracker.tick(next, next, 1).reward == 0);
}

static void TeamGoalsAndRandomStarts() {
    for (const auto team : {RocketSim::Team::BLUE, RocketSim::Team::ORANGE}) {
        const float sign = team == RocketSim::Team::BLUE ? 1.f : -1.f;
        for (int outcome : {-1, 1}) {
            AttentionWorld world(1, 1, team, 12);
            auto start = CreatePracticeStart(12, .3f, CurriculumStage::Finish, team);
            start.ball.pos = {0, sign * outcome * 5200, 93.15f};
            start.ball.vel = {0, sign * outcome * 3000, 0};
            for (size_t index = 0; index < start.cars.size(); ++index) {
                start.cars[index].pos = {index ? 3000.f : -3000.f, index ? 3000.f : -3000.f, 17};
                start.cars[index].vel = {}; start.cars[index].rotMat = RocketSim::RotMat::GetIdentity();
            }
            world.ResetFromStates(start.ball, start.cars);
            CurriculumTracker tracker(CurriculumStage::Finish, .3f, CurriculumStage::Finish);
            bool seenGoal = false;
            for (int tick = 0; tick < 10 && !world.Done(); ++tick) {
                auto before = world.State(); Packet(world);
                auto result = tracker.tick(before, world.State(), world.LearnerId());
                if (result.events & (GoalEvent | ConcedeEvent)) {
                    seenGoal = true; assert(result.scored == (outcome == 1));
                    assert(result.conceded == (outcome == -1));
                    assert(result.success == (outcome == 1));
                    assert((outcome == 1 && result.reward > 1) || (outcome == -1 && result.reward < -2.9));
                    assert(tracker.tick(world.State(), world.State(), world.LearnerId()).reward == 0);
                }
            }
            assert(seenGoal && !tracker.summary().fullChain);
        }
    }
    std::set<int> wallSides;
    for (int stage = 0; stage < 6; ++stage) {
        for (uint64_t seed = 0; seed < 20; ++seed) {
            const auto team = seed % 2 ? RocketSim::Team::BLUE : RocketSim::Team::ORANGE;
            auto start = CreatePracticeStart(seed, .4f, CurriculumStage(stage), team);
            auto same = CreatePracticeStart(seed, .4f, CurriculumStage(stage), team);
            assert(start.ball.pos == same.ball.pos && start.cars.size() == 2);
            assert(start.ball.pos.z > 90 && start.ball.pos.z < 1400);
            const auto& learner = start.cars[team == RocketSim::Team::BLUE ? 0 : 1];
            assert(learner.boost >= 56 && learner.boost <= 100);
            assert(std::abs(learner.rotMat.forward.Dot(learner.rotMat.up)) < 1e-5);
            assert(std::abs(learner.rotMat.forward.Length() - 1) < 1e-5);
            wallSides.insert(start.wallSide);
            // Real physics must accept every randomized stage/color stateset.
            AttentionWorld world(1, 1, team, 12);
            world.ResetFromStates(start.ball, start.cars, start.cooldowns);
            CurriculumTracker tracker(CurriculumStage(stage), .4f, CurriculumStage(stage));
            for (int tick = 0; tick < 16; ++tick) {
                auto before = world.State(); Packet(world);
                const auto result = tracker.tick(before, world.State(), world.LearnerId());
                assert(std::isfinite(result.reward));
                // Initial synthetic unlocks themselves never pay event rewards.
                if (stage > 0) assert(!(tracker.summary().earnedEvents & ((1u << stage) - 1)));
            }
        }
    }
    assert(wallSides.size() == 2);
}

int main(int argc, char** argv) {
    if (argc != 2) throw std::invalid_argument("Pass collision meshes directory");
    RocketSim::Init(argv[1], false);
    RealWheelReset(); RealWallRollBothSides(); FalseResetsAndProximity(); UsefulResetShotsAreCapped();
    WallAndCarryRequireActualProgress(); DeadlineStopsMechanicRewardsButKeepsGoals(); TeamGoalsAndRandomStarts();
    std::cout << "NATIVE_ATTENTION_CURRICULUM_PASS real_wheel_reset=1 real_wall_roll_both_sides=1 false_reset_rejected=1 "
              << "proximity_farming=0 capped_repeats=3 goals_both_colors=1 randomized_starts=120\n";
}
