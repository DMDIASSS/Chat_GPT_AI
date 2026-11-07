#pragma once
#include "native_features.h"
#include <GigaLearnCPP/PPO/PPOLearner.h>
#include <RLGymCPP/ThreadPool.h>
#include <nlohmann/json.hpp>
#include <memory>

namespace GF {
using namespace GGL;using nlohmann::json;
struct EvalModel { ModelSet model;bool chronos;std::string body; };
struct EvalGame {
 std::unique_ptr<Arena> arena;
 GameState state,previous;
 int subject,opponent,side,seed,goalCount=0,forGoals=0,againstGoals=0;
 bool candidate;
 std::string opponentName;
 std::array<std::unique_ptr<Obs>,2> obs;
 std::vector<Action> planned=std::vector<Action>(2);
 // RocketSim's default respawn RNG is thread-local. Persist its state per
 // match so paired actors cannot receive different respawns just because the
 // worker scheduler assigned them to different threads.
 std::default_random_engine random;
 void Step(int ticks){
  auto& worker=RocketSim::Math::GetRandEngine();worker=random;
  arena->Step(ticks);random=worker;
 }
 void Reset(){
  auto& worker=RocketSim::Math::GetRandEngine();worker.seed(seed+goalCount*1000003);
  arena->ResetToRandomKickoff();
  random=worker;
  state=GameState(arena.get());previous=GameState();
  for(auto& builder:obs)builder->Reset(state);
 }
};
inline json Evaluate(const json& spec,torch::Device device,std::function<void(PPOLearnerConfig&,const std::string&)> shape){
 std::vector<EvalModel> models;
 auto add=[&](const json& descriptor){
  PPOLearnerConfig config;shape(config,descriptor.at("family"));
  EvalModel entry;entry.chronos=descriptor.at("family")=="chronos";entry.body=descriptor.at("hitbox");
  PPOLearner::MakeModels(false,entry.chronos?225:258,90,config.sharedHead,config.policy,config.critic,device,entry.model);
  entry.model.Load(descriptor.at("path").get<std::string>(),false,false);models.push_back(entry);
 };
 add(spec.at("candidate"));add(spec.at("baseline"));for(const auto& o:spec.at("opponents"))add(o);
 std::vector<std::unique_ptr<EvalGame>> games;
 int pairs=spec.at("pairs"),seed=spec.at("seed"),ticks=int(std::round(spec.at("seconds").get<double>()*15));
 for(size_t o=0;o<spec["opponents"].size();o++)for(int p=0;p<pairs;p++)for(int side=0;side<2;side++)for(int candidate=0;candidate<2;candidate++){
  auto g=std::make_unique<EvalGame>();g->subject=candidate?0:1;g->opponent=int(o)+2;g->candidate=candidate;
  g->side=side;g->seed=seed+int(o)*10000+p;g->opponentName=spec["opponents"][o]["name"];
  g->arena.reset(Arena::Create(GameMode::SOCCAR));
  for(int team=0;team<2;team++){
   auto& model=models[team==side?g->subject:g->opponent];
   g->arena->AddCar(Team(team),model.body=="breakout"?CAR_CONFIG_BREAKOUT:CAR_CONFIG_OCTANE);
   g->obs[team]=std::make_unique<Obs>(model.chronos,g->seed+team*113);
  }
  g->Reset();games.push_back(std::move(g));
 }
 struct Query {size_t game,player;};
 auto started=std::chrono::steady_clock::now();
 torch::NoGradGuard guard;
 for(int decision=0;decision<ticks;decision++){
  if(spec.contains("stop_file") && std::filesystem::exists(spec["stop_file"].get<std::string>()))throw std::runtime_error("Evaluation stopped");
  std::vector<std::vector<float>> features(models.size());std::vector<std::vector<uint8_t>> masks(models.size());
  std::vector<std::vector<Query>> indices(models.size());
  for(size_t i=0;i<games.size();i++){
   auto& g=*games[i];
   for(size_t p=0;p<g.state.players.size();p++){
    const auto& car=g.state.players[p];int team=int(car.team);int model=team==g.side?g.subject:g.opponent;
    features[model]+=g.obs[team]->BuildObs(car,g.state);
    Actions parser(models[model].chronos);auto mask=parser.GetActionMask(car,g.state);
    masks[model].insert(masks[model].end(),mask.begin(),mask.end());indices[model].push_back({i,p});
   }
  }
  // Physics advances held controls while the batched networks run.
  g_ThreadPool.StartBatchedJobs([&](int i){games[i]->Step(7);},int(games.size()),true);
  for(size_t m=0;m<models.size();m++)if(!indices[m].empty()){
   auto x=torch::tensor(features[m]).reshape({-1,models[m].chronos?225:258}).to(device);
   auto mask=torch::tensor(masks[m]).reshape({-1,90}).to(device);torch::Tensor actions;
   PPOLearner::InferActionsFromModels(models[m].model,x,mask,true,1,false,&actions,nullptr);
   auto ids=TENSOR_TO_VEC<int>(actions);Actions parser(models[m].chronos);
   for(size_t j=0;j<ids.size();j++){
    const auto& query=indices[m][j];auto& g=*games[query.game];
    g.planned[query.player]=parser.ParseAction(ids[j],g.state.players[query.player],g.state);
   }
  }
  g_ThreadPool.WaitUntilDone();
  g_ThreadPool.StartBatchedJobs([&](int i){
   auto& g=*games[i];
   for(size_t p=0;p<g.state.players.size();p++)g.arena->GetCar(g.state.players[p].carId)->controls=CarControls(g.planned[p]);
   g.Step(1);g.previous=g.state;g.state.UpdateFromArena(g.arena.get(),g.planned,&g.previous);
   if(g.state.goalScored){
    bool scored=(g.state.ball.pos.y>0)==(g.side==0);g.forGoals+=scored;g.againstGoals+=!scored;g.goalCount++;g.Reset();
   }
  },int(games.size()),false);
  if(decision%150==0)std::cout<<"NATIVE_EVAL "<<decision/15<<"/"<<ticks/15<<"s across "<<games.size()<<" games"<<std::endl;
 }
 json result={{"trials",json::array()},{"baseline_trials",json::array()}};
 for(auto& g:games){
  json row={{"opponent",g->opponentName},{"seed",g->seed},{"side",g->side},{"scenario","match"},
   {"goals_for",g->forGoals},{"goals_against",g->againstGoals},{"outcome",(g->forGoals>g->againstGoals)-(g->forGoals<g->againstGoals)},{"seconds",ticks/15.}};
  result[g->candidate?"trials":"baseline_trials"].push_back(row);
 }
 result["wall_seconds"]=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
 result["player_decisions"]=ticks*games.size()*2;
 result["evaluation_protocol"]="arena-rng-v3";
 for(auto& model:models)model.model.Free();
 return result;
}
}
