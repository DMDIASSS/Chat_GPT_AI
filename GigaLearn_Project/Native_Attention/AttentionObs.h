#pragma once
// Exact current Python TeamObserver contract, adapted from Nexto/Necto.
// Upstream observation source: vendor/nexto/nexto_obs.py (CC BY-NC-SA 4.0).
// Deliberately independent of LibTorch: inference batches own their buffers.
#include <RLGymCPP/Gamestates/GameState.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace SlaterAttention {

using Controls = std::array<float, 8>;
using PreviousActions = std::unordered_map<uint32_t, Controls>;
using AgentLabels = std::unordered_map<uint32_t, std::string>;

struct FlatObservation {
    uint32_t carId = 0;
    std::array<float, 32> q{};
    std::array<float, 41 * 24> kv{};
    std::array<float, 41> mask{};
};

// Append observations across arenas, then wrap/copy these buffers as
// q[B,1,32], kv[B,41,24], mask[B,41]. All arrays are contiguous float32.
struct FlatBatch {
    std::vector<float> q, kv, mask;
    std::vector<uint32_t> carIds;
    void Reserve(size_t rows) { q.reserve(rows * 32); kv.reserve(rows * 984); mask.reserve(rows * 41); carIds.reserve(rows); }
    void Append(const FlatObservation& row) {
        q.insert(q.end(), row.q.begin(), row.q.end());
        kv.insert(kv.end(), row.kv.begin(), row.kv.end());
        mask.insert(mask.end(), row.mask.begin(), row.mask.end());
        carIds.push_back(row.carId);
    }
    size_t Size() const { return carIds.size(); }
};

class AttentionObs {
    using Features = std::array<double, 24>;
    using Matrix = std::array<std::array<double, 3>, 3>;
    inline static constexpr double BoostLocations[34][3] = {
        {0,-4240,70}, {-1792,-4184,70}, {1792,-4184,70}, {-3072,-4096,73}, {3072,-4096,73},
        {-940,-3308,70}, {940,-3308,70}, {0,-2816,70}, {-3584,-2484,70}, {3584,-2484,70},
        {-1788,-2300,70}, {1788,-2300,70}, {-2048,-1036,70}, {0,-1024,70}, {2048,-1036,70},
        {-3584,0,73}, {-1024,0,70}, {1024,0,70}, {3584,0,73}, {-2048,1036,70}, {0,1024,70},
        {2048,1036,70}, {-1788,2300,70}, {1788,2300,70}, {-3584,2484,70}, {3584,2484,70},
        {0,2816,70}, {-940,3310,70}, {940,3308,70}, {-3072,4096,73}, {3072,4096,73},
        {-1792,4184,70}, {1792,4184,70}, {0,4240,70}
    };

    static void SetVec(Features& out, size_t offset, const RocketSim::Vec& value) {
        for (size_t axis = 0; axis < 3; ++axis) out[offset + axis] = value[axis];
    }

    // Python encodes a rotation matrix to a quaternion, then reconstructs it.
    // Preserve that round trip (not just the original basis vectors), including
    // all four trace branches and double precision before the final float cast.
    static Matrix RoundTripRotation(const RocketSim::RotMat& rotation) {
        Matrix m{};
        for (size_t row = 0; row < 3; ++row)
            for (size_t col = 0; col < 3; ++col) m[row][col] = rotation[col][row];
        std::array<double, 4> q{};
        const double trace = m[0][0] + m[1][1] + m[2][2];
        if (trace > 0) {
            double s = std::sqrt(trace + 1);
            q[0] = s * .5; s = .5 / s;
            q[1] = (m[2][1] - m[1][2]) * s;
            q[2] = (m[0][2] - m[2][0]) * s;
            q[3] = (m[1][0] - m[0][1]) * s;
        } else if (m[0][0] >= m[1][1] && m[0][0] >= m[2][2]) {
            const double s = std::sqrt(1 + m[0][0] - m[1][1] - m[2][2]), inv = .5 / s;
            q[1] = .5 * s; q[2] = (m[1][0] + m[0][1]) * inv;
            q[3] = (m[2][0] + m[0][2]) * inv; q[0] = (m[2][1] - m[1][2]) * inv;
        } else if (m[1][1] > m[2][2]) {
            const double s = std::sqrt(1 + m[1][1] - m[0][0] - m[2][2]), inv = .5 / s;
            q[1] = (m[0][1] + m[1][0]) * inv; q[2] = .5 * s;
            q[3] = (m[1][2] + m[2][1]) * inv; q[0] = (m[0][2] - m[2][0]) * inv;
        } else {
            const double s = std::sqrt(1 + m[2][2] - m[0][0] - m[1][1]), inv = .5 / s;
            q[1] = (m[0][2] + m[2][0]) * inv; q[2] = (m[1][2] + m[2][1]) * inv;
            q[3] = .5 * s; q[0] = (m[1][0] - m[0][1]) * inv;
        }
        const double w = q[0], x = q[1], y = q[2], z = q[3];
        const double norm = w*w + x*x + y*y + z*z;
        Matrix result{};
        if (norm == 0) return result;
        const double s = 1 / norm;
        result[0][0] = 1 - 2*s*(y*y + z*z); result[1][0] = 2*s*(x*y + z*w); result[2][0] = 2*s*(x*z - y*w);
        result[0][1] = 2*s*(x*y - z*w); result[1][1] = 1 - 2*s*(x*x + z*z); result[2][1] = 2*s*(y*z + x*w);
        result[0][2] = 2*s*(x*z + y*w); result[1][2] = 2*s*(y*z - x*w); result[2][2] = 1 - 2*s*(x*x + y*y);
        return result;
    }

    static void Normalize(Features& f) {
        for (size_t j = 5; j < 11; ++j) f[j] /= 2300.;
        for (size_t j = 17; j < 20; ++j) f[j] /= 5.5;
    }
    static void Invert(Features& f) {
        for (size_t j = 5; j < 20; j += 3) { f[j] = -f[j]; f[j + 1] = -f[j + 1]; }
        std::swap(f[1], f[2]);
    }

public:
    // Stateless: GameState already supplies the time-dependent simulation
    // fields. The legacy builder uses boost-active/demo booleans, not timers.
    // Therefore observing multiple players or repeated calls cannot advance a
    // fictitious countdown. PreviousActions are the actual prior commands.
    static std::vector<FlatObservation> BuildAll(
        const RLGC::GameState& state, const PreviousActions& previous = {}, const AgentLabels& labels = {}) {
        if (state.players.size() < 2 || state.players.size() > 6 || state.boostPadTimers.size() != 34)
            throw std::invalid_argument("Attention observations require 2..6 players and 34 boost timers");
        std::vector<const RLGC::Player*> players;
        std::unordered_set<uint32_t> ids;
        size_t blue = 0, orange = 0;
        for (const auto& p : state.players) {
            if (!ids.insert(p.carId).second) throw std::invalid_argument("Duplicate attention car ID");
            if (p.team == RocketSim::Team::BLUE) ++blue;
            else if (p.team == RocketSim::Team::ORANGE) ++orange;
            else throw std::invalid_argument("Invalid attention team");
            players.push_back(&p);
        }
        if (blue < 1 || blue > 3 || orange < 1 || orange > 3)
            throw std::invalid_argument("Attention team sizes must each be 1..3");
        auto label = [&labels](uint32_t id) {
            auto it = labels.find(id); return it == labels.end() ? std::to_string(id) : it->second;
        };
        std::sort(players.begin(), players.end(), [&](const auto* a, const auto* b) {
            if (a->team != b->team) return a->team == RocketSim::Team::BLUE;
            return label(a->carId) < label(b->carId);
        });
        std::array<Features, 41> shared{};
        for (size_t i = 0; i < players.size(); ++i) {
            const auto& p = *players[i]; auto& f = shared[i];
            f[p.team == RocketSim::Team::BLUE ? 1 : 2] = 1;
            SetVec(f, 5, p.pos); SetVec(f, 8, p.vel); SetVec(f, 17, p.angVel);
            const auto rotation = RoundTripRotation(p.rotMat);
            for (size_t axis = 0; axis < 3; ++axis) { f[11 + axis] = rotation[axis][0]; f[14 + axis] = rotation[axis][2]; }
            f[20] = double(p.boost) / 100.; f[21] = p.isDemoed; f[22] = p.isOnGround;
            // RLGym v2 has_flip excludes a used/expired flip even on ground;
            // HasFlipOrJump() would OR isOnGround and change that contract.
            f[23] = !p.hasDoubleJumped && !p.hasFlipped && p.airTimeSinceJump < 1.25;
        }
        auto& ball = shared[6]; ball[3] = 1;
        SetVec(ball, 5, state.ball.pos); SetVec(ball, 8, state.ball.vel); SetVec(ball, 17, state.ball.angVel);
        for (size_t i = 0; i < 34; ++i) {
            auto& f = shared[7 + i]; f[4] = 1;
            for (size_t axis = 0; axis < 3; ++axis) f[5 + axis] = BoostLocations[i][axis];
            f[20] = .12 + .88 * (BoostLocations[i][2] > 72);
            if (!std::isfinite(state.boostPadTimers[i])) throw std::invalid_argument("Nonfinite attention boost timer");
            f[21] = state.boostPadTimers[i] <= 1e-6;
        }
        for (const auto& f : shared) for (double value : f)
            if (!std::isfinite(value)) throw std::invalid_argument("Nonfinite attention state");
        std::vector<FlatObservation> result; result.reserve(players.size());
        for (size_t i = 0; i < players.size(); ++i) {
            auto entities = shared; entities[i][0] = 1;
            for (auto& f : entities) { if (players[i]->team == RocketSim::Team::ORANGE) Invert(f); Normalize(f); }
            const auto query = entities[i];
            const double theta = std::atan2(query[11], query[12]), ct = std::cos(theta), st = std::sin(theta);
            FlatObservation output; output.carId = players[i]->carId;
            for (size_t j = 0; j < 24; ++j) output.q[j] = static_cast<float>(query[j]);
            auto controls = previous.find(output.carId);
            for (size_t j = 0; j < 8; ++j) {
                const float value = controls == previous.end() ? 0 : controls->second[j];
                if (!std::isfinite(value) || std::abs(value) > 1.001f) throw std::invalid_argument("Invalid attention previous controller input");
                output.q[24 + j] = value;
            }
            for (size_t entity = 0; entity < 41; ++entity) {
                if (entity >= players.size() && entity < 6) { output.mask[entity] = -10000; continue; }
                auto& f = entities[entity];
                for (size_t axis = 0; axis < 3; ++axis) f[5 + axis] -= query[5 + axis];
                for (size_t offset = 5; offset < 20; offset += 3) {
                    const double x = f[offset], y = f[offset + 1];
                    f[offset] = ct*x - st*y; f[offset + 1] = st*x + ct*y;
                }
                for (size_t j = 0; j < 24; ++j) output.kv[entity*24 + j] = static_cast<float>(f[j]);
            }
            result.push_back(output);
        }
        return result;
    }
};

} // namespace SlaterAttention
