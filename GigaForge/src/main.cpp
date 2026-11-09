#include <GigaLearnCPP/Learner.h>
#include <GigaLearnCPP/PPO/PPOLearner.h>
#include <GigaLearnCPP/Util/Models.h>
#include <RLGymCPP/StateSetters/KickoffState.h>
#include <RLGymCPP/TerminalConditions/GoalScoreCondition.h>
#include <nlohmann/json.hpp>
#include <torch/nn/modules/linear.h>
#include <torch/serialize.h>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif
#include "native_features.h"
#include "checks.h"
#include "evaluate.h"

using namespace GGL;using namespace RLGC;using nlohmann::json;
json recipe;
#include "stationary_contract.h"
ModelSet opponentModels;
std::vector<std::unique_ptr<GF::Obs>> opponentObs;
std::vector<float> preparedObs;
std::vector<uint8_t> preparedMasks;
Learner* currentLearner=nullptr;
void PrepareOpponent(const std::vector<GameState>& states,const IList& indices){
 preparedObs.clear();preparedMasks.clear();
 size_t wanted=0;int index=0;
 GF::Actions actions(false);
 for(size_t arena=0;arena<states.size();arena++){
  const auto& s=states[arena];
  if(!s.prev)opponentObs[arena]->Reset(s);
  for(const auto& player:s.players){
   if(wanted<indices.size() && index==indices[wanted]){
    preparedObs+=opponentObs[arena]->BuildObs(player,s);
    auto mask=actions.GetActionMask(player,s);preparedMasks.insert(preparedMasks.end(),mask.begin(),mask.end());wanted++;
   }
   index++;
  }
 }
 if(wanted!=indices.size())throw std::runtime_error("External opponent index mismatch");
}
IList InferOpponent(){
 int size=recipe["opponent"]["family"]=="chronos"?225:258;
 auto obs=torch::tensor(preparedObs).reshape({-1,size}).to(currentLearner->ppo->device);
 auto masks=torch::tensor(preparedMasks).reshape({-1,90}).to(currentLearner->ppo->device);
 torch::Tensor result;
 PPOLearner::InferActionsFromModels(opponentModels,obs,masks,true,1.f,false,&result,nullptr);
 return TENSOR_TO_VEC<int>(result);
}
void Shape(PPOLearnerConfig& p,const std::string& family){
 bool c=family=="chronos";
 p.sharedHead.layerSizes=c?std::vector<int>{960,960}:std::vector<int>{1024,1024};
 p.policy.layerSizes=c?std::vector<int>{960,800,640,640}:std::vector<int>{1024,1024,1024,1024};
 p.critic.layerSizes={256,256};
 for(auto* m:{&p.sharedHead,&p.policy,&p.critic}){
  m->addLayerNorm=true;m->activationType=c?ModelActivationType::RELU:ModelActivationType::LEAKY_RELU;
  m->optimType=ModelOptimType::ADAM;
 }
 p.sharedHead.addOutputLayer=false;
}
EnvCreateResult MakeEnvironment(int index){
 bool c=recipe.at("family")=="chronos";
 auto a=Arena::Create(GameMode::SOCCAR);
 auto body=recipe.at("hitbox")=="breakout"?CAR_CONFIG_BREAKOUT:CAR_CONFIG_OCTANE;
 bool external=recipe.contains("opponent");
 Team learnerTeam=Team(index%2);
 auto otherBody=external && recipe["opponent"]["hitbox"]=="breakout"?CAR_CONFIG_BREAKOUT:CAR_CONFIG_OCTANE;
 bool otherC=external?recipe["opponent"]["family"]=="chronos":c;
 a->AddCar(Team::BLUE,!external || learnerTeam==Team::BLUE?body:otherBody);
 a->AddCar(Team::ORANGE,!external || learnerTeam==Team::ORANGE?body:otherBody);
 EnvCreateResult e={};e.arena=a;e.obsBuilder=new GF::Obs(c,recipe.at("seed").get<unsigned>()+index);
 if(external)static_cast<GF::Obs*>(e.obsBuilder)->onlyTeam=int(learnerTeam);
 e.actionParser=new GF::Actions(c,otherC,learnerTeam);
 float defProb=recipe.value("defensive_curriculum_prob",0.f);
 if(defProb>0.f)e.stateSetter=new GF::DefensiveCurriculumStateSetter(defProb,learnerTeam,recipe.at("seed").get<unsigned>()+index*7919u+104729u);
 else e.stateSetter=new KickoffState;
 e.terminalConditions={new GoalScoreCondition};
 std::array<float,5> weights={.35f,.1f,0.f,0.f,0.f};
 if(recipe.contains("potential_weights"))weights=recipe["potential_weights"].get<std::array<float,5>>();
 if(recipe.value("stationary_objective",std::string())=="goal_only")weights={0,0,0,0,0};
 if(recipe.value("winrate_dominance_reward",false)){
  e.rewards={{new GF::WinRateDominanceGoalPotential(recipe.at("gamma"),weights,recipe.value("win_scale",2.f)),1.f}};
 }else if(recipe.value("validated_antidive_reward",false)){
  e.rewards={{new GF::ValidatedAntiDiveMechanicsGoalPotential(recipe.at("gamma"),weights,recipe.value("mechanics_scale",1.f),recipe.value("defense_scale",1.f)),1.f}};
 }else if(recipe.value("defensive_mechanics_reward",false)){
  e.rewards={{new GF::DefensiveMechanicsGoalPotential(recipe.at("gamma"),weights,recipe.value("mechanics_scale",1.f),recipe.value("defense_scale",1.f)),1.f}};
 }else if(recipe.value("mechanics_reward",false)){
  e.rewards={{new GF::MechanicsGoalPotential(recipe.at("gamma"),weights,recipe.value("mechanics_scale",1.f)),1.f}};
 }else{
  e.rewards={{new GF::GoalPotential(recipe.at("gamma"),weights),1.f}};
 }
 return e;
}
void Step(Learner* l,const std::vector<GameState>& states,Report& report){
 int arenaIndex=0;
 for(const auto& s:states){
  report.AddAvg("game/goal_fraction",float(s.goalScored));
  if(recipe.contains("opponent") && s.goalScored){
   bool scored=(s.ball.pos.y>0)==((arenaIndex%2)==0);
   report["game/learner_goals_for"]+=scored;report["game/learner_goals_against"]+=!scored;
   report.AddAvg("game/learner_goal_share",float(scored));
  }
  arenaIndex++;
  for(const auto& p:s.players)report.AddAvg("game/touch_fraction",float(p.ballTouchedStep));
 }
 // Removed: the old cluster counter counted both player perspectives, not learner wins.
 // Shared trunk is also frozen by SetLearningRates(0, criticLR).
 bool warmup=l->totalIterations<recipe.at("warmup_iterations").get<uint64_t>();
 float actor=warmup?0.f:recipe.at("actor_lr").get<float>();
 if(l->ppo->config.policyLR!=actor)l->ppo->SetLearningRates(actor,recipe.at("critic_lr"));
 for(auto name:{"shared_head","policy"}){
  auto model=l->ppo->models[name];
  bool enabled=!warmup && !(std::string(name)=="shared_head" && recipe.value("freeze_shared",false));
  if(model->parameters().front().requires_grad()!=enabled)
   for(auto& parameter:model->parameters())parameter.requires_grad_(enabled);
 }
 report["train/critic_warmup"]=warmup;
}
int main(int argc,char** argv){
 try{
  if(argc==2 && std::string(argv[1])=="--stationary-contract"){
   std::cout<<json({{"version","stationary-pilot-v1"},{"objectives",{"goal_only","goal_potential"}},
    {"temperature_consistent",true},{"sample_accounting","fixed-rollout-v1"},
    {"hitboxes",{{"chronos","breakout"},{"galactus","octane"}}}}).dump()<<std::endl;return 0;
  }
  if(argc==2 && std::string(argv[1])=="--stationary-selftest")return GF::StationarySelfTest();
  if(argc==2 && std::string(argv[1])=="--head-to-head-protocol"){
   std::cout<<"direct-h2h-v1"<<std::endl;return 0;
  }
  if(argc==2 && std::string(argv[1])=="--evaluation-protocol"){
   std::cout<<"arena-rng-v4"<<std::endl;return 0;
  }
  if(argc==2 && (std::string(argv[1])=="--selftest" || std::string(argv[1])=="--research-selftest"))return GF::SelfTest();
  if(argc==6 && std::string(argv[1])=="--features")return GF::Features(argv[2],argv[3],argv[4],argv[5]);
  if(argc!=2)throw std::runtime_error("Usage: GigaForge recipe.json");
  recipe=json::parse(std::ifstream(argv[1]));
  if(!recipe.contains("evaluation"))GF::ValidateStationaryRecipe(recipe);
#ifdef _WIN32
  // The executable uses PyTorch's common C++ ABI. Register the CUDA backend
  // from a matching CUDA-enabled wheel before the first CUDA hook query.
  if(const char* path=std::getenv("GIGAFORGE_TORCH_LIB")){
   auto cuda=std::filesystem::path(path)/"torch_cuda.dll";
   if(std::filesystem::exists(cuda) && !LoadLibraryExW(cuda.wstring().c_str(),nullptr,LOAD_WITH_ALTERED_SEARCH_PATH))
    throw std::runtime_error("Could not register torch_cuda.dll: Win32 "+std::to_string(GetLastError()));
  }
#endif
  torch::set_num_threads(recipe.value("torch_threads",1));
  RocketSim::Init(recipe.at("meshes").get<std::string>());
  if(recipe.contains("evaluation")){
   auto result=GF::Evaluate(recipe["evaluation"],recipe.value("device","cpu")=="cuda"?torch::Device(torch::kCUDA):torch::Device(torch::kCPU),Shape);
   std::ofstream(recipe["evaluation"]["output"].get<std::string>())<<result.dump(2);return 0;
  }
  bool c=recipe.at("family")=="chronos";
  if(recipe.at("family")!="chronos" && recipe.at("family")!="galactus")throw std::runtime_error("Unknown family");
  LearnerConfig cfg;cfg.numGames=recipe.at("games");cfg.randomSeed=recipe.at("seed");
  cfg.tickSkip=8;cfg.actionDelay=7;
  cfg.deviceType=recipe.value("device","cpu")=="cuda"?LearnerDeviceType::GPU_CUDA:LearnerDeviceType::CPU;
  cfg.sendMetrics=false;cfg.renderMode=false;
  cfg.standardizeObs=false;cfg.standardizeReturns=false;
  cfg.ppo.rewardClipRange=0;cfg.ppo.gaeGamma=recipe.at("gamma");cfg.ppo.gaeLambda=recipe.value("gae_lambda",.97f);
  cfg.ppo.tsPerItr=recipe.at("rollout");cfg.ppo.batchSize=recipe.at("batch");cfg.ppo.miniBatchSize=recipe.at("minibatch");
  cfg.ppo.epochs=recipe.value("epochs",2);cfg.ppo.clipRange=recipe.value("clip_range",.05f);
  // Native entropy is normalized by log(number of valid actions).
  cfg.ppo.entropyScale=.0002f*std::log(90.f);cfg.ppo.maskEntropy=false;
  cfg.ppo.policyLR=0;cfg.ppo.criticLR=recipe.at("critic_lr");
  cfg.ppo.maxEpisodeDuration=recipe.value("trajectory_seconds",60.);
  cfg.ppo.policyTemperature=recipe.value("policy_temperature",1.f);
  cfg.ppo.useHalfPrecision=false;Shape(cfg.ppo,recipe.at("family"));
  cfg.checkpointFolder=recipe.at("checkpoints").get<std::string>();cfg.tsPerSave=32768;
  cfg.checkpointsToKeep=3;cfg.savePolicyVersions=!cfg.checkpointFolder.empty();cfg.tsPerVersion=32768;cfg.maxOldVersions=4;
  cfg.trainAgainstOldVersions=!cfg.checkpointFolder.empty();cfg.trainAgainstOldChance=.25;
  if(recipe.contains("opponent")){
   cfg.trainAgainstOldVersions=false;cfg.prepareOpponent=PrepareOpponent;cfg.inferOpponent=InferOpponent;
  }
  cfg.stopFile=recipe.at("stop_file").get<std::string>();cfg.maxTimesteps=recipe.value("stop_at",uint64_t(0));
  cfg.maxIterations=recipe.value("max_iterations",uint64_t(0));
  cfg.fixedRollout=recipe.value("fixed_rollout",false);
  cfg.reportFile=recipe.at("metrics_file").get<std::string>();
  cfg.ppo.useGuidingPolicy=true;cfg.ppo.guidingPolicyPath=recipe.at("anchor").get<std::string>();cfg.ppo.guidingStrength=recipe.value("anchor_coef",.2f);
  Learner learner(MakeEnvironment,cfg,Step);
  currentLearner=&learner;
  for(size_t i=0;i<learner.envSet->arenas.size();i++){
   for(auto car:learner.envSet->arenas[i]->GetCars()){
    bool own=!recipe.contains("opponent") || int(car->team)==int(i%2);
    std::string expected=own?recipe["hitbox"].get<std::string>():recipe["opponent"]["hitbox"].get<std::string>();
    auto body=expected=="breakout"?CAR_CONFIG_BREAKOUT:CAR_CONFIG_OCTANE;
    if(car->config.hitboxSize.x!=body.hitboxSize.x)throw std::runtime_error("Arena hitbox mismatch");
   }
  }
  std::cout<<"NATIVE_BODY_CHECK_PASS "<<recipe["family"]<<" "<<recipe["hitbox"]<<std::endl;
  if(recipe.contains("opponent")){
   auto otherConfig=cfg.ppo;Shape(otherConfig,recipe["opponent"]["family"]);
   int size=recipe["opponent"]["family"]=="chronos"?225:258;
   PPOLearner::MakeModels(false,size,90,otherConfig.sharedHead,otherConfig.policy,otherConfig.critic,learner.ppo->device,opponentModels);
   opponentModels.Load(recipe["opponent"]["path"].get<std::string>(),false,false);
   for(int i=0;i<cfg.numGames;i++)opponentObs.push_back(std::make_unique<GF::Obs>(size==225,cfg.randomSeed+i+999991));
  }
  if(learner.obsSize!=(c?225:258)||learner.numActions!=90)throw std::runtime_error("Network/environment contract mismatch");
  if(learner.totalTimesteps==0){
   // Initial actors must exist: never silently start a random policy.
   auto folder=std::filesystem::path(recipe.at("anchor").get<std::string>());
   learner.ppo->models["shared_head"]->Load(folder,false,false);
   learner.ppo->models["policy"]->Load(folder,false,false);
   if(recipe.contains("critic_init")){
    auto cfolder=std::filesystem::path(recipe.at("critic_init").get<std::string>());
    learner.ppo->models["critic"]->Load(cfolder,false,false);
   }else{
    auto seq=learner.ppo->models["critic"]->seq;
    {torch::NoGradGuard guard;auto& last=seq->at<torch::nn::LinearImpl>(seq->size()-1);last.weight.zero_();last.bias.zero_();}
   }
  }
  // A cross-language probe checks the exact loaded policy before any updates.
  if(recipe.contains("probe_input")){
   auto values=recipe.at("probe_input").get<std::vector<float>>();
   auto x=torch::tensor(values).reshape({-1,learner.obsSize}).to(learner.ppo->device);
   torch::NoGradGuard guard;
   auto logits=learner.ppo->models["policy"]->Forward(learner.ppo->models["shared_head"]->Forward(x,false),false).cpu().contiguous();
   auto flat=logits.flatten();std::vector<float> data(flat.data_ptr<float>(),flat.data_ptr<float>()+flat.numel());
   std::ofstream(recipe.at("probe_output").get<std::string>())<<json(data).dump();
   if(recipe.value("probe_only",false))return 0;
  }
  if(recipe.contains("benchmark_decisions")){
   auto& env=*learner.envSet;torch::NoGradGuard guard;
   auto run=[&](int target){
    int count=0;
    while(count<target){
     env.Reset();auto x=DIMLIST2_TO_TENSOR<float>(env.state.obs).to(learner.ppo->device);
     auto masks=DIMLIST2_TO_TENSOR<uint8_t>(env.state.actionMasks).to(learner.ppo->device);
     env.StepFirstHalf(true);torch::Tensor a;learner.ppo->InferActions(x,masks,&a,nullptr);
     auto actions=TENSOR_TO_VEC<int>(a);env.Sync();env.StepSecondHalf(actions,false);count+=env.state.numPlayers;
    }
    return count;
   };
   run(512);auto started=std::chrono::steady_clock::now();int count=run(recipe["benchmark_decisions"]);
   double elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
   json result={{"decisions",count},{"seconds",elapsed},{"collection_decisions_per_second",count/elapsed},{"games",cfg.numGames},{"family",recipe["family"]},{"device",recipe["device"]}};
   std::ofstream(recipe.at("benchmark_output").get<std::string>())<<result.dump(2);return 0;
  }
  learner.Start();
  return 0;
 }catch(const std::exception& e){std::cerr<<"GIGAFORGE_FAILED: "<<e.what()<<std::endl;return 1;}
}
