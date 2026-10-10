// AFK_GIGALEARN_WATCH_V1: native .lt RocketSim viewer frame source.
// This source intentionally reuses the patched trainer's EnvCreateFunc so
// observations, network layers and action parser match existing training.
// No backpropagation, reward updates, optimizer loading or writes occur.
#define main afk_hub_trainer_main_unused
#include "ExampleMain.cpp"
#undef main

#include <GigaLearnCPP/Util/InferUnit.h>
#include <RLGymCPP/EnvSet/EnvSet.h>
#include <RLGymCPP/StateSetters/StateSetter.h>
#include <nlohmann/json.hpp>
#include <filesystem>
#include <iostream>
#include <cstdlib>
#include <string>
#include <algorithm>
#include <cmath>

using nlohmann::json;
namespace fs=std::filesystem;

static int kickoffSeed=12345;
class WatchKickoff:public RLGC::StateSetter {
 public:
 void ResetArena(RocketSim::Arena* arena) override {
  arena->ResetToRandomKickoff(kickoffSeed);
  for(auto* car:arena->_cars)car->controls=RocketSim::CarControls{};
 }
};
static RLGC::EnvCreateResult WatchEnvironment(int index) {
 auto result=EnvCreateFunc(index);
 result.stateSetter=new WatchKickoff(); // same short-lived setter convention as HubEval
 return result;
}
static std::string Arg(int argc,char**argv,const std::string&key,const std::string&def="") {
 for(int i=1;i+1<argc;i++)if(argv[i]==key)return argv[i+1];
 return def;
}
static json VecJ(const RocketSim::Vec&v){return json::array({v.x,v.y,v.z});}
static json PhysJ(const RocketSim::PhysState&p) {
 return {{"pos",VecJ(p.pos)},{"vel",VecJ(p.vel)},{"ang_vel",VecJ(p.angVel)},
         {"forward",VecJ(p.rotMat.forward)},{"right",VecJ(p.rotMat.right)},
         {"up",VecJ(p.rotMat.up)}};
}
static json Snapshot(const RLGC::GameState&gs, int episode,int step,bool aBlue) {
 json j;
 j["type"]="frame";j["episode"]=episode;j["decision"]=step;
 j["a_blue"]=aBlue;
 j["goal"]=(bool)gs.goalScored;
 j["ball"]=PhysJ(gs.ball);
 j["boost_pad_states"]=json::array();
 for(bool pad:gs.boostPads)j["boost_pad_states"].push_back(pad);
 j["cars"]=json::array();
 for(const auto&p:gs.players) {
  json c={{"id",p.carId},{"team",p.team==RocketSim::Team::BLUE?0:1},
          {"phys",PhysJ(p)},{"boost",p.boost},{"on_ground",p.isOnGround},
          {"demoed",p.isDemoed},{"has_flip",p.HasFlipOrJump()},
          {"ball_touched",p.ballTouchedStep}};
  j["cars"].push_back(c);
 }
 return j;
}
static bool SameAction(const RLGC::Action&a,const RLGC::Action&b) {
 for(size_t i=0;i<RLGC::Action::ELEM_AMOUNT;i++)if(a[i]!=b[i])return false;
 return true;
}
static int ActionIndex(const RLGC::Action&a,const RLGC::DefaultAction&parser) {
 for(int i=0;i<(int)parser.actions.size();i++)if(SameAction(a,parser.actions[i]))return i;
 throw std::runtime_error("GigaLearn action is not in default action table");
}
static void CheckWeights(const fs::path&p) {
 if(!fs::is_directory(p)||!fs::is_regular_file(p/"POLICY.lt")||
    !fs::is_regular_file(p/"SHARED_HEAD.lt"))
  throw std::runtime_error("Missing GigaLearn 1v1 model weights: "+p.string());
}
static void EmitFrame(const RLGC::GameState&state,int episode,int decision,bool aBlue) {
 std::cout<<Snapshot(state,episode,decision,aBlue).dump()<<'\n'<<std::flush;
}
int main(int argc,char**argv) {
 try {
  if(Arg(argc,argv,"--help")=="1") {
   std::cerr<<"GigaLearnWatch --a checkpoint --b checkpoint [--decisions 900]"
      " [--episodes 0] [--seed 12345] [--sample 0] [--gpu 0]\n";
   return 0;
  }
  fs::path pa=Arg(argc,argv,"--a"),pb=Arg(argc,argv,"--b");
  if(pa.empty()||pb.empty())throw std::runtime_error("Missing --a / --b paths");
  CheckWeights(pa);CheckWeights(pb);
  int decisions=std::stoi(Arg(argc,argv,"--decisions","900"));
  int episodes=std::stoi(Arg(argc,argv,"--episodes","0"));
  int seed=std::stoi(Arg(argc,argv,"--seed","12345"));
  bool sample=Arg(argc,argv,"--sample","0")=="1";
  bool gpu=Arg(argc,argv,"--gpu","0")=="1";
  if(decisions<60||decisions>9000||episodes<0||episodes>10000||seed<1)
    throw std::runtime_error("Invalid decisions / episodes / seed");
  const char*mesh=std::getenv("GIGALEARN_MESHES");
  if(!mesh||!fs::is_directory(mesh))throw std::runtime_error("GIGALEARN_MESHES missing");
  RocketSim::Init(mesh);
  RLGC::EnvSetConfig cfg={};cfg.envCreateFn=WatchEnvironment;
  cfg.numArenas=1;cfg.tickSkip=8;cfg.actionDelay=7;cfg.saveRewards=false;
  RLGC::EnvSet env(cfg);
  if(env.state.gameStates[0].players.size()!=2)
   throw std::runtime_error("Only 1v1 GigaLearn checkpoints supported by this viewer");
  auto*parser=dynamic_cast<RLGC::DefaultAction*>(env.actionParsers[0]);
  if(!parser)throw std::runtime_error("DefaultAction parser required");
  GGL::PartialModelConfig shared={},actor={};
  shared.layerSizes={256,256};shared.addOutputLayer=false;
  actor.layerSizes={256,256,256};
  shared.activationType=actor.activationType=GGL::ModelActivationType::RELU;
  shared.optimType=actor.optimType=GGL::ModelOptimType::ADAM;
  shared.addLayerNorm=actor.addLayerNorm=true;
  int obsSize=env.obsSize;
  GGL::InferUnit modelA(new RLGC::AdvancedObs(),obsSize,new RLGC::DefaultAction(),
      shared,actor,pa,gpu);
  GGL::InferUnit modelB(new RLGC::AdvancedObs(),obsSize,new RLGC::DefaultAction(),
      shared,actor,pb,gpu);
  std::cerr<<"WATCH READY: "<<pa<<" vs "<<pb<<" | obs="<<obsSize<<" | sample="<<sample<<std::endl;
  for(int ep=0;episodes==0||ep<episodes;ep++){
    const bool aBlue=ep%2==0;
    kickoffSeed=seed+(ep/2)*9973;
    env.ResetArena(0);
    modelA.obsBuilder->Reset(env.state.gameStates[0]);
    modelB.obsBuilder->Reset(env.state.gameStates[0]);
    EmitFrame(env.state.gameStates[0],ep+1,0,aBlue);
    int blueTouches=0,orangeTouches=0;
    for(int step=1;step<=decisions;step++){
      const auto&state=env.state.gameStates[0];
      std::vector<int>actionIDs;
      actionIDs.reserve(state.players.size());
      for(const auto&player:state.players){
        bool isA=(player.team==RocketSim::Team::BLUE)==aBlue;
        auto action=(isA?modelA:modelB).InferAction(player,state,!sample);
        actionIDs.push_back(ActionIndex(action,*parser));
      }
      env.StepFirstHalf(false);
      env.StepSecondHalf(actionIDs,false);
      const auto&next=env.state.gameStates[0];
      for(const auto&p:next.players)if(p.ballTouchedStep) {
       if(p.team==RocketSim::Team::BLUE)blueTouches++;else orangeTouches++;
      }
      EmitFrame(next,ep+1,step,aBlue);
      if(next.goalScored)break;
    }
    std::cerr<<"EPISODE "<<ep+1<<" | blue touches "<<blueTouches
       <<" | orange touches "<<orangeTouches<<std::endl;
  }
  return 0;
 } catch(const std::exception&e) {
  std::cerr<<"[WATCH ERROR] "<<e.what()<<std::endl;
  return 2;
 }
}
