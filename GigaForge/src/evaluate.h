#pragma once
#include "native_features.h"
#include <GigaLearnCPP/PPO/PPOLearner.h>
#include <RLGymCPP/ThreadPool.h>
#include <nlohmann/json.hpp>
#include <memory>
#include <deque>

namespace GF {
using namespace GGL;using nlohmann::json;
struct EvalModel { ModelSet model;bool chronos;std::string body; };

struct StepSnapshot {
 bool unreachableDive=false;
 bool overcommitted=false;
 bool boostDetour=false;
 bool outsideThreatLane=false;
 bool airborneNoTouch=false;
};

struct EvalGame {
 std::unique_ptr<Arena> arena;
 GameState state,previous;
 int subject,opponent,side,seed,goalCount=0,forGoals=0,againstGoals=0;
 bool candidate;
 std::string opponentName;
 std::string scenarioMode="match";
 std::array<std::unique_ptr<Obs>,2> obs;
 std::vector<Action> planned=std::vector<Action>(2);
 // RocketSim's default respawn RNG is thread-local. Persist its state per
 // match so paired actors cannot receive different respawns just because the
 // worker scheduler assigned them to different threads.
 std::default_random_engine random;

 // Objective defensive & offensive telemetry
 int savesAndClears=0;
 int failedChallenges=0;
 int attackingShots=0;
 int oppPossessionSteps=0;
 int goalsideShadowSteps=0;
 int ballInOppHalfSteps=0;
 int passiveNetCampSteps=0;
 int pendingChallengeTimer=0;
 bool pendingChallengeTouched=false;

 // Concession forensics (3.0s = 45 decisions prior to each conceded goal)
 std::deque<StepSnapshot> window;
 int concedeUnreachableDive=0;
 int concedeOvercommitBehindBall=0;
 int concedeBoostDetour=0;
 int concedeNotGoalsideLane=0;
 int concedeSlowRecovery=0;

 void Step(int ticks){
  auto& worker=RocketSim::Math::GetRandEngine();worker=random;
  arena->Step(ticks);random=worker;
 }
 void Reset(){
  auto& worker=RocketSim::Math::GetRandEngine();worker.seed(seed+goalCount*1000003);
  if(scenarioMode=="defensive_threats"){
   std::mt19937 scenRng(static_cast<unsigned>(seed+goalCount*1000003));
   ApplyDefensiveScenario(arena.get(),Team(side),(seed+goalCount)%6,scenRng);
  }else{
   arena->ResetToRandomKickoff();
  }
  random=worker;
  state=GameState(arena.get());previous=GameState();
  for(auto& builder:obs)builder->Reset(state);
  window.clear();
  pendingChallengeTimer=0;
  pendingChallengeTouched=false;
 }

 void RecordTelemetry(){
  if(state.players.size()!=2)return;
  const Player* subj=nullptr;
  for(const auto& p:state.players)if(int(p.team)==side){subj=&p;break;}
  if(!subj)return;
  float dir=(side==0)?1.f:-1.f;
  auto t=AssessTactical(*subj,state);
  Vec toBall=state.ball.pos-subj->pos;
  Vec dirToBall=MechanicsGoalPotential::UnitVec(toBall);
  float closingToBall=subj->vel.Dot(dirToBall);

  // 1. Track opponent possession & goalside shadowing
  if(t.oppControl>0.30f){
   oppPossessionSteps++;
   if(t.isGoalside && t.distToThreatLine<700.f)goalsideShadowSteps++;
  }

  // 2. Track passive net camping when ball is in opponent half
  if(dir*state.ball.pos.y>600.f){
   ballInOppHalfSteps++;
   if(dir*subj->pos.y<-4350.f && subj->vel.Length()<450.f)passiveNetCampSteps++;
  }

  // 3. Track optimistic / unreachable challenge initiation (validated against retreats and recoveries)
  bool initiatedCommit=t.validatedDive;
  if(pendingChallengeTimer>0){
   if(subj->ballTouchedStep)pendingChallengeTouched=true;
   pendingChallengeTimer--;
   if(pendingChallengeTimer==0 && !pendingChallengeTouched)failedChallenges++;
  }else if(initiatedCommit && !subj->ballTouchedStep){
   pendingChallengeTimer=15;
   pendingChallengeTouched=false;
  }

  // 4. Track saves/clears and attacking on-target shots on ball touch
  if(subj->ballTouchedStep && previous.players.size()==2){
   float dvy=dir*(state.ball.vel.y-previous.ball.vel.y);
   float vy=dir*state.ball.vel.y;
   float prevInward=-dir*previous.ball.vel.y;
   if(dir*state.ball.pos.y<-900.f && (prevInward>300.f || t.danger>0.25f) && dvy>350.f){
    savesAndClears++;
   }
   if(dir*state.ball.pos.y>-500.f && dvy>200.f && vy>750.f){
    float dtGoal=std::max(0.05f,(5120.f-dir*state.ball.pos.y)/std::max(200.f,vy));
    float projX=state.ball.pos.x+state.ball.vel.x*dtGoal;
    if(std::abs(projX)<1150.f)attackingShots++;
   }
  }

  // 5. Push snapshot to 45-decision (3.0s) pre-concession ring buffer
  StepSnapshot snap;
  snap.unreachableDive=initiatedCommit && !subj->ballTouchedStep;
  snap.overcommitted=t.isOvercommitted;
  Vec velHoriz(subj->vel.x,subj->vel.y,0.f);
  bool movingToSideWall=(std::abs(subj->pos.x)>2100.f && subj->pos.x*subj->vel.x>300.f*2100.f);
  snap.boostDetour=(t.danger>0.25f && !t.isGoalside && subj->boost<65.f && movingToSideWall && t.distToThreatLine>900.f);
  snap.outsideThreatLane=(!t.isGoalside || t.distToThreatLine>620.f);
  snap.airborneNoTouch=(!subj->isOnGround && subj->pos.z>55.f && !subj->ballTouchedStep);
  window.push_back(snap);
  if(window.size()>45)window.pop_front();
 }

 void RecordConcessionForensics(){
  bool hadDive=false,hadOvercommit=false,hadBoostDetour=false,hadOutsideLaneNearEnd=false;
  int airSteps=0;
  int n=int(window.size());
  for(int i=0;i<n;i++){
   const auto& s=window[i];
   if(s.unreachableDive)hadDive=true;
   if(s.overcommitted)hadOvercommit=true;
   if(s.boostDetour)hadBoostDetour=true;
   if(s.airborneNoTouch)airSteps++;
   if(i>=std::max(0,n-15) && s.outsideThreatLane)hadOutsideLaneNearEnd=true;
  }
  if(hadDive)concedeUnreachableDive++;
  if(hadOvercommit)concedeOvercommitBehindBall++;
  if(hadBoostDetour)concedeBoostDetour++;
  if(hadOutsideLaneNearEnd)concedeNotGoalsideLane++;
  if(airSteps>=12)concedeSlowRecovery++;
 }
};

inline json Evaluate(const json& spec,torch::Device device,std::function<void(PPOLearnerConfig&,const std::string&)> shape){
 const int64_t requestedSeed=spec.at("seed").get<int64_t>();
 const int64_t requestedPairs=spec.at("pairs").get<int64_t>();
 if(requestedPairs<1 || requestedPairs>10000 || spec.at("opponents").empty())
  throw std::runtime_error("Invalid evaluation pairs/opponents");
 if(requestedSeed<0 || requestedSeed>2000000000-requestedPairs-10000*int64_t(spec.at("opponents").size()))
  throw std::runtime_error("Evaluation seed outside supported signed range (maximum 2000000000)");
 const double requestedSeconds=spec.at("seconds").get<double>();
 if(!std::isfinite(requestedSeconds) || requestedSeconds<=0 || requestedSeconds>3600 ||
    std::abs(requestedSeconds*15-std::round(requestedSeconds*15))>1e-8)
  throw std::runtime_error("Invalid evaluation duration; use a positive multiple of 1/15 second");
 std::vector<EvalModel> models;
 auto add=[&](const json& descriptor){
  PPOLearnerConfig config;shape(config,descriptor.at("family"));
  EvalModel entry;entry.chronos=descriptor.at("family")=="chronos";entry.body=descriptor.at("hitbox");
  PPOLearner::MakeModels(false,entry.chronos?225:258,90,config.sharedHead,config.policy,config.critic,device,entry.model);
  entry.model.Load(descriptor.at("path").get<std::string>(),false,false);models.push_back(entry);
 };
 bool compareBaseline=spec.value("compare_baseline",true);
 std::string scenarioMode=spec.value("scenario_mode",std::string("match"));
 add(spec.at("candidate"));
 if(compareBaseline)add(spec.at("baseline"));else models.emplace_back();
 for(const auto& o:spec.at("opponents"))add(o);
 std::vector<std::unique_ptr<EvalGame>> games;
 int pairs=spec.at("pairs"),seed=spec.at("seed"),ticks=int(std::round(spec.at("seconds").get<double>()*15));
 for(size_t o=0;o<spec["opponents"].size();o++)for(int p=0;p<pairs;p++)for(int side=0;side<2;side++)for(int candidate=compareBaseline?0:1;candidate<2;candidate++){
  auto g=std::make_unique<EvalGame>();g->subject=candidate?0:1;g->opponent=int(o)+2;g->candidate=candidate;
  g->side=side;g->seed=seed+int(o)*10000+p;g->opponentName=spec["opponents"][o]["name"];
  g->scenarioMode=scenarioMode;
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
   g.RecordTelemetry();
   if(g.state.goalScored){
    bool scored=(g.state.ball.pos.y>0)==(g.side==0);
    if(!scored)g.RecordConcessionForensics();
    g.forGoals+=scored;g.againstGoals+=!scored;g.goalCount++;g.Reset();
   }
  },int(games.size()),false);
  if(decision%150==0)std::cout<<"NATIVE_EVAL "<<decision/15<<"/"<<ticks/15<<"s across "<<games.size()<<" games"<<std::endl;
 }
 json result={{"trials",json::array()},{"baseline_trials",json::array()}};
 for(auto& g:games){
  json row={
   {"opponent",g->opponentName},{"seed",g->seed},{"side",g->side},{"scenario",g->scenarioMode},
   {"goals_for",g->forGoals},{"goals_against",g->againstGoals},
   {"outcome",(g->forGoals>g->againstGoals)-(g->forGoals<g->againstGoals)},{"seconds",ticks/15.},
   {"saves_and_clears",g->savesAndClears},
   {"failed_challenges",g->failedChallenges},
   {"attacking_shots",g->attackingShots},
   {"opp_possession_steps",g->oppPossessionSteps},
   {"goalside_shadow_steps",g->goalsideShadowSteps},
   {"ball_in_opp_half_steps",g->ballInOppHalfSteps},
   {"passive_net_camp_steps",g->passiveNetCampSteps},
   {"concede_unreachable_dive",g->concedeUnreachableDive},
   {"concede_overcommit_behind_ball",g->concedeOvercommitBehindBall},
   {"concede_boost_detour",g->concedeBoostDetour},
   {"concede_not_goalside_lane",g->concedeNotGoalsideLane},
   {"concede_slow_recovery",g->concedeSlowRecovery}
  };
  result[g->candidate?"trials":"baseline_trials"].push_back(row);
 }
 result["wall_seconds"]=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
 result["player_decisions"]=ticks*games.size()*2;
 result["evaluation_protocol"]="arena-rng-v4";
 result["direct_head_to_head"]=!compareBaseline;
 for(auto& model:models)model.model.Free();
 return result;
}
}
