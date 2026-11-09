#pragma once
#include "native_features.h"
#include <nlohmann/json.hpp>

namespace GF {
inline void ValidateStationaryRecipe(const nlohmann::json& r){
 if(r.value("winrate_dominance_reward",false))
  throw std::runtime_error("Legacy winrate-dominance counters include BOTH players; use a NEW stationary pilot run. Do not resume an old objective in place.");
 if(!r.contains("stationary_objective"))return;
 auto objective=r.at("stationary_objective").get<std::string>();
 if(objective!="goal_only" && objective!="goal_potential")throw std::runtime_error("Unknown stationary objective");
 for(auto flag:{"mechanics_reward","defensive_mechanics_reward","validated_antidive_reward"})
  if(r.value(flag,false))throw std::runtime_error("Stationary objectives cannot enable event bonuses");
 if(r.value("defensive_curriculum_prob",0.f)!=0.f)throw std::runtime_error("Stationary control pilot requires the same kickoff distribution in both arms");
 float temp=r.value("policy_temperature",1.f);
 if(!std::isfinite(temp) || temp<=0)throw std::runtime_error("Invalid policy temperature");
 if(!r.value("fixed_rollout",false))throw std::runtime_error("Stationary pilot requires complete fixed rollouts");
}

inline int StationarySelfTest(){
 using nlohmann::json;
 GameState previous,state;previous.players.resize(2);state.players.resize(2);
 for(int i=0;i<2;i++){
  previous.players[i].team=state.players[i].team=Team(i);
  previous.players[i].carId=state.players[i].carId=i+1;
  state.players[i].prev=&previous.players[i];
 }
 state.prev=&previous;state.goalScored=true;state.ball.pos=Vec(0,5200,93);
 WinRateDominanceGoalPotential::ResetStats();
 WinRateDominanceGoalPotential legacy(.999f,{0,0,0,0,0},2.f);
 GoalPotential stationary(.999f,{0,0,0,0,0});
 for(int i=0;i<100;i++){
  legacy.GetAllRewards(state,true);auto values=stationary.GetAllRewards(state,true);
  if(values[0]!=10.f || values[1]!=-10.f)throw std::runtime_error("Stationary goal signs failed");
 }
 float reported=WinRateDominanceGoalPotential::CurrentWinRate();
 if(reported!=.5f)throw std::runtime_error("Legacy reward reproduction changed; review source");
 state.ball.pos.y=-5200;auto values=stationary.GetAllRewards(state,true);
 if(values[0]!=-10.f || values[1]!=10.f)throw std::runtime_error("Orange goal signs failed");
 state.goalScored=false;values=stationary.GetAllRewards(state,false);
 if(values[0]!=0.f || values[1]!=0.f)throw std::runtime_error("Goal-only paid a non-goal bonus");
 bool rejected=false;
 try{ValidateStationaryRecipe(json{{"winrate_dominance_reward",true}});}catch(const std::exception&){rejected=true;}
 if(!rejected)throw std::runtime_error("Invalid legacy objective was accepted");
 std::cout<<json({{"stationary_goal_signs_pass",true},{"non_goal_bonus",0},
  {"legacy_test_blue_goals",100},{"legacy_reported_win_rate",reported},
  {"legacy_counter_cancellation_reproduced",true},{"legacy_training_rejected",true}}).dump()<<std::endl;
 return 0;
}
}
