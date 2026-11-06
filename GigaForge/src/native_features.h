#pragma once
#include <RLGymCPP/ObsBuilders/ObsBuilder.h>
#include <RLGymCPP/Gamestates/StateUtil.h>
#include <RLGymCPP/ActionParsers/DefaultAction.h>
#include <RLGymCPP/Rewards/Reward.h>
#include <RLGymCPP/Framework.h>
#include <Sim/BallPredTracker/BallPredTracker.h>
#include <random>
#include <array>

namespace GF {
using namespace RLGC;
inline bool Mirror(const Player& p) { return InvertPhys(p,p.team==Team::ORANGE).pos.x>0; }
class Actions : public DefaultAction {
 bool chronos,otherChronos;
 Team learnerTeam;
public:
 Actions(bool c,bool other,Team learner):chronos(c),otherChronos(other),learnerTeam(learner){}
 explicit Actions(bool c):Actions(c,c,Team::BLUE){}
 Action ParseAction(int index,const Player& p,const GameState& s) override {
  auto a=DefaultAction::ParseAction(index,p,s);
  if((p.team==learnerTeam?chronos:otherChronos) && Mirror(p)){a.steer=-a.steer;a.yaw=-a.yaw;a.roll=-a.roll;}
  return a;
 }
 std::vector<uint8_t> GetActionMask(const Player& p,const GameState& s) override {
  // RLBot's public packet has no contact normal. Use the same available
  // information in native collection, evaluation and exported controllers.
  if(p.worldContact.hasContact && !p.HasFlipOrJump()){
   auto visible=p;visible.worldContact.hasContact=false;
   return DefaultAction::GetActionMask(visible,s);
  }
  return DefaultAction::GetActionMask(p,s);
 }
};

class Obs : public ObsBuilder {
 bool chronos;
 std::mt19937 rng;
 std::unique_ptr<BallPredTracker> forecast;
 uint64_t lastPred=0;
 bool hasPred=false;
public:
 int forcedSlot=-1;
 int onlyTeam=-1;
 std::vector<PhysState> externalPrediction;
 Obs(bool c,unsigned seed):chronos(c),rng(seed){}
 void Reset(const GameState& s) override { hasPred=false; }
 void PlayerObs(FList& out,const Player& p,bool inv,bool mirror,const PhysState& ball) {
  auto phys=MirrorPhysX(InvertPhys(p,inv),mirror);
  out+=phys.pos/5000;out+=phys.rotMat.forward;out+=phys.rotMat.up;
  out+=phys.vel/2300;out+=phys.angVel/3;out+=phys.rotMat.Dot(phys.angVel)/3;
  out+=phys.rotMat.Dot(ball.pos-phys.pos)/5000;
  out+=phys.rotMat.Dot(ball.vel-phys.vel)/2300;
  out+=p.boost/100;out+=float(p.isOnGround);out+=float(p.HasFlipOrJump());
  out+=float(p.isDemoed);out+=float(p.hasJumped);
 }
 FList BuildObs(const Player& p,const GameState& s) override {
  if(s.players.size()!=2)throw std::runtime_error("GigaForge native contract is 1v1");
  if(onlyTeam>=0 && int(p.team)!=onlyTeam)return FList(chronos?225:258,0.f);
  bool inv=p.team==Team::ORANGE,mirror=chronos && Mirror(p);
  auto ball=MirrorPhysX(InvertPhys(s.ball,inv),mirror);
  FList out;out.reserve(chronos?225:258);
  out+=ball.pos/5000;out+=ball.vel/2300;out+=ball.angVel/3;
  Action prev=p.prevAction;
  if(mirror){prev.steer=-prev.steer;prev.yaw=-prev.yaw;prev.roll=-prev.roll;}
  for(float x:prev)out+=x;
  const auto& pads=s.GetBoostPads(inv);
  // Preserve the deployed Chronos timer orientation, including its quirk.
  const auto& timers=s.GetBoostPadTimers(chronos?inv:!inv);
  for(int i=0;i<34;i++){
   int idx=i;
   if(mirror){auto v=CommonValues::BOOST_LOCATIONS[i];
    for(int j=0;j<34;j++){auto b=CommonValues::BOOST_LOCATIONS[j];
     if(std::abs(b.x+v.x)<3 && std::abs(b.y-v.y)<3){idx=j;break;}}}
   out+=pads[idx]?1.f:1.f/(1.f+timers[idx]);
  }
  if(!chronos){
   auto own=InvertPhys(p,inv).pos;Vec relative={};float distance=1500*1500;
   for(int i:{3,4,15,18,29,30}){auto delta=CommonValues::BOOST_LOCATIONS[i]-own;
    float d=delta.x*delta.x+delta.y*delta.y;
    if(pads[i] && d<=distance){distance=d;relative=delta;}}
   out+=relative/5000;
  }
  PlayerObs(out,p,inv,mirror,ball);
  out.insert(out.end(),58,0.f);
  FList other;
  for(const auto& x:s.players)if(x.carId!=p.carId)PlayerObs(other,x,inv,mirror,ball);
  int slot=forcedSlot>=0?forcedSlot:std::uniform_int_distribution<int>(0,2)(rng);
  for(int i=0;i<3;i++)if(i==slot)out+=other;else out.insert(out.end(),29,0.f);
  if(!chronos){
   if(!externalPrediction.empty()){
    for(auto phys:externalPrediction){phys=InvertPhys(phys,inv);out+=phys.pos/5000;out+=phys.vel/2300;}
   }else{
    if(!s.lastArena)throw std::runtime_error("Galactus needs an arena for its ball forecast");
    if(!forecast)forecast=std::make_unique<BallPredTracker>(s.lastArena,273);
    if(!hasPred || s.lastTickCount<lastPred || s.lastTickCount-lastPred>=32){
     forecast->ForceUpdateAllPred(s.ball);lastPred=s.lastTickCount;hasPred=true;
    }
    int age=int(s.lastTickCount-lastPred);
    for(int t:{30,60,120,180,240}){auto phys=InvertPhys(forecast->predData.at(t+age),inv);out+=phys.pos/5000;out+=phys.vel/2300;}
   }
  }
  if(out.size()!=(chronos?225:258))throw std::runtime_error("Wrong native observation size");
  for(float x:out)if(!std::isfinite(x))throw std::runtime_error("Nonfinite native observation");
  return out;
 }
};

class GoalPotential : public Reward {
 float gamma;std::array<float,5> weights;
public:
 GoalPotential(float g,std::array<float,5> w={.35f,.1f,0.f,0.f,0.f}):gamma(g),weights(w){
  if(!(gamma>0 && gamma<1))throw std::runtime_error("Invalid shaping gamma");
  for(float x:w)if(!std::isfinite(x)||std::abs(x)>1)throw std::runtime_error("Invalid potential coefficient");
 }
 static std::array<float,5> Basis(const Player& p,const GameState& s){
  float dir=p.team==Team::BLUE?1.f:-1.f;
  float own=(s.ball.pos-p.pos).Length(),other=12000;
  for(const auto& x:s.players)if(x.team!=p.team)other=std::min(other,(s.ball.pos-x.pos).Length());
  float y=dir*s.ball.pos.y,v=dir*s.ball.vel.y;
  float threat=std::clamp((-y-2000.f)/3120.f,0.f,1.f)*std::clamp(-v/6000.f,0.f,1.f);
  return {y/5120.f,-std::min(own,12000.f)/6000.f,
   std::clamp(v/6000.f,-1.f,1.f),-threat,
   std::clamp((other-own)/6000.f,-1.f,1.f)*std::exp(-own/2500.f)};
 }
 float Phi(const Player& p,const GameState& s)const{
  auto b=Basis(p,s);float value=0;for(int i=0;i<5;i++)value+=weights[i]*b[i];return value;
 }
 float GetReward(const Player& p,const GameState& s,bool final) override {
  if(!s.prev || !p.prev)return 0;
  float goal=0;
  if(s.goalScored)goal=((s.ball.pos.y>0)==(p.team==Team::BLUE))?10.f:-10.f;
  // Truncation is a sampling boundary, not a task terminal: retain Phi(s').
  return goal+gamma*(s.goalScored?0.f:Phi(p,s))-Phi(*p.prev,*s.prev);
 }
 std::string GetName() override{return "goal-potential-native-v2";}
};
}
