#pragma once

// Native migration of the match branch in slater_versatile_env.py.  The world
// deliberately knows nothing about Torch, PPO, observations, or learner buffers.
#include <RLGymCPP/Gamestates/GameState.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <memory>
#include <numeric>
#include <random>
#include <stdexcept>
#include <vector>

namespace SlaterAttention {

using Action = RLGC::Action;

inline Action ZeroAction() { return Action(0, 0, 0, 0, 0, 0, 0, 0); }

inline Action KickoffAction(int tick) {
    constexpr int lengths[] = {44, 16, 8, 4, 4, 52, 40};
    constexpr float values[][8] = {
        {1, 0, 0, 0, 0, 0, 1, 0}, {1, -1, 0, 0, 0, 0, 1, 0},
        {1, 0, 0, 0, 0, 1, 1, 0}, {1, 0, 0, 0, 0, 0, 1, 0},
        {1, 0, -.7f, .8f, 0, 1, 1, 0}, {1, 0, 1, 0, 0, 0, 1, 0},
        {1, 0, .5f, 0, 1, 0, 0, 0}};
    if (tick < 0 || tick >= 168) throw std::out_of_range("Kickoff tick outside 0..167");
    int stage = 0;
    while (tick >= lengths[stage]) tick -= lengths[stage++];
    const auto& a = values[stage];
    return Action(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]);
}

// Exact one-packet NextoV4Clock order, including the original left-goes branch
// and the mutation of action by kickoff overrides.  Every frozen car has its
// own clock; controls and action are different quantities between update ticks.
struct FrozenClock {
    int ticks = 8;
    bool updateAction = true;
    int kickoffIndex = -1;
    Action action = ZeroAction(), controls = ZeroAction();
    uint64_t inferences = 0, scriptTicks = 0;

    static bool KickoffTaker(const RLGC::GameState& state, uint32_t carId) {
        const RLGC::Player* ours = nullptr;
        float closest = INFINITY;
        for (const auto& p : state.players) {
            closest = std::min(closest, p.pos.Dist2D(state.ball.pos));
            if (p.carId == carId) ours = &p;
        }
        if (!ours) throw std::invalid_argument("Unknown frozen car");
        const float distance = ours->pos.Dist2D(state.ball.pos);
        if (std::abs(closest - distance) > 10) return false;
        bool taking = true;
        for (const auto& other : state.players) {
            if (other.carId == carId || other.team != ours->team ||
                std::abs(other.pos.Dist2D(state.ball.pos) - distance) > 10) continue;
            const bool isLeft = ours->team == RocketSim::Team::BLUE
                ? other.pos.x < ours->pos.x : other.pos.x > ours->pos.x;
            if (!isLeft) taking = false;  // Source condition, not a rewritten intent.
        }
        return taking;
    }

    Action Frame(const RLGC::GameState& state, uint32_t carId,
                 bool kickoffPause, const Action* neuralAction) {
        ++ticks;
        if (updateAction) {
            if (!neuralAction) throw std::invalid_argument("Missing ready frozen policy action");
            for (float value : *neuralAction)
                if (!std::isfinite(value)) throw std::invalid_argument("Nonfinite frozen control");
            updateAction = false;
            action = *neuralAction;
            ++inferences;
        }
        if (ticks >= 7) controls = action;
        if (ticks >= 8) { ticks = 0; updateAction = true; }
        if (kickoffPause) {
            if (kickoffIndex >= 0) ++kickoffIndex;
            else if (kickoffIndex == -1)
                kickoffIndex = KickoffTaker(state, carId) ? 0 : -2;
            if (kickoffIndex >= 0 && kickoffIndex < 168 && state.ball.pos.y == 0) {
                action = KickoffAction(kickoffIndex);
                controls = action;
                ++scriptTicks;
            }
        } else kickoffIndex = -1;
        return controls;
    }
};

struct WorldStepInfo {
    int outcome = 0;                // Relative to learner team, never a rival sample.
    bool terminal = false, timeout = false;
    int physicsTicks = 0;
    uint64_t episodePhysicsTicks = 0, scriptPhysicsTicks = 0;
    int learnerTouchTicks = 0, goalwardTouchTicks = 0;
    double reward = 0;
};

inline double MatchPotential(const RocketSim::Vec& ball, const RocketSim::Vec& car,
                             float learnerSign) {
    return .4 * learnerSign * double(ball.y) / 5120.0
        - .12 * std::min(double((ball - car).Length()) / 5000.0, 1.0);
}

inline double MatchPotentialReward(double potential, double previous) {
    return std::pow(.995, 1.0 / 8.0) * potential - previous - .02 / 120.0;
}

class AttentionWorld {
    std::unique_ptr<RocketSim::Arena> arena_;
    std::vector<uint32_t> blueIds_, orangeIds_;
    RLGC::GameState state_, prior_;
    std::map<uint32_t, FrozenClock> clocks_;
    std::map<uint32_t, Action> previous_;  // Commands emitted, not last physics controls.
    Action learnerAction_ = ZeroAction();
    uint32_t learnerId_ = 0;
    float sign_ = 1;
    uint64_t episodeTicks_ = 0, maxTicks_ = 0;
    int lastTouch_ = -100, touchPayments_ = 0;
    bool ballTouched_ = false, stepActive_ = false, episodeDone_ = false;
    double potential_ = 0, episodeReward_ = 0;
    WorldStepInfo info_;

    void Refresh() {
        prior_ = state_;
        prior_.prev = nullptr;
        std::vector<Action> actions;
        actions.reserve(arena_->GetCars().size());
        for (auto* car : arena_->GetCars()) actions.push_back(previous_.at(car->id));
        state_.ResetBeforeStep();
        state_.UpdateFromArena(arena_.get(), actions,
                               prior_.players.size() == actions.size() ? &prior_ : nullptr);
        // Keep the same authoritative soccar threshold as the Python reference.
        state_.goalScored = std::abs(state_.ball.pos.y) > 5215.5f;
    }

    void FinishReset() {
        previous_.clear(); clocks_.clear();
        for (auto* car : arena_->GetCars()) {
            car->controls = RocketSim::CarControls();
            previous_[car->id] = ZeroAction();
            if (car->id != learnerId_) clocks_.emplace(car->id, FrozenClock{});
        }
        for (auto* pad : arena_->GetBoostPads()) pad->SetState(RocketSim::BoostPadState{});
        state_ = RLGC::GameState{}; prior_ = RLGC::GameState{};
        state_.lastTickCount = arena_->tickCount;
        Refresh();
        episodeTicks_ = 0; lastTouch_ = -100; touchPayments_ = 0;
        ballTouched_ = stepActive_ = episodeDone_ = false;
        episodeReward_ = 0; info_ = {};
        potential_ = MatchPotential(state_.ball.pos, state_.players.at(LearnerIndex()).pos, sign_);
    }

public:
    // RocketSim::Init(meshes) belongs to executable startup, before any worlds.
    AttentionWorld(int blueSize = 1, int orangeSize = 1,
                   RocketSim::Team learnerTeam = RocketSim::Team::BLUE,
                   double maxSeconds = 30)
        : arena_(RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR)) {
        if (blueSize < 1 || blueSize > 3 || orangeSize < 1 || orangeSize > 3 ||
            !std::isfinite(maxSeconds) || maxSeconds <= 0)
            throw std::invalid_argument("World requires 1..3 cars per side and positive duration");
        maxTicks_ = uint64_t(std::llround(maxSeconds * 120));
        for (int i = 0; i < blueSize; ++i) blueIds_.push_back(arena_->AddCar(RocketSim::Team::BLUE)->id);
        for (int i = 0; i < orangeSize; ++i) orangeIds_.push_back(arena_->AddCar(RocketSim::Team::ORANGE)->id);
        learnerId_ = (learnerTeam == RocketSim::Team::BLUE ? blueIds_ : orangeIds_).front();
        sign_ = learnerTeam == RocketSim::Team::BLUE ? 1.f : -1.f;
        Reset(0);
    }

    AttentionWorld(const AttentionWorld&) = delete;
    AttentionWorld& operator=(const AttentionWorld&) = delete;
    RocketSim::Arena* Arena() { return arena_.get(); }
    const RLGC::GameState& State() const { return state_; }
    uint32_t LearnerId() const { return learnerId_; }
    float LearnerSign() const { return sign_; }
    size_t LearnerSlot() const {
        const auto& ids = sign_ > 0 ? blueIds_ : orangeIds_;
        const auto found = std::find(ids.begin(), ids.end(), learnerId_);
        if (found == ids.end()) throw std::logic_error("Learner absent from own roster");
        return size_t(std::distance(ids.begin(), found));
    }
    size_t LearnerIndex() const {
        for (size_t i = 0; i < state_.players.size(); ++i)
            if (state_.players[i].carId == learnerId_) return i;
        throw std::runtime_error("Learner absent from native GameState");
    }
    const std::vector<uint32_t>& BlueIds() const { return blueIds_; }
    const std::vector<uint32_t>& OrangeIds() const { return orangeIds_; }
    // Rotate the trained seat at an episode boundary. Reset rebuilds frozen
    // clocks, so the former learner never carries controls into its new role.
    void SelectLearner(RocketSim::Team team, size_t slot) {
        if (stepActive_) throw std::logic_error("Change learner only at an action boundary");
        const auto& ids = team == RocketSim::Team::BLUE ? blueIds_ : orangeIds_;
        learnerId_ = ids.at(slot);
        sign_ = team == RocketSim::Team::BLUE ? 1.f : -1.f;
    }
    const std::map<uint32_t, Action>& PreviousActions() const { return previous_; }
    Action PreviousForInference(uint32_t carId) const { return clocks_.at(carId).action; }
    bool Done() const { return episodeDone_; }
    bool StepComplete() const { return !stepActive_; }
    double Reward() const { return info_.reward; }
    double EpisodeReward() const { return episodeReward_; }
    const WorldStepInfo& StepInfo() const { return info_; }
    uint64_t EpisodeTicks() const { return episodeTicks_; }

    // std::shuffle and Python random.shuffle have different seeded streams.
    // Pass the Python permutation explicitly for cross-framework fixtures.
    void Reset(uint64_t seed, const std::array<int, 5>* explicitPermutation = nullptr) {
        std::array<int, 5> order = {0, 1, 2, 3, 4};
        if (explicitPermutation) order = *explicitPermutation;
        else { std::mt19937_64 rng(seed); std::shuffle(order.begin(), order.end(), rng); }
        auto checked = order; std::sort(checked.begin(), checked.end());
        if (checked != std::array<int, 5>{0, 1, 2, 3, 4})
            throw std::invalid_argument("Invalid kickoff spawn permutation");
        constexpr float xy[5][2] = {{-2048, -2560}, {2048, -2560}, {-256, -3840},
                                    {256, -3840}, {0, -4608}};
        constexpr float pi = 3.14159265358979323846f;
        constexpr float yaw[5] = {pi / 4, 3 * pi / 4, pi / 2, pi / 2, pi / 2};
        constexpr float orangeYaw[5] = {-3 * pi / 4, -pi / 4, -pi / 2, -pi / 2, -pi / 2};
        for (int team = 0; team < 2; ++team) {
            const auto& ids = team == 0 ? blueIds_ : orangeIds_;
            const float orientation = team == 0 ? 1.f : -1.f;
            for (size_t i = 0; i < ids.size(); ++i) {
                const int spawn = order.at(i);
                const float angle = team ? orangeYaw[spawn] : yaw[spawn];
                RocketSim::CarState car;
                car.pos = {orientation * xy[spawn][0], orientation * xy[spawn][1], 17};
                car.rotMat = RocketSim::RotMat({std::cos(angle), std::sin(angle), 0},
                                               {-std::sin(angle), std::cos(angle), 0}, {0, 0, 1});
                car.boost = 33.3f;
                car.isOnGround = true;
                for (bool& contact : car.wheelsWithContact) contact = true;
                arena_->GetCar(ids[i])->SetState(car);
            }
        }
        RocketSim::BallState ball;
        ball.pos = {0, 0, 93.15f}; ball.vel = {}; ball.angVel = {};
        arena_->ball->SetState(ball);
        FinishReset();
    }

    // Stable order is blue-0..N, orange-0..M regardless of arena's unordered set.
    void ResetFromStates(const RocketSim::BallState& ball,
                         const std::vector<RocketSim::CarState>& cars,
                         const std::vector<float>& boostCooldowns = {}) {
        if (cars.size() != blueIds_.size() + orangeIds_.size())
            throw std::invalid_argument("Fixture car count differs from world team sizes");
        std::vector<uint32_t> ids = blueIds_;
        ids.insert(ids.end(), orangeIds_.begin(), orangeIds_.end());
        for (size_t i = 0; i < ids.size(); ++i) arena_->GetCar(ids[i])->SetState(cars[i]);
        arena_->ball->SetState(ball); FinishReset();
        if (!boostCooldowns.empty()) {
            if (boostCooldowns.size() != arena_->GetBoostPads().size())
                throw std::invalid_argument("Fixture boost-pad count differs from arena");
            for (size_t i = 0; i < boostCooldowns.size(); ++i) {
                RocketSim::BoostPadState pad;
                pad.cooldown = boostCooldowns[i]; pad.isActive = pad.cooldown <= 0;
                arena_->GetBoostPads()[i]->SetState(pad);
            }
            Refresh();
        }
    }

    void BeginAction(const Action& learnerAction) {
        if (episodeDone_) throw std::logic_error("Reset terminal world before collection");
        if (stepActive_) throw std::logic_error("Previous eight-packet action still running");
        for (float value : learnerAction)
            if (!std::isfinite(value)) throw std::invalid_argument("Nonfinite learner control");
        learnerAction_ = learnerAction; info_ = {}; stepActive_ = true;
    }

    // Evaluation-only per-packet kickoff override. Normal PPO collection does
    // not call this hook and continues holding its sampled action for 8 ticks.
    void SetLearnerPacketAction(const Action& action) {
        if (!stepActive_) throw std::logic_error("BeginAction before packet override");
        for (float value : action)
            if (!std::isfinite(value)) throw std::invalid_argument("Nonfinite packet control");
        learnerAction_ = action;
    }

    // A drill can fail its physical phase deadline before the ordinary arena
    // time limit. This is a task terminal, not a goal or an artificial timeout.
    void EndPracticeEpisode() {
        if (episodeDone_) return;
        episodeDone_ = true; stepActive_ = false;
        info_.terminal = true; info_.timeout = false;
        info_.episodePhysicsTicks = episodeTicks_;
    }

    std::vector<uint32_t> ReadyCars() const {
        std::vector<uint32_t> ids;
        if (!stepActive_) return ids;
        for (const auto& [id, clock] : clocks_) if (clock.updateAction) ids.push_back(id);
        return ids;
    }

    // Caller batches ReadyCars across every world, infers frozen attention once,
    // and supplies only those actions here.  This function can run in parallel
    // across independently owned arenas; it uses no mutable shared RNG/state.
    void Tick(const std::map<uint32_t, Action>& readyActions) {
        if (!stepActive_) throw std::logic_error("BeginAction must precede physics packet");
        const bool kickoff = !ballTouched_ && episodeTicks_ < 168 &&
            state_.ball.pos.Length2D() < 1 && state_.ball.pos.z < 100;
        std::map<uint32_t, Action> commands = {{learnerId_, learnerAction_}};
        for (auto& [id, clock] : clocks_) {
            auto found = readyActions.find(id);
            const Action* predicted = found == readyActions.end() ? nullptr : &found->second;
            commands[id] = clock.Frame(state_, id, kickoff, predicted);
        }
        // rlbot_delay=True: simulate old controls, then install current commands.
        arena_->Step(1);
        for (auto* car : arena_->GetCars()) car->controls = (RocketSim::CarControls)commands.at(car->id);
        previous_ = commands;
        Refresh();
        ++episodeTicks_; ++info_.physicsTicks;
        bool touched = false;
        for (const auto& player : state_.players) touched |= player.ballTouchedStep;
        ballTouched_ |= touched;
        const auto& learner = state_.players.at(LearnerIndex());
        const bool goal = state_.goalScored;
        const double nextPotential = goal ? 0 : MatchPotential(state_.ball.pos, learner.pos, sign_);
        double reward = MatchPotentialReward(nextPotential, potential_);
        potential_ = nextPotential;
        if (learner.ballTouchedStep) {
            ++info_.learnerTouchTicks;
            if (sign_ * state_.ball.vel.y > 100) ++info_.goalwardTouchTicks;
            if (int64_t(episodeTicks_) - lastTouch_ > 30 && touchPayments_ < 6) {
                if (sign_ * state_.ball.vel.y > 100) { reward += .05; ++touchPayments_; }
                lastTouch_ = int(episodeTicks_);
            }
        }
        if (goal) {
            info_.outcome = sign_ * state_.ball.pos.y > 0 ? 1 : -1;
            reward += 10 * info_.outcome;
            info_.terminal = true;
        }
        info_.timeout = !goal && episodeTicks_ >= maxTicks_;
        episodeDone_ = info_.terminal || info_.timeout;
        info_.reward += reward; episodeReward_ += reward;
        info_.episodePhysicsTicks = episodeTicks_;
        info_.scriptPhysicsTicks = 0;
        for (const auto& [id, clock] : clocks_) info_.scriptPhysicsTicks += clock.scriptTicks;
        if (episodeDone_ || info_.physicsTicks == 8) stepActive_ = false;
    }
};

} // namespace SlaterAttention
