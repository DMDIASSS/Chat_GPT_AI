#include "AttentionObs.h"
#include "AttentionWorld.h"
#include "AttentionPPO.h"
#include "AttentionEval.h"
#include "AttentionCurriculum.h"
#include "AttentionTasks.h"
#include <RLGymCPP/ActionParsers/DefaultAction.h>
#include <ATen/Parallel.h>
#include <torch/cuda.h>
#include <thread_pool.h>
#include <nlohmann/json.hpp>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <future>
#include <iomanip>
#include <iostream>
#include <map>
#include <memory>
#include <sstream>

using json=nlohmann::json;
using World=SlaterAttention::AttentionWorld;
using Flat=SlaterAttention::FlatObservation;
using Action=SlaterAttention::Action;
using Engine=slater_attention::Engine;
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;

double seconds(Clock::time_point start){return std::chrono::duration<double>(Clock::now()-start).count();}
std::string read(const fs::path& path){std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("Cannot read "+path.string());return {std::istreambuf_iterator<char>(f),{}};}
void atomic_json(const fs::path& path,const json& value){fs::create_directories(path.parent_path());auto temp=path;temp+=".writing";{std::ofstream f(temp,std::ios::binary);f<<value.dump(2);f.close();if(!f)throw std::runtime_error("Cannot write report");}if(fs::exists(path))fs::remove(path);fs::rename(temp,path);}
std::string numbered(uint64_t number){std::ostringstream s;s<<"checkpoint_"<<std::setw(6)<<std::setfill('0')<<number;return s.str();}

struct Options{
 std::string mode="train",actor,teacher,rival,meshes,out,protocol,pause,resume,fixture,kickoffs,device="cpu",eval_manifest,curriculum="none",routine="match",formats="1v1",opponent_pool;
 int games=8,steps=128,updates=100,seed=20261013,eval_seeds=2,threads=1,sim_threads=2,eval_worlds=8,start_stage=0,selfplay_refresh=0;
 bool learner_scripted_kickoff=false;
 double actor_lr=3e-6,critic_lr=1e-4,target_kl=.005,teacher_weight=.1,duration=12,practice_fraction=.5,practice_anchor=.025,curriculum_difficulty=.1;
};
Options options(int argc,char** argv){Options o;for(int i=1;i<argc;++i){std::string key=argv[i];if(i+1==argc)throw std::runtime_error("Missing value for "+key);std::string v=argv[++i];
 if(key=="--mode")o.mode=v;else if(key=="--actor")o.actor=v;else if(key=="--teacher")o.teacher=v;else if(key=="--rival")o.rival=v;
 else if(key=="--meshes")o.meshes=v;else if(key=="--out")o.out=v;else if(key=="--protocol")o.protocol=v;else if(key=="--pause")o.pause=v;
 else if(key=="--kickoffs")o.kickoffs=v;else if(key=="--resume")o.resume=v;else if(key=="--fixture")o.fixture=v;else if(key=="--device")o.device=v;
 else if(key=="--eval-manifest")o.eval_manifest=v;else if(key=="--eval-worlds")o.eval_worlds=std::stoi(v);
 else if(key=="--curriculum")o.curriculum=v;else if(key=="--start-stage")o.start_stage=std::stoi(v);
 else if(key=="--practice-fraction")o.practice_fraction=std::stod(v);else if(key=="--practice-anchor")o.practice_anchor=std::stod(v);
 else if(key=="--curriculum-difficulty")o.curriculum_difficulty=std::stod(v);
 else if(key=="--routine")o.routine=v;else if(key=="--formats")o.formats=v;else if(key=="--opponent-pool")o.opponent_pool=v;else if(key=="--selfplay-refresh")o.selfplay_refresh=std::stoi(v);
 else if(key=="--learner-scripted-kickoff"){if(v!="0"&&v!="1")throw std::runtime_error("Learner kickoff flag requires 0 or 1");o.learner_scripted_kickoff=v=="1";}
 else if(key=="--games")o.games=std::stoi(v);else if(key=="--steps")o.steps=std::stoi(v);else if(key=="--updates")o.updates=std::stoi(v);
 else if(key=="--seed")o.seed=std::stoi(v);else if(key=="--eval-seeds")o.eval_seeds=std::stoi(v);else if(key=="--threads")o.threads=std::stoi(v);
 else if(key=="--sim-threads")o.sim_threads=std::stoi(v);else if(key=="--seconds")o.duration=std::stod(v);
 else if(key=="--actor-lr")o.actor_lr=std::stod(v);else if(key=="--critic-lr")o.critic_lr=std::stod(v);
 else if(key=="--target-kl")o.target_kl=std::stod(v);else if(key=="--teacher-weight")o.teacher_weight=std::stod(v);
 else throw std::runtime_error("Unknown option "+key);
 }
 bool selection=o.mode=="selector-eval";
 if((!selection&&(o.actor.empty()||o.teacher.empty()||o.rival.empty()||o.protocol.empty()))||(selection&&o.eval_manifest.empty())||o.out.empty()||o.games<1||o.games>128||o.steps<16||o.steps>4096||o.updates<0||o.updates>100000||o.duration<.1||o.duration>3600||o.eval_seeds<1||o.eval_seeds>64||o.threads<1||o.threads>32||o.sim_threads<1||o.sim_threads>32||o.eval_worlds<1||o.eval_worlds>128)throw std::runtime_error("Invalid attention inputs/profile");
 if((o.curriculum!="none"&&o.curriculum!="wall-reset")||o.start_stage<0||o.start_stage>5||!std::isfinite(o.practice_fraction)||o.practice_fraction<.25||o.practice_fraction>.75||!std::isfinite(o.practice_anchor)||o.practice_anchor<0||o.practice_anchor>1||!std::isfinite(o.curriculum_difficulty)||o.curriculum_difficulty<0||o.curriculum_difficulty>1)throw std::runtime_error("Invalid curriculum profile");
 if(o.curriculum=="wall-reset"&&o.routine=="match")o.routine="wall-reset";
 if(o.routine=="air-control"){o.curriculum="wall-reset";o.start_stage=std::max(2,o.start_stage);}
 if(o.routine=="wall-reset")o.curriculum="wall-reset";
 if(o.routine!="wall-reset"&&o.routine!="air-control")SlaterAttention::ParsePracticeRoutine(o.routine);
 if(o.selfplay_refresh<0||o.selfplay_refresh>10000||(o.routine!="match"&&o.games<2))throw std::runtime_error("Invalid self-play/practice world allocation");
 return o;
}
struct Inputs{torch::Tensor q,kv,mask;};
Inputs tensor_inputs(const SlaterAttention::FlatBatch& b,torch::Device device){
 if(!b.Size())throw std::runtime_error("Empty observation batch");auto n=static_cast<int64_t>(b.Size());auto opt=torch::TensorOptions().dtype(torch::kFloat32);
 return {torch::from_blob(const_cast<float*>(b.q.data()),{n,1,32},opt).clone().to(device),torch::from_blob(const_cast<float*>(b.kv.data()),{n,41,24},opt).clone().to(device),torch::from_blob(const_cast<float*>(b.mask.data()),{n,41},opt).clone().to(device)};
}
std::vector<Flat> observe(World& world,bool clock_previous=false){SlaterAttention::PreviousActions previous;
 for(const auto& [id,a]:world.PreviousActions()){SlaterAttention::Controls c{};for(int j=0;j<8;++j)c[j]=a[j];previous[id]=c;}
 if(clock_previous)for(auto id:world.ReadyCars()){auto a=world.PreviousForInference(id);for(int j=0;j<8;++j)previous[id][j]=a[j];}
 return SlaterAttention::AttentionObs::BuildAll(world.State(),previous);
}
const Flat& car_view(const std::vector<Flat>& views,uint32_t id){for(const auto& v:views)if(v.carId==id)return v;throw std::runtime_error("Missing car observation");}
torch::Tensor policy(torch::jit::Module& module,const Inputs& in){auto tuple=c10::ivalue::Tuple::create({in.q,in.kv,in.mask});auto l=module.forward({tuple}).toTuple()->elements()[0].toTensor();slater_attention::finite(l,"policy logits");return l;}

// Batches every ready frozen car across arenas. Each car retains its own
// source-matched clock; no frozen-policy experience enters the learner buffer.
struct Rollout{
 std::vector<std::unique_ptr<World>> worlds;
 std::vector<uint64_t> episode_seeds;
 std::vector<std::string> rival_keys,teammate_keys;
 std::vector<int> practice_sides;
 std::vector<Action> actions;
 std::vector<std::unique_ptr<SlaterAttention::CurriculumTracker>> trackers;
 std::vector<std::unique_ptr<SlaterAttention::TaskTracker>> task_trackers;
 std::vector<double> practice_rewards;
 std::vector<std::pair<int,int>> formats;
 std::map<uint64_t,std::array<int,5>> kickoff_orders;
 std::map<std::string,torch::jit::Module> frozen;
 std::map<std::string,std::string> snapshot_paths;
 std::vector<std::string> recent_snapshots,external_keys;
 std::map<std::string,std::vector<std::string>> format_opponents;
 std::vector<int> learner_kickoff_index;
 std::vector<uint8_t> step_scripted,packet_scripted,ball_touched;
 uint64_t learner_script_ticks=0,excluded_script_rows=0;
 std::unique_ptr<dp::thread_pool<>> pool;
 torch::Device device;
 Options config;
 SlaterAttention::PracticeRoutine task_routine=SlaterAttention::PracticeRoutine::Match;
 bool curriculum=false,practice=false,rotate_roles=false;
 int target_stage=0,normal_worlds=0;
 double difficulty=.1,practice_anchor=.025,match_anchor=.1;
 json recent=json::array(),advances=json::array();
 uint64_t physics_ticks=0,script_ticks=0,inference_rows=0,goals_for=0,goals_against=0,timeouts=0;
 uint64_t match_goals_for=0,match_goals_against=0,practice_episodes=0,practice_successes=0;
 void load_frozen(const std::string& id,const std::string& path){
  if(frozen.contains(id))return;
  auto module=slater_attention::load_attention(path,device);module.eval();for(auto p:module.parameters())p.set_requires_grad(false);
  frozen.emplace(id,std::move(module));
 }
 Rollout(const Options& o,torch::Device d):device(d),config(o){
  curriculum=o.curriculum=="wall-reset";practice=o.routine!="match";target_stage=o.start_stage;difficulty=o.curriculum_difficulty;
  if(!curriculum)task_routine=SlaterAttention::ParsePracticeRoutine(o.routine);
  practice_anchor=o.practice_anchor;match_anchor=o.teacher_weight;
  normal_worlds=practice?std::clamp(int(std::ceil(o.games*(1-o.practice_fraction))),1,o.games-1):o.games;
  std::istringstream stream(o.formats);std::string token;
  while(std::getline(stream,token,',')){
   if(token.size()!=3||token[1]!='v'||token[0]<'1'||token[0]>'3'||token[2]<'1'||token[2]>'3')throw std::runtime_error("Formats require comma-separated 1v1..3v3 rosters");
   auto f=std::pair{token[0]-'0',token[2]-'0'};if(std::find(formats.begin(),formats.end(),f)==formats.end())formats.push_back(f);
  }
  if(formats.empty())throw std::runtime_error("Empty training formats");
  rotate_roles=practice||formats.size()>1||formats[0]!=std::pair{1,1}||o.selfplay_refresh>0;
  load_frozen("source",o.teacher);load_frozen("nexto",o.rival);
  if(!o.opponent_pool.empty()){
   // Keep the parsed document alive throughout iteration (C++20 does not
   // extend a temporary's lifetime through json::at's returned reference).
   auto document=json::parse(read(o.opponent_pool));
   for(const auto& row:document.at("actors")){
    auto id=row.at("id").get<std::string>();if(id=="source"||id=="nexto"||id.rfind("snapshot_",0)==0||frozen.contains(id))throw std::runtime_error("Reserved or duplicate self-play actor ID");
    load_frozen(id,row.at("path").get<std::string>());external_keys.push_back(id);
   }
   if(document.contains("rivals_by_format"))for(auto it=document.at("rivals_by_format").begin();it!=document.at("rivals_by_format").end();++it){
    auto ids=it.value().get<std::vector<std::string>>();if(ids.empty())throw std::runtime_error("Empty per-format opponents");
    for(const auto& id:ids)if(!frozen.contains(id))throw std::runtime_error("Unknown per-format opponent: "+id);
    format_opponents[it.key()]=ids;
   }
   if(!format_opponents.empty())for(auto [ours,theirs]:formats)
    if(!format_opponents.contains(std::to_string(ours)+"v"+std::to_string(theirs)))throw std::runtime_error("Missing per-format training opponents");
  }
  trackers.resize(o.games);task_trackers.resize(o.games);practice_rewards.resize(o.games);practice_sides.resize(o.games);
  rival_keys.resize(o.games);teammate_keys.resize(o.games);
  learner_kickoff_index.resize(o.games,-1);step_scripted.resize(o.games);packet_scripted.resize(o.games);ball_touched.resize(o.games);
  if(!o.kickoffs.empty()){if(practice||rotate_roles)throw std::runtime_error("Benchmark starts require original 1v1 match profile");auto data=json::parse(read(o.kickoffs));for(const auto& row:data.at("orders"))kickoff_orders[row.at("seed").get<uint64_t>()]=row.at("permutation").get<std::array<int,5>>();}
  RLGC::DefaultAction table;actions=table.actions;if(actions.size()!=90)throw std::runtime_error("Action ordering/count changed");
  if(o.sim_threads>1)pool=std::make_unique<dp::thread_pool<>>(o.sim_threads);
  worlds.resize(o.games);
  for(int i=0;i<o.games;++i){episode_seeds.push_back(uint64_t(o.seed)+7919*i);reset_seed(i,episode_seeds.back());}
 }
 bool is_practice(size_t i)const{return practice&&int(i)>=normal_worlds;}
 void assign_policies(size_t i,uint64_t seed,int ours,int theirs){
  std::vector<std::string> opponents;
  if(format_opponents.empty()){opponents={"nexto","source"};opponents.insert(opponents.end(),external_keys.begin(),external_keys.end());}
  else opponents=format_opponents.at(std::to_string(ours)+"v"+std::to_string(theirs));
  opponents.insert(opponents.end(),recent_snapshots.begin(),recent_snapshots.end());
  rival_keys[i]=rotate_roles||opponents.size()>2?opponents[(seed/2+i)%opponents.size()]:((i/2)%2==0?"nexto":"source");
  teammate_keys[i]=recent_snapshots.empty()?"source":recent_snapshots[(seed/7+i)%recent_snapshots.size()];
 }
 void reset_seed(size_t i,uint64_t seed){
  const auto episode=seed-(uint64_t(config.seed)+7919*i);
  const auto visit=(i+episode)/formats.size();
  auto [ours,theirs]=formats[(i+episode)%formats.size()];
  if(curriculum&&is_practice(i))ours=theirs=1;
  const bool blueTurn=curriculum&&is_practice(i)?((episode+i)%2==0):((visit+i)%2==0);
  auto team=(rotate_roles?blueTurn:(i%2==0))?RocketSim::Team::BLUE:RocketSim::Team::ORANGE;
  int blue=team==RocketSim::Team::BLUE?ours:theirs,orange=team==RocketSim::Team::BLUE?theirs:ours;
  if(!worlds[i]||int(worlds[i]->BlueIds().size())!=blue||int(worlds[i]->OrangeIds().size())!=orange)worlds[i]=std::make_unique<World>(blue,orange,team,config.duration);
  size_t slot=is_practice(i)?0:size_t((visit/2+i)%ours);
  worlds[i]->SelectLearner(team,slot);trackers[i].reset();task_trackers[i].reset();practice_rewards[i]=0;
  assign_policies(i,seed,ours,theirs);
  learner_kickoff_index[i]=-1;ball_touched[i]=false;
  if(curriculum&&is_practice(i)){
   int start=target_stage;auto choice=seed%4;if(choice==0)start=0;else if(choice==1)start=std::max(0,target_stage-1);
   float level=float(std::min(1.,difficulty+.05*target_stage));
   auto state=SlaterAttention::CreatePracticeStart(seed,level,SlaterAttention::CurriculumStage(start),team);
   worlds[i]->ResetFromStates(state.ball,state.cars,state.cooldowns);
   trackers[i]=std::make_unique<SlaterAttention::CurriculumTracker>(SlaterAttention::CurriculumStage(target_stage),level,SlaterAttention::CurriculumStage(start));practice_sides[i]=state.wallSide;
  }else if(is_practice(i)){
   auto state=SlaterAttention::CreateTaskStart(seed,difficulty,task_routine,ours,theirs,team);
   worlds[i]->ResetFromStates(state.ball,state.cars,state.boostCooldowns);
   task_trackers[i]=std::make_unique<SlaterAttention::TaskTracker>(task_routine,difficulty);
  }else if(kickoff_orders.empty())worlds[i]->Reset(seed);
  else{auto it=kickoff_orders.find(seed);if(it==kickoff_orders.end())throw std::runtime_error("Benchmark kickoff sequence exhausted");worlds[i]->Reset(seed,&it->second);}
 }
 int task_for(size_t i)const{
  if(trackers[i])return 1+int(trackers[i]->summary().targetStage);
  if(!task_trackers[i])return 0;
  switch(task_routine){case SlaterAttention::PracticeRoutine::Defense:return 7;case SlaterAttention::PracticeRoutine::Recovery:return 8;case SlaterAttention::PracticeRoutine::Boost:return 9;case SlaterAttention::PracticeRoutine::Bump:return 10;case SlaterAttention::PracticeRoutine::BumpEvasion:return 11;default:return 0;}
 }
 torch::Tensor tasks()const{std::vector<int64_t> ids;for(size_t i=0;i<worlds.size();++i)ids.push_back(task_for(i));return torch::tensor(ids,torch::kInt64).to(device);}
 double anchor_for(size_t i)const{return is_practice(i)?practice_anchor:match_anchor;}
 double reward_for(size_t i)const{return trackers[i]?practice_rewards[i]:worlds[i]->Reward()+practice_rewards[i];}
 double episode_reward(size_t i)const{return trackers[i]?trackers[i]->summary().reward:worlds[i]->EpisodeReward()+(task_trackers[i]?task_trackers[i]->Summary().reward:0);}
 json drill_summary(size_t i)const{
  if(task_trackers[i]){const auto& s=task_trackers[i]->Summary();return {{"routine",config.routine},{"reward",s.reward},{"ticks",s.ticks},{"useful_pickups",s.usefulPickups},{"shared_pickups",s.sharedPickups},{"controlled_clears",s.controlledClears},{"recoveries",s.recoveries},{"useful_bumps",s.usefulBumps},{"evasions",s.evasions},{"demos",s.demos},{"success",s.succeeded}};}
  if(!trackers[i])return nullptr;const auto& s=trackers[i]->summary();
  return {{"start_stage",int(s.initialStage)},{"target_stage",int(s.targetStage)},{"target",SlaterAttention::CurriculumStageName(s.targetStage)},
   {"highest_unlocked",s.highestUnlocked},{"resets_acquired",s.resetsAcquired},{"resets_used",s.resetsUsed},{"earned_events",s.earnedEvents},
   {"seconds",s.seconds},{"controlled_air_seconds",s.controlledAirSeconds},{"best_carry_seconds",s.bestCarrySeconds},
   {"wall_rise",s.wallRise},{"carry_progress",s.carryProgress},{"reward",s.reward},{"scored",s.scored},{"conceded",s.conceded},
   {"success",s.success},{"expired",s.expired},{"full_chain",s.fullChain},{"reverse_initialized",s.reverseInitialized},{"wall_side",practice_sides[i]}};
 }
 void record_episode(size_t i){
  const auto& info=worlds[i]->StepInfo();
  if(task_trackers[i]){++practice_episodes;practice_successes+=task_trackers[i]->Summary().succeeded&&info.outcome!=-1;return;}
  if(!trackers[i]){match_goals_for+=info.outcome==1;match_goals_against+=info.outcome==-1;return;}
  ++practice_episodes;const auto& s=trackers[i]->summary();bool safe_success=s.success&&!s.conceded;practice_successes+=safe_success;
  if(int(s.targetStage)==target_stage){recent.push_back({{"success",safe_success},{"full_start",s.initialStage==SlaterAttention::CurriculumStage::WallRoll},
   {"full_chain",s.fullChain},{"blue",worlds[i]->LearnerSign()>0},{"wall_side",practice_sides[i]}});if(recent.size()>60)recent.erase(recent.begin());}
 }
 void maybe_advance(){
  if(!curriculum||target_stage>=5||recent.size()<40)return;
  int success=0,full=0,full_success=0,blue=0,orange=0,left=0,right=0,blue_ok=0,orange_ok=0,left_ok=0,right_ok=0;
  for(const auto& row:recent){bool ok=row.at("success");success+=ok;bool prefix=row.at("full_start");full+=prefix;full_success+=prefix&&ok;
   bool side=row.at("blue");bool wall_left=row.at("wall_side").get<int>()<0;blue+=side;orange+=!side;left+=wall_left;right+=!wall_left;
   blue_ok+=side&&ok;orange_ok+=!side&&ok;left_ok+=wall_left&&ok;right_ok+=!wall_left&&ok;}
  if(success<.7*recent.size()||full<8||full_success<.5*full||std::min(blue,orange)<8||std::min(left,right)<8||blue_ok<.5*blue||orange_ok<.5*orange||left_ok<.5*left||right_ok<.5*right)return;
  advances.push_back({{"from",target_stage},{"to",target_stage+1},{"episodes",recent.size()},{"successes",success},{"full_start_successes",full_success},
   {"note","Practice progression only; independent match strength and full-chain mastery unconfirmed."}});
  ++target_stage;recent=json::array();std::cout<<"SLATER_CURRICULUM_ADVANCE "<<advances.back().dump()<<std::endl;
 }

 json progress()const{return {{"enabled",curriculum},{"routine",config.routine},{"formats",config.formats},{"target_stage",target_stage},{"target",SlaterAttention::CurriculumStageName(SlaterAttention::CurriculumStage(target_stage))},
  {"normal_worlds",normal_worlds},{"practice_worlds",int(worlds.size())-normal_worlds},{"recent",recent},{"advances",advances},
  {"practice_episodes",practice_episodes},{"practice_successes",practice_successes},{"match_goals_for",match_goals_for},{"match_goals_against",match_goals_against}};}
 void restore_progress(const json& saved){if(saved.is_null())return;if(saved.value("enabled",false)!=curriculum||saved.value("routine",config.routine)!=config.routine)throw std::runtime_error("Resume curriculum changed");
  target_stage=saved.at("target_stage");if(target_stage<0||target_stage>5)throw std::runtime_error("Invalid saved curriculum stage");recent=saved.at("recent");advances=saved.at("advances");
  practice_episodes=saved.value("practice_episodes",uint64_t(0));practice_successes=saved.value("practice_successes",uint64_t(0));match_goals_for=saved.value("match_goals_for",uint64_t(0));match_goals_against=saved.value("match_goals_against",uint64_t(0));}
 json selfplay_progress()const{
  json assigned=json::array();for(size_t i=0;i<worlds.size();++i){auto& w=*worlds[i];int ours=w.LearnerSign()>0?w.BlueIds().size():w.OrangeIds().size();int theirs=w.LearnerSign()>0?w.OrangeIds().size():w.BlueIds().size();assigned.push_back({{"world",i},{"format",std::to_string(ours)+"v"+std::to_string(theirs)},{"rival",rival_keys[i]},{"teammate",teammate_keys[i]}});}
  return {{"assigned_opponents",assigned},{"refresh_updates",config.selfplay_refresh},{"recent",recent_snapshots},{"snapshot_paths",snapshot_paths},{"external",external_keys},{"rivals_by_format",format_opponents},{"frozen_actors",frozen.size()},{"learner_experience_only",true},{"teacher_remains_initial_source",true},{"learner_scripted_kickoff",config.learner_scripted_kickoff},{"learner_script_ticks",learner_script_ticks},{"excluded_script_rows",excluded_script_rows}};}
 void plan_snapshot(uint64_t update,const fs::path& checkpoint){
  if(config.selfplay_refresh==0||update==0||update%config.selfplay_refresh)return;
  auto id="snapshot_"+std::to_string(update);snapshot_paths[id]=(checkpoint/"actor.pt").string();recent_snapshots.push_back(id);if(recent_snapshots.size()>3)recent_snapshots.erase(recent_snapshots.begin());
 }
 void refresh_snapshots(){
  std::set<std::string> keep(recent_snapshots.begin(),recent_snapshots.end());for(const auto& id:rival_keys)keep.insert(id);for(const auto& id:teammate_keys)keep.insert(id);
  for(auto it=snapshot_paths.begin();it!=snapshot_paths.end();){if(!keep.contains(it->first)){frozen.erase(it->first);it=snapshot_paths.erase(it);}else{auto folder=fs::path(it->second).parent_path();if(!fs::is_regular_file(folder/"COMPLETE")&&!fs::is_regular_file(folder/"COMPLETE.json"))throw std::runtime_error("Self-play snapshot is incomplete");load_frozen(it->first,it->second);++it;}}
 }
 void restore_selfplay(const json& state){if(state.is_null())return;if(state.at("refresh_updates").get<int>()!=config.selfplay_refresh)throw std::runtime_error("Self-play refresh changed");recent_snapshots=state.at("recent").get<std::vector<std::string>>();snapshot_paths=state.at("snapshot_paths").get<std::map<std::string,std::string>>();refresh_snapshots();}
 Inputs learners(){SlaterAttention::FlatBatch b;b.Reserve(worlds.size());for(auto& world:worlds){auto v=observe(*world);b.Append(car_view(v,world->LearnerId()));}return tensor_inputs(b,device);}
 void begin(const torch::Tensor& choices){auto cpu=choices.to(torch::kCPU,torch::kInt64).contiguous();auto p=cpu.data_ptr<int64_t>();for(size_t i=0;i<worlds.size();++i){practice_rewards[i]=0;step_scripted[i]=false;worlds[i]->BeginAction(actions.at(p[i]));}}
 void packet(){
  std::fill(packet_scripted.begin(),packet_scripted.end(),0);
  std::map<std::string,SlaterAttention::FlatBatch> batches;
  std::map<std::string,std::vector<std::pair<size_t,uint32_t>>> positions;
  for(size_t i=0;i<worlds.size();++i){if(worlds[i]->StepComplete())continue;auto ready=worlds[i]->ReadyCars();if(ready.empty())continue;auto views=observe(*worlds[i],true);
   const auto ownTeam=worlds[i]->LearnerSign()>0?RocketSim::Team::BLUE:RocketSim::Team::ORANGE;
   for(auto id:ready){auto key=worlds[i]->Arena()->GetCar(id)->team==ownTeam?teammate_keys[i]:rival_keys[i];batches[key].Append(car_view(views,id));positions[key].emplace_back(i,id);}}
  std::vector<std::map<uint32_t,Action>> predictions(worlds.size());
  {torch::NoGradGuard guard;for(auto& [key,batch]:batches){auto input=tensor_inputs(batch,device);auto indices=policy(frozen.at(key),input).argmax(-1).to(torch::kCPU).contiguous();auto p=indices.data_ptr<int64_t>();for(size_t j=0;j<positions[key].size();++j){auto [i,id]=positions[key][j];predictions[i][id]=actions.at(p[j]);}inference_rows+=batch.Size();}}
  auto tick_world=[&](size_t i){
   auto& world=*worlds[i];
   bool kickoff=!ball_touched[i]&&world.EpisodeTicks()<168&&world.State().ball.pos.Length2D()<1&&world.State().ball.pos.z<100;
   if(config.learner_scripted_kickoff&&kickoff){
    auto& index=learner_kickoff_index[i];
    if(index==-1)index=SlaterAttention::FrozenClock::KickoffTaker(world.State(),world.LearnerId())?0:-2;
    else if(index>=0)++index;
    if(index>=0&&index<168){world.SetLearnerPacketAction(SlaterAttention::KickoffAction(index));step_scripted[i]=true;packet_scripted[i]=true;}
   }
   if(trackers[i]||task_trackers[i]){auto before=worlds[i]->State();before.prev=nullptr;worlds[i]->Tick(predictions[i]);
    if(trackers[i]){auto result=trackers[i]->tick(before,worlds[i]->State(),worlds[i]->LearnerId());practice_rewards[i]+=result.reward;
     if(result.expired||result.success)worlds[i]->EndPracticeEpisode();}
    else practice_rewards[i]+=task_trackers[i]->Tick(before,worlds[i]->State(),worlds[i]->LearnerId()).reward;
   }else worlds[i]->Tick(predictions[i]);
   for(const auto& player:world.State().players)ball_touched[i]|=player.ballTouchedStep;
  };
  std::vector<std::future<void>> futures;
  for(size_t i=0;i<worlds.size();++i)if(!worlds[i]->StepComplete()){
   if(pool)futures.push_back(pool->enqueue([&,i]{tick_world(i);}));else tick_world(i);++physics_ticks;
  }
  for(auto& f:futures)f.get();
  // Counters are updated after joining workers, avoiding writes to shared totals.
  for(auto scripted:packet_scripted)learner_script_ticks+=scripted;
 }
 void advance(){for(int tick=0;tick<8;++tick)packet();}
 void reset(size_t i){++episode_seeds[i];reset_seed(i,episode_seeds[i]);}
};
struct Rows{
 SlaterAttention::FlatBatch features;
 std::vector<int64_t> action,task;
 std::vector<int64_t> policy_owned;
 std::vector<float> logp,value,reward,done,adv,ret,anchor;
};
torch::Tensor floats(const std::vector<float>& v,torch::Device d){return torch::from_blob(const_cast<float*>(v.data()),{static_cast<int64_t>(v.size())},torch::kFloat32).clone().to(d);}
slater_attention::Batch collect(Engine& engine,Rollout& rollout,const Options& o,json& outcomes){
 auto d=engine.device();std::vector<Rows> rows(o.games);for(auto& r:rows)r.features.Reserve(o.steps);outcomes=json::array();
 bool has_policy_row=false;
 for(int step=0;step<o.steps||(!has_policy_row&&step<o.steps+24);++step){auto input=rollout.learners();auto task=rollout.tasks();slater_attention::Choice choice;
  {torch::NoGradGuard guard;choice=engine.sample(input.q,input.kv,input.mask,task);}
  auto a=choice.action.to(torch::kCPU).contiguous(),l=choice.logp.to(torch::kCPU).contiguous(),v=choice.value.to(torch::kCPU).contiguous();
  // Store the pre-action states independently, then advance eight physics packets.
  for(int i=0;i<o.games;++i){auto views=observe(*rollout.worlds[i]);rows[i].features.Append(car_view(views,rollout.worlds[i]->LearnerId()));rows[i].action.push_back(a.data_ptr<int64_t>()[i]);rows[i].logp.push_back(l.data_ptr<float>()[i]);rows[i].value.push_back(v.data_ptr<float>()[i]);rows[i].task.push_back(rollout.task_for(i));rows[i].anchor.push_back(float(rollout.anchor_for(i)));}
  rollout.begin(choice.action);rollout.advance();
  for(int i=0;i<o.games;++i){auto& world=*rollout.worlds[i];auto info=world.StepInfo();double reward=rollout.reward_for(i);
   rows[i].policy_owned.push_back(!rollout.step_scripted[i]);has_policy_row|=!rollout.step_scripted[i];
   rollout.excluded_script_rows+=rollout.step_scripted[i];
   if(info.timeout){SlaterAttention::FlatBatch b;b.Append(car_view(observe(world),world.LearnerId()));auto after=tensor_inputs(b,d);torch::NoGradGuard guard;auto next=engine.values(after.q,after.kv,after.mask,torch::full({1},rollout.task_for(i),torch::TensorOptions().dtype(torch::kInt64).device(d))).item<double>();reward+=.995*next;++rollout.timeouts;}
   rows[i].reward.push_back(static_cast<float>(reward));rows[i].done.push_back(world.Done()?1.f:0.f);
   if(world.Done()){outcomes.push_back({{"world",i},{"side",world.LearnerSign()>0?"blue":"orange"},{"rival",rollout.rival_keys[i]},{"outcome",info.outcome},{"timeout",info.timeout},{"physics_ticks",info.episodePhysicsTicks},{"reward",rollout.episode_reward(i)},{"frozen_script_ticks",info.scriptPhysicsTicks},{"practice",rollout.is_practice(i)},{"our_size",world.LearnerSign()>0?world.BlueIds().size():world.OrangeIds().size()},{"their_size",world.LearnerSign()>0?world.OrangeIds().size():world.BlueIds().size()},{"learner_slot",world.LearnerSlot()},{"teammate_policy",rollout.teammate_keys[i]},{"curriculum",rollout.drill_summary(i)}});rollout.record_episode(i);rollout.goals_for+=info.outcome==1;rollout.goals_against+=info.outcome==-1;rollout.script_ticks+=info.scriptPhysicsTicks;rollout.reset(i);}
  }
 }
 auto last=rollout.learners();torch::Tensor boot;{torch::NoGradGuard guard;boot=engine.values(last.q,last.kv,last.mask,rollout.tasks()).to(torch::kCPU).contiguous();}
 Rows joined;
 for(int i=0;i<o.games;++i){auto& r=rows[i];auto [adv,ret]=slater_attention::gae(floats(r.reward,torch::kCPU),floats(r.value,torch::kCPU),floats(r.done,torch::kCPU),boot.data_ptr<float>()[i]);
  r.adv.assign(adv.data_ptr<float>(),adv.data_ptr<float>()+adv.numel());r.ret.assign(ret.data_ptr<float>(),ret.data_ptr<float>()+ret.numel());
  joined.features.q.insert(joined.features.q.end(),r.features.q.begin(),r.features.q.end());joined.features.kv.insert(joined.features.kv.end(),r.features.kv.begin(),r.features.kv.end());joined.features.mask.insert(joined.features.mask.end(),r.features.mask.begin(),r.features.mask.end());joined.features.carIds.insert(joined.features.carIds.end(),r.features.carIds.begin(),r.features.carIds.end());
  joined.action.insert(joined.action.end(),r.action.begin(),r.action.end());joined.task.insert(joined.task.end(),r.task.begin(),r.task.end());joined.anchor.insert(joined.anchor.end(),r.anchor.begin(),r.anchor.end());
  joined.policy_owned.insert(joined.policy_owned.end(),r.policy_owned.begin(),r.policy_owned.end());
  for(auto pair:{std::pair{&joined.logp,&r.logp},std::pair{&joined.value,&r.value},std::pair{&joined.reward,&r.reward},std::pair{&joined.done,&r.done},std::pair{&joined.adv,&r.adv},std::pair{&joined.ret,&r.ret}})pair.first->insert(pair.first->end(),pair.second->begin(),pair.second->end());
 }
 auto x=tensor_inputs(joined.features,d);slater_attention::Batch b;b.q=x.q;b.kv=x.kv;b.mask=x.mask;b.action=torch::tensor(joined.action,torch::TensorOptions().dtype(torch::kInt64)).to(d);b.old_logp=floats(joined.logp,d);b.value=floats(joined.value,d);b.reward=floats(joined.reward,d);b.done=floats(joined.done,d);b.adv=floats(joined.adv,d);b.ret=floats(joined.ret,d);b.task=torch::tensor(joined.task,torch::TensorOptions().dtype(torch::kInt64)).to(d);b.anchor_weight=floats(joined.anchor,d);
 // GAE retains real temporal spacing through forced controls. Only transitions
 // wholly controlled by the sampled policy may contribute PPO/critic gradients.
 auto owned=torch::tensor(joined.policy_owned,torch::kInt64).to(d).nonzero().reshape({-1});
 if(owned.numel()==0)throw std::runtime_error("No policy-controlled transitions after scripted kickoff");
 for(auto* field:{&b.q,&b.kv,&b.mask,&b.action,&b.old_logp,&b.value,&b.reward,&b.done,&b.adv,&b.ret,&b.task,&b.anchor_weight})*field=field->index_select(0,owned);
 return b;
}

json evaluation(Engine& engine,torch::jit::Module& rival,const Options& o){
 RLGC::DefaultAction table;json records=json::array();auto start=Clock::now();
 for(int seed=0;seed<o.eval_seeds;++seed)for(int kind=0;kind<2;++kind)for(int side=0;side<2;++side){
  json pair;for(int model=0;model<2;++model){World w(1,1,side==0?RocketSim::Team::BLUE:RocketSim::Team::ORANGE,o.duration);uint64_t s=uint64_t(o.seed)+1000000+997*seed;w.Reset(s);uint64_t total=0;int gf=0,ga=0,episodes=0,kickoff_index=-1;bool ball_touched=false;auto& actor=model==0?engine.actor():engine.teacher();
   while(total<uint64_t(std::llround(o.duration*120))){SlaterAttention::FlatBatch b;b.Append(car_view(observe(w),w.LearnerId()));auto in=tensor_inputs(b,engine.device());int index;{torch::NoGradGuard guard;index=policy(actor,in).argmax(-1).item<int>();}w.BeginAction(table.actions.at(index));
    for(int tick=0;tick<8&&!w.StepComplete()&&total<uint64_t(std::llround(o.duration*120));++tick){std::map<uint32_t,Action> pred;auto ready=w.ReadyCars();if(!ready.empty()){auto views=observe(w,true);SlaterAttention::FlatBatch f;for(auto id:ready)f.Append(car_view(views,id));auto fin=tensor_inputs(f,engine.device());torch::NoGradGuard guard;auto a=policy(kind==0?rival:engine.teacher(),fin).argmax(-1).to(torch::kCPU).contiguous();for(size_t j=0;j<ready.size();++j)pred[ready[j]]=table.actions.at(a.data_ptr<int64_t>()[j]);}
     bool kickoff=!ball_touched&&w.EpisodeTicks()<168&&w.State().ball.pos.Length2D()<1&&w.State().ball.pos.z<100;
     if(o.learner_scripted_kickoff&&kickoff){if(kickoff_index==-1)kickoff_index=SlaterAttention::FrozenClock::KickoffTaker(w.State(),w.LearnerId())?0:-2;else if(kickoff_index>=0)++kickoff_index;if(kickoff_index>=0&&kickoff_index<168)w.SetLearnerPacketAction(SlaterAttention::KickoffAction(kickoff_index));}
     w.Tick(pred);for(const auto& player:w.State().players)ball_touched|=player.ballTouchedStep;++total;}
    if(w.Done()){gf+=w.StepInfo().outcome==1;ga+=w.StepInfo().outcome==-1;++episodes;if(total<uint64_t(std::llround(o.duration*120))){w.Reset(s+7919*episodes);kickoff_index=-1;ball_touched=false;}}
   }
   pair[model==0?"candidate":"reference"]={{"seed",s},{"side",side==0?"blue":"orange"},{"rival",kind==0?"nexto":"source"},{"seconds",double(total)/120},{"goals_for",gf},{"goals_against",ga},{"goal_diff",gf-ga},{"student_scripted_kickoff",o.learner_scripted_kickoff}};
  }records.push_back(pair);std::cout<<"SLATER_ATTENTION_EVAL "<<records.size()<<"/"<<o.eval_seeds*4<<" "<<pair.dump()<<std::endl;
 }
 int cgd=0,rgd=0;for(const auto& p:records){cgd+=p["candidate"]["goal_diff"].get<int>();rgd+=p["reference"]["goal_diff"].get<int>();}
 return {{"records",records},{"seeds",o.eval_seeds},{"seconds",o.duration},{"candidate_goal_diff",cgd},{"reference_goal_diff",rgd},{"paired_mean_goal_diff_per_game",double(cgd-rgd)/records.size()},{"wall_seconds",seconds(start)},{"promoted",false},{"confirmed",false},{"note","Native matched screen; one learner, frozen scripted rivals; exploratory only."}};
}
int main(int argc,char** argv){try{
 auto o=options(argc,argv);at::set_num_threads(o.threads);at::set_num_interop_threads(1);torch::manual_seed(o.seed);
 auto d=o.device=="cuda"||(o.device=="auto"&&torch::cuda::is_available())?torch::Device(torch::kCUDA,0):torch::Device(torch::kCPU);
 if(o.device!="cpu"&&o.device!="cuda"&&o.device!="auto")throw std::runtime_error("Unknown device");if(d.is_cuda()&&!torch::cuda::is_available())throw std::runtime_error("CUDA requested but unavailable");
 if(o.mode=="selector-eval"){
  if(o.meshes.empty())throw std::runtime_error("Collision meshes required");
  auto result=slater_attention_eval::run_batched_evaluation(o.eval_manifest,o.meshes,o.out,d,o.pause,o.eval_worlds,o.sim_threads);
  result.erase("records");std::cout<<"SLATER_SELECTOR_COMPLETE "<<result.dump()<<std::endl;return 0;
 }
 slater_attention::Config cfg;cfg.actor_lr=o.actor_lr;cfg.critic_lr=o.critic_lr;cfg.teacher_weight=o.teacher_weight;cfg.target_kl=o.target_kl;cfg.epochs=2;cfg.minibatch=std::min(256,o.games*o.steps);
 Engine engine(o.actor,o.teacher,cfg,d);auto protocol=read(o.protocol);json state={{"updates",0},{"decisions",0}};
 if(!o.resume.empty())state=json::parse(engine.load_checkpoint(o.resume,protocol));
 auto rival=slater_attention::load_attention(o.rival,d);rival.eval();for(auto p:rival.parameters())p.set_requires_grad(false);
 if(o.mode=="parity"){
  if(o.fixture.empty())throw std::runtime_error("Tensor fixture required");auto f=torch::jit::load(o.fixture,torch::kCPU);auto q=f.attr("q").toTensor().to(d),kv=f.attr("kv").toTensor().to(d),m=f.attr("mask").toTensor().to(d);torch::NoGradGuard guard;auto expected=f.attr("expected").toTensor();auto got=engine.logits(q,kv,m).to(torch::kCPU);double error=(got-expected).abs().max().item<double>();if(error>(d.is_cuda()?2e-4:2e-5))throw std::runtime_error("Attention tensor forward parity failed");json result={{"forward_max_abs_error",error},{"rows",q.size(0)},{"device",d.str()},{"source_sha",ATTENTION_SOURCE_SHA}};atomic_json(fs::path(o.out)/"parity.json",result);std::cout<<"SLATER_ATTENTION_PARITY "<<result.dump()<<std::endl;return 0;
 }
 if(o.meshes.empty())throw std::runtime_error("Collision meshes required");RocketSim::Init(o.meshes,true);
 if(o.mode=="eval"){auto result=evaluation(engine,rival,o);atomic_json(fs::path(o.out)/"evaluation.json",result);std::cout<<"SLATER_ATTENTION_EVAL_COMPLETE "<<result.dump()<<std::endl;return 0;}
 if(o.mode!="train"&&o.mode!="benchmark")throw std::runtime_error("Unsupported native mode");
 Rollout rollout(o,d);if(state.contains("selfplay"))rollout.restore_selfplay(state["selfplay"]);if(state.contains("curriculum"))rollout.restore_progress(state["curriculum"]);
 if(state.contains("episode_seeds")){auto saved=state["episode_seeds"].get<std::vector<uint64_t>>();if(saved.size()!=rollout.worlds.size())throw std::runtime_error("Resume arena count changed");for(size_t i=0;i<saved.size();++i){rollout.episode_seeds[i]=saved[i]+1;rollout.reset_seed(i,rollout.episode_seeds[i]);}}
 auto out=fs::path(o.out);fs::create_directories(out/"checkpoints");std::string latest=o.resume;
 if(o.resume.empty()){state["episode_seeds"]=rollout.episode_seeds;state["curriculum"]=rollout.progress();state["selfplay"]=rollout.selfplay_progress();latest=(out/"checkpoints"/numbered(0)).string();engine.save_checkpoint(latest,protocol,state.dump());}
 auto start=Clock::now();double collection=0,optimization=0,saving=0;uint64_t count=0;std::string status="FINITE_BUDGET_COMPLETE";
 for(int update=0;update<o.updates;++update){if(fs::space(out).available<512ull*1024*1024){status="DISK_FLOOR_REACHED";break;}if(!o.pause.empty()&&fs::exists(o.pause)){status="PAUSED";break;}auto t=Clock::now();json outcomes;auto batch=collect(engine,rollout,o,outcomes);double ct=seconds(t);collection+=ct;t=Clock::now();auto metrics=engine.update(batch,uint64_t(o.seed)+state["updates"].get<uint64_t>());double ot=seconds(t);optimization+=ot;count+=batch.size();state["updates"]=state["updates"].get<uint64_t>()+1;state["decisions"]=state["decisions"].get<uint64_t>()+batch.size();state["episode_seeds"]=rollout.episode_seeds;rollout.maybe_advance();state["curriculum"]=rollout.progress();latest=(out/"checkpoints"/numbered(state["updates"].get<uint64_t>())).string();rollout.plan_snapshot(state["updates"].get<uint64_t>(),latest);state["selfplay"]=rollout.selfplay_progress();t=Clock::now();engine.save_checkpoint(latest,protocol,state.dump());rollout.refresh_snapshots();double st=seconds(t);saving+=st;
  json task_counts=json::array();auto task_cpu=batch.task.to(torch::kCPU);for(int task=0;task<12;++task)task_counts.push_back(task_cpu.eq(task).sum().item<int64_t>());json row=json::parse(metrics.json());row["learner_rows_per_task"]=task_counts;row.update({{"update",state["updates"]},{"decisions",state["decisions"]},{"collection_seconds",ct},{"optimization_seconds",ot},{"checkpoint_seconds",st},{"collection_decisions_per_second",batch.size()/ct},{"overall_decisions_per_second",batch.size()/(ct+ot+st)},{"episode_outcomes",outcomes},{"checkpoint",latest},{"learner_scripted_kickoff",o.learner_scripted_kickoff},{"frozen_scripted_kickoff",true},{"curriculum",rollout.progress()},{"selfplay",rollout.selfplay_progress()}});atomic_json(out/("update_"+std::to_string(state["updates"].get<uint64_t>())+".json"),row);state["latest"]=latest;state["status"]="RUNNING";atomic_json(out/"progress.json",state);std::cout<<"SLATER_ATTENTION_UPDATE "<<row.dump()<<std::endl;
 }
 state["latest"]=latest;state["status"]=status;atomic_json(out/"progress.json",state);
 json result={{"status",status},{"checkpoint",latest},{"updates",state["updates"]},{"decisions",state["decisions"]},{"session_decisions",count},{"collection_seconds",collection},{"optimization_seconds",optimization},{"checkpoint_seconds",saving},{"wall_seconds",seconds(start)},{"collection_decisions_per_second",collection>0?count/collection:0},{"overall_decisions_per_second",count/std::max(seconds(start),1e-9)},{"physics_ticks",rollout.physics_ticks},{"physics_ticks_per_second",rollout.physics_ticks/std::max(collection,1e-9)},{"frozen_inference_rows",rollout.inference_rows},{"goals_for",rollout.goals_for},{"goals_against",rollout.goals_against},{"timeout_bootstraps",rollout.timeouts},{"frozen_teacher_unchanged",engine.teacher_unchanged()},{"device",d.str()},{"architecture","ORIGINAL_NEXTO_ATTENTION"},{"source_sha",ATTENTION_SOURCE_SHA},{"resume_worlds","seeded reset at rollout boundary; physical arenas not serialized"},{"promoted",false},{"curriculum",rollout.progress()},{"selfplay",rollout.selfplay_progress()}};
 atomic_json(out/"result.json",result);std::cout<<"SLATER_ATTENTION_COMPLETE "<<result.dump()<<std::endl;return 0;
 }catch(const std::exception& e){std::cerr<<"SLATER_ATTENTION_ERROR "<<e.what()<<std::endl;return 1;}}
