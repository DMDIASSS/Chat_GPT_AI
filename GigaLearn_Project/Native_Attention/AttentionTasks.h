#pragma once

// Targeted practice adds bounded event rewards to the ordinary match reward.
// No policy, Torch, filesystem, or JSON dependency belongs in this tracker.
#include <RLGymCPP/Gamestates/GameState.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <random>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace SlaterAttention {

enum class PracticeRoutine { Match, Defense, Recovery, Boost, Bump, BumpEvasion };
using enumPracticeRoutine = PracticeRoutine;

inline const char* PracticeRoutineName(PracticeRoutine routine) {
    switch (routine) {
    case PracticeRoutine::Match: return "match";
    case PracticeRoutine::Defense: return "defense";
    case PracticeRoutine::Recovery: return "recovery";
    case PracticeRoutine::Boost: return "boost";
    case PracticeRoutine::Bump: return "bump";
    case PracticeRoutine::BumpEvasion: return "bump-evasion";
    }
    throw std::invalid_argument("Unknown practice routine");
}

inline PracticeRoutine ParsePracticeRoutine(const std::string& name) {
    for (auto routine : {PracticeRoutine::Match, PracticeRoutine::Defense,
                        PracticeRoutine::Recovery, PracticeRoutine::Boost,
                        PracticeRoutine::Bump, PracticeRoutine::BumpEvasion})
        if (name == PracticeRoutineName(routine)) return routine;
    throw std::invalid_argument("Unknown native practice routine: " + name);
}

struct TaskStart {
    RocketSim::BallState ball;
    std::vector<RocketSim::CarState> cars; // Blue first, then orange, just like ResetFromStates.
    std::vector<float> boostCooldowns;
    size_t learnerIndex = 0;
};

inline double TaskDifficulty(double value) {
    if (!std::isfinite(value)) throw std::invalid_argument("Nonfinite practice difficulty");
    return std::clamp(value, 0.0, 1.0);
}

inline RocketSim::RotMat TaskYaw(float yaw) {
    return RocketSim::RotMat({std::cos(yaw), std::sin(yaw), 0},
                            {-std::sin(yaw), std::cos(yaw), 0}, {0, 0, 1});
}

inline TaskStart CreateTaskStart(uint64_t seed, double difficulty, PracticeRoutine routine,
                                int ourSize, int theirSize, RocketSim::Team learnerTeam) {
    if (ourSize < 1 || ourSize > 3 || theirSize < 1 || theirSize > 3)
        throw std::invalid_argument("Practice rosters require 1..3 cars per team");
    const float d = float(TaskDifficulty(difficulty));
    std::mt19937_64 rng(seed);
    const auto random = [&](float low, float high) {
        return std::uniform_real_distribution<float>(low, high)(rng);
    };
    constexpr float pi = 3.14159265358979323846f;
    const float sign = learnerTeam == RocketSim::Team::BLUE ? 1.f : -1.f;
    TaskStart start;
    start.cars.resize(ourSize + theirSize);
    start.learnerIndex = learnerTeam == RocketSim::Team::BLUE ? 0 : size_t(theirSize);
    const auto ourIndex = [&](int i) { return start.learnerIndex + size_t(i); };
    const auto theirIndex = [&](int i) { return learnerTeam == RocketSim::Team::BLUE ? size_t(ourSize + i) : size_t(i); };
    for (int i = 0; i < ourSize + theirSize; ++i) {
        const int blueSize = learnerTeam == RocketSim::Team::BLUE ? ourSize : theirSize;
        const bool blue = i < blueSize;
        const float teamSign = blue ? 1.f : -1.f;
        const int slot = blue ? i : i - blueSize;
        auto& car = start.cars[i];
        car.pos = {(-1800.f + slot * 1700.f) + random(-200, 200), -teamSign * (3400.f + slot * 380.f), 17};
        car.rotMat = TaskYaw(teamSign * pi / 2);
        car.boost = random(20, 70);
        car.isOnGround = true;
        for (bool& wheel : car.wheelsWithContact) wheel = true;
    }
    start.ball.pos = {random(-650, 650), sign * random(-800, 800), 93.15f};
    auto& us = start.cars[start.learnerIndex];
    switch (routine) {
    case PracticeRoutine::Match:
        // Caller uses AttentionWorld::Reset for normal kickoff episodes.
        break;
    case PracticeRoutine::Defense:
        start.ball.pos = {random(-650, 650), -sign * random(2400, 3250), random(93.15f, 93.15f + 180.f * d)};
        start.ball.vel = {-start.ball.pos.x * .2f, -sign * random(850, 1100 + 1500 * d), random(0, 80 * d)};
        us.pos = {random(-600, 600), -sign * random(4050, 4550), 17};
        us.boost = random(15, 70);
        start.cars[theirIndex(0)].pos = {start.ball.pos.x + 350, start.ball.pos.y + sign * 900, 17};
        start.cars[theirIndex(0)].vel = {0, -sign * 700, 0};
        break;
    case PracticeRoutine::Recovery: {
        us.pos = {random(-2400, 2400), sign * random(-2200, 2200), random(260, 450 + 450 * d)};
        us.vel = {random(-650, 650), sign * random(350, 1100), random(-200 - 450 * d, 0)};
        const float yaw = random(-pi, pi), angle = random(1.1f, 2.4f + .6f * d);
        RocketSim::Vec forward(std::cos(yaw), std::sin(yaw), 0);
        RocketSim::Vec flatRight(-std::sin(yaw), std::cos(yaw), 0);
        RocketSim::Vec right = flatRight * std::cos(angle) + RocketSim::Vec(0, 0, std::sin(angle));
        us.rotMat = RocketSim::RotMat(forward, right, forward.Cross(right));
        us.isOnGround = false;
        for (bool& wheel : us.wheelsWithContact) wheel = false;
        us.hasJumped = true; us.airTime = .6f; us.airTimeSinceJump = .6f;
        us.angVel = {random(-1.5f, 1.5f), random(-1.5f, 1.5f), 0};
        us.boost = random(10, 60);
        start.ball.pos = {random(-500, 500), sign * random(800, 1800), 93.15f};
        break;
    }
    case PracticeRoutine::Boost: {
        const int index = learnerTeam == RocketSim::Team::BLUE ? 7 : 26;
        const auto pad = RLGC::CommonValues::BOOST_LOCATIONS[index];
        start.ball.pos = {random(-600, 600), pad.y + sign * random(1100, 2300), 93.15f};
        us.pos = {pad.x + random(-120, 120), pad.y - sign * random(220, 380), 17};
        us.vel = {0, sign * random(300, 700), 0};
        us.boost = random(0, 25);
        if (ourSize > 1 && (seed & 1)) {
            // A competing low-boost teammate starts closer: route choice matters.
            us.pos.y = pad.y - sign * 450;
            us.boost = random(50, 80);
            auto& teammate = start.cars[ourIndex(1)];
            teammate.pos = {pad.x + 90, pad.y - sign * 100, 17};
            teammate.vel = {0, sign * 350, 0}; teammate.boost = 0;
        }
        break;
    }
    case PracticeRoutine::Bump:
        start.ball.pos = {random(-400, 400), sign * random(1800, 2600), 93.15f};
        start.ball.vel = {-start.ball.pos.x * .15f, sign * random(850, 1350), 0};
        us.pos = {start.ball.pos.x + random(250, 500), start.ball.pos.y + sign * 350, 17};
        us.vel = {-200, sign * random(1100, 1500 + 350 * d), 0}; us.boost = random(30, 80);
        start.cars[theirIndex(0)].pos = {start.ball.pos.x + random(-150, 150), start.ball.pos.y + sign * 950, 17};
        start.cars[theirIndex(0)].vel = {random(-100, 100), -sign * random(0, 600 * d), 0};
        break;
    case PracticeRoutine::BumpEvasion:
        us.pos = {random(-1300, 1300), -sign * random(900, 1900), 17};
        us.vel = {0, sign * random(200, 550), 0}; us.boost = random(20, 60);
        start.cars[theirIndex(0)].pos = {us.pos.x + random(-60, 60), us.pos.y - sign * random(500, 950), 17};
        start.cars[theirIndex(0)].rotMat = TaskYaw(sign * pi / 2);
        start.cars[theirIndex(0)].vel = {0, sign * random(1850, 2000 + 250 * d), 0};
        start.cars[theirIndex(0)].boost = 75;
        start.ball.pos = {random(-500, 500), sign * random(300, 1800), 93.15f};
        break;
    }
    return start;
}

enum TaskEvent : uint32_t {
    TaskClear = 1u << 0, TaskRecovery = 1u << 1, TaskPickup = 1u << 2,
    TaskSharedPickup = 1u << 3, TaskUsefulBump = 1u << 4, TaskEvasion = 1u << 5,
    TaskDemoed = 1u << 6
};
struct TaskTick { double reward = 0; bool success = false; uint32_t events = 0; };
struct TaskSummary {
    double reward = 0;
    uint64_t ticks = 0;
    int usefulPickups = 0, sharedPickups = 0, controlledClears = 0, recoveries = 0;
    int usefulBumps = 0, evasions = 0, demos = 0;
    bool succeeded = false;
};

class TaskTracker {
    PracticeRoutine routine_;
    double difficulty_;
    TaskSummary summary_;
    double positivePaid_ = 0, shadowPaid_ = 0;
    uint64_t lastClearTick_ = 0;
    std::set<uint32_t> bumped_, evaded_;
    struct Threat { uint64_t began; RocketSim::Vec position; };
    std::map<uint32_t, Threat> threats_;

    static const RLGC::Player* Find(const RLGC::GameState& state, uint32_t id) {
        for (const auto& player : state.players) if (player.carId == id) return &player;
        return nullptr;
    }
    static bool Continuous(const RLGC::Player& before, const RLGC::Player& after) {
        return !before.isDemoed && !after.isDemoed && before.pos.Dist(after.pos) < 200 &&
               after.updateCounter >= before.updateCounter;
    }
    static bool TouchEdge(const RLGC::Player& before, const RLGC::Player& after) {
        return after.ballTouchedTick && (!before.ballTouchedTick ||
               after.ballHitInfo.tickCountWhenHit != before.ballHitInfo.tickCountWhenHit);
    }
    static bool GoalThreat(const RocketSim::BallState& ball, float sign) {
        if (sign * ball.vel.y >= -200) return false;
        const float t = (-sign * 5120 - ball.pos.y) / ball.vel.y;
        if (t < 0 || t > 2.5f) return false;
        const float x = ball.pos.x + ball.vel.x * t;
        const float z = std::max(93.15f, ball.pos.z + ball.vel.z * t - 325 * t * t);
        return std::abs(x) < 842 && z < 610;
    }
    static double ShadowPotential(const RLGC::GameState& state, const RLGC::Player& player, float sign) {
        if (!GoalThreat(state.ball, sign)) return 0;
        RocketSim::Vec target = state.ball.pos;
        target.y -= sign * 700; target.z = 17;
        return -.1 * std::min(double(player.pos.Dist2D(target)) / 2000, 1.0);
    }
    static int PickupPad(const RLGC::GameState& before, const RLGC::GameState& after,
                         const RLGC::Player& carBefore, const RLGC::Player& carAfter) {
        if (!Continuous(carBefore, carAfter) || carAfter.boost - carBefore.boost < .5f) return -1;
        for (int i = 0; i < RLGC::CommonValues::BOOST_LOCATIONS_AMOUNT; ++i)
            if (size_t(i) < before.boostPads.size() && size_t(i) < after.boostPads.size() &&
                before.boostPads[i] && !after.boostPads[i] &&
                carAfter.pos.Dist2D(RLGC::CommonValues::BOOST_LOCATIONS[i]) < 180)
                return i;
        return -1;
    }
    static bool TeammateNeedsPad(const RLGC::Player& us, const RLGC::Player& other,
                                 const RocketSim::Vec& pad, const RocketSim::BallState& ball) {
        if (other.team != us.team || other.carId == us.carId || other.isDemoed || other.boost >= 20) return false;
        return other.pos.Dist2D(pad) + 80 < us.pos.Dist2D(pad) &&
               other.pos.Dist2D(ball.pos) < us.pos.Dist2D(ball.pos) + 350;
    }
    static bool ProductivePickup(const RLGC::GameState& before, const RLGC::GameState& after,
                                  const RLGC::Player& p, const RLGC::Player& q, float sign) {
        if (p.boost >= 45) return false;
        const auto toBall = (after.ball.pos - q.pos).Normalized();
        const bool progressing = q.vel.Dot(toBall) > 100 ||
            p.pos.Dist2D(before.ball.pos) - q.pos.Dist2D(after.ball.pos) > .5f;
        const bool urgentDefense = GoalThreat(before.ball, sign) &&
            q.pos.Dist2D(after.ball.pos) > p.pos.Dist2D(before.ball.pos) + 25;
        return progressing && !urgentDefense;
    }
    static bool ShotCorridor(const RLGC::GameState& state, const RLGC::Player& victim, float sign) {
        if (sign * state.ball.vel.y < 600 || sign * state.ball.pos.y < -500) return false;
        const float goalTime = (sign * 5120 - state.ball.pos.y) / state.ball.vel.y;
        if (goalTime < 0 || goalTime > 4 ||
            std::abs(state.ball.pos.x + state.ball.vel.x * goalTime) > 1300) return false;
        const float time = (victim.pos.y - state.ball.pos.y) / state.ball.vel.y;
        if (time < -.2f || time > goalTime + .2f) return false;
        const float expectedX = state.ball.pos.x + state.ball.vel.x * std::max(time, 0.f);
        const float expectedZ = std::max(93.15f, state.ball.pos.z + state.ball.vel.z * std::max(time, 0.f) - 325 * time * time);
        return std::abs(victim.pos.x - expectedX) < 650 && std::abs(victim.pos.z - expectedZ) < 600;
    }
    static bool DemoThreat(const RLGC::Player& us, const RLGC::Player& other) {
        if (other.team == us.team || other.isDemoed || other.vel.Length2D() < 1600) return false;
        const auto offset = other.pos - us.pos, relative = other.vel - us.vel;
        const float speed2 = relative.LengthSq();
        if (offset.Length2D() > 1200 || speed2 < 10000) return false;
        const float time = -offset.Dot(relative) / speed2;
        return time > 0 && time < .7f && (offset + relative * time).Length() < 180;
    }
    void Pay(TaskTick& result, double value, uint32_t event, bool success = true) {
        const double bounded = std::min(std::max(0.0, value), 3.0 - positivePaid_);
        if (bounded <= 0) return;
        positivePaid_ += bounded; result.reward += bounded; result.events |= event;
        result.success = result.success || success;
    }

public:
    explicit TaskTracker(PracticeRoutine routine = PracticeRoutine::Match, double difficulty = 0)
        : routine_(routine), difficulty_(TaskDifficulty(difficulty)) {}
    void Reset() {
        summary_ = {}; positivePaid_ = shadowPaid_ = 0; lastClearTick_ = 0;
        bumped_.clear(); evaded_.clear(); threats_.clear();
    }
    PracticeRoutine Routine() const { return routine_; }
    const TaskSummary& Summary() const { return summary_; }

    TaskTick Tick(const RLGC::GameState& before, const RLGC::GameState& after, uint32_t learnerId) {
        TaskTick result;
        const auto* p = Find(before, learnerId); const auto* q = Find(after, learnerId);
        if (!p || !q) throw std::invalid_argument("Learner missing from practice state");
        ++summary_.ticks;
        if (routine_ == PracticeRoutine::Match) return result;
        const float sign = q->team == RocketSim::Team::BLUE ? 1.f : -1.f;
        const bool continuous = Continuous(*p, *q);
        const bool contact = continuous && TouchEdge(*p, *q);

        if (routine_ == PracticeRoutine::Defense && continuous) {
            if (contact && sign * before.ball.pos.y < 0 &&
                (summary_.controlledClears == 0 || summary_.ticks > lastClearTick_ + 120) &&
                summary_.controlledClears < 3) {
                const bool saved = GoalThreat(before.ball, sign) && !GoalThreat(after.ball, sign);
                const bool controlled = sign * after.ball.vel.y > 500 &&
                    sign * (after.ball.vel.y - before.ball.vel.y) > 400;
                if (saved || controlled) {
                    Pay(result, saved ? .75 : .35, TaskClear);
                    ++summary_.controlledClears; lastClearTick_ = summary_.ticks;
                }
            }
            // Potential differences, never payment for merely sitting in shadow position.
            if (GoalThreat(before.ball, sign) && GoalThreat(after.ball, sign) &&
                q->pos.Dist2D(p->pos) > .05) {
                const double change = std::clamp(ShadowPotential(after, *q, sign) -
                    ShadowPotential(before, *p, sign), -.025, .025);
                const double positive = std::min(std::max(0.0, change), .3 - shadowPaid_);
                shadowPaid_ += positive; result.reward += positive + std::min(change, 0.0);
            }
        }
        if ((routine_ == PracticeRoutine::Recovery || routine_ == PracticeRoutine::BumpEvasion) &&
            continuous && !p->isOnGround && q->isOnGround && p->rotMat.up.z < .7f &&
            q->rotMat.up.z > .85f && q->vel.Length2D() > 250 &&
            q->vel.Length2D() >= p->vel.Length2D() * .35f && summary_.recoveries < 2) {
            Pay(result, (routine_ == PracticeRoutine::Recovery ? .65 : .2) *
                std::clamp(double(q->vel.Length2D()) / 1100, .4, 1.0), TaskRecovery);
            ++summary_.recoveries;
        }
        if (routine_ == PracticeRoutine::Boost && continuous) {
            const int padIndex = PickupPad(before, after, *p, *q);
            if (padIndex >= 0) {
                bool steals = false;
                for (const auto& other : before.players)
                    steals = steals || (p->boost >= 45 && TeammateNeedsPad(*p, other,
                        RLGC::CommonValues::BOOST_LOCATIONS[padIndex], before.ball));
                if (steals) result.reward -= .2;
                else if (summary_.usefulPickups < 4 && ProductivePickup(before, after, *p, *q, sign)) {
                    Pay(result, .25 * std::min(double(q->boost - p->boost) / 12, 1.5), TaskPickup);
                    ++summary_.usefulPickups;
                }
            }
            if (summary_.sharedPickups < 2) for (const auto& other : before.players) {
                const auto* updated = Find(after, other.carId);
                if (!updated || other.team != p->team || other.carId == learnerId) continue;
                const int shared = PickupPad(before, after, other, *updated);
                if (shared >= 0 && TeammateNeedsPad(*p, other,
                    RLGC::CommonValues::BOOST_LOCATIONS[shared], before.ball)) {
                    Pay(result, .2, TaskSharedPickup); ++summary_.sharedPickups;
                }
            }
        }
        if (routine_ == PracticeRoutine::Bump && continuous && q->carContact.otherCarID) {
            const auto victimId = q->carContact.otherCarID;
            const bool edge = p->carContact.otherCarID != victimId ||
                q->carContact.cooldownTimer > p->carContact.cooldownTimer + 1e-4f;
            const auto* victim = Find(after, victimId); const auto* oldVictim = Find(before, victimId);
            if (edge && victim && oldVictim && victim->team != q->team &&
                !oldVictim->isDemoed && !bumped_.count(victimId) &&
                (ShotCorridor(before, *oldVictim, sign) || ShotCorridor(after, *victim, sign))) {
                Pay(result, victim->isDemoed ? .85 : .65, TaskUsefulBump);
                bumped_.insert(victimId); ++summary_.usefulBumps;
            }
        }
        if (routine_ == PracticeRoutine::BumpEvasion) {
            if (!p->isDemoed && q->isDemoed) {
                result.reward -= .5; result.events |= TaskDemoed; ++summary_.demos;
                threats_.clear();
            }
            if (continuous) for (const auto& other : before.players) {
                if (other.team == p->team || evaded_.count(other.carId)) continue;
                const auto* updated = Find(after, other.carId);
                if (!updated) continue;
                if (DemoThreat(*p, other) && !threats_.count(other.carId))
                    threats_[other.carId] = {summary_.ticks, p->pos};
                auto threat = threats_.find(other.carId);
                if (threat == threats_.end()) continue;
                const uint64_t age = summary_.ticks - threat->second.began;
                const bool separating = q->pos.Dist(updated->pos) > p->pos.Dist(other.pos) + .05f;
                if (age >= 8 && age < 240 && !updated->isDemoed && !DemoThreat(*q, *updated) &&
                    separating && q->pos.Dist2D(threat->second.position) > 100 &&
                    q->vel.Length2D() > 300) {
                    Pay(result, .45, TaskEvasion); ++summary_.evasions;
                    evaded_.insert(other.carId); threats_.erase(threat);
                } else if (age >= 240) threats_.erase(threat);
            }
        }
        summary_.reward += result.reward;
        summary_.succeeded = summary_.succeeded || result.success;
        return result;
    }
};

} // namespace SlaterAttention
