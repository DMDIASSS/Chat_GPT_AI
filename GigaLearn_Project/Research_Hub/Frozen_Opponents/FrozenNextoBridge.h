// Frozen Nexto-family opponent bridge for RLGymCPP, GigaLearn native PPO.
// Read-only inference through the existing embedded Python interpreter.
#pragma once
#include <GigaLearnCPP/Learner.h>
#include <RLGymCPP/ActionParsers/DefaultAction.h>
#include <pybind11/embed.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <array>
#include <cstdlib>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace GGL {
namespace py = pybind11;

class FrozenNextoBridge {
    py::object worker;
    std::string active;
    static const char* EnvRequired(const char* name) {
        const char* v = std::getenv(name);
        if (!v || !*v) throw std::runtime_error(std::string("[FrozenNexto] missing environment variable: ") + name);
        return v;
    }
    static void PutVec(float* dest, int& offset, const RocketSim::Vec& v) {
        dest[offset++] = v.x;
        dest[offset++] = v.y;
        dest[offset++] = v.z;
    }
    static void PutPlayer(float* dest, int& offset, const RLGC::Player& p) {
        PutVec(dest, offset, p.pos);
        PutVec(dest, offset, p.rotMat.forward);
        PutVec(dest, offset, p.rotMat.right);
        PutVec(dest, offset, p.rotMat.up);
        PutVec(dest, offset, p.vel);
        PutVec(dest, offset, p.angVel);
        dest[offset++] = p.boost;
        dest[offset++] = p.isOnGround ? 1.f : 0.f;
        dest[offset++] = p.HasFlipOrJump() ? 1.f : 0.f;
        dest[offset++] = p.isDemoed ? 1.f : 0.f;
        dest[offset++] = p.ballTouchedStep ? 1.f : 0.f;
    }
public:
    explicit FrozenNextoBridge(const RLGC::EnvSet& env) {
        if (env.state.gameStates.empty() || env.actionParsers.empty() ||
            env.actionParsers.at(0)->GetActionAmount() != 90)
            throw std::runtime_error("[FrozenNexto] requires a 1v1 DefaultAction arena with 90 actions");
        if (env.config.tickSkip != 8)
            throw std::runtime_error("[FrozenNexto] requires tickSkip=8 to match Nexto training");
        const auto* parser = dynamic_cast<RLGC::DefaultAction*>(env.actionParsers.at(0));
        if (!parser || parser->actions.size() != 90)
            throw std::runtime_error("[FrozenNexto] expected the exact native DefaultAction parser");
        auto controls = py::array_t<float>({90, 8});
        auto table = controls.mutable_unchecked<2>();
        for (int i = 0; i < 90; ++i)
            for (int j = 0; j < 8; ++j) table(i,j) = parser->actions[i][j];
        py::module_ sys = py::module_::import("sys");
        sys.attr("path").attr("insert")(0, EnvRequired("GL_FROZEN_BRIDGE_DIR"));
        py::module_ mod = py::module_::import("frozen_nexto_bridge");
        py::dict paths;
        paths["nexto"] = EnvRequired("GL_FROZEN_NEXTO_PT");
        paths["cycle9"] = EnvRequired("GL_FROZEN_CYCLE9_PT");
        paths["wavedash"] = EnvRequired("GL_FROZEN_WAVEDASH_PT");
        worker = mod.attr("FrozenRotation")(paths, controls, "cpu");
    }
    void Select(const std::string& name) {
        if (name != active) {
            worker.attr("select")(name);
            active = name;
        }
    }
    // One frozen player per game, in arena index order. The student opponent does not
    // participate in experience collection or PPO gradient updates.
    std::vector<int> Infer(const RLGC::EnvState& state, const std::vector<uint8_t>& resetFlags,
                           RocketSim::Team opponentTeam) {
        const size_t arenas = state.gameStates.size();
        if (resetFlags.size() != arenas)
            throw std::runtime_error("[FrozenNexto] incorrect reset flags");
        std::vector<py::ssize_t> payloadShape = {static_cast<py::ssize_t>(arenas), static_cast<py::ssize_t>(89)};
        py::array_t<float> payload(payloadShape);
        auto arr = payload.mutable_unchecked<2>();
        for (size_t i = 0; i < arenas; ++i) {
            const auto& gs = state.gameStates.at(i);
            if (gs.players.size() != 2 || gs.boostPads.size() != 34)
                throw std::runtime_error("[FrozenNexto] expected one blue, one orange and 34 boost pads");
            float row[89]{};
            int cursor = 0;
            for (bool pad : gs.boostPads) row[cursor++] = pad ? 1.f : 0.f;
            PutVec(row, cursor, gs.ball.pos);
            PutVec(row, cursor, gs.ball.vel);
            PutVec(row, cursor, gs.ball.angVel);
            const RLGC::Player* blue = nullptr;
            const RLGC::Player* orange = nullptr;
            for (const auto& p : gs.players) {
                if (p.team == RocketSim::Team::BLUE) blue = &p;
                else if (p.team == RocketSim::Team::ORANGE) orange = &p;
            }
            if (!blue || !orange)
                throw std::runtime_error("[FrozenNexto] missing player team");
            PutPlayer(row, cursor, *blue);
            PutPlayer(row, cursor, *orange);
            if (cursor != 89) throw std::runtime_error("[FrozenNexto] invalid state payload layout");
            for (int j = 0; j < 89; ++j) arr(static_cast<py::ssize_t>(i),j) = row[j];
        }
        auto result = worker.attr("infer")(payload, py::cast(resetFlags), opponentTeam == RocketSim::Team::ORANGE);
        auto actions = result.cast<std::vector<int>>();
        if (actions.size() != arenas)
            throw std::runtime_error("[FrozenNexto] opponent actions count mismatched arena count");
        for (int a : actions)
            if (a < 0 || a >= 90) throw std::runtime_error("[FrozenNexto] invalid opponent action ID");
        return actions;
    }
};
} // namespace GGL
