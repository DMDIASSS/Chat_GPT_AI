// Standalone JSON state bridge for real Python RocketSim observation parity.
// This intentionally injects states, avoiding simulator-version differences.
#include "AttentionObs.h"
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <iomanip>

using json = nlohmann::json;

static RocketSim::Vec ReadVec(const json& value) {
    if (!value.is_array() || value.size() != 3) throw std::invalid_argument("Expected three-vector");
    return {value.at(0).get<float>(), value.at(1).get<float>(), value.at(2).get<float>()};
}

int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::invalid_argument("Usage: SlaterAttentionObsParity states.json observations.json");
        std::ifstream input(argv[1]); if (!input) throw std::runtime_error("Cannot open parity states");
        json payload; input >> payload; json output = json::array();
        for (const auto& frame : payload.at("states")) {
            RLGC::GameState state;
            state.boostPadTimers = frame.at("boost_pad_timers").get<std::vector<float>>();
            state.ball.pos = ReadVec(frame.at("ball").at("position"));
            state.ball.vel = ReadVec(frame.at("ball").at("linear_velocity"));
            state.ball.angVel = ReadVec(frame.at("ball").at("angular_velocity"));
            SlaterAttention::PreviousActions previous;
            SlaterAttention::AgentLabels labels;
            for (const auto& car : frame.at("cars")) {
                RLGC::Player p{};
                p.carId = car.at("car_id").get<uint32_t>();
                p.team = car.at("is_orange").get<bool>() ? RocketSim::Team::ORANGE : RocketSim::Team::BLUE;
                p.pos = ReadVec(car.at("position")); p.vel = ReadVec(car.at("linear_velocity"));
                p.angVel = ReadVec(car.at("angular_velocity"));
                for (size_t row = 0; row < 3; ++row)
                    for (size_t col = 0; col < 3; ++col) p.rotMat[col][row] = car.at("rotation_mtx").at(row).at(col).get<float>();
                p.boost = car.at("boost_amount").get<float>(); p.isDemoed = car.at("is_demoed").get<bool>();
                p.isOnGround = car.at("on_ground").get<bool>(); p.hasDoubleJumped = car.at("has_double_jumped").get<bool>();
                p.hasFlipped = car.at("has_flipped").get<bool>(); p.airTimeSinceJump = car.at("air_time_since_jump").get<float>();
                state.players.push_back(p);
                labels.emplace(p.carId, car.at("agent_id").get<std::string>());
                if (car.contains("previous")) previous.emplace(p.carId, car.at("previous").get<SlaterAttention::Controls>());
            }
            json observations = json::array();
            for (const auto& obs : SlaterAttention::AttentionObs::BuildAll(state, previous, labels))
                observations.push_back({{"agent_id", labels.at(obs.carId)}, {"q", obs.q}, {"kv", obs.kv}, {"mask", obs.mask}});
            output.push_back({{"name", frame.at("name")}, {"observations", observations}});
        }
        std::ofstream result(argv[2]); if (!result) throw std::runtime_error("Cannot write parity observations");
        result << std::setprecision(17) << json{{"states", output}}.dump();
        return 0;
    } catch (const std::exception& error) { std::cerr << "ATTENTION_OBS_PARITY_ERROR " << error.what() << '\n'; return 1; }
}
