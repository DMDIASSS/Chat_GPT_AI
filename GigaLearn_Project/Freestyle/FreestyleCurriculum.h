#pragma once

// Independent from the existing Slater actors: every freestyle environment owns
// its episode state, RNG and chain history. Nothing below mutates update180/271.
#include <RLGymCPP/StateSetters/StateSetter.h>
#include <RLGymCPP/TerminalConditions/TerminalCondition.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <map>
#include <limits>
#include <memory>
#include <mutex>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>

namespace SlaterFreestyle {

enum class Stage : int {
    ContactPop, AirCarry, ResetAcquire, ResetUse, MultiReset,
    Pinch, DoubleTap, PsychoProxy, WallRecovery, WallDashProxy
};
inline constexpr int STAGE_COUNT = 10;
inline constexpr std::array<const char*, STAGE_COUNT> STAGE_NAMES = {
    "contact_pop", "air_carry", "reset_acquire", "reset_use", "multi_reset",
    "pinch_proxy", "double_tap_proxy", "psycho_proxy", "wall_recovery", "walldash_proxy"
};
inline const char* StageName(Stage stage) {
    return STAGE_NAMES.at(static_cast<size_t>(stage));
}
inline Stage ParseStage(const std::string& name) {
    for (int i = 0; i < STAGE_COUNT; ++i) if (name == STAGE_NAMES[i]) return Stage(i);
    throw std::invalid_argument("Unknown freestyle stage: " + name);
}
inline float Clip(float x, float lo = 0.f, float hi = 1.f) {
    return std::clamp(x, lo, hi);
}
inline RocketSim::Vec Unit(const RocketSim::Vec& v) {
    const float length = v.Length();
    return length > 1e-5f ? v / length : RocketSim::Vec(0, 0, 0);
}

// Updated between PPO iterations, sampled only when an arena resets. This
// avoids changing the reward meaning half way through an episode.
struct CurriculumControl {
    std::atomic<int> stage{0};
    std::atomic<float> difficulty{0.f};
    std::atomic<float> episodeSeconds{12.f};
    std::atomic<bool> evaluation{false};
    std::atomic<float> privilegedDropout{.5f};
};

class FreestyleTelemetry {
    mutable std::mutex mutex_;
    std::map<std::string, double> values_;
public:
    void Add(const std::string& key, double value = 1) {
        if (!std::isfinite(value)) throw std::invalid_argument("Nonfinite freestyle telemetry");
        std::lock_guard<std::mutex> lock(mutex_); values_[key] += value;
    }
    void Add(const std::map<std::string, double>& values) {
        std::lock_guard<std::mutex> lock(mutex_);
        for (const auto& item : values) {
            if (!std::isfinite(item.second)) throw std::invalid_argument("Nonfinite freestyle telemetry");
            values_[item.first] += item.second;
        }
    }
    std::map<std::string, double> Snapshot() const {
        std::lock_guard<std::mutex> lock(mutex_); return values_;
    }
    std::map<std::string, double> Drain() {
        std::lock_guard<std::mutex> lock(mutex_);
        auto result = values_; values_.clear(); return result;
    }
};

struct ChainState {
    float elapsed = 0, lastTouch = -100, lastAirTouch = -100, lastNoseTouch = -100;
    float wallAt = -100, popAt = -100, carry = 0, bestCarry = 0, carryDistance = 0;
    float resetAt = -100, flipAt = -100, noFlipAt = -100, wallLaunchAt = -100;
    float boardAt = -100, pinchAt = -100, retouchAt = -100, lastRewardedTouch = -100;
    float recoveryStart = -100, wallSpeedBefore = 0, carryCredit = 0;
    int touches = 0, noseTouches = 0, resets = 0, resetUses = 0, resetChain = 0, chainUses = 0, bestUsedResetChain = 0;
    int wallDashes = 0;
    bool wall = false, pop = false, pendingReset = false, airborneSinceReset = false;
    bool pinch = false, board = false, retouch = false, ownBoard = false;
    bool recovered = false, recoveryNeeded = false, successful = false, finished = false, ownScored = false;
    bool lastFourWheels = false, wasAirborne = false, lastJump = false, goalPaid = false, active = false;
    uint64_t lastHitTick = ~uint64_t(0);
    RocketSim::Vec initialBall{}, lastBall{}, lastCar{};
    std::map<std::string, float> rawCredit;
};

struct PhysicsEvidence {
    bool initialized = false, previousAvailable = false, previousFlipped = false;
    bool spent = false, earnedAvailable = false;
    uint64_t rechargeTick = ~uint64_t(0), lastResetTick = ~uint64_t(0), lastFlipTick = ~uint64_t(0);
    unsigned resets = 0, flipsFromReset = 0, fourWheelBallContacts = 0;
};

struct FreestyleContext {
    std::shared_ptr<CurriculumControl> control;
    std::shared_ptr<FreestyleTelemetry> telemetry;
    std::mt19937_64 rng;
    Stage stage = Stage::ContactPop;
    float difficulty = 0, episodeSeconds = 12;
    bool evaluation = false, privilegedVisible = false;
    uint32_t learnerId = 0;
    uint64_t startTick = 0, rewardTick = ~uint64_t(0), resetCount = 0;
    std::unordered_map<uint32_t, ChainState> chains;
    std::unordered_map<uint32_t, PhysicsEvidence> physics;

    FreestyleContext(std::shared_ptr<CurriculumControl> curriculum = std::make_shared<CurriculumControl>(),
                     std::shared_ptr<FreestyleTelemetry> metrics = std::make_shared<FreestyleTelemetry>(),
                     uint64_t seed = 1)
        : control(std::move(curriculum)), telemetry(std::move(metrics)), rng(seed) {}
    float Rand(float lo, float hi) {
        return std::uniform_real_distribution<float>(lo, hi)(rng);
    }
    void SampleSettings() {
        const int value = control->stage.load();
        if (value < 0 || value >= STAGE_COUNT) throw std::invalid_argument("Invalid freestyle stage index");
        stage = Stage(value); difficulty = control->difficulty.load();
        episodeSeconds = control->episodeSeconds.load(); evaluation = control->evaluation.load();
        if (!std::isfinite(difficulty) || difficulty < 0 || difficulty > 1 ||
            !std::isfinite(episodeSeconds) || episodeSeconds < 1 || episodeSeconds > 120)
            throw std::invalid_argument("Invalid freestyle curriculum difficulty/duration");
        const float dropout=control->privilegedDropout.load();
        if (!std::isfinite(dropout)||dropout<0||dropout>1)
            throw std::invalid_argument("Invalid freestyle privileged state dropout");
        privilegedVisible=Rand(0,1)>=dropout;
    }
};

// Called BEFORE EACH PHYSICS TICK by the action parser and once after the last
// tick by reward.PreStep. Otherwise tickSkip can hide a four-wheel contact that
// lasted one tick, producing the earlier "zero reset successes" failure mode.
// The wheel count + resource recharge + ball geometry are authoritative;
// HasFlipReset() alone is deliberately insufficient.
inline void FreestyleObservePhysics(const std::shared_ptr<FreestyleContext>& context,
                                    RocketSim::Arena* arena) {
    if (!arena) return;
    const auto ball = arena->ball->GetState();
    for (auto* car : arena->GetCars()) {
        if (context->learnerId && car->id != context->learnerId) continue;
        const auto state = car->GetState(); auto& e = context->physics[car->id];
        const bool available = state.HasFlipOrJump();
        if (!e.initialized) {
            e.initialized=true; e.previousAvailable=available;
            e.previousFlipped=state.hasFlipped; e.spent=!available;
            continue; // Starting states cannot grant an earned reset.
        }
        if (!available) e.spent=true;
        if (!e.previousAvailable && available && e.spent) e.rechargeTick=arena->tickCount;
        bool four=true;
        for (int wheel=0;wheel<4;++wheel) {
            const auto& contact=car->_bulletVehicle.getWheelInfo(wheel).m_raycastInfo;
            // Compare actual suspension raycast collision objects with THIS
            // ball's rigid body. Ground, another car, and a nearby ball cannot
            // spoof this even when jump availability was restored.
            four=four&&state.wheelsWithContact[wheel]&&contact.m_isInContact&&
                contact.m_groundObject==static_cast<void*>(&arena->ball->_rigidBody);
        }
        const auto delta=ball.pos-state.pos;
        const bool ballGeometry=ball.pos.z>300 && state.pos.z>180 && delta.Length()<185 &&
            (-state.rotMat.up).Dot(Unit(delta))>.65f &&
            std::abs(state.pos.x)<3750 && std::abs(state.pos.y)<4720 && state.pos.z<1850;
        if (four && ballGeometry && !state.worldContact.hasContact) {
            ++e.fourWheelBallContacts;
            if (e.spent && available && e.rechargeTick!=~uint64_t(0) &&
                arena->tickCount-e.rechargeTick<=4 && !e.earnedAvailable) {
                ++e.resets; e.lastResetTick=arena->tickCount;
                e.spent=false; e.earnedAvailable=true;
            }
        }
        if (e.earnedAvailable && state.hasFlipped && !e.previousFlipped) {
            ++e.flipsFromReset; e.lastFlipTick=arena->tickCount; e.earnedAvailable=false;
        }
        // Landing on a world surface invalidates the pending ball-earned flip.
        if (state.worldContact.hasContact || state.pos.z<100) e.earnedAvailable=false;
        e.previousAvailable=available; e.previousFlipped=state.hasFlipped;
    }
}

class FreestyleStateSetter : public RLGC::StateSetter {
    std::shared_ptr<FreestyleContext> context_;
    static RocketSim::RotMat Facing(const RocketSim::Vec& direction,
                                    const RocketSim::Vec& up = RocketSim::Vec(0, 0, 1)) {
        auto forward = Unit(direction); auto right = Unit(up.Cross(forward));
        return RocketSim::RotMat(forward, right, Unit(forward.Cross(right)));
    }
public:
    explicit FreestyleStateSetter(std::shared_ptr<FreestyleContext> context) : context_(std::move(context)) {}
    void ResetArena(RocketSim::Arena* arena) override {
        auto& c = *context_; c.SampleSettings(); ++c.resetCount;
        if (arena->GetCars().empty()) throw std::invalid_argument("Freestyle requires at least one car");
        if (!c.learnerId) {
            // Arena.GetCars() is unordered. The trained side is BLUE by
            // default; an ORANGE defender must not accidentally become the
            // learner solely because of container iteration order.
            uint32_t blue=std::numeric_limits<uint32_t>::max();
            uint32_t any=std::numeric_limits<uint32_t>::max();
            for(auto* car:arena->GetCars()) {
                any=std::min(any,car->id);
                if(car->team==RocketSim::Team::BLUE)blue=std::min(blue,car->id);
            }
            c.learnerId=blue==std::numeric_limits<uint32_t>::max()?any:blue;
        }
        RocketSim::Car* learner = nullptr;
        for (auto* car : arena->GetCars()) if (car->id == c.learnerId) learner = car;
        if (!learner) throw std::invalid_argument("Freestyle learner absent from arena");
        float sign = learner->team == RocketSim::Team::BLUE ? 1.f : -1.f;
        const float d = c.difficulty, side = c.Rand(0, 1) < .5f ? -1.f : 1.f;
        RocketSim::BallState ball{};
        ball.pos = {c.Rand(-700, 700) * (.25f + d), c.Rand(-900, 900), 93};
        RocketSim::CarState own{};
        own.boost = c.Rand(70 - 25*d, 100); own.isOnGround = true;
        own.pos = ball.pos - RocketSim::Vec(c.Rand(-100, 100)*d, sign*(210 + 550*d), 76);
        own.rotMat = Facing(ball.pos - own.pos);

        const bool replayFoundation = !c.evaluation && c.stage != Stage::ContactPop && c.Rand(0, 1) < .12f;
        Stage setup = replayFoundation ? Stage::ContactPop : c.stage;
        if (setup == Stage::ContactPop) {
            // Ground + low bounce + sidewall starts: easier starts remain in the
            // distribution as difficulty grows, with no forced input sequence.
            if (c.Rand(0, 1) < .35f) {
                ball.pos.z = c.Rand(130, 210 + 180*d); ball.vel.z = c.Rand(30, 180);
            }
            if (c.Rand(0, 1) < .3f) {
                ball.pos.x = side*(3600 + 250*d); ball.pos.z = c.Rand(130, 350 + 350*d);
                ball.vel = {side*80, sign*180, 100};
                own.pos = {ball.pos.x-side*230, ball.pos.y-sign*180, 17};
                own.rotMat = Facing(ball.pos-own.pos);
            }
        } else if (setup == Stage::AirCarry || setup == Stage::ResetAcquire ||
                   setup == Stage::ResetUse || setup == Stage::MultiReset) {
            ball.pos = {c.Rand(-450, 450)*(1+d), sign*c.Rand(-400, 1800), c.Rand(550, 850+300*d)};
            ball.vel = {c.Rand(-100, 100)*d, sign*c.Rand(320, 650), c.Rand(-60, 120)};
            own.pos = ball.pos - RocketSim::Vec(c.Rand(-30,30)*(1+2*d), sign*(145+100*d), 110+70*d);
            own.vel = ball.vel + RocketSim::Vec(c.Rand(-100,100)*d, 0, c.Rand(-70,70)*d);
            own.isOnGround = false; own.hasJumped = true; own.hasDoubleJumped = true;
            own.hasFlipped = true; own.airTimeSinceJump = 2;
            own.rotMat = Facing({0,sign*.8f,.6f}, {0,-sign*.6f,.8f});
            if (setup == Stage::ResetAcquire || setup == Stage::ResetUse || setup == Stage::MultiReset) {
                // A used flip is essential: a synthesized airborne car with
                // hasJumped=false would falsely look like an earned flip reset.
                const float warm = (setup == Stage::MultiReset) ? .5f : .9f;
                if (c.Rand(0,1) < warm) {
                    own.pos = ball.pos - RocketSim::Vec(c.Rand(-18,18)*(1+d), 0, 152+110*d);
                    own.vel = ball.vel + RocketSim::Vec(0,0,c.Rand(40,130));
                    own.rotMat = Facing({0,sign,0},{0,0,-1});
                }
            }
        } else if (setup == Stage::Pinch) {
            ball.pos = {side*3970, c.Rand(-1600,1600), c.Rand(180,500+400*d)};
            own.pos = ball.pos - RocketSim::Vec(side*(240+450*d),sign*90,40+70*d);
            own.vel = {side*c.Rand(450,900),sign*100,100}; own.isOnGround=false;
            own.hasJumped=true; own.airTimeSinceJump=.5f;
            own.rotMat = Facing(ball.pos-own.pos);
        } else if (setup == Stage::DoubleTap || setup == Stage::PsychoProxy) {
            const bool psycho = setup == Stage::PsychoProxy;
            const float boardSign = psycho ? -sign : sign;
            ball.pos = {c.Rand(-450,450)*(1+d),boardSign*c.Rand(3000,4000),c.Rand(850,1150)};
            ball.vel = {c.Rand(-100,100)*d,boardSign*c.Rand(900,1500),c.Rand(-50,100)};
            own.pos = ball.pos-RocketSim::Vec(0,boardSign*(150+220*d),80+90*d);
            own.vel=ball.vel; own.isOnGround=false; own.hasJumped=true;
            own.airTimeSinceJump=.4f; own.rotMat=Facing(ball.pos-own.pos);
        } else {
            own.pos={side*4079,c.Rand(-1400,1400),c.Rand(300,850)};
            own.vel={0,sign*c.Rand(300,900),c.Rand(-80,180)};
            own.rotMat=Facing({0,sign,0},{-side,0,0}); own.isOnGround=true;
            if (setup == Stage::WallRecovery) {
                own.pos.x=side*c.Rand(3500,3850); own.isOnGround=false; own.hasJumped=true;
                own.hasFlipped=true; own.airTimeSinceJump=2;
                own.rotMat=RocketSim::Angle(c.Rand(-3.14f,3.14f),c.Rand(-1.2f,1.2f),c.Rand(-3.14f,3.14f)).ToRotMat();
                own.angVel={c.Rand(-2,2),c.Rand(-2,2),c.Rand(-2,2)};
            }
            ball.pos={side*3300,own.pos.y+sign*800,93};
        }
        if (c.Rand(0,1)<.25f*d) own.boost=c.Rand(30,65);
        arena->ball->SetState(ball);
        for (auto* car : arena->GetCars()) {
            car->controls = RocketSim::CarControls{};
            if (car == learner) car->SetState(own);
            else {
                RocketSim::CarState other{}; other.pos={c.Rand(-2500,2500),-sign*4000,17};
                other.boost=50; other.rotMat=Facing(ball.pos-other.pos); car->SetState(other);
            }
        }
        for (auto* pad : arena->GetBoostPads()) pad->SetState(RocketSim::BoostPadState{});
    }
};

class FreestyleDeadline : public RLGC::TerminalCondition {
    std::shared_ptr<FreestyleContext> context_;
    uint64_t start_ = 0;
public:
    explicit FreestyleDeadline(std::shared_ptr<FreestyleContext> context) : context_(std::move(context)) {}
    void Reset(const RLGC::GameState& state) override { start_=state.lastTickCount; }
    bool IsTerminal(const RLGC::GameState& state) override {
        return state.lastTickCount-start_ >= uint64_t(context_->episodeSeconds*120);
    }
    bool IsTruncation() override { return true; }
};

} // namespace SlaterFreestyle
