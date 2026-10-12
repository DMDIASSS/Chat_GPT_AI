#include <GigaLearnCPP/Learner.h>
#include <RLGymCPP/Rewards/CommonRewards.h>
#include <RLGymCPP/Rewards/ZeroSumReward.h>
#include <RLGymCPP/TerminalConditions/NoTouchCondition.h>
#include <RLGymCPP/TerminalConditions/GoalScoreCondition.h>
#include <RLGymCPP/ObsBuilders/AdvancedObs.h>
#include <RLGymCPP/StateSetters/KickoffState.h>
#include <RLGymCPP/ActionParsers/DefaultAction.h>
#include <torch/torch.h>
#include "PaddedObs.h"
#include "ReplayBank.h"
#include "ReplayBC.h"
#include "NativeProbe.h"
#include "Campaign.h"
#include "KickoffBC.h"
#include <cstdlib>
#include <iostream>
#include <filesystem>
using namespace GGL;
using namespace RLGC;
int games=16,players=1;bool campaign=false;
EnvCreateResult createEnv(int index) {
    EnvCreateResult r{};
    r.arena=Arena::Create(GameMode::SOCCAR);
    for(int i=0;i<players;i++){r.arena->AddCar(Team::BLUE);r.arena->AddCar(Team::ORANGE);}
    r.actionParser=campaign?static_cast<ActionParser*>(new CampaignAction()):new DefaultAction();r.obsBuilder=new PaddedObs();
    r.stateSetter=campaign?static_cast<StateSetter*>(new CampaignSetter()):new ReplayMixedSetter();
    r.terminalConditions={new NoTouchCondition(10),new GoalScoreCondition()};
    r.rewards={{new VelocityPlayerToBallReward(),campaign?.05f:.25f},
               {new ZeroSumReward(new VelocityBallToGoalReward(),1),campaign?.1f:1.f},
               {new StrongTouchReward(20,100),.1f},{new GoalReward(),10.f}};
    if(campaign)r.rewards.push_back({new SkillReward(),1.f});
    return r;
}
void envSet(const char* key,const std::string& value){
#ifdef _WIN32
    _putenv_s(key,value.c_str());
#else
    setenv(key,value.c_str(),1);
#endif
}
int main(int argc,char** argv){
 try{
    std::string meshes,checkpoint,device="cpu",bank,probe,probeOut;int steps=4096,iterations=2,threads=2,bcEpochs=0,width=128,depth=2;
    float oldChance=.4f;int saveEvery=0,kickoffEpochs=0,kickoffDemos=32;
    uint64_t decisionBudget=0;
    for(int i=1;i<argc;i++){
      std::string key=argv[i];if(i+1>=argc)throw std::runtime_error("Missing value for "+key);
      std::string value=argv[++i];
      if(key=="--meshes")meshes=value;else if(key=="--checkpoints")checkpoint=value;
      else if(key=="--probe")probe=value;else if(key=="--probe-out")probeOut=value;
      else if(key=="--campaign")campaign=std::stoi(value)!=0;else if(key=="--focus")campaignFocus=value;
      else if(key=="--old-chance")oldChance=std::stof(value);else if(key=="--save-every")saveEvery=std::stoi(value);
      else if(key=="--decisions")decisionBudget=std::stoull(value);
      else if(key=="--kickoff-epochs")kickoffEpochs=std::stoi(value);else if(key=="--kickoff-demos")kickoffDemos=std::stoi(value);
      else if(key=="--width")width=std::stoi(value);else if(key=="--depth")depth=std::stoi(value);else if(key=="--replay-bank")bank=value;else if(key=="--bc-epochs")bcEpochs=std::stoi(value);else if(key=="--device")device=value;else if(key=="--games")games=std::stoi(value);
      else if(key=="--steps")steps=std::stoi(value);else if(key=="--iterations")iterations=std::stoi(value);
      else if(key=="--threads")threads=std::stoi(value);else if(key=="--players")players=std::stoi(value);
      else throw std::runtime_error("Unknown argument "+key);
    }
    if(meshes.empty()||checkpoint.empty()||games<2||games>1024||steps<512||iterations<1||threads<1||threads>32||players<1||players>3||width<64||width>1024||depth<1||depth>6||bcEpochs<0||bcEpochs>10)
       throw std::runtime_error("Invalid/missing meshes, checkpoints or training limits");
    if(kickoffEpochs<0||kickoffEpochs>5||kickoffDemos<10||kickoffDemos>128)throw std::runtime_error("Invalid kickoff imitation budget");
    torch::set_num_threads(threads);torch::set_num_interop_threads(1);
    RocketSim::Init(meshes);
    LearnerConfig cfg{};cfg.numGames=games;cfg.tickSkip=8;cfg.actionDelay=1;cfg.randomSeed=20261012;
    cfg.deviceType=device=="cpu"?LearnerDeviceType::CPU:device=="cuda"?LearnerDeviceType::GPU_CUDA:LearnerDeviceType::AUTO;
    if(device!="cpu"&&device!="cuda"&&device!="auto")throw std::runtime_error("device must be cpu, cuda or auto");
    cfg.checkpointFolder=checkpoint;cfg.checkpointsToKeep=-1;cfg.tsPerSave=steps;
    if(saveEvery>0)cfg.tsPerSave=saveEvery;
    if(campaign){
        if(oldChance<0||oldChance>1)throw std::runtime_error("Invalid old-version probability");
        std::vector<std::string> focusOptions={"mixed","ground","defense","recovery","low_boost","aerial","wall","air_dribble","reset_use"};
        if(std::find(focusOptions.begin(),focusOptions.end(),campaignFocus)==focusOptions.end())throw std::runtime_error("Unknown practice focus");
        cfg.savePolicyVersions=true;cfg.trainAgainstOldVersions=true;cfg.trainAgainstOldChance=oldChance;
        cfg.tsPerVersion=steps*10;cfg.maxOldVersions=16;
    }
    cfg.sendMetrics=false;cfg.renderMode=false;cfg.addRewardsToMetrics=false;
    cfg.ppo.tsPerItr=steps;cfg.ppo.batchSize=steps;cfg.ppo.miniBatchSize=steps;cfg.ppo.epochs=1;
    cfg.ppo.policyLR=1e-4;cfg.ppo.criticLR=1e-4;cfg.ppo.entropyScale=.02;cfg.ppo.gaeGamma=.995;
    cfg.ppo.sharedHead.layerSizes={width,width};cfg.ppo.policy.layerSizes=std::vector<int>(depth,width);cfg.ppo.critic.layerSizes=std::vector<int>(depth,width);
    cfg.ppo.sharedHead.addLayerNorm=true;cfg.ppo.policy.addLayerNorm=true;cfg.ppo.critic.addLayerNorm=true;
    envSet("SLATER_GL_NO_KEY_THREAD","1");
    if(!bank.empty()){replayBank=std::make_shared<ReplayBank>(bank);if(replayBank->players!=2*players)throw std::runtime_error("Replay bank player count differs");}
    Learner* learner=new Learner(createEnv,cfg,[](Learner* l,const std::vector<GameState>&,Report&){
        static uint64_t last=uint64_t(-1);
        if(replayBank&&last!=l->totalIterations){std::cout<<"SLATER_REPLAY_RESETS count="<<replayResetCount.load()<<std::endl;last=l->totalIterations;}
        static uint64_t lastCampaign=uint64_t(-1);
        if(campaign&&lastCampaign!=l->totalIterations){
            std::cout<<"SLATER_PRACTICE_RESETS count="<<practiceResets.load()<<" frozen_script_ticks="<<frozenScriptTicks.load()<<std::endl;lastCampaign=l->totalIterations;
        }
    });
    if(!probe.empty()){if(probeOut.empty())throw std::runtime_error("Missing probe output");nativeProbe(learner,probe,probeOut);return 0;}
    replayBC(learner,bcEpochs);
    kickoffBC(learner,kickoffEpochs,kickoffDemos);
    envSet("SLATER_GL_STOP_ITERATION",std::to_string(learner->totalIterations+iterations));
    if(decisionBudget)envSet("SLATER_GL_STOP_TIMESTEP",std::to_string(learner->totalTimesteps+decisionBudget));
    std::cout<<"SLATER_GIGA_BEGIN games="<<games<<" steps="<<steps<<" device="<<device<<" architecture=GIGALEARN_MLP"<<std::endl;
    learner->Start();
    return 0;
 }catch(const std::exception& e){std::cerr<<"SLATER_GIGA_ERROR "<<e.what()<<std::endl;return 1;}
}
