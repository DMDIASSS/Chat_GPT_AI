#pragma once

// Durable, inference-only screening of original attention policies. A job
// changes one learner slot; every teammate and opponent remains fixed.
#include "AttentionObs.h"
#include "AttentionWorld.h"
#include "AttentionPPO.h"
#include <RLGymCPP/ActionParsers/DefaultAction.h>
#include <thread_pool.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <memory>
#include <set>
#include <unordered_map>

namespace slater_attention_eval {
using json = nlohmann::json;
namespace fs = std::filesystem;
using World = SlaterAttention::AttentionWorld;
using Action = SlaterAttention::Action;
using Flat = SlaterAttention::FlatObservation;
using Clock = std::chrono::steady_clock;

inline json read_json(const fs::path& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error("Cannot read evaluation JSON: " + path.string());
    json value; file >> value; return value;
}
inline void write_json(const fs::path& path, const json& value) {
    fs::create_directories(path.parent_path());
    auto temporary = path; temporary += ".writing";
    { std::ofstream file(temporary, std::ios::binary | std::ios::trunc);
      file << value.dump(2); file.close();
      if (!file) throw std::runtime_error("Cannot write evaluation record: " + path.string()); }
    // Windows rename cannot replace a file. Per-game complete records are never
    // replaced; progress/summary are rebuildable and may be replaced here.
    if (fs::exists(path)) fs::remove(path);
    fs::rename(temporary, path);
}
inline bool safe_id(const std::string& value) {
    if (value.empty() || value.size() > 160) return false;
    for (unsigned char c : value)
        if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') ||
              (c >= 'a' && c <= 'z') || c == '_' || c == '-')) return false;
    return true;
}
inline bool valid_sha(const std::string& value) {
    if (value.size() != 64) return false;
    return std::all_of(value.begin(), value.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    });
}
struct ActorSpec {
    std::string id, sha;
    fs::path path;
};
struct Job {
    json original, descriptor;
    std::string id, candidate, rival, teammate, team_policy = "fixed_reference";
    int learner_count = 1, rival_count = 1;
    uint64_t seed = 0, ticks = 0;
    bool blue = true, scripted = false, first_goal = false;
};
struct Plan {
    std::map<std::string, ActorSpec> actors;
    std::vector<Job> jobs;
    std::string reference_id, protocol_sha;
    fs::path cache_dir;
};
inline Plan parse_plan(const fs::path& manifest_path, const fs::path& out,
                       torch::Device device, int batch_worlds) {
    auto manifest = read_json(manifest_path);
    if (manifest.at("schema").get<int>() != 1)
        throw std::runtime_error("Unsupported native selection manifest schema");
    Plan plan;
    plan.reference_id = manifest.at("reference_id").get<std::string>();
    plan.protocol_sha = manifest.at("protocol_sha").get<std::string>();
    if (!valid_sha(plan.protocol_sha)) throw std::runtime_error("Invalid selection protocol SHA");
    plan.cache_dir = manifest.contains("cache_dir")
        ? fs::path(manifest.at("cache_dir").get<std::string>()) : out / "records";
    if (plan.cache_dir.is_relative() && manifest.contains("cache_dir"))
        plan.cache_dir = manifest_path.parent_path() / plan.cache_dir;
    for (const auto& row : manifest.at("actors")) {
        ActorSpec spec{row.at("id").get<std::string>(), row.at("sha256").get<std::string>(),
                       fs::path(row.at("path").get<std::string>())};
        if (!safe_id(spec.id) || !valid_sha(spec.sha))
            throw std::runtime_error("Invalid evaluation actor ID or SHA");
        if (spec.path.is_relative()) spec.path = manifest_path.parent_path() / spec.path;
        if (spec.path.extension() != ".pt" || !fs::is_regular_file(spec.path))
            throw std::runtime_error("Selection requires private portable attention .pt actors; .lt is not attention: " + spec.path.string());
        if (!plan.actors.emplace(spec.id, spec).second)
            throw std::runtime_error("Duplicate selection actor ID");
    }
    if (!plan.actors.count(plan.reference_id)) throw std::runtime_error("Protected reference actor absent");
    std::set<std::string> job_ids;
    bool contains_reference = false;
    for (const auto& row : manifest.at("jobs")) {
        Job job; job.original = row;
        job.id = row.at("id").get<std::string>();
        job.candidate = row.at("candidate_id").get<std::string>();
        job.rival = row.at("rival_id").get<std::string>();
        job.teammate = row.value("reference_id", plan.reference_id);
        auto format = row.at("format").get<std::array<int, 2>>();
        job.learner_count = format[0]; job.rival_count = format[1];
        const auto& seed = row.at("seed");
        if (!seed.is_number_integer() || (seed.is_number_integer() && !seed.is_number_unsigned() && seed.get<int64_t>() < 0))
            throw std::runtime_error("Selection seeds must be nonnegative integers");
        job.seed = seed.get<uint64_t>();
        const std::string team = row.at("learner_team").get<std::string>();
        if (team != "blue" && team != "orange") throw std::runtime_error("Invalid learner color");
        job.blue = team == "blue";
        double duration = row.at("seconds").get<double>();
        if (!safe_id(job.id) || !job_ids.insert(job.id).second ||
            !plan.actors.count(job.candidate) || !plan.actors.count(job.rival) || !plan.actors.count(job.teammate) ||
            job.learner_count < 1 || job.learner_count > 3 || job.rival_count < 1 || job.rival_count > 3 ||
            !std::isfinite(duration) || duration < .1 || duration > 3600)
            throw std::runtime_error("Invalid or duplicate selection job");
        job.ticks = uint64_t(std::llround(duration * 120));
        job.scripted = row.value("learner_scripted_kickoff", false);
        job.first_goal = row.value("stop_after_first_goal", false);
        job.team_policy = row.value("team_policy", "fixed_reference");
        if (job.team_policy != "fixed_reference" && job.team_policy != "candidate_squad")
            throw std::runtime_error("Unknown selection team_policy");
        if (row.contains("team_policy") &&
            ((job.team_policy == "fixed_reference" && job.teammate != plan.reference_id) ||
             (job.team_policy == "candidate_squad" && job.teammate != job.candidate)))
            throw std::runtime_error("Selection team_policy disagrees with frozen teammate actor assignment");
        if (!row.value("frozen_scripted_kickoff", true))
            throw std::runtime_error("Frozen kickoff scripts must remain ON in selection");
        contains_reference |= job.candidate == plan.reference_id;
        // The descriptor is independent of the candidate inventory/global stage:
        // matching reference games can be reused across groups and stages.
        job.descriptor = {
            {"contract", "native-attention-selection-v1"}, {"backend_sha", ATTENTION_SOURCE_SHA},
            {"candidate_sha", plan.actors.at(job.candidate).sha},
            {"rival_sha", plan.actors.at(job.rival).sha}, {"teammate_sha", plan.actors.at(job.teammate).sha},
            {"format", format}, {"seed", job.seed}, {"learner_team", team},
            {"team_policy", job.team_policy},
            {"ticks", job.ticks}, {"learner_scripted_kickoff", job.scripted},
            {"frozen_scripted_kickoff", true}, {"device", device.str()}, {"batch_worlds", batch_worlds},
            {"policy", "greedy-unmasked-90"}, {"clock", "one-old-seven-new-frozen-v4"}};
        if (job.first_goal) job.descriptor["round_end"] = "first-goal-or-timeout-v1";
        plan.jobs.push_back(std::move(job));
    }
    if (!contains_reference && !plan.jobs.empty())
        throw std::runtime_error("Each selection manifest must include protected reference games");
    return plan;
}

inline std::vector<Flat> observations(const World& world, bool frozen_clock_previous = false,
                                       const SlaterAttention::FrozenClock* learner_clock = nullptr) {
    SlaterAttention::PreviousActions previous;
    for (const auto& [id, action] : world.PreviousActions())
        for (int j = 0; j < 8; ++j) previous[id][j] = action[j];
    if (frozen_clock_previous)
        for (auto id : world.ReadyCars()) {
            auto action = world.PreviousForInference(id);
            for (int j = 0; j < 8; ++j) previous[id][j] = action[j];
        }
    if (learner_clock)
        for (int j = 0; j < 8; ++j) previous[world.LearnerId()][j] = learner_clock->action[j];
    return SlaterAttention::AttentionObs::BuildAll(world.State(), previous);
}
inline const Flat& view_for(const std::vector<Flat>& views, uint32_t id) {
    for (const auto& view : views) if (view.carId == id) return view;
    throw std::runtime_error("Car absent from selection observations");
}
inline torch::Tensor choices(torch::jit::Module& actor, const SlaterAttention::FlatBatch& batch,
                              torch::Device device) {
    if (!batch.Size()) throw std::runtime_error("Empty selection inference batch");
    auto n = static_cast<int64_t>(batch.Size());
    auto options = torch::TensorOptions().dtype(torch::kFloat32);
    auto q = torch::from_blob(const_cast<float*>(batch.q.data()), {n, 1, 32}, options).clone().to(device);
    auto kv = torch::from_blob(const_cast<float*>(batch.kv.data()), {n, 41, 24}, options).clone().to(device);
    auto mask = torch::from_blob(const_cast<float*>(batch.mask.data()), {n, 41}, options).clone().to(device);
    auto input = c10::ivalue::Tuple::create({q, kv, mask});
    auto output = actor.forward({input});
    if (!output.isTuple() || output.toTuple()->elements().empty() || !output.toTuple()->elements()[0].isTensor())
        throw std::runtime_error("Selection actor does not implement original attention output contract");
    auto logits = output.toTuple()->elements()[0].toTensor();
    slater_attention::finite(logits, "selection logits");
    if (logits.dim() != 2 || logits.size(0) != n || logits.size(1) != 90)
        throw std::runtime_error("Selection actor requires 90 original attention actions");
    return logits.argmax(-1).to(torch::kCPU, torch::kInt64).contiguous();
}
class ActorCache {
    const Plan& plan_; torch::Device device_;
    // Equal source digests share one immutable graph even under different IDs.
    std::map<std::string, torch::jit::Module> modules_;
public:
    ActorCache(const Plan& plan, torch::Device device) : plan_(plan), device_(device) {}
    torch::jit::Module& get(const std::string& id) {
        const auto& spec = plan_.actors.at(id);
        auto found = modules_.find(spec.sha);
        if (found != modules_.end()) return found->second;
        auto actor = slater_attention::load_attention(spec.path, device_);
        int64_t count = 0; size_t tensors = 0;
        for (auto parameter : actor.parameters()) { ++tensors; count += parameter.numel(); parameter.set_requires_grad(false); }
        if (tensors != 44 || count != 444032)
            throw std::runtime_error("Selection supports original attention actors, not flat native MLP checkpoints");
        actor.eval(); return modules_.emplace(spec.sha, std::move(actor)).first->second;
    }
    void retain(const std::set<std::string>& ids) {
        std::set<std::string> wanted;
        for (const auto& id : ids) wanted.insert(plan_.actors.at(id).sha);
        for (auto it = modules_.begin(); it != modules_.end();)
            if (!wanted.count(it->first)) it = modules_.erase(it); else ++it;
    }
    size_t size() const { return modules_.size(); }
};
struct ActiveGame {
    size_t job_index = 0;
    std::unique_ptr<World> world;
    SlaterAttention::FrozenClock learner_clock;
    uint64_t total_ticks = 0, episodes = 0, touch_ticks = 0, goalward_ticks = 0;
    uint64_t learner_script_ticks = 0, frozen_script_ticks = 0;
    uint64_t last_learner_script_ticks = 0, last_frozen_script_ticks = 0;
    int goals_for = 0, goals_against = 0;
    int early_goals_for = 0, early_goal_concessions = 0;
    bool ball_touched = false;
    explicit ActiveGame(const Job& job, size_t index) : job_index(index) {
        int blue_count = job.blue ? job.learner_count : job.rival_count;
        int orange_count = job.blue ? job.rival_count : job.learner_count;
        world = std::make_unique<World>(blue_count, orange_count,
            job.blue ? RocketSim::Team::BLUE : RocketSim::Team::ORANGE, double(job.ticks) / 120.0);
        world->Reset(job.seed);
    }
    void reset(const Job& job) {
        ++episodes;
        world->Reset(job.seed + 7919 * episodes);
        learner_clock = {}; ball_touched = false;
        last_learner_script_ticks = last_frozen_script_ticks = 0;
    }
};
struct PendingBatch {
    SlaterAttention::FlatBatch rows;
    std::vector<std::pair<size_t, uint32_t>> positions;
};
inline json record_for(const Plan& plan, const Job& job, const ActiveGame& game) {
    auto record = job.original;
    record.update({{"candidate_id", job.candidate}, {"model_id", job.candidate},
        {"rival_id", job.rival}, {"reference_id", job.teammate},
        {"is_reference", job.candidate == plan.reference_id}, {"team_policy", job.team_policy},
        {"goals_for", game.goals_for}, {"goals_against", game.goals_against},
        {"gf", game.goals_for}, {"ga", game.goals_against},
        {"goal_diff", game.goals_for - game.goals_against},
        {"early_goal_concessions", game.early_goal_concessions},
        {"early_goals_for", game.early_goals_for}, {"early_goal_window_seconds", 10},
        {"seconds", double(game.total_ticks) / 120.0}, {"physics_ticks", game.total_ticks},
        {"learner_touch_ticks", game.touch_ticks}, {"goalward_touch_ticks", game.goalward_ticks},
        {"learner_script_ticks", game.learner_script_ticks}, {"frozen_script_ticks", game.frozen_script_ticks},
        {"learner_scripted_kickoff", job.scripted}, {"frozen_scripted_kickoff", true},
        {"policy_sampling", false}, {"episodes", game.episodes + 1},
        {"scope", job.team_policy == "candidate_squad"
            ? "one learner plus frozen scripted candidate teammates"
            : "one learner plus fixed scripted reference teammates"},
        {"finish", "COMPLETE"}, {"game_complete", true}, {"descriptor", job.descriptor}});
    if (job.first_goal) record["round_end"] = game.goals_for + game.goals_against
        ? "FIRST_GOAL" : "NO_GOAL_TIMEOUT";
    return record;
}

// Calls RocketSim::Init itself. The supplied portable actor files are private
// copies validated and SHA-checked by Python before/after native invocation.
// A pause drains only already-active games, then exits. An abrupt interruption
// loses only unfinished games; every complete game is independently durable.
inline json run_batched_evaluation(const fs::path& manifest_path, const fs::path& meshes_path,
                                    const fs::path& out, torch::Device device,
                                    const fs::path& pause_file, int batch_worlds = 8,
                                    int sim_threads = 2) {
    if (batch_worlds < 1 || batch_worlds > 128 || sim_threads < 1 || sim_threads > 32)
        throw std::runtime_error("Invalid selection batching/thread limits");
    auto plan = parse_plan(manifest_path, out, device, batch_worlds);
    fs::create_directories(out); fs::create_directories(plan.cache_dir);
    const auto protocol_path = out / "native_protocol.json";
    json protocol = {{"manifest", read_json(manifest_path)}, {"device", device.str()},
                     {"batch_worlds", batch_worlds}, {"backend_sha", ATTENTION_SOURCE_SHA}};
    if (fs::exists(protocol_path) && read_json(protocol_path) != protocol)
        throw std::runtime_error("Existing native evaluation folder has a different manifest/configuration");
    if (!fs::exists(protocol_path)) write_json(protocol_path, protocol);
    std::vector<json> records(plan.jobs.size());
    std::vector<size_t> pending;
    size_t cached = 0;
    for (size_t index = 0; index < plan.jobs.size(); ++index) {
        const auto& job = plan.jobs[index]; const auto path = plan.cache_dir / (job.id + ".json");
        if (!fs::exists(path)) { pending.push_back(index); continue; }
        auto record = read_json(path);
        if (!record.value("game_complete", false) || record.value("finish", "") != "COMPLETE" ||
            !record.contains("descriptor") || record.at("descriptor") != job.descriptor)
            throw std::runtime_error("Selection cache descriptor mismatch: " + path.string());
        // Same-weight policies may have different display IDs in another stage.
        record.update({{"id", job.id}, {"candidate_id", job.candidate}, {"model_id", job.candidate},
                       {"rival_id", job.rival}, {"reference_id", job.teammate},
                       {"is_reference", job.candidate == plan.reference_id}, {"team_policy", job.team_policy}});
        records[index] = std::move(record); ++cached;
    }
    auto start = Clock::now();
    RocketSim::Init(meshes_path, true);
    RLGC::DefaultAction table;
    if (table.actions.size() != 90) throw std::runtime_error("Original 90-action ordering changed");
    ActorCache actors(plan, device);
    std::unique_ptr<dp::thread_pool<>> pool;
    if (sim_threads > 1) pool = std::make_unique<dp::thread_pool<>>(sim_threads);
    std::vector<std::unique_ptr<ActiveGame>> active(batch_worlds);
    size_t next = 0, completed = cached, max_loaded = 0;
    uint64_t inference_rows = 0, simulation_ticks = 0;
    bool stopping = !pause_file.empty() && fs::exists(pause_file);
    auto fill = [&] {
        if (!pause_file.empty() && fs::exists(pause_file)) stopping = true;
        if (stopping) return;
        for (auto& slot : active) if (!slot && next < pending.size()) {
            auto index = pending[next++]; slot = std::make_unique<ActiveGame>(plan.jobs[index], index);
        }
    };
    torch::NoGradGuard no_grad;
    torch::jit::setGraphExecutorOptimize(false);
    fill();
    while (true) {
        if (!pause_file.empty() && fs::exists(pause_file)) stopping = true;
        bool any_active = false;
        std::set<std::string> wanted;
        for (const auto& slot : active) if (slot) {
            any_active = true; const auto& job = plan.jobs[slot->job_index];
            wanted.insert(job.candidate); wanted.insert(job.rival); wanted.insert(job.teammate);
        }
        if (!any_active) break;
        actors.retain(wanted);
        // Begin all learner actions that ended the previous eight physics packets.
        std::map<std::string, PendingBatch> learner_batches;
        for (size_t i = 0; i < active.size(); ++i) if (active[i]) {
            auto& slot = *active[i]; auto& world = *slot.world;
            if (!world.StepComplete()) continue;
            const auto& job = plan.jobs[slot.job_index];
            if (job.scripted) { world.BeginAction(SlaterAttention::ZeroAction()); continue; }
            auto views = observations(world); auto& batch = learner_batches[job.candidate];
            batch.rows.Append(view_for(views, world.LearnerId()));
            batch.positions.emplace_back(i, world.LearnerId());
        }
        for (auto& [id, batch] : learner_batches) {
            auto indices = choices(actors.get(id), batch.rows, device); auto values = indices.data_ptr<int64_t>();
            for (size_t j = 0; j < batch.positions.size(); ++j)
                active[batch.positions[j].first]->world->BeginAction(table.actions.at(values[j]));
            inference_rows += batch.rows.Size();
        }
        // Ready frozen cars (and optional script-enabled learner) are pooled by
        // immutable policy across all arenas, regardless of candidate family.
        std::map<std::string, PendingBatch> frozen_batches;
        for (size_t i = 0; i < active.size(); ++i) if (active[i]) {
            auto& slot = *active[i]; auto& world = *slot.world;
            const auto& job = plan.jobs[slot.job_index];
            auto ready = world.ReadyCars();
            bool learner_ready = job.scripted && slot.learner_clock.updateAction;
            if (ready.empty() && !learner_ready) continue;
            auto views = observations(world, true, learner_ready ? &slot.learner_clock : nullptr);
            const auto& allies = job.blue ? world.BlueIds() : world.OrangeIds();
            for (auto id : ready) {
                bool own_team = std::find(allies.begin(), allies.end(), id) != allies.end();
                auto& batch = frozen_batches[own_team ? job.teammate : job.rival];
                batch.rows.Append(view_for(views, id)); batch.positions.emplace_back(i, id);
            }
            if (learner_ready) {
                auto& batch = frozen_batches[job.candidate];
                batch.rows.Append(view_for(views, world.LearnerId()));
                batch.positions.emplace_back(i, world.LearnerId());
            }
        }
        std::vector<std::map<uint32_t, Action>> predictions(active.size());
        for (auto& [id, batch] : frozen_batches) {
            auto indices = choices(actors.get(id), batch.rows, device); auto values = indices.data_ptr<int64_t>();
            for (size_t j = 0; j < batch.positions.size(); ++j) {
                auto [i, car_id] = batch.positions[j]; predictions[i][car_id] = table.actions.at(values[j]);
            }
            inference_rows += batch.rows.Size();
        }
        max_loaded = std::max(max_loaded, actors.size());
        std::vector<std::future<void>> futures;
        auto tick = [&](size_t i) {
            auto& slot = *active[i]; auto& world = *slot.world;
            const auto& job = plan.jobs[slot.job_index];
            if (job.scripted) {
                auto found = predictions[i].find(world.LearnerId());
                auto neural = found == predictions[i].end() ? nullptr : &found->second;
                bool kickoff = !slot.ball_touched && world.EpisodeTicks() < 168 &&
                    world.State().ball.pos.Length2D() < 1 && world.State().ball.pos.z < 100;
                world.SetLearnerPacketAction(slot.learner_clock.Frame(world.State(), world.LearnerId(), kickoff, neural));
                predictions[i].erase(world.LearnerId());
            }
            auto old_touches = world.StepInfo().learnerTouchTicks;
            auto old_goalward = world.StepInfo().goalwardTouchTicks;
            world.Tick(predictions[i]); ++slot.total_ticks;
            slot.touch_ticks += world.StepInfo().learnerTouchTicks - old_touches;
            slot.goalward_ticks += world.StepInfo().goalwardTouchTicks - old_goalward;
            // FrozenClock counts persist across steps but restart after goals.
            auto script_ticks = world.StepInfo().scriptPhysicsTicks;
            slot.frozen_script_ticks += script_ticks - slot.last_frozen_script_ticks;
            slot.last_frozen_script_ticks = script_ticks;
            for (const auto& player : world.State().players) slot.ball_touched |= player.ballTouchedStep;
            slot.learner_script_ticks += slot.learner_clock.scriptTicks - slot.last_learner_script_ticks;
            slot.last_learner_script_ticks = slot.learner_clock.scriptTicks;
        };
        for (size_t i = 0; i < active.size(); ++i) if (active[i]) {
            if (pool) futures.push_back(pool->enqueue([&, i] { tick(i); })); else tick(i);
            ++simulation_ticks;
        }
        for (auto& future : futures) future.get();
        for (auto& slot : active) if (slot) {
            const auto& job = plan.jobs[slot->job_index];
            if (slot->world->Done()) {
                slot->goals_for += slot->world->StepInfo().outcome == 1;
                slot->goals_against += slot->world->StepInfo().outcome == -1;
                if (slot->world->EpisodeTicks() <= 1200) {
                    slot->early_goals_for += slot->world->StepInfo().outcome == 1;
                    slot->early_goal_concessions += slot->world->StepInfo().outcome == -1;
                }
                if (slot->total_ticks < job.ticks && !job.first_goal) slot->reset(job);
            }
            if (slot->total_ticks < job.ticks &&
                !(job.first_goal && slot->goals_for + slot->goals_against > 0)) continue;
            auto record = record_for(plan, job, *slot);
            const auto path = plan.cache_dir / (job.id + ".json");
            if (fs::exists(path)) throw std::runtime_error("Evaluation cache appeared during run; concurrent writer refused");
            write_json(path, record); records[slot->job_index] = record; ++completed;
            json console = {{"id", job.id}, {"candidate_id", job.candidate}, {"rival_id", job.rival},
                {"format", job.original.at("format")}, {"learner_team", job.blue ? "blue" : "orange"},
                {"team_policy", job.team_policy}, {"gf", slot->goals_for}, {"ga", slot->goals_against},
                {"seconds", double(slot->total_ticks) / 120.0}, {"cached", cached}};
            std::cout << "SLATER_SELECTION_GAME " << completed << "/" << plan.jobs.size()
                      << " " << console.dump() << std::endl;
            write_json(out / "progress.json", {{"completed", completed}, {"planned", plan.jobs.size()},
                {"cached", cached}, {"last_game", job.id}, {"status", stopping ? "PAUSING" : "RUNNING"}});
            slot.reset();
        }
        fill();
    }
    json rows = json::array();
    for (const auto& record : records) if (!record.is_null()) rows.push_back(record);
    double elapsed = std::chrono::duration<double>(Clock::now() - start).count();
    std::set<std::string> team_policies;
    for (const auto& job : plan.jobs) team_policies.insert(job.team_policy);
    json result = {{"schema", 1}, {"status", completed == plan.jobs.size() ? "FINITE_EVALUATION_COMPLETE" : "PAUSED"},
        {"completed", completed}, {"planned", plan.jobs.size()}, {"cached", cached},
        {"wall_seconds", elapsed}, {"inference_rows", inference_rows},
        {"physics_ticks", simulation_ticks}, {"max_loaded_actors", max_loaded},
        {"batch_worlds", batch_worlds}, {"device", device.str()},
        {"protocol_sha", plan.protocol_sha}, {"backend_sha", ATTENTION_SOURCE_SHA},
        {"cache_dir", plan.cache_dir.string()}, {"records", rows}, {"team_policies", team_policies},
        {"promoted", false}, {"confirmed", false},
        {"scope", "one learner slot; fixed-reference or candidate-squad teammates as configured; all frozen players scripted; greedy inference"}};
    write_json(out / "evaluation.json", result); write_json(out / "progress.json", result);
    return result;
}
} // namespace slater_attention_eval
