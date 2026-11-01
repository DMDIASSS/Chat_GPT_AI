#pragma once

// Optional event-based practice rewards.  Normal match rewards remain owned by
// AttentionWorld; the collector must select one reward stream, never add both.
#include <RLGymCPP/Gamestates/GameState.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <random>
#include <stdexcept>
#include <vector>

namespace SlaterAttention {

enum class CurriculumStage : int {
    WallRoll = 0, WallPop = 1, AirCarry = 2,
    ResetAcquire = 3, ResetShot = 4, Finish = 5
};

inline const char* CurriculumStageName(CurriculumStage stage) {
    constexpr const char* names[] = {"wall_roll", "wall_pop", "air_carry", "reset_acquire", "reset_shot", "finish"};
    const int index = int(stage);
    if (index < 0 || index > 5) throw std::invalid_argument("Unknown native practice stage");
    return names[index];
}

enum CurriculumEvent : uint32_t {
    WallRollEvent = 1, WallPopEvent = 2, AirCarryEvent = 4,
    ResetAcquireEvent = 8, ResetShotEvent = 16, GoalEvent = 32,
    ConcedeEvent = 64, DeadlineEvent = 128, BoostEvent = 256
};

struct CurriculumSummary {
    CurriculumStage initialStage = CurriculumStage::WallRoll;
    CurriculumStage targetStage = CurriculumStage::WallRoll;
    int highestUnlocked = 0, resetsAcquired = 0, resetsUsed = 0;
    uint32_t earnedEvents = 0;
    double seconds = 0, controlledAirSeconds = 0, bestCarrySeconds = 0;
    double wallRise = 0, carryProgress = 0, reward = 0;
    bool scored = false, conceded = false, success = false, expired = false;
    bool fullChain = false, reverseInitialized = false;
};

struct CurriculumTick {
    double reward = 0;
    uint32_t events = 0;
    bool success = false, scored = false, conceded = false, expired = false;
};

struct PracticeStart {
    RocketSim::BallState ball;
    // Stable AttentionWorld.ResetFromStates order: blue, then orange.
    std::vector<RocketSim::CarState> cars;
    std::vector<float> cooldowns; // Empty keeps pads available.
    CurriculumStage stage = CurriculumStage::WallRoll;
    float difficulty = 0;
    int wallSide = 1;
    RocketSim::Team learnerTeam = RocketSim::Team::BLUE;
};

inline RocketSim::RotMat CurriculumBasis(RocketSim::Vec forward, RocketSim::Vec up) {
    forward = forward.Normalized();
    auto right = up.Cross(forward).Normalized();
    up = forward.Cross(right).Normalized();
    return RocketSim::RotMat(forward, right, up);
}

// Reverse curriculum starts practise the remaining chain.  A late-stage start
// unlocks prerequisites but does not invent earned wall/carry/reset events.
inline PracticeStart CreatePracticeStart(uint64_t seed, float difficulty,
                                         CurriculumStage stage,
                                         RocketSim::Team learnerTeam = RocketSim::Team::BLUE) {
    CurriculumStageName(stage);
    if (!std::isfinite(difficulty) || difficulty < 0 || difficulty > 1)
        throw std::invalid_argument("Practice difficulty must be in [0,1]");
    std::mt19937_64 random(seed);
    const auto range = [&](float low, float high) {
        return std::uniform_real_distribution<float>(low, high)(random);
    };
    PracticeStart start;
    start.stage = stage; start.difficulty = difficulty; start.learnerTeam = learnerTeam;
    start.wallSide = (random() & 1) ? 1 : -1;
    start.cars.resize(2);
    const float sign = learnerTeam == RocketSim::Team::BLUE ? 1.f : -1.f;
    const size_t learnerIndex = learnerTeam == RocketSim::Team::BLUE ? 0 : 1;
    auto& ours = start.cars[learnerIndex];
    auto& opponent = start.cars[1 - learnerIndex];
    const float y = range(-2200, 2000) * sign;
    const float speed = range(350, 850);
    const float wall = float(start.wallSide);
    ours.boost = range(70 - 35 * difficulty, 100);
    ours.isOnGround = true;
    for (bool& contact : ours.wheelsWithContact) contact = true;
    ours.rotMat = CurriculumBasis({0, sign, 0}, {0, 0, 1});
    if (stage == CurriculumStage::WallRoll) {
        // The car must actually take a moving ground ball into the curved wall.
        start.ball.pos = {wall * range(3350, 3750), y, 93.15f};
        start.ball.vel = {wall * range(200, 480), sign * range(30, 180), 0};
        ours.pos = start.ball.pos + RocketSim::Vec(-wall * range(220, 480), -sign * range(10, 100), -76.15f);
        ours.vel = {wall * speed, sign * range(20, 150), 0};
        ours.rotMat = CurriculumBasis({wall, sign * range(-.12f, .12f), 0}, {0, 0, 1});
    } else if (stage == CurriculumStage::WallPop) {
        const float height = range(360, 700);
        start.ball.pos = {wall * 4002.85f, y, height};
        start.ball.vel = {0, sign * range(50, 180), range(500, 800)};
        ours.pos = {wall * 4078.f, y - sign * range(5, 60), height - range(170, 240)};
        ours.vel = {0, sign * range(50, 180), range(450, 720)};
        ours.rotMat = CurriculumBasis({0, sign * .1f, 1}, {-wall, 0, 0});
    } else {
        const float height = range(550, 1150);
        const float x = stage == CurriculumStage::AirCarry ? wall * range(2100, 2900) : range(-1700, 1700);
        const float shotY = stage == CurriculumStage::Finish ? sign * range(2800, 3900) : y;
        ours.isOnGround = false;
        for (bool& contact : ours.wheelsWithContact) contact = false;
        ours.pos = {x, shotY, height};
        ours.vel = {range(-100, 100), sign * speed, range(-40, 120)};
        start.ball.vel = ours.vel;
        ours.hasJumped = true; ours.hasFlipped = true; ours.airTime = 1.f;
        ours.airTimeSinceJump = 1.f;
        if (stage == CurriculumStage::ResetAcquire) {
            // Spent flip, wheels facing the ball, small noncontact gap; the
            // simulator must produce a real four-wheel reacquisition.
            ours.rotMat = CurriculumBasis({0, sign, 0}, {0, 0, -1});
            start.ball.pos = ours.pos + RocketSim::Vec(range(-12, 12), range(-12, 12), range(150, 200));
            ours.vel.z = range(100, 220); start.ball.vel.z = range(0, 50);
        } else {
            ours.rotMat = CurriculumBasis({0, sign, range(.08f, .22f)}, {0, 0, 1});
            start.ball.pos = ours.pos + RocketSim::Vec(range(-30, 30), sign * range(125, 175), range(50, 90));
            if (stage == CurriculumStage::ResetShot) {
                // A deliberately supplied reset is permitted for reset-use
                // practice; it earns no acquisition reward or full-chain label.
                ours.hasJumped = ours.hasFlipped = false;
                ours.airTimeSinceJump = 0;
            }
        }
    }
    opponent.isOnGround = true;
    for (bool& contact : opponent.wheelsWithContact) contact = true;
    opponent.boost = range(30, 100);
    opponent.pos = {range(-900, 900), sign * (4500 - 1400 * difficulty), 17};
    opponent.rotMat = CurriculumBasis({0, -sign, 0}, {0, 0, 1});
    opponent.vel = {0, -sign * 300 * difficulty, 0};
    return start;
}

// Collision-wheel evidence is independently checked against four actual
// wheel ray origins.  This excludes wheel contact with ground/walls and false
// HasFlipReset flags on a freshly stateset airborne car.
inline bool FourWheelBallContact(const RLGC::Player& car, const RocketSim::BallState& ball,
                                 const RocketSim::CarConfig& config = RocketSim::CAR_CONFIG_OCTANE) {
    if (car.isDemoed || std::abs(car.pos.x) > 3500 || std::abs(car.pos.y) > 4500 ||
        car.pos.z < 250 || car.pos.z > 1750 || ball.pos.z < 300) return false;
    if ((ball.pos - car.pos).Length() > 190) return false;
    const auto direction = -car.rotMat.up;
    if (direction.Dot((ball.pos - car.pos).Normalized()) < .70f) return false;
    constexpr float radius = 93.15f + 5; // Numeric wheel-ray/collision tolerance.
    for (size_t wheel = 0; wheel < 4; ++wheel) {
        if (!car.wheelsWithContact[wheel]) return false;
        const auto& pair = wheel < 2 ? config.frontWheels : config.backWheels;
        auto offset = pair.connectionPointOffset;
        if (wheel % 2) offset.y = -offset.y;
        const auto origin = car.pos + car.rotMat.forward * offset.x +
            car.rotMat.right * offset.y + car.rotMat.up * offset.z;
        const auto delta = ball.pos - origin;
        const float along = delta.Dot(direction);
        const float reach = pair.suspensionRestLength + pair.wheelRadius + 20;
        if (along < -radius || along > reach + radius) return false;
        const auto nearest = origin + direction * std::clamp(along, 0.f, reach);
        if ((nearest - ball.pos).LengthSq() > radius * radius) return false;
    }
    return true;
}

class CurriculumTracker {
    CurriculumSummary summary_;
    float difficulty_ = 0;
    bool initialized_ = false, finished_ = false, contactLastTick_ = false;
    int side_ = 1, activeStage_ = 0;
    float sign_ = 1;
    double stageAt_ = 0, lastTouchAt_ = -100, lastNoseAt_ = -100;
    double wallInitialHeight_ = 0, wallHighWater_ = 0, paidRise_ = 0;
    double popCandidateAt_ = -100, carryStreak_ = 0, carryStartY_ = 0;
    double paidCarry_ = 0, carryHighWater_ = 0, paidProgress_ = 0;
    double resetCandidateAt_ = -100, resetAt_ = -100, flipAt_ = -100;
    double lastAcquisitionAt_ = -100, paidBoost_ = 0;
    bool resetPendingUse_ = false, suppliedReset_ = false;
    int noseContacts_ = 0;

    static const RLGC::Player& Find(const RLGC::GameState& state, uint32_t id) {
        for (const auto& player : state.players) if (player.carId == id) return player;
        throw std::invalid_argument("Practice learner absent from state");
    }

    double Deadline() const {
        // More generous than a speedrun.  Higher difficulty tightens after
        // collection of actual success evidence by the campaign controller.
        constexpr double deadlines[] = {7, 5, 5, 5, 4, 5};
        return deadlines[std::clamp(activeStage_, 0, 5)] * (1 - .20 * difficulty_);
    }
    double TimeBonus() const {
        return 1 + .25 * std::clamp(1 - (summary_.seconds - stageAt_) / Deadline(), 0.0, 1.0);
    }
    void Earn(CurriculumTick& out, uint32_t event, double payment) {
        out.events |= event; summary_.earnedEvents |= event; out.reward += payment;
        const uint32_t target = 1u << int(summary_.targetStage);
        if (event == target && summary_.targetStage != CurriculumStage::Finish) {
            out.success = true; summary_.success = true;
        }
    }
    void Advance(int stage) {
        activeStage_ = stage; summary_.highestUnlocked = std::max(summary_.highestUnlocked, stage);
        stageAt_ = summary_.seconds;
    }

public:
    explicit CurriculumTracker(CurriculumStage targetStage = CurriculumStage::WallRoll, float difficulty = 0,
                               CurriculumStage startStage = CurriculumStage::WallRoll) {
        reset(targetStage, difficulty, startStage);
    }
    void reset(CurriculumStage targetStage, float difficulty = 0,
               CurriculumStage startStage = CurriculumStage::WallRoll) {
        CurriculumStageName(targetStage); CurriculumStageName(startStage);
        if (int(startStage) > int(targetStage))
            throw std::invalid_argument("Reverse start cannot skip the target skill");
        if (!std::isfinite(difficulty) || difficulty < 0 || difficulty > 1)
            throw std::invalid_argument("Practice difficulty must be in [0,1]");
        *this = CurriculumTracker(Uninitialized{});
        summary_.initialStage = startStage; summary_.targetStage = targetStage;
        summary_.highestUnlocked = activeStage_ = int(startStage);
        summary_.reverseInitialized = startStage != CurriculumStage::WallRoll;
        difficulty_ = difficulty;
        suppliedReset_ = startStage == CurriculumStage::ResetShot;
        resetPendingUse_ = suppliedReset_;
        if (suppliedReset_) resetAt_ = 0;
    }
    CurriculumStage stage() const { return CurriculumStage(std::clamp(activeStage_, 0, 5)); }
    const CurriculumSummary& summary() const { return summary_; }

    CurriculumTick tick(const RLGC::GameState& before, const RLGC::GameState& after,
                        uint32_t learnerId) {
        CurriculumTick out;
        if (finished_) return out; // Terminal/report polling never pays twice.
        const auto& old = Find(before, learnerId);
        const auto& car = Find(after, learnerId);
        if (!initialized_) {
            sign_ = car.team == RocketSim::Team::BLUE ? 1.f : -1.f;
            side_ = before.ball.pos.x < 0 ? -1 : 1;
            wallInitialHeight_ = wallHighWater_ = before.ball.pos.z;
            carryStartY_ = before.ball.pos.y;
            initialized_ = true;
        }
        const double dt = after.deltaTime > 0 ? after.deltaTime : 1.0 / 120.0;
        if (!std::isfinite(dt) || dt > .1) throw std::invalid_argument("Practice tracker requires per-physics transitions");
        summary_.seconds += dt;
        out.reward -= .01 * dt;
        out.reward -= .0005 * std::max(0.f, old.boost - car.boost);
        const float collected = std::max(0.f, car.boost - old.boost);
        if (collected > 1 && paidBoost_ < 50) {
            const double paid = std::min(double(collected), 50 - paidBoost_);
            paidBoost_ += paid; Earn(out, BoostEvent, .001 * paid);
        }
        const bool touch = car.ballTouchedStep || car.ballTouchedTick;
        if (touch) lastTouchAt_ = summary_.seconds;
        const auto delta = after.ball.pos - car.pos;
        const float distance = delta.Length();
        const auto local = car.rotMat.Dot(delta);
        const bool airborne = car.pos.z > 220 && after.ball.pos.z > 300;
        const bool nose = touch && airborne && local.x > 35 && std::abs(local.y) < 105 && local.z > -35 && local.z < 160;
        if (nose && (!contactLastTick_ || summary_.seconds - lastNoseAt_ >= .10)) {
            lastNoseAt_ = summary_.seconds; ++noseContacts_;
        }
        contactLastTick_ = nose;

        if (!summary_.expired && activeStage_ == 0) {
            const bool nearWall = side_ * after.ball.pos.x > 3720 && side_ * car.pos.x > 3750;
            int wheels = 0; for (bool contact : car.wheelsWithContact) wheels += contact;
            const bool climbing = nearWall && wheels >= 2 && distance < 280 && car.pos.z > 65 &&
                after.ball.vel.z > 80 && car.vel.z > 10 && summary_.seconds - lastTouchAt_ < .35;
            if (climbing) {
                wallHighWater_ = std::max(wallHighWater_, double(after.ball.pos.z));
                summary_.wallRise = std::max(0.0, wallHighWater_ - wallInitialHeight_);
                const double target = std::min(400.0, summary_.wallRise);
                out.reward += .0015 * std::max(0.0, target - paidRise_); paidRise_ = target;
                if (summary_.wallRise >= 120 && after.ball.pos.z >= 200) {
                    Earn(out, WallRollEvent, .5 * TimeBonus()); Advance(1);
                }
            }
        }
        if (!summary_.expired && activeStage_ == 1) {
            const float oldOutward = -side_ * before.ball.vel.x;
            const float outward = -side_ * after.ball.vel.x;
            if (touch && side_ * before.ball.pos.x > 3700 && after.ball.pos.z > 260 &&
                outward > 150 && outward - oldOutward > 100)
                popCandidateAt_ = summary_.seconds;
            if (summary_.seconds - popCandidateAt_ <= .45 && side_ * after.ball.pos.x < 3876 &&
                after.ball.pos.z > 300 && outward > 150) {
                Earn(out, WallPopEvent, .8 * TimeBonus()); Advance(2);
                carryStartY_ = after.ball.pos.y;
            }
        }
        const bool controlled = airborne && distance < 245 &&
            (after.ball.vel - car.vel).Length() < 650 &&
            car.rotMat.forward.Dot(delta.Normalized()) > .35 &&
            summary_.seconds - lastNoseAt_ < .32 && sign_ * after.ball.vel.y > 80;
        if (!summary_.expired && activeStage_ >= 2 && controlled) {
            if (carryStreak_ == 0) carryStartY_ = before.ball.pos.y;
            carryStreak_ += dt;
            summary_.controlledAirSeconds += dt;
            summary_.bestCarrySeconds = std::max(summary_.bestCarrySeconds, carryStreak_);
            const double progress = std::max(0.0, sign_ * double(after.ball.pos.y - carryStartY_));
            summary_.carryProgress = std::max(summary_.carryProgress, progress);
            if (activeStage_ == 2) {
                const double duration = std::min(dt, std::max(0.0, 1.5 - paidCarry_));
                paidCarry_ += duration; out.reward += .25 * duration;
                carryHighWater_ = std::max(carryHighWater_, progress);
                const double target = std::min(carryHighWater_, 450.0);
                out.reward += .001 * std::max(0.0, target - paidProgress_); paidProgress_ = target;
                if (carryStreak_ >= .45 && noseContacts_ >= 2 && progress > 120) {
                    Earn(out, AirCarryEvent, 1.2 * TimeBonus()); Advance(3);
                }
            }
        } else carryStreak_ = 0;

        // A false -> true jump/flip transition, *four ball-facing wheel rays*,
        // real physics wheel contacts and a spent prior flip are all required.
        // The regained candidate may precede full four-wheel contact by a few
        // physics packets because RocketSim regains at >=3 contact wheels.
        const bool spent = old.hasFlipped || old.hasDoubleJumped || old.airTimeSinceJump >= 1.25f;
        if (!summary_.expired && activeStage_ >= 3 && spent && !old.HasFlipOrJump() && car.HasFlipOrJump() &&
            (after.ball.pos - car.pos).Length() < 190 && airborne)
            resetCandidateAt_ = summary_.seconds;
        RocketSim::CarConfig configuration = RocketSim::CAR_CONFIG_OCTANE;
        if (after.lastArena) configuration = after.lastArena->GetCar(learnerId)->config;
        if (!summary_.expired && activeStage_ >= 3 && !resetPendingUse_ && summary_.resetsAcquired < 3 &&
            summary_.seconds - resetCandidateAt_ <= .10 &&
            summary_.seconds - lastAcquisitionAt_ > .18 && car.HasFlipOrJump() &&
            FourWheelBallContact(car, after.ball, configuration)) {
            resetPendingUse_ = true; resetAt_ = lastAcquisitionAt_ = summary_.seconds;
            resetCandidateAt_ = -100; flipAt_ = -100;
            ++summary_.resetsAcquired;
            Earn(out, ResetAcquireEvent, .7 * TimeBonus() / summary_.resetsAcquired);
            Advance(4);
        }
        if (!summary_.expired && resetPendingUse_ && old.HasFlipOrJump() && !car.HasFlipOrJump() &&
            (car.hasFlipped || car.isFlipping)) flipAt_ = summary_.seconds;
        const float oldGoalward = sign_ * before.ball.vel.y;
        const float goalward = sign_ * after.ball.vel.y;
        const auto towardGoal = RocketSim::Vec(0, sign_ * 5120, 300) - after.ball.pos;
        const bool usefulDirection = after.ball.vel.Normalized().Dot(towardGoal.Normalized()) > .65f;
        if (!summary_.expired && resetPendingUse_ && summary_.seconds - flipAt_ <= .45 && touch &&
            summary_.seconds - resetAt_ <= 3.5 && goalward > 250 &&
            goalward - oldGoalward > 120 && usefulDirection && summary_.resetsUsed < 3) {
            ++summary_.resetsUsed;
            Earn(out, ResetShotEvent, 1.8 * TimeBonus() / summary_.resetsUsed);
            resetPendingUse_ = false; flipAt_ = resetAt_ = -100; Advance(5);
        }
        if (after.goalScored && !before.goalScored) {
            out.scored = sign_ * after.ball.pos.y > 0;
            out.conceded = !out.scored;
            summary_.scored = out.scored; summary_.conceded = out.conceded;
            if (out.scored) {
                // Ordinary goals remain useful, while verified chain completion
                // receives a separate capped bonus; own goals never qualify.
                const double base = .5 + .20 * std::min(activeStage_, 5);
                Earn(out, GoalEvent, base);
                constexpr uint32_t fullPrefix = WallRollEvent | WallPopEvent | AirCarryEvent | ResetAcquireEvent | ResetShotEvent;
                const bool fullEarned = (summary_.earnedEvents & fullPrefix) == fullPrefix;
                summary_.fullChain = fullEarned;
                const bool partialFinish = summary_.initialStage == CurriculumStage::Finish ||
                    (summary_.earnedEvents & ResetShotEvent) != 0;
                const bool finishedChain = !summary_.expired && (fullEarned || partialFinish);
                if (summary_.targetStage == CurriculumStage::Finish) out.success = finishedChain;
                if (finishedChain) out.reward += (fullEarned ? 3.0 : 1.5) * TimeBonus();
            } else Earn(out, ConcedeEvent, -3.0);
            finished_ = true;
        } else if (!summary_.expired && summary_.seconds - stageAt_ > Deadline()) {
            out.expired = true; summary_.expired = true; out.events |= DeadlineEvent;
        }
        summary_.success |= out.success;
        summary_.reward += out.reward;
        if (!std::isfinite(out.reward)) throw std::runtime_error("Nonfinite native practice reward");
        return out;
    }

private:
    struct Uninitialized {};
    explicit CurriculumTracker(Uninitialized) {}
};

} // namespace SlaterAttention
