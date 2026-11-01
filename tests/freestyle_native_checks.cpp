#include "GigaLearn_Project/Freestyle/FreestyleRewards.h"
#include "GigaLearn_Project/Freestyle/FreestyleObs.h"
#include "GigaLearn_Project/Freestyle/FreestyleActions.h"
#include <cassert>
#include <iostream>
#include <memory>
#include <set>

using namespace SlaterFreestyle;

static RocketSim::RotMat Basis(const RocketSim::Vec& forward,
                              const RocketSim::Vec& up = {0, 0, 1}) {
    const auto f = Unit(forward), r = Unit(up.Cross(f));
    return RocketSim::RotMat(f, r, Unit(f.Cross(r)));
}

static RLGC::GameState Fixture(RocketSim::Team team = RocketSim::Team::BLUE) {
    RLGC::GameState state;
    state.deltaTime = 1.f / 120;
    state.players.resize(1);
    auto& p = state.players[0];
    p.carId = 1; p.team = team; p.index = 0;
    p.ballTouchedStep = p.ballTouchedTick = false;
    p.pos = {0, 0, 600}; p.vel = {0, team == RocketSim::Team::BLUE ? 500.f : -500.f, 0};
    p.rotMat = Basis(p.vel); p.isOnGround = false;
    p.hasFlipped = p.hasJumped = true; p.airTimeSinceJump = 2;
    p.prevAction = RLGC::Action(1, 0, 0, 0, 0, 0, 0, 0);
    const float sign = team == RocketSim::Team::BLUE ? 1.f : -1.f;
    state.ball.pos = p.pos + RocketSim::Vec(0, sign * 130, 65);
    state.ball.vel = p.vel;
    return state;
}

static void Next(RLGC::GameState& state, bool touch = false) {
    ++state.lastTickCount;
    auto& p = state.players[0]; p.ballTouchedStep = touch;
    if (touch) {
        p.ballHitInfo.isValid = true;
        p.ballHitInfo.tickCountWhenHit = state.lastTickCount;
    }
}

static void NoContactFarming() {
    auto ctx = std::make_shared<FreestyleContext>(); ctx->learnerId = 1;
    ctx->stage = Stage::AirCarry;
    FreestyleReward reward(ctx);
    auto state = Fixture(); reward.Reset(state);
    for (int i = 0; i < 1200; ++i) {
        Next(state); state.ball.pos.y += 4; state.players[0].pos.y += 4;
        assert(reward.GetReward(state.players[0], state, false) == 0);
    }
    assert(!reward.IsSuccess(1));
    assert(ctx->chains.at(1).bestCarry == 0);
    assert(ctx->chains.at(1).noseTouches == 0);
    reward.FinishEpisode();
    assert(ctx->telemetry->Snapshot().at("measurements/positive_reward_sum") == 0);
}

static void GoalAttributionAndRepeatedTick() {
    for (const auto team : {RocketSim::Team::BLUE, RocketSim::Team::ORANGE}) {
        const float sign = team == RocketSim::Team::BLUE ? 1.f : -1.f;
        for (const bool attributed : {false, true}) {
            auto ctx = std::make_shared<FreestyleContext>(); ctx->learnerId = 1;
            FreestyleReward reward(ctx);
            auto state = Fixture(team); reward.Reset(state);
            if (attributed) {
                Next(state, true); reward.PreStep(state);
            }
            Next(state); state.goalScored = true; state.ball.pos = {0, sign * 5300, 93};
            state.lastTouchCarID = attributed ? 1 : 2;
            const float paid = reward.GetReward(state.players[0], state, false);
            const auto metrics = ctx->telemetry->Snapshot();
            reward.PreStep(state);
            assert(ctx->telemetry->Snapshot() == metrics);
            assert(attributed ? paid >= .5f : paid < .5f); // Modest solo-pop goal reward.
            Next(state); reward.GetReward(state.players[0], state, false);
            const auto final = ctx->telemetry->Snapshot();
            auto goals = final.find("events/learner_goal");
            assert(attributed ? goals != final.end() && goals->second == 1 : goals == final.end());
            auto goalReward = final.find("weighted_sum/goal");
            assert(attributed ? goalReward != final.end() && goalReward->second == .5 : goalReward == final.end());
        }
    }
}

static double Metric(const std::shared_ptr<FreestyleContext>& ctx,const std::string& name) {
    auto values=ctx->telemetry->Snapshot();auto found=values.find(name);
    return found==values.end()?0:found->second;
}

static void OrdinaryShotsCannotBecomeFreestyleFinishes() {
    for(auto team:{RocketSim::Team::BLUE,RocketSim::Team::ORANGE}) {
        const float sign=team==RocketSim::Team::BLUE?1.f:-1.f;
        auto ctx=std::make_shared<FreestyleContext>();ctx->learnerId=1;
        FreestyleReward reward(ctx);auto state=Fixture(team);
        state.players[0].pos={0,0,17};state.players[0].vel={0,sign*2200,0};
        state.players[0].isOnGround=true;state.ball.pos={0,sign*130,93};state.ball.vel={0,0,0};
        reward.Reset(state);auto before=state;state.prev=&before;
        Next(state,true);state.ball.vel={0,sign*2500,0};state.lastTouchCarID=1;
        reward.PreStep(state);
        assert(!ctx->chains.at(1).pinch);
        Next(state);state.goalScored=true;state.ball.pos={0,sign*5300,93};reward.PreStep(state);
        assert(Metric(ctx,"events/learner_goal")==1);
        assert(Metric(ctx,"weighted_sum/goal")==.5);
        assert(Metric(ctx,"weighted_sum/qualified_finish")==0);
        assert(Metric(ctx,"events/qualified_mechanic_goal")==0);
    }
    // A genuine compression proxy is rewarded only by the pinch curriculum.
    for(auto stage:{Stage::ContactPop,Stage::Pinch}) {
        auto ctx=std::make_shared<FreestyleContext>();ctx->learnerId=1;ctx->stage=stage;
        FreestyleReward reward(ctx);auto state=Fixture();
        state.players[0].pos={0,0,160};state.players[0].vel={0,1000,-800};
        state.ball.pos={0,50,93};state.ball.vel={0,0,0};reward.Reset(state);
        auto before=state;state.prev=&before;Next(state,true);state.ball.vel={0,2500,0};
        state.lastTouchCarID=1;reward.PreStep(state);assert(ctx->chains.at(1).pinch);
        Next(state);state.goalScored=true;state.ball.pos={0,5300,93};reward.PreStep(state);
        assert((Metric(ctx,"weighted_sum/pinch_proxy")>0)==(stage==Stage::Pinch));
        assert((Metric(ctx,"weighted_sum/qualified_finish")>0)==(stage==Stage::Pinch));
    }
}

static void LearnerLiftMustRiseThenReceiveASeparateAirTouch() {
    for(bool learnerLastTouch:{false,true}) {
        auto ctx=std::make_shared<FreestyleContext>();ctx->learnerId=1;
        ctx->difficulty=.3f;ctx->contactObjective=2;
        FreestyleReward reward(ctx);auto state=Fixture();
        state.players[0].pos={0,0,17};state.players[0].isOnGround=true;
        state.ball.pos={0,130,93};state.ball.vel={0,200,0};reward.Reset(state);
        auto before=state;state.prev=&before;Next(state,true);
        state.ball.pos.z=95;state.ball.vel.z=400;state.lastTouchCarID=1;
        reward.PreStep(state);
        assert(!ctx->chains.at(1).pop&&ctx->chains.at(1).pendingLift);
        assert(Metric(ctx,"weighted_sum/lift_progress")>0);
        for(int i=0;i<12;++i)Next(state);
        state.ball.pos.z=155;state.lastTouchCarID=learnerLastTouch?1:2;reward.PreStep(state);
        assert(ctx->chains.at(1).pop==learnerLastTouch);
        assert(!reward.IsSuccess(1));
        if(!learnerLastTouch)continue;
        for(int i=0;i<12;++i)Next(state);
        state.players[0].pos.z=400;state.players[0].isOnGround=false;state.players[0].airTime=1;
        state.ball.pos.z=450;Next(state,true);reward.PreStep(state);
        assert(ctx->chains.at(1).popRetouch&&reward.IsSuccess(1));
        assert(Metric(ctx,"events/pop_air_retouch")==1);
        for(int i=0;i<24;++i){Next(state,true);reward.PreStep(state);}
        assert(Metric(ctx,"events/pop_air_retouch")==1); // Cannot farm the chain step.
        Next(state);state.goalScored=true;state.ball.pos={0,5300,93};reward.PreStep(state);
        assert(Metric(ctx,"weighted_sum/qualified_finish")==6);
    }
    auto ctx=std::make_shared<FreestyleContext>();ctx->learnerId=1;ctx->contactObjective=2;
    FreestyleReward reward(ctx);auto state=Fixture();reward.Reset(state);
    Next(state,true);reward.PreStep(state);
    assert(!ctx->chains.at(1).pop&&!reward.IsSuccess(1)); // High spawn + touch is not a pop.
}

static void GradualContactObjectives() {
    auto ctx=std::make_shared<FreestyleContext>();
    for(float difficulty:{0.f,.175f,.3f,.675f,1.f}) {
        ctx->control->difficulty=difficulty;int pops=0,retouches=0;
        for(int n=0;n<1000;++n){ctx->SampleSettings();pops+=ctx->contactObjective>0;retouches+=ctx->contactObjective==2;}
        if(difficulty==0)assert(pops==0);
        if(difficulty==.175f)assert(pops>400&&pops<600);
        if(difficulty==.3f)assert(pops==1000&&retouches==0);
        if(difficulty==.675f)assert(pops==1000&&retouches>400&&retouches<600);
        if(difficulty==1)assert(retouches==1000);
    }
}

static void SequentialResetUseAndEpisodeCap() {
    auto ctx = std::make_shared<FreestyleContext>(); ctx->learnerId = 1;
    ctx->stage = Stage::MultiReset;
    RewardConfig config; config.maxEpisodePositive = 12;
    FreestyleReward reward(ctx, config);
    auto state = Fixture(); reward.Reset(state);
    // A touch and flip without ball-earned resource evidence cannot earn use.
    state.players[0].hasFlipped = true;
    Next(state, true); reward.PreStep(state);
    assert(ctx->chains.at(1).resets == 0 && ctx->chains.at(1).resetUses == 0);
    double sum = reward.GetReward(state.players[0], state, false);
    // Mock verified physics counters here; physical recharge is checked below.
    // Include expired use and landing to prove ordering/deadlines matter.
    ctx->physics[1].resets = 1; Next(state); reward.PreStep(state);
    for (int i = 0; i < 320; ++i) { Next(state); sum += reward.GetReward(state.players[0], state, false); }
    ctx->physics[1].flipsFromReset = 1; Next(state, true);
    state.ball.vel.y += 300; sum += reward.GetReward(state.players[0], state, false);
    assert(ctx->chains.at(1).resetUses == 0);
    for (int repetition = 0; repetition < 20; ++repetition) {
        ++ctx->physics[1].resets; Next(state); sum += reward.GetReward(state.players[0], state, false);
        ++ctx->physics[1].flipsFromReset;
        auto previous = state; Next(state, true); state.prev = &previous;
        state.ball.vel.y += 300;
        sum += reward.GetReward(state.players[0], state, false);
        state.prev = nullptr;
    }
    assert(ctx->chains.at(1).resetUses == 20);
    assert(reward.IsSuccess(1));
    assert(sum <= config.maxEpisodePositive + 1e-4);
    reward.FinishEpisode();
    assert(ctx->telemetry->Snapshot().at("measurements/positive_reward_sum") <= 12.0001);
    const auto before = ctx->telemetry->Snapshot(); reward.FinishEpisode();
    assert(before == ctx->telemetry->Snapshot());
}

static void RealResetAndFalseResourceEdges() {
    std::unique_ptr<RocketSim::Arena> arena(RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR));
    auto* car = arena->AddCar(RocketSim::Team::BLUE);
    auto ctx = std::make_shared<FreestyleContext>(); ctx->learnerId = car->id;
    RocketSim::BallState ball; ball.pos = {0, 0, 950}; ball.vel = {0, 400, 0};
    RocketSim::CarState own; own.pos = {0, 0, 840}; own.vel = {0, 400, 150};
    own.rotMat = Basis({0, 1, 0}, {0, 0, -1}); own.isOnGround = false;
    own.hasFlipped = own.hasJumped = true; own.airTimeSinceJump = 2;
    arena->ball->SetState(ball); car->SetState(own);
    assert(!car->GetState().HasFlipOrJump());
    FreestyleObservePhysics(ctx, arena.get());
    for (int tick = 0; tick < 100; ++tick) {
        arena->Step(); FreestyleObservePhysics(ctx, arena.get());
    }
    assert(ctx->physics.at(car->id).resets == 1);
    assert(ctx->physics.at(car->id).fourWheelBallContacts > 0);
    assert(ctx->physics.at(car->id).flipsFromReset == 0);

    // Already-available airborne starts and world landings cannot be resets.
    for (bool worldContact : {false, true}) {
        ctx->physics.clear(); own = RocketSim::CarState{};
        own.pos = {worldContact ? 4000.f : 0.f, 0, 840}; own.isOnGround = false;
        own.rotMat = Basis({0, 1, 0}, {0, 0, -1});
        own.worldContact.hasContact = worldContact;
        for (bool& wheel : own.wheelsWithContact) wheel = true;
        own.hasFlipped = own.hasJumped = true; own.airTimeSinceJump = 2;
        ball.pos = own.pos + RocketSim::Vec(0, 0, 110);
        arena->ball->SetState(ball); car->SetState(own); FreestyleObservePhysics(ctx, arena.get());
        own.hasFlipped = own.hasJumped = false; own.airTimeSinceJump = 0;
        car->SetState(own); ++arena->tickCount; FreestyleObservePhysics(ctx, arena.get());
        if (worldContact) assert(ctx->physics.at(car->id).resets == 0);
        else assert(ctx->physics.at(car->id).resets == 0); // Boolean wheel flags alone are not ball raycasts.
        // The same contact cannot pay repeatedly.
        for (int i = 0; i < 20; ++i) { ++arena->tickCount; FreestyleObservePhysics(ctx, arena.get()); }
        assert(ctx->physics.at(car->id).resets == 0);
    }
    ctx->physics.clear(); own.hasFlipped = own.hasJumped = false;
    own.worldContact.hasContact = false; own.pos = {0, 0, 840};
    ball.pos = {0, 0, 950}; arena->ball->SetState(ball); car->SetState(own);
    FreestyleObservePhysics(ctx, arena.get());
    assert(ctx->physics.at(car->id).resets == 0);
}

static void StateSettersAndObservations() {
    std::set<int> wallSides;
    for (const auto team : {RocketSim::Team::BLUE, RocketSim::Team::ORANGE}) {
        std::unique_ptr<RocketSim::Arena> arena(RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR));
        auto* car = arena->AddCar(team);
        auto control = std::make_shared<CurriculumControl>(); control->evaluation = true;
        auto ctx = std::make_shared<FreestyleContext>(control, std::make_shared<FreestyleTelemetry>(), 73);
        ctx->learnerId = car->id;
        FreestyleStateSetter setter(ctx); FreestyleObs obs(ctx);
        for (int stage = 0; stage < STAGE_COUNT; ++stage) {
            control->stage = stage;
            for (int sample = 0; sample < 12; ++sample) {
                control->difficulty = float(sample) / 11; setter.ResetArena(arena.get());
                const auto own = car->GetState();
                const auto ball = arena->ball->GetState();
                assert(std::isfinite(own.pos.Length()) && std::isfinite(ball.pos.Length()));
                assert(own.boost >= 0 && own.boost <= 100 && own.pos.z > 0 && ball.pos.z >= 90);
                assert(std::abs(own.rotMat.forward.Length() - 1) < 1e-4);
                assert(std::abs(own.rotMat.up.Length() - 1) < 1e-4);
                assert(std::abs(own.rotMat.forward.Dot(own.rotMat.up)) < 1e-4);
                if (stage == int(Stage::WallRecovery) || stage == int(Stage::WallDashProxy))
                    wallSides.insert(own.pos.x > 0 ? 1 : -1);
                RLGC::GameState state(arena.get()); obs.Reset(state);
                const auto values = obs.BuildObs(state.players[0], state);
                assert(values.size() == FreestyleObs::SIZE);
                for (float value : values) assert(std::isfinite(value));
                FreestyleReward reward(ctx); reward.Reset(state);
                assert(!reward.IsSuccess(car->id));
                assert(ctx->physics.at(car->id).resets == 0);
                arena->Step(4); RLGC::GameState after(arena.get());
                assert(std::isfinite(after.ball.pos.Length()));
            }
        }
    }
    assert(wallSides.size() == 2);
}

static void TeamSymmetryAndMasking() {
    auto blue = Fixture(); blue.players[0].pos.x = 200;
    blue.players[0].angVel = {.3f, -.8f, 1.2f};
    blue.ball.pos.x = 270; blue.ball.angVel = {.4f, .6f, -.2f};
    for (size_t pad = 0; pad < 34; ++pad) {
        blue.boostPads[pad] = pad % 3 != 0;
        blue.boostPadTimers[pad] = float(pad % 10);
    }
    auto orange = blue; auto flip = [](const RocketSim::Vec& v) {
        return RocketSim::Vec(-v.x, -v.y, v.z);
    };
    orange.players[0].team = RocketSim::Team::ORANGE;
    for (auto* v : {&orange.players[0].pos, &orange.players[0].vel, &orange.players[0].angVel,
                   &orange.players[0].rotMat.forward, &orange.players[0].rotMat.right,
                   &orange.players[0].rotMat.up, &orange.ball.pos, &orange.ball.vel, &orange.ball.angVel})
        *v = flip(*v);
    for (size_t source = 0; source < 34; ++source) {
        const auto target = flip(RLGC::CommonValues::BOOST_LOCATIONS[source]);
        bool found = false;
        for (size_t dest = 0; dest < 34; ++dest) {
            // The pinned upstream map has one 3310-vs-3308 boost location typo.
            if ((RLGC::CommonValues::BOOST_LOCATIONS[dest] - target).Length() < 2.001f) {
                orange.boostPads[dest] = blue.boostPads[source];
                orange.boostPadTimers[dest] = blue.boostPadTimers[source];
                found = true; break;
            }
        }
        assert(found);
    }
    auto ctx = std::make_shared<FreestyleContext>(); FreestyleObs obs(ctx);
    const auto a = obs.BuildObs(blue.players[0], blue), b = obs.BuildObs(orange.players[0], orange);
    assert(a.size() == 512 && b.size() == 512);
    for (size_t i = 0; i < a.size(); ++i) {
        const float tolerance = i >= 125 && i < 295 ? 2.001f / 6000 : 1e-5f;
        if (std::abs(a[i] - b[i]) > tolerance) {
            std::cerr << "TEAM_SYMMETRY_MISMATCH " << i << ": " << a[i] << " != " << b[i] << '\n';
            assert(false);
        }
    }
    auto altered = blue;
    for (bool& wheel : altered.players[0].wheelsWithContact) wheel = true;
    altered.players[0].worldContact.hasContact = true;
    altered.players[0].worldContact.contactNormal = {1, 0, 0};
    const auto hidden = obs.BuildObs(altered.players[0], altered);
    assert(hidden == a); // Unavailable oracle channels cannot leak through their mask.
    ctx->privilegedVisible = true;
    assert(obs.BuildObs(altered.players[0], altered) != hidden);

    auto squad = blue;
    for (unsigned index = 1; index < 6; ++index) {
        auto other = blue.players[0]; other.carId = index + 1;
        other.team = index % 2 ? RocketSim::Team::ORANGE : RocketSim::Team::BLUE;
        other.pos += RocketSim::Vec(index * 100, index * 200, 0);
        squad.players.push_back(other);
    }
    const auto roster = obs.BuildObs(squad.players[0], squad);
    assert(roster.size() == 512);
    for (float value : roster) assert(std::isfinite(value));
    std::reverse(squad.players.begin() + 1, squad.players.end());
    assert(obs.BuildObs(squad.players[0], squad) == roster);
}

static void TwoCarLearnerSelectionAndRewards() {
    // Arena::GetCars() is unordered: its first entry is usually the last added
    // orange defender. The training learner must still be the blue car.
    for (const bool blueFirst : {false, true}) {
        std::unique_ptr<RocketSim::Arena> arena(RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR));
        RocketSim::Car* blue;
        RocketSim::Car* orange;
        if (blueFirst) {
            blue = arena->AddCar(RocketSim::Team::BLUE);
            orange = arena->AddCar(RocketSim::Team::ORANGE);
        } else {
            orange = arena->AddCar(RocketSim::Team::ORANGE);
            blue = arena->AddCar(RocketSim::Team::BLUE);
        }
        auto ctx = std::make_shared<FreestyleContext>();
        FreestyleStateSetter setter(ctx); setter.ResetArena(arena.get());
        assert(ctx->learnerId == blue->id);
        for (bool reverse : {false, true}) {
            auto state = Fixture(); state.players[0].carId = blue->id;
            auto defender = state.players[0]; defender.carId = orange->id;
            defender.team = RocketSim::Team::ORANGE; defender.pos = {1000, 1000, 17};
            defender.prevAction = RLGC::Action(1, 0, 0, 0, 0, 0, 1, 0);
            state.players.push_back(defender);
            if (reverse) std::reverse(state.players.begin(), state.players.end());
            FreestyleReward reward(ctx); reward.Reset(state);
            ++state.lastTickCount;
            auto learner = std::find_if(state.players.begin(), state.players.end(),
                [&](const auto& p) { return p.carId == blue->id; });
            auto rival = std::find_if(state.players.begin(), state.players.end(),
                [&](const auto& p) { return p.carId == orange->id; });
            learner->ballTouchedStep = true; learner->ballHitInfo.isValid = true;
            learner->ballHitInfo.tickCountWhenHit = state.lastTickCount;
            assert(reward.GetReward(*learner, state, false) > 0);
            assert(reward.GetReward(*rival, state, false) == 0);
            assert(reward.IsSuccess(blue->id));
            assert(!reward.IsSuccess(orange->id));
            const auto report = ctx->telemetry->Snapshot();
            assert(report.at("events/learner_touch") == 1);
            assert(report.at("weighted_sum/ball_touch") > 0);
            ctx->telemetry->Drain();
        }
    }
}

static void FreestyleControlsAndMasks() {
    FreestyleControls controls; RLGC::DefaultAction original;
    assert(controls.GetActionAmount() == 94);
    assert(original.GetActionAmount() == 90);
    for (size_t action = 0; action < original.actions.size(); ++action)
        for (size_t axis = 0; axis < RLGC::Action::ELEM_AMOUNT; ++axis)
            assert(original.actions[action][axis] == controls.actions[action][axis]);
    for (const auto& action : controls.actions)
        for (float value : action) assert(std::isfinite(value) && value >= -1 && value <= 1);
    auto state = Fixture(); auto& learner = state.players[0];
    learner.hasFlipped = learner.hasDoubleJumped = false;
    learner.hasJumped = true; learner.airTimeSinceJump = .05f; learner.boost = 100;
    const auto available = controls.GetActionMask(learner, state);
    assert(available.size() == 94);
    for (size_t action = 90; action < 94; ++action) {
        assert(available[action]);
        const auto command = controls.ParseAction(int(action), learner, state);
        assert(command.jump == 1 && command.pitch == 0 && command.yaw == -command.roll);
    }
    learner.boost = 0;
    const auto emptyBoost = controls.GetActionMask(learner, state);
    for (size_t action = 0; action < controls.actions.size(); ++action)
        if (controls.actions[action].boost) assert(!emptyBoost[action]);
    assert(emptyBoost[90] && emptyBoost[92]);
    learner.hasFlipped = true; learner.airTimeSinceJump = 2;
    const auto spent = controls.GetActionMask(learner, state);
    for (size_t action = 90; action < 94; ++action) assert(!spent[action]);

    // Run the four new controls through real physics. This proves controls are
    // available to the learner, not that its random policy has learned stalls.
    std::unique_ptr<RocketSim::Arena> arena(RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR));
    auto* car = arena->AddCar(RocketSim::Team::BLUE);
    for (size_t action = 90; action < 94; ++action) {
        RocketSim::CarState own;
        own.pos = {0, 0, 900}; own.vel = {0, 400, 0}; own.rotMat = Basis({0, 1, 0});
        own.isOnGround = false; own.hasJumped = true; own.airTimeSinceJump = .05f;
        car->SetState(own); car->controls = static_cast<RocketSim::CarControls>(controls.actions[action]);
        arena->Step(4);
        const auto after = car->GetState();
        assert(std::isfinite(after.pos.Length()) && std::isfinite(after.vel.Length()));
        assert(after.lastControls.jump);
        assert(after.lastControls.yaw == controls.actions[action].yaw);
        assert(after.lastControls.roll == controls.actions[action].roll);
    }
}

int main(int argc, char** argv) {
    if (argc != 2) throw std::invalid_argument("Pass collision meshes directory");
    RocketSim::Init(argv[1], false);
    NoContactFarming(); GoalAttributionAndRepeatedTick(); SequentialResetUseAndEpisodeCap();
    RealResetAndFalseResourceEdges(); StateSettersAndObservations(); TeamSymmetryAndMasking();
    TwoCarLearnerSelectionAndRewards();
    FreestyleControlsAndMasks();
    OrdinaryShotsCannotBecomeFreestyleFinishes();LearnerLiftMustRiseThenReceiveASeparateAirTouch();GradualContactObjectives();
    std::cout << "FREESTYLE_NATIVE_PASS real_wheel_reset=1 proximity_farming=0 positive_cap=12 "
                 "goal_attribution=both_colors spawn_reset_rejected=1 randomized_starts=240 "
                 "two_car_learner=blue offpolicy_defender_reward=0 controls=94 masks_valid=1 "
                 "ground_shot_bonus=0 delayed_pop=1 gradual_objectives=1\n";
}
