#include "AttentionObs.h"
#include "AttentionWorld.h"
#include "AttentionPPO.h"
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
 std::string mode="train",actor,teacher,rival,meshes,out,protocol,pause,resume,fixture,kickoffs,device="cpu";
 int games=8,steps=128,updates=100,seed=20261013,eval_seeds=2,threads=1,sim_threads=2;
 double actor_lr=3e-6,critic_lr=1e-4,target_kl=.005,teacher_weight=.1,duration=12;
};
Options options(int argc,char** argv){Options o;for(int i=1;i<argc;++i){std::string key=argv[i];if(i+1==argc)throw std::runtime_error("Missing value for "+key);std::string v=argv[++i];
 if(key=="--mode")o.mode=v;else if(key=="--actor")o.actor=v;else if(key=="--teacher")o.teacher=v;else if(key=="--rival")o.rival=v;
 else if(key=="--meshes")o.meshes=v;else if(key=="--out")o.out=v;else if(key=="--protocol")o.protocol=v;else if(key=="--pause")o.pause=v;
 else if(key=="--kickoffs")o.kickoffs=v;else if(key=="--resume")o.resume=v;else if(key=="--fixture")o.fixture=v;else if(key=="--device")o.device=v;
 else if(key=="--games")o.games=std::stoi(v);else if(key=="--steps")o.steps=std::stoi(v);else if(key=="--updates")o.updates=std::stoi(v);
 else if(key=="--seed")o.seed=std::stoi(v);else if(key=="--eval-seeds")o.eval_seeds=std::stoi(v);else if(key=="--threads")o.threads=std::stoi(v);
 else if(key=="--sim-threads")o.sim_threads=std::stoi(v);else if(key=="--seconds")o.duration=std::stod(v);
 else if(key=="--actor-lr")o.actor_lr=std::stod(v);else if(key=="--critic-lr")o.critic_lr=std::stod(v);
 else if(key=="--target-kl")o.target_kl=std::stod(v);else if(key=="--teacher-weight")o.teacher_weight=std::stod(v);
 else throw std::runtime_error("Unknown option "+key);
 }
 if(o.actor.empty()||o.teacher.empty()||o.rival.empty()||o.out.empty()||o.protocol.empty()||o.games<1||o.games>128||o.steps<16||o.steps>4096||o.updates<0||o.updates>100000||o.duration<.1||o.duration>3600||o.eval_seeds<1||o.eval_seeds>64||o.threads<1||o.threads>32||o.sim_threads<1||o.sim_threads>32)throw std::runtime_error("Invalid attention inputs/profile");
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
 std::vector<int> rival_kind;
 std::vector<Action> actions;
 std::map<uint64_t,std::array<int,5>> kickoff_orders;
 std::unique_ptr<dp::thread_pool<>> pool;
 torch::jit::Module& teacher;torch::jit::Module& rival;torch::Device device;
 uint64_t physics_ticks=0,script_ticks=0,inference_rows=0,goals_for=0,goals_against=0,timeouts=0;
 Rollout(const Options& o,torch::jit::Module& t,torch::jit::Module& r,torch::Device d):teacher(t),rival(r),device(d){
  if(!o.kickoffs.empty()){auto data=json::parse(read(o.kickoffs));for(const auto& row:data.at("orders"))kickoff_orders[row.at("seed").get<uint64_t>()]=row.at("permutation").get<std::array<int,5>>();}
  RLGC::DefaultAction table;actions=table.actions;if(actions.size()!=90)throw std::runtime_error("Action ordering/count changed");
  if(o.sim_threads>1)pool=std::make_unique<dp::thread_pool<>>(o.sim_threads);
  for(int i=0;i<o.games;++i){auto side=i%2==0?RocketSim::Team::BLUE:RocketSim::Team::ORANGE;worlds.push_back(std::make_unique<World>(1,1,side,o.duration));episode_seeds.push_back(uint64_t(o.seed)+7919*i);rival_kind.push_back((i/2)%2);reset_seed(i,episode_seeds.back());}
 }
 void reset_seed(size_t i,uint64_t seed){if(kickoff_orders.empty())worlds[i]->Reset(seed);else{auto it=kickoff_orders.find(seed);if(it==kickoff_orders.end())throw std::runtime_error("Benchmark kickoff sequence exhausted");worlds[i]->Reset(seed,&it->second);}}
 Inputs learners(){SlaterAttention::FlatBatch b;b.Reserve(worlds.size());for(auto& world:worlds){auto v=observe(*world);b.Append(car_view(v,world->LearnerId()));}return tensor_inputs(b,device);}
 void begin(const torch::Tensor& choices){auto cpu=choices.to(torch::kCPU,torch::kInt64).contiguous();auto p=cpu.data_ptr<int64_t>();for(size_t i=0;i<worlds.size();++i)worlds[i]->BeginAction(actions.at(p[i]));}
 void packet(){
  std::array<SlaterAttention::FlatBatch,2> batches;
  std::array<std::vector<std::pair<size_t,uint32_t>>,2> positions;
  for(size_t i=0;i<worlds.size();++i){if(worlds[i]->StepComplete())continue;auto ready=worlds[i]->ReadyCars();if(ready.empty())continue;auto v=observe(*worlds[i],true);for(auto id:ready){batches[rival_kind[i]].Append(car_view(v,id));positions[rival_kind[i]].emplace_back(i,id);}}
  std::vector<std::map<uint32_t,Action>> predictions(worlds.size());
  {torch::NoGradGuard guard;for(int k=0;k<2;++k){if(!batches[k].Size())continue;auto in=tensor_inputs(batches[k],device);auto indices=policy(k==0?rival:teacher,in).argmax(-1).to(torch::kCPU).contiguous();auto p=indices.data_ptr<int64_t>();for(size_t j=0;j<positions[k].size();++j){auto [i,id]=positions[k][j];predictions[i][id]=actions.at(p[j]);}inference_rows+=batches[k].Size();}}
  std::vector<std::future<void>> futures;
  for(size_t i=0;i<worlds.size();++i)if(!worlds[i]->StepComplete()){
   if(pool)futures.push_back(pool->enqueue([&,i]{worlds[i]->Tick(predictions[i]);}));else worlds[i]->Tick(predictions[i]);++physics_ticks;
  }
  for(auto& f:futures)f.get();
 }
 void advance(){for(int tick=0;tick<8;++tick)packet();}
 void reset(size_t i){++episode_seeds[i];reset_seed(i,episode_seeds[i]);}
};
struct Rows{
 SlaterAttention::FlatBatch features;
 std::vector<int64_t> action;
 std::vector<float> logp,value,reward,done,adv,ret;
};
torch::Tensor floats(const std::vector<float>& v,torch::Device d){return torch::from_blob(const_cast<float*>(v.data()),{static_cast<int64_t>(v.size())},torch::kFloat32).clone().to(d);}
slater_attention::Batch collect(Engine& engine,Rollout& rollout,const Options& o,json& outcomes){
 auto d=engine.device();std::vector<Rows> rows(o.games);for(auto& r:rows)r.features.Reserve(o.steps);outcomes=json::array();
 for(int step=0;step<o.steps;++step){auto input=rollout.learners();auto task=torch::zeros({o.games},torch::TensorOptions().dtype(torch::kInt64).device(d));slater_attention::Choice choice;
  {torch::NoGradGuard guard;choice=engine.sample(input.q,input.kv,input.mask,task);}
  auto a=choice.action.to(torch::kCPU).contiguous(),l=choice.logp.to(torch::kCPU).contiguous(),v=choice.value.to(torch::kCPU).contiguous();
  // Store the pre-action states independently, then advance eight physics packets.
  for(int i=0;i<o.games;++i){auto views=observe(*rollout.worlds[i]);rows[i].features.Append(car_view(views,rollout.worlds[i]->LearnerId()));rows[i].action.push_back(a.data_ptr<int64_t>()[i]);rows[i].logp.push_back(l.data_ptr<float>()[i]);rows[i].value.push_back(v.data_ptr<float>()[i]);}
  rollout.begin(choice.action);rollout.advance();
  for(int i=0;i<o.games;++i){auto& world=*rollout.worlds[i];auto info=world.StepInfo();double reward=info.reward;
   if(info.timeout){SlaterAttention::FlatBatch b;b.Append(car_view(observe(world),world.LearnerId()));auto after=tensor_inputs(b,d);torch::NoGradGuard guard;auto next=engine.values(after.q,after.kv,after.mask,torch::zeros({1},torch::TensorOptions().dtype(torch::kInt64).device(d))).item<double>();reward+=.995*next;++rollout.timeouts;}
   rows[i].reward.push_back(static_cast<float>(reward));rows[i].done.push_back(world.Done()?1.f:0.f);
   if(world.Done()){outcomes.push_back({{"world",i},{"side",world.LearnerSign()>0?"blue":"orange"},{"rival",rollout.rival_kind[i]==0?"nexto":"source"},{"outcome",info.outcome},{"timeout",info.timeout},{"physics_ticks",info.episodePhysicsTicks},{"reward",world.EpisodeReward()},{"frozen_script_ticks",info.scriptPhysicsTicks}});rollout.goals_for+=info.outcome==1;rollout.goals_against+=info.outcome==-1;rollout.script_ticks+=info.scriptPhysicsTicks;rollout.reset(i);}
  }
 }
 auto last=rollout.learners();torch::Tensor boot;{torch::NoGradGuard guard;boot=engine.values(last.q,last.kv,last.mask,torch::zeros({o.games},torch::TensorOptions().dtype(torch::kInt64).device(d))).to(torch::kCPU).contiguous();}
 Rows joined;
 for(int i=0;i<o.games;++i){auto& r=rows[i];auto [adv,ret]=slater_attention::gae(floats(r.reward,torch::kCPU),floats(r.value,torch::kCPU),floats(r.done,torch::kCPU),boot.data_ptr<float>()[i]);
  r.adv.assign(adv.data_ptr<float>(),adv.data_ptr<float>()+adv.numel());r.ret.assign(ret.data_ptr<float>(),ret.data_ptr<float>()+ret.numel());
  joined.features.q.insert(joined.features.q.end(),r.features.q.begin(),r.features.q.end());joined.features.kv.insert(joined.features.kv.end(),r.features.kv.begin(),r.features.kv.end());joined.features.mask.insert(joined.features.mask.end(),r.features.mask.begin(),r.features.mask.end());joined.features.carIds.insert(joined.features.carIds.end(),r.features.carIds.begin(),r.features.carIds.end());
  joined.action.insert(joined.action.end(),r.action.begin(),r.action.end());
  for(auto pair:{std::pair{&joined.logp,&r.logp},std::pair{&joined.value,&r.value},std::pair{&joined.reward,&r.reward},std::pair{&joined.done,&r.done},std::pair{&joined.adv,&r.adv},std::pair{&joined.ret,&r.ret}})pair.first->insert(pair.first->end(),pair.second->begin(),pair.second->end());
 }
 auto x=tensor_inputs(joined.features,d);slater_attention::Batch b;b.q=x.q;b.kv=x.kv;b.mask=x.mask;b.action=torch::tensor(joined.action,torch::TensorOptions().dtype(torch::kInt64)).to(d);b.old_logp=floats(joined.logp,d);b.value=floats(joined.value,d);b.reward=floats(joined.reward,d);b.done=floats(joined.done,d);b.adv=floats(joined.adv,d);b.ret=floats(joined.ret,d);b.task=torch::zeros({b.size()},torch::TensorOptions().dtype(torch::kInt64).device(d));b.anchor_weight=torch::full({b.size()},o.teacher_weight,torch::TensorOptions().dtype(torch::kFloat32).device(d));return b;
}

json evaluation(Engine& engine,torch::jit::Module& rival,const Options& o){
 RLGC::DefaultAction table;json records=json::array();auto start=Clock::now();
 for(int seed=0;seed<o.eval_seeds;++seed)for(int kind=0;kind<2;++kind)for(int side=0;side<2;++side){
  json pair;for(int model=0;model<2;++model){World w(1,1,side==0?RocketSim::Team::BLUE:RocketSim::Team::ORANGE,o.duration);uint64_t s=uint64_t(o.seed)+1000000+997*seed;w.Reset(s);uint64_t total=0;int gf=0,ga=0,episodes=0;auto& actor=model==0?engine.actor():engine.teacher();
   while(total<uint64_t(std::llround(o.duration*120))){SlaterAttention::FlatBatch b;b.Append(car_view(observe(w),w.LearnerId()));auto in=tensor_inputs(b,engine.device());int index;{torch::NoGradGuard guard;index=policy(actor,in).argmax(-1).item<int>();}w.BeginAction(table.actions.at(index));
    for(int tick=0;tick<8&&!w.StepComplete()&&total<uint64_t(std::llround(o.duration*120));++tick){std::map<uint32_t,Action> pred;auto ready=w.ReadyCars();if(!ready.empty()){auto views=observe(w,true);SlaterAttention::FlatBatch f;for(auto id:ready)f.Append(car_view(views,id));auto fin=tensor_inputs(f,engine.device());torch::NoGradGuard guard;auto a=policy(kind==0?rival:engine.teacher(),fin).argmax(-1).to(torch::kCPU).contiguous();for(size_t j=0;j<ready.size();++j)pred[ready[j]]=table.actions.at(a.data_ptr<int64_t>()[j]);}w.Tick(pred);++total;}
    if(w.Done()){gf+=w.StepInfo().outcome==1;ga+=w.StepInfo().outcome==-1;++episodes;if(total<uint64_t(std::llround(o.duration*120)))w.Reset(s+7919*episodes);}
   }
   pair[model==0?"candidate":"reference"]={{"seed",s},{"side",side==0?"blue":"orange"},{"rival",kind==0?"nexto":"source"},{"seconds",double(total)/120},{"goals_for",gf},{"goals_against",ga},{"goal_diff",gf-ga},{"student_scripted_kickoff",false}};
  }records.push_back(pair);std::cout<<"SLATER_ATTENTION_EVAL "<<records.size()<<"/"<<o.eval_seeds*4<<" "<<pair.dump()<<std::endl;
 }
 int cgd=0,rgd=0;for(const auto& p:records){cgd+=p["candidate"]["goal_diff"].get<int>();rgd+=p["reference"]["goal_diff"].get<int>();}
 return {{"records",records},{"seeds",o.eval_seeds},{"seconds",o.duration},{"candidate_goal_diff",cgd},{"reference_goal_diff",rgd},{"paired_mean_goal_diff_per_game",double(cgd-rgd)/records.size()},{"wall_seconds",seconds(start)},{"promoted",false},{"confirmed",false},{"note","Native matched screen; one learner, frozen scripted rivals; exploratory only."}};
}
int main(int argc,char** argv){try{
 auto o=options(argc,argv);at::set_num_threads(o.threads);at::set_num_interop_threads(1);torch::manual_seed(o.seed);
 auto d=o.device=="cuda"||(o.device=="auto"&&torch::cuda::is_available())?torch::Device(torch::kCUDA,0):torch::Device(torch::kCPU);
 if(o.device!="cpu"&&o.device!="cuda"&&o.device!="auto")throw std::runtime_error("Unknown device");if(d.is_cuda()&&!torch::cuda::is_available())throw std::runtime_error("CUDA requested but unavailable");
 slater_attention::Config cfg;cfg.actor_lr=o.actor_lr;cfg.critic_lr=o.critic_lr;cfg.teacher_weight=o.teacher_weight;cfg.target_kl=o.target_kl;cfg.epochs=2;cfg.minibatch=std::min(256,o.games*o.steps);
 Engine engine(o.actor,o.teacher,cfg,d);auto protocol=read(o.protocol);json state={{"updates",0},{"decisions",0}};
 if(!o.resume.empty())state=json::parse(engine.load_checkpoint(o.resume,protocol));
 auto rival=torch::jit::load(o.rival,d);rival.eval();for(auto p:rival.parameters())p.set_requires_grad(false);
 if(o.mode=="parity"){
  if(o.fixture.empty())throw std::runtime_error("Tensor fixture required");auto f=torch::jit::load(o.fixture,torch::kCPU);auto q=f.attr("q").toTensor().to(d),kv=f.attr("kv").toTensor().to(d),m=f.attr("mask").toTensor().to(d);torch::NoGradGuard guard;auto expected=f.attr("expected").toTensor();auto got=engine.logits(q,kv,m).to(torch::kCPU);double error=(got-expected).abs().max().item<double>();if(error>(d.is_cuda()?2e-4:2e-5))throw std::runtime_error("Attention tensor forward parity failed");json result={{"forward_max_abs_error",error},{"rows",q.size(0)},{"device",d.str()},{"source_sha",ATTENTION_SOURCE_SHA}};atomic_json(fs::path(o.out)/"parity.json",result);std::cout<<"SLATER_ATTENTION_PARITY "<<result.dump()<<std::endl;return 0;
 }
 if(o.meshes.empty())throw std::runtime_error("Collision meshes required");RocketSim::Init(o.meshes,true);
 if(o.mode=="eval"){auto result=evaluation(engine,rival,o);atomic_json(fs::path(o.out)/"evaluation.json",result);std::cout<<"SLATER_ATTENTION_EVAL_COMPLETE "<<result.dump()<<std::endl;return 0;}
 if(o.mode!="train"&&o.mode!="benchmark")throw std::runtime_error("Unsupported native mode");
 Rollout rollout(o,engine.teacher(),rival,d);
 if(state.contains("episode_seeds")){auto saved=state["episode_seeds"].get<std::vector<uint64_t>>();if(saved.size()!=rollout.worlds.size())throw std::runtime_error("Resume arena count changed");for(size_t i=0;i<saved.size();++i){rollout.episode_seeds[i]=saved[i]+1;rollout.reset_seed(i,rollout.episode_seeds[i]);}}
 auto out=fs::path(o.out);fs::create_directories(out/"checkpoints");std::string latest=o.resume;
 if(o.resume.empty()){state["episode_seeds"]=rollout.episode_seeds;latest=(out/"checkpoints"/numbered(0)).string();engine.save_checkpoint(latest,protocol,state.dump());}
 auto start=Clock::now();double collection=0,optimization=0,saving=0;uint64_t count=0;std::string status="FINITE_BUDGET_COMPLETE";
 for(int update=0;update<o.updates;++update){if(fs::space(out).available<512ull*1024*1024){status="DISK_FLOOR_REACHED";break;}if(!o.pause.empty()&&fs::exists(o.pause)){status="PAUSED";break;}auto t=Clock::now();json outcomes;auto batch=collect(engine,rollout,o,outcomes);double ct=seconds(t);collection+=ct;t=Clock::now();auto metrics=engine.update(batch,uint64_t(o.seed)+state["updates"].get<uint64_t>());double ot=seconds(t);optimization+=ot;count+=batch.size();state["updates"]=state["updates"].get<uint64_t>()+1;state["decisions"]=state["decisions"].get<uint64_t>()+batch.size();state["episode_seeds"]=rollout.episode_seeds;latest=(out/"checkpoints"/numbered(state["updates"].get<uint64_t>())).string();t=Clock::now();engine.save_checkpoint(latest,protocol,state.dump());double st=seconds(t);saving+=st;
  json row=json::parse(metrics.json());row.update({{"update",state["updates"]},{"decisions",state["decisions"]},{"collection_seconds",ct},{"optimization_seconds",ot},{"checkpoint_seconds",st},{"collection_decisions_per_second",batch.size()/ct},{"overall_decisions_per_second",batch.size()/(ct+ot+st)},{"episode_outcomes",outcomes},{"checkpoint",latest},{"learner_scripted_kickoff",false},{"frozen_scripted_kickoff",true}});atomic_json(out/("update_"+std::to_string(state["updates"].get<uint64_t>())+".json"),row);state["latest"]=latest;state["status"]="RUNNING";atomic_json(out/"progress.json",state);std::cout<<"SLATER_ATTENTION_UPDATE "<<row.dump()<<std::endl;
 }
 state["latest"]=latest;state["status"]=status;atomic_json(out/"progress.json",state);
 json result={{"status",status},{"checkpoint",latest},{"updates",state["updates"]},{"decisions",state["decisions"]},{"session_decisions",count},{"collection_seconds",collection},{"optimization_seconds",optimization},{"checkpoint_seconds",saving},{"wall_seconds",seconds(start)},{"collection_decisions_per_second",collection>0?count/collection:0},{"overall_decisions_per_second",count/std::max(seconds(start),1e-9)},{"physics_ticks",rollout.physics_ticks},{"physics_ticks_per_second",rollout.physics_ticks/std::max(collection,1e-9)},{"frozen_inference_rows",rollout.inference_rows},{"goals_for",rollout.goals_for},{"goals_against",rollout.goals_against},{"timeout_bootstraps",rollout.timeouts},{"frozen_teacher_unchanged",engine.teacher_unchanged()},{"device",d.str()},{"architecture","ORIGINAL_NEXTO_ATTENTION"},{"source_sha",ATTENTION_SOURCE_SHA},{"resume_worlds","seeded reset at rollout boundary; physical arenas not serialized"},{"promoted",false}};
 atomic_json(out/"result.json",result);std::cout<<"SLATER_ATTENTION_COMPLETE "<<result.dump()<<std::endl;return 0;
 }catch(const std::exception& e){std::cerr<<"SLATER_ATTENTION_ERROR "<<e.what()<<std::endl;return 1;}}
