#pragma once
#include <GigaLearnCPP/PPO/GAE.h>
#include "native_features.h"
#include <nlohmann/json.hpp>
namespace GF {
inline int SelfTest(){
 torch::set_num_threads(1);
 auto rewards=torch::tensor({1.f,2.f,3.f,4.f});
 auto terminals=torch::tensor({0,2,0,2},torch::kInt8);
 auto values=torch::tensor({.1f,.2f,.3f,.4f});
 auto ends=torch::tensor({5.f,7.f});
 torch::Tensor adv,target,returns;float clip;
 GGL::GAE::Compute(rewards,terminals,values,ends,adv,target,returns,clip,.9f,.8f,1,0);
 auto expected=torch::tensor({5.616f,6.3f,10.188f,9.9f});
 if(!torch::allclose(adv,expected,1e-5,1e-5))throw std::runtime_error("GAE timeout bootstrap test failed");
 GGL::GAE::Compute(torch::tensor({3.f}),torch::tensor({1},torch::kInt8),torch::tensor({.25f}),{},adv,target,returns,clip,.9f,.8f,1,0);
 if(std::abs(adv.item<float>()-2.75f)>1e-6)throw std::runtime_error("GAE terminal read test failed");
 if(CAR_CONFIG_BREAKOUT.hitboxSize.x==CAR_CONFIG_OCTANE.hitboxSize.x)throw std::runtime_error("Body presets are identical");
 Actions parser(true);if(parser.GetActionAmount()!=90)throw std::runtime_error("Action count mismatch");
 // PBRS telescopes under the same discount. Truncation keeps the next
 // potential; only a true scored goal zeros it.
 for(auto weights:std::vector<std::array<float,5>>{{.35f,.1f,0,0,0},{.35f,.15f,.25f,.1f,.05f},{.2f,.15f,.05f,.4f,.05f},{.15f,.2f,0,.15f,.3f}}){
  GoalPotential reward(.9f,weights);GameState a,b,c;
  Player pa={},pb={},pc={};pa.team=pb.team=pc.team=Team::BLUE;
  pa.pos={0,-1000,17};pb.pos={0,-500,17};pc.pos={0,100,17};
  a.ball.pos={0,0,93};b.ball.pos={0,700,93};c.ball.pos={0,1500,93};
  a.players={pa};b.players={pb};c.players={pc};
  pb.prev=&pa;pc.prev=&pb;b.prev=&a;c.prev=&b;
  float r1=reward.GetReward(pb,b,false),r2=reward.GetReward(pc,c,true);
  float expected=-reward.Phi(pa,a)+.81f*reward.Phi(pc,c);
  if(std::abs(r1+.9f*r2-expected)>1e-5)throw std::runtime_error("PBRS fragment telescoping failed");
  c.goalScored=true;
  float terminal=reward.GetReward(pc,c,true);
  if(std::abs(r1+.9f*terminal-(-reward.Phi(pa,a)+9.f))>1e-5)throw std::runtime_error("PBRS terminal potential failed");
 }
 std::cout<<"RESEARCH_FIXED_ROLLOUT_PBRS_GAE_SELFTEST_PASS"<<std::endl;
 std::cout<<"NATIVE_GAE_TERMINAL_TIMEOUT_ORDER_BODY_ACTION_TESTS_PASS"<<std::endl;
 return 0;
}
inline int Features(const std::string& family,const char* input,const char* output,const char* slots){
 std::ifstream in(input,std::ios::binary), slotInput(slots);
 if(!in||!slotInput)throw std::runtime_error("Missing native fixture input");
 auto slotList=nlohmann::json::parse(slotInput).get<std::vector<int>>();
 std::ofstream out(output,std::ios::binary);size_t row=0;
 auto f=[&](){float x;if(!in.read((char*)&x,4))throw std::runtime_error("Truncated fixture");return x;};
 auto vec=[&](){float x=f(),y=f(),z=f();return Vec(x,y,z);};
 auto write=[&](float x){out.write((char*)&x,4);};
 while(in.peek()!=EOF){
  GameState s;int controlled=int(f());s.ball.pos=vec();s.ball.vel=vec();s.ball.angVel=vec();
  for(int j=0;j<2;j++){
   Player p={};p.carId=j;p.team=Team(int(f()));p.pos=vec();p.vel=vec();p.angVel=vec();
   p.rotMat.forward=vec();p.rotMat.right=vec();p.rotMat.up=vec();
   p.boost=f();p.isOnGround=f();p.hasJumped=f();p.hasFlipped=f();p.hasDoubleJumped=f();p.airTimeSinceJump=f();
   for(int i=0;i<8;i++)p.prevAction[i]=f();s.players.push_back(p);
  }
  for(int i=0;i<34;i++){s.boostPadTimers[i]=f();s.boostPads[i]=s.boostPadTimers[i]==0;}
  for(int i=0;i<34;i++){s.boostPadTimersInv[i]=s.boostPadTimers[33-i];s.boostPadsInv[i]=s.boostPads[33-i];}
  Obs obs(family=="chronos",271);obs.forcedSlot=slotList.at(row++);
  for(int i=0;i<5;i++){PhysState p;p.pos=vec();p.vel=vec();obs.externalPrediction.push_back(p);}
  for(float x:obs.BuildObs(s.players[controlled],s))write(x);
  Actions parser(family=="chronos");for(auto x:parser.GetActionMask(s.players[controlled],s))write(x);
  for(const auto& a:parser.actions)for(float x:a)write(x);
 }
 return 0;
}
}
