#pragma once
#include <RLGymCPP/ObsBuilders/ObsBuilder.h>
#include <RLGymCPP/Gamestates/StateUtil.h>
#include <RLGymCPP/ActionParsers/DefaultAction.h>
#include <RLGymCPP/Rewards/Reward.h>
#include <RLGymCPP/StateSetters/StateSetter.h>
#include <RLGymCPP/Framework.h>
#include <Sim/BallPredTracker/BallPredTracker.h>
#include <random>
#include <array>
#include <cmath>
#include <algorithm>
#include <atomic>

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

class MechanicsGoalPotential : public Reward {
 float gamma,mechScale;std::array<float,5> weights;
public:
 MechanicsGoalPotential(float g,std::array<float,5> w={.35f,.15f,.30f,.15f,.20f},float ms=1.f):gamma(g),mechScale(ms),weights(w){
  if(!(gamma>0 && gamma<1))throw std::runtime_error("Invalid shaping gamma");
  if(!std::isfinite(mechScale)||mechScale<0||mechScale>10)throw std::runtime_error("Invalid mechanics scale");
  for(float x:w)if(!std::isfinite(x)||std::abs(x)>1)throw std::runtime_error("Invalid potential coefficient");
 }
 static Vec UnitVec(const Vec& v){
  float len=v.Length();return len>1e-5f?v/len:Vec(0,0,0);
 }
 float Phi(const Player& p,const GameState& s)const{
  auto b=GoalPotential::Basis(p,s);
  float value=0;for(int i=0;i<5;i++)value+=weights[i]*b[i];
  float oppBoost=p.boost;
  for(const auto& x:s.players)if(x.team!=p.team)oppBoost=x.boost;
  Vec toBall=s.ball.pos-p.pos;float dist=toBall.Length();
  float closing=std::clamp(p.vel.Dot(UnitVec(toBall))/2300.f,-1.f,1.f)*std::exp(-dist/3000.f);
  value+=0.08f*((p.boost-oppBoost)/100.f)+0.06f*closing;
  return value;
 }
 float GetReward(const Player& p,const GameState& s,bool final) override {
  if(!s.prev || !p.prev)return 0;
  float dir=p.team==Team::BLUE?1.f:-1.f;
  float goal=0;
  if(s.goalScored)goal=((s.ball.pos.y>0)==(p.team==Team::BLUE))?10.f:-10.f;
  float base=goal+gamma*(s.goalScored?0.f:Phi(p,s))-Phi(*p.prev,*s.prev);
  if(mechScale<=0.f)return base;

  float bonus=0.f;
  Vec delta=s.ball.pos-p.pos;float dist=delta.Length();Vec dirToBall=UnitVec(delta);
  float speed=p.vel.Length(),closingSpeed=p.vel.Dot(dirToBall);
  bool freeAir=!p.isOnGround && !p.worldContact.hasContact && p.pos.z>190.f;

  // 1. Speedflip kickoff & supersonic approach
  if(dist<2600.f && closingSpeed>1350.f && p.isFlipping && p.prevAction.pitch<-0.5f && std::abs(p.prevAction.yaw+p.prevAction.roll)>0.5f){
   bonus+=0.010f*std::clamp(closingSpeed/2200.f,0.5f,1.2f);
  }

  // 2. Touch mechanics: supersonic first-touch, power shots on target, aerial pops, reset flip-shots
  if(p.ballTouchedStep){
   float dvy=dir*(s.ball.vel.y-s.prev->ball.vel.y);
   float vy=dir*s.ball.vel.y;
   if(speed>1550.f && dvy>200.f){
    bonus+=0.06f*std::clamp(dvy/1500.f,0.f,1.5f);
   }
   if(dvy>250.f && vy>850.f){
    float dtGoal=std::max(0.05f,(5120.f-dir*s.ball.pos.y)/std::max(200.f,vy));
    float projX=s.ball.pos.x+s.ball.vel.x*dtGoal;
    if(std::abs(projX)<1150.f && s.ball.pos.z<1800.f){
     bonus+=0.12f*std::clamp(vy/2100.f,0.2f,1.5f);
    }
   }
   if(freeAir && s.ball.pos.z>260.f && vy>200.f){
    bonus+=0.10f*std::clamp(s.ball.pos.z/900.f,0.2f,1.4f);
    if(p.isFlipping && vy>550.f){
     bonus+=0.22f*std::clamp(vy/1800.f,0.4f,1.5f);
    }
   }
  }

  // 3. Air-dribble carry toward opponent net
  if(freeAir && s.ball.pos.z>280.f && dist<230.f && (s.ball.vel-p.vel).Length()<620.f && dir*s.ball.vel.y>280.f && p.rotMat.forward.Dot(dirToBall)>0.35f){
   bonus+=0.016f*std::clamp(dir*s.ball.vel.y/1400.f,0.3f,1.2f);
  }

  // 4. Flip-reset & Maktuf / 360 spin reset acquisition on ball
  if(freeAir && s.ball.pos.z>270.f && dist<190.f && (-p.rotMat.up).Dot(dirToBall)>0.55f){
   if(p.HasFlipOrJump() && !p.prev->HasFlipOrJump()){
    float spinMult=(p.angVel.Length()>1.9f)?1.5f:1.0f;
    bonus+=0.28f*spinMult;
   }
  }

  return base+mechScale*bonus;
 }
 std::string GetName() override{return "mechanics-goal-potential-v1";}
};

// Physics-informed reachability, possession, scoring danger & shadow coverage.
struct TacticalState {
 float ownDist=12000.f,oppDist=12000.f;
 float etaSelf=5.f,etaOpp=5.f,etaMargin=0.f; // etaMargin = etaOpp - etaSelf (>0 means self reaches first)
 float oppControl=0.f;  // [0, 1] opponent controllability & earlier arrival
 float danger=0.f;      // [0, 1] credible scoring danger toward own net
 float attackGate=1.f;  // [0, 1] feasibility of challenging / attacking the ball directly
 float defendGate=0.f;  // [0, 1] need for shadow / goal-line intercept coverage
 Vec ownGoal=Vec(0,0,0),interceptPos=Vec(0,0,0);
 float distToIntercept=0.f,distToThreatLine=0.f;
 bool isGoalside=true;
 bool isStrictlyGoalside=false;
 bool isOvercommitted=false;
 float unreachableThreatGate=0.f;
 bool isUpfieldLunge=false;
 bool validatedDive=false;
 float velTowardOwnGoal=0.f;
 float velAlongThreat=0.f;
};

inline float EstimateKinematicETA(const Player& c,const PhysState& ball){
 constexpr float ACTION_DELAY=7.f/120.f; // 58.33 ms control delay
 Vec posAfterDelay=c.pos+c.vel*ACTION_DELAY;
 Vec ballAfterDelay=ball.pos+ball.vel*ACTION_DELAY;

 Vec toBall0=ballAfterDelay-posAfterDelay;
 float rawDist=std::max(0.f,toBall0.Length()-140.f);
 Vec d0=MechanicsGoalPotential::UnitVec(toBall0);
 float relV0=std::max(350.f,(c.vel-ball.vel).Dot(d0));
 float lookahead=std::clamp(rawDist/relV0,0.f,0.75f);

 Vec targetBall=ballAfterDelay+ball.vel*lookahead;
 targetBall.x=std::clamp(targetBall.x,-3950.f,3950.f);
 targetBall.y=std::clamp(targetBall.y,-5020.f,5020.f);
 targetBall.z=std::clamp(targetBall.z,93.f,1950.f);

 Vec toTarget=targetBall-posAfterDelay;
 float dist=std::max(0.f,toTarget.Length()-135.f);
 Vec dir=MechanicsGoalPotential::UnitVec(toTarget);
 float speedAlong=c.vel.Dot(dir);
 float align=c.rotMat.forward.Dot(dir);

 // Braking penalty when moving away from target + orientation turn penalty
 float brakePenalty=std::max(0.f,-speedAlong)/3200.f;
 float turnPenalty=(c.isOnGround?0.18f:0.34f)*std::max(0.f,1.f-align);
 // Airborne / flip recovery penalty if in air and not moving toward target
 float recoveryPenalty=0.f;
 if(!c.isOnGround && speedAlong<400.f){
  float airH=std::max(0.f,c.pos.z-17.f);
  recoveryPenalty=std::clamp(airH/std::max(220.f,-c.vel.z+350.f),0.08f,0.85f);
  if(c.isFlipping)recoveryPenalty=std::max(recoveryPenalty,0.35f);
 }
 // Height penalty if ball is high and car is on ground with low boost
 float aerialPenalty=0.f;
 if(targetBall.z>320.f && c.isOnGround){
  float neededZ=targetBall.z-120.f;
  aerialPenalty=neededZ/950.f+(c.boost<20.f?0.45f:0.f);
 }

 // Kinematic travel time with throttle + available boost acceleration
 float v0=std::max(200.f,speedAlong);
 float boostAccel=(c.boost>12.f)?991.67f:0.f;
 float throttleAccel=(v0<1400.f)?650.f:0.f;
 float accel=std::max(200.f,throttleAccel+boostAccel);
 float maxV=(c.boost>12.f)?2250.f:std::max(1410.f,v0);
 float tAccel=(maxV-v0)/accel;
 float dAccel=v0*tAccel+0.5f*accel*tAccel*tAccel;
 float travelTime=0.f;
 if(dist<=dAccel){
  travelTime=(-v0+std::sqrt(std::max(0.f,v0*v0+2.f*accel*dist)))/accel;
 }else{
  travelTime=tAccel+(dist-dAccel)/maxV;
 }
 return ACTION_DELAY+brakePenalty+turnPenalty+recoveryPenalty+aerialPenalty+travelTime;
}

inline TacticalState AssessTactical(const Player& p,const GameState& s){
 TacticalState t;
 float dir=p.team==Team::BLUE?1.f:-1.f;
 t.ownGoal=Vec(0.f,-dir*5140.f,93.f);
 t.ownDist=(s.ball.pos-p.pos).Length();
 const Player* opp=nullptr;
 for(const auto& x:s.players)if(x.team!=p.team){opp=&x;t.oppDist=(s.ball.pos-x.pos).Length();break;}

 t.etaSelf=EstimateKinematicETA(p,s.ball);
 t.etaOpp=opp?EstimateKinematicETA(*opp,s.ball):5.f;
 t.etaMargin=t.etaOpp-t.etaSelf;

 Vec ballToGoal=t.ownGoal-s.ball.pos;
 float ballToGoalLen=std::max(1.f,ballToGoal.Length());
 Vec threatDir=ballToGoal/ballToGoalLen;
 Vec toOwnGoalDir=MechanicsGoalPotential::UnitVec(t.ownGoal-p.pos);
 Vec toBallDir=MechanicsGoalPotential::UnitVec(s.ball.pos-p.pos);

 float proj=(p.pos-s.ball.pos).Dot(threatDir);
 float clampedProj=std::clamp(proj,0.f,ballToGoalLen);
 Vec closestOnLine=s.ball.pos+threatDir*clampedProj;
 t.distToThreatLine=(Vec(p.pos.x,p.pos.y,0.f)-Vec(closestOnLine.x,closestOnLine.y,0.f)).Length();

 float standoff=std::clamp(0.42f*ballToGoalLen,520.f,1700.f);
 t.interceptPos=s.ball.pos+threatDir*standoff;
 t.interceptPos.z=17.f;
 t.distToIntercept=(p.pos-t.interceptPos).Length();

 t.isGoalside=(dir*(s.ball.pos.y-p.pos.y)>120.f) && (proj>80.f);
 t.isStrictlyGoalside=(dir*(s.ball.pos.y-p.pos.y)>180.f) && (proj>200.f);
 t.isOvercommitted=(dir*(p.pos.y-s.ball.pos.y)>250.f) && (t.etaOpp+0.12f<t.etaSelf);

 t.velTowardOwnGoal=p.vel.Dot(toOwnGoalDir);
 t.velAlongThreat=p.vel.Dot(threatDir);
 float closingToBall=p.vel.Dot(toBallDir);

 float ballVelTowardGoal=std::max(0.f,s.ball.vel.Dot(threatDir));
 float shotThreat=std::clamp(ballVelTowardGoal/1450.f,0.f,1.f)*std::clamp((2200.f-dir*s.ball.pos.y)/6500.f,0.25f,1.f);
 float fieldDanger=std::clamp((2400.f-dir*s.ball.pos.y)/5500.f,0.35f,1.f);

 if(opp){
  Vec oppToOwnGoal=MechanicsGoalPotential::UnitVec(t.ownGoal-opp->pos);
  float oppThreatAlign=std::clamp((opp->rotMat.forward.Dot(oppToOwnGoal)+0.30f)/1.30f,0.25f,1.f);
  float oppProx=std::clamp((750.f-t.oppDist)/550.f,0.f,1.f);
  float oppEtaAdv=std::max(std::clamp((-t.etaMargin-0.12f)/0.25f,0.f,1.f), (t.oppDist<320.f && t.etaMargin<-0.16f)?0.80f:0.f);
  t.oppControl=oppProx*oppEtaAdv*oppThreatAlign;
  if(t.isStrictlyGoalside && t.ownDist>550.f && t.oppDist<520.f && t.etaMargin<-0.16f){
   t.unreachableThreatGate=std::clamp(oppProx*oppEtaAdv*oppThreatAlign*fieldDanger*1.65f,0.f,1.f);
  }else{
   t.unreachableThreatGate=0.f;
  }
 }

 float exposureMult=(!t.isGoalside || t.distToThreatLine>650.f)?1.25f:0.85f;
 float possessionThreat=t.oppControl*fieldDanger;
 t.danger=std::clamp(std::max(shotThreat,possessionThreat)*exposureMult,0.f,1.f);

 t.attackGate=std::clamp((t.etaMargin+0.16f)/0.34f,0.f,1.f);
 if(t.oppDist<340.f && t.ownDist>680.f && t.etaMargin<-0.10f)t.attackGate=0.f;
 t.defendGate=(1.f-t.attackGate)*std::clamp(t.danger*1.45f,0.f,1.f);

 t.isUpfieldLunge = t.isStrictlyGoalside && (t.velTowardOwnGoal<-300.f) && (t.velAlongThreat<-300.f) && (closingToBall>750.f) &&
  (p.isFlipping || (!p.isOnGround && p.pos.z>70.f) || closingToBall>750.f);
 t.validatedDive = (t.unreachableThreatGate>0.30f) && (t.ownDist>550.f) && t.isUpfieldLunge;

 return t;
}

class DefensiveMechanicsGoalPotential : public Reward {
 float gamma,mechScale,defScale;std::array<float,5> weights;
public:
 DefensiveMechanicsGoalPotential(float g,std::array<float,5> w={.35f,.15f,.30f,.18f,.20f},float ms=1.f,float ds=1.f)
  :gamma(g),mechScale(ms),defScale(ds),weights(w){
  if(!(gamma>0 && gamma<1))throw std::runtime_error("Invalid shaping gamma");
  if(!std::isfinite(mechScale)||mechScale<0||mechScale>10)throw std::runtime_error("Invalid mechanics scale");
  if(!std::isfinite(defScale)||defScale<0||defScale>10)throw std::runtime_error("Invalid defense scale");
  for(float x:w)if(!std::isfinite(x)||std::abs(x)>1)throw std::runtime_error("Invalid potential coefficient");
 }
 float Phi(const Player& p,const GameState& s)const{
  auto b=GoalPotential::Basis(p,s);
  auto t=AssessTactical(p,s);
  // Blend distance potential: when attackGate is high, minimize distance to ball;
  // when defendGate is high (opponent controls ball with danger), minimize distance to the goalside shadow intercept point!
  float blend=std::clamp(t.defendGate*defScale,0.f,1.f);
  float effectiveDist=(1.f-blend)*t.ownDist+blend*t.distToIntercept;
  b[1]=-std::min(effectiveDist,12000.f)/6000.f;

  // Upgrade b[4] (possession potential) to reflect kinematic ETA advantage, not just raw distance
  float etaAdv=std::clamp(t.etaMargin/1.2f,-1.f,1.f)*std::exp(- std::min(t.ownDist,t.oppDist)/2800.f);
  b[4]=0.5f*b[4]+0.5f*etaAdv;

  float value=0;for(int i=0;i<5;i++)value+=weights[i]*b[i];

  float oppBoost=p.boost;
  for(const auto& x:s.players)if(x.team!=p.team)oppBoost=x.boost;
  // Suppress boost-pad greed during urgent defensive danger so Chronos never detours for boost over defending open net
  float boostGate=std::clamp(1.f-0.85f*blend,0.15f,1.f);
  value+=0.08f*boostGate*((p.boost-oppBoost)/100.f);

  // Context-gated velocity potential: close to ball when feasible, or close to shadow intercept & goalside coverage under threat
  Vec toBall=s.ball.pos-p.pos;
  float closingBall=std::clamp(p.vel.Dot(MechanicsGoalPotential::UnitVec(toBall))/2300.f,-1.f,1.f)*std::exp(-t.ownDist/3000.f);
  Vec toIntercept=t.interceptPos-p.pos;
  float closingIntercept=(t.distToIntercept>180.f)
   ?std::clamp(p.vel.Dot(MechanicsGoalPotential::UnitVec(toIntercept))/2300.f,-1.f,1.f)
   :std::clamp(p.rotMat.forward.Dot(MechanicsGoalPotential::UnitVec(toBall)),0.f,1.f);
  float shadowCoverage=std::exp(-t.distToIntercept/1400.f)*(t.isGoalside?1.f:0.25f)*(p.isOnGround?1.f:0.6f);

  value+=0.06f*((1.f-blend)*closingBall+blend*closingIntercept);
  value+=0.09f*defScale*t.danger*(shadowCoverage-0.5f*(t.isOvercommitted?1.f:0.f));
  return value;
 }

 float GetReward(const Player& p,const GameState& s,bool final) override {
  if(!s.prev || !p.prev)return 0;
  float dir=p.team==Team::BLUE?1.f:-1.f;
  float goal=0;
  if(s.goalScored)goal=((s.ball.pos.y>0)==(p.team==Team::BLUE))?10.f:-10.f;
  float base=goal+gamma*(s.goalScored?0.f:Phi(p,s))-Phi(*p.prev,*s.prev);
  if(mechScale<=0.f && defScale<=0.f)return base;

  auto t=AssessTactical(p,s);
  auto tPrev=AssessTactical(*p.prev,*s.prev);
  float bonus=0.f;
  Vec delta=s.ball.pos-p.pos;float dist=delta.Length();Vec dirToBall=MechanicsGoalPotential::UnitVec(delta);
  float speed=p.vel.Length(),closingSpeed=p.vel.Dot(dirToBall);
  bool freeAir=!p.isOnGround && !p.worldContact.hasContact && p.pos.z>190.f;

  // 1. Reachability-Gated Speedflip Kickoff & Supersonic Approach:
  // Only reward speedflip approaches when the challenge is actually feasible (attackGate > 0.45 or kickoff),
  // NEVER when diving into an opponent-controlled ball as last defender.
  bool isKickoff=(s.ball.pos.x*s.ball.pos.x+s.ball.pos.y*s.ball.pos.y<100.f && s.ball.vel.Length()<50.f);
  if((isKickoff || (t.attackGate>0.45f && t.defendGate<0.25f)) &&
     dist<2600.f && closingSpeed>1350.f && p.isFlipping && p.prevAction.pitch<-0.5f && std::abs(p.prevAction.yaw+p.prevAction.roll)>0.5f){
   bonus+=mechScale*0.010f*std::clamp(closingSpeed/2200.f,0.5f,1.2f);
  }

  // 2. Offensive & Defensive Touch Mechanics
  if(p.ballTouchedStep){
   float dvy=dir*(s.ball.vel.y-s.prev->ball.vel.y);
   float vy=dir*s.ball.vel.y;
   if(speed>1550.f && dvy>200.f){
    bonus+=mechScale*0.06f*std::clamp(dvy/1500.f,0.f,1.5f);
   }
   if(dvy>250.f && vy>850.f){
    float dtGoal=std::max(0.05f,(5120.f-dir*s.ball.pos.y)/std::max(200.f,vy));
    float projX=s.ball.pos.x+s.ball.vel.x*dtGoal;
    if(std::abs(projX)<1150.f && s.ball.pos.z<1800.f){
     bonus+=mechScale*0.12f*std::clamp(vy/2100.f,0.2f,1.5f);
    }
   }
   if(freeAir && s.ball.pos.z>260.f && vy>200.f){
    bonus+=mechScale*0.10f*std::clamp(s.ball.pos.z/900.f,0.2f,1.4f);
    if(p.isFlipping && vy>550.f){
     bonus+=mechScale*0.22f*std::clamp(vy/1800.f,0.4f,1.5f);
    }
   }
   // Defensive Save / Clear / Safe Interception Bonus:
   // When ball was threatening own half/net and touch arrests inward velocity or clears it forward/wide
   float prevInwardVel=-dir*s.prev->ball.vel.y;
   if(dir*s.ball.pos.y<-900.f && (prevInwardVel>350.f || tPrev.danger>0.30f) && dvy>380.f){
    bool unsafeCenter=(std::abs(s.ball.pos.x)<950.f && dir*s.ball.pos.y<-3500.f && vy<250.f && std::abs(s.ball.vel.x)<450.f);
    if(!unsafeCenter){
     bonus+=defScale*0.15f*std::clamp(dvy/1600.f,0.3f,1.4f);
    }
   }
  }

  // 3. Air-dribble carry toward opponent net
  if(freeAir && s.ball.pos.z>280.f && dist<230.f && (s.ball.vel-p.vel).Length()<620.f && dir*s.ball.vel.y>280.f && p.rotMat.forward.Dot(dirToBall)>0.35f){
   bonus+=mechScale*0.016f*std::clamp(dir*s.ball.vel.y/1400.f,0.3f,1.2f);
  }

  // 4. Flip-reset & Maktuf / 360 spin reset acquisition on ball
  if(freeAir && s.ball.pos.z>270.f && dist<190.f && (-p.rotMat.up).Dot(dirToBall)>0.55f){
   if(p.HasFlipOrJump() && !p.prev->HasFlipOrJump()){
    float spinMult=(p.angVel.Length()>1.9f)?1.5f:1.0f;
    bonus+=mechScale*0.28f*spinMult;
   }
  }

  // 5. Penalty for Unfeasible Last-Defender Diving Flip-Commitment:
  // When opponent clearly reaches ball first (>220ms margin) with credible scoring danger and self is >550uu away,
  // initiating a flip toward the ball instead of shadowing/covering the intercept line leaves an open net.
  if(defScale>0.f && tPrev.defendGate>0.42f && tPrev.etaMargin<-0.22f && tPrev.ownDist>550.f){
   bool newFlip=(p.isFlipping && !p.prev->isFlipping);
   if(newFlip && closingSpeed>400.f && t.distToIntercept>650.f){
    bonus-=defScale*0.045f*tPrev.defendGate;
   }
  }

  return base+bonus;
 }
 std::string GetName() override{return "mechanics-defense-v2";}
};

class ValidatedAntiDiveMechanicsGoalPotential : public Reward {
 float gamma,mechScale,defScale;std::array<float,5> weights;
public:
 ValidatedAntiDiveMechanicsGoalPotential(float g,std::array<float,5> w={.35f,.15f,.30f,.15f,.20f},float ms=1.f,float ds=1.f)
  :gamma(g),mechScale(ms),defScale(ds),weights(w){
  if(!(gamma>0 && gamma<1))throw std::runtime_error("Invalid shaping gamma");
  if(!std::isfinite(mechScale)||mechScale<0||mechScale>10)throw std::runtime_error("Invalid mechanics scale");
  if(!std::isfinite(defScale)||defScale<0||defScale>10)throw std::runtime_error("Invalid defense scale");
  for(float x:w)if(!std::isfinite(x)||std::abs(x)>1)throw std::runtime_error("Invalid potential coefficient");
 }
 float Phi(const Player& p,const GameState& s)const{
  auto b=GoalPotential::Basis(p,s);
  float value=0;for(int i=0;i<5;i++)value+=weights[i]*b[i];
  float oppBoost=p.boost;
  for(const auto& x:s.players)if(x.team!=p.team)oppBoost=x.boost;
  value+=0.08f*((p.boost-oppBoost)/100.f);

  auto t=AssessTactical(p,s);
  Vec toBall=s.ball.pos-p.pos;float dist=toBall.Length();
  Vec dirToBall=MechanicsGoalPotential::UnitVec(toBall);
  float rawClosing=p.vel.Dot(dirToBall);

  float effectiveClosing=rawClosing;
  if(t.unreachableThreatGate>0.25f && t.isStrictlyGoalside){
   float g=std::clamp(t.unreachableThreatGate*defScale,0.f,1.f);
   if(t.velTowardOwnGoal<0.f){
    effectiveClosing=(1.f-g)*rawClosing+g*std::min(0.f,rawClosing);
   }
  }
  float closing=std::clamp(effectiveClosing/2300.f,-1.f,1.f)*std::exp(-dist/3000.f);
  value+=0.06f*closing;
  return value;
 }

 float GetReward(const Player& p,const GameState& s,bool final) override {
  if(!s.prev || !p.prev)return 0;
  float dir=p.team==Team::BLUE?1.f:-1.f;
  float goal=0;
  if(s.goalScored)goal=((s.ball.pos.y>0)==(p.team==Team::BLUE))?10.f:-10.f;
  float base=goal+gamma*(s.goalScored?0.f:Phi(p,s))-Phi(*p.prev,*s.prev);
  if(mechScale<=0.f)return base;

  auto t=AssessTactical(p,s);
  auto tPrev=AssessTactical(*p.prev,*s.prev);
  float bonus=0.f;
  Vec delta=s.ball.pos-p.pos;float dist=delta.Length();Vec dirToBall=MechanicsGoalPotential::UnitVec(delta);
  float speed=p.vel.Length(),closingSpeed=p.vel.Dot(dirToBall);
  bool freeAir=!p.isOnGround && !p.worldContact.hasContact && p.pos.z>190.f;

  bool isKickoff=(s.ball.pos.x*s.ball.pos.x+s.ball.pos.y*s.ball.pos.y<100.f && s.ball.vel.Length()<50.f);
  bool suppressSpeedflip=(!isKickoff && t.unreachableThreatGate>0.25f && t.velTowardOwnGoal<-200.f);
  if(!suppressSpeedflip && dist<2600.f && closingSpeed>1350.f && p.isFlipping && p.prevAction.pitch<-0.5f && std::abs(p.prevAction.yaw+p.prevAction.roll)>0.5f){
   bonus+=mechScale*0.010f*std::clamp(closingSpeed/2200.f,0.5f,1.2f);
  }

  if(p.ballTouchedStep){
   float dvy=dir*(s.ball.vel.y-s.prev->ball.vel.y);
   float vy=dir*s.ball.vel.y;
   if(speed>1550.f && dvy>200.f){
    bonus+=mechScale*0.06f*std::clamp(dvy/1500.f,0.f,1.5f);
   }
   if(dvy>250.f && vy>850.f){
    float dtGoal=std::max(0.05f,(5120.f-dir*s.ball.pos.y)/std::max(200.f,vy));
    float projX=s.ball.pos.x+s.ball.vel.x*dtGoal;
    if(std::abs(projX)<1150.f && s.ball.pos.z<1800.f){
     bonus+=mechScale*0.12f*std::clamp(vy/2100.f,0.2f,1.5f);
    }
   }
   if(freeAir && s.ball.pos.z>260.f && vy>200.f){
    bonus+=mechScale*0.10f*std::clamp(s.ball.pos.z/900.f,0.2f,1.4f);
    if(p.isFlipping && vy>550.f){
     bonus+=mechScale*0.22f*std::clamp(vy/1800.f,0.4f,1.5f);
    }
   }
  }

  if(freeAir && s.ball.pos.z>270.f && dist<190.f && (-p.rotMat.up).Dot(dirToBall)>0.55f){
   if(p.HasFlipOrJump() && !p.prev->HasFlipOrJump()){
    float spinMult=(p.angVel.Length()>1.9f)?1.5f:1.0f;
    bonus+=mechScale*0.28f*spinMult;
   }
  }

  if(defScale>0.f && tPrev.unreachableThreatGate>0.30f && tPrev.ownDist>550.f){
   bool newFlip=(p.isFlipping && !p.prev->isFlipping);
   if(newFlip && tPrev.isStrictlyGoalside && tPrev.velTowardOwnGoal<-300.f && tPrev.velAlongThreat<-300.f && closingSpeed>600.f){
    bonus-=defScale*0.035f*tPrev.unreachableThreatGate;
   }
  }

  return base+bonus;
 }
 std::string GetName() override{return "mechanics-validated-antidive-v3";}
};

class WinRateDominanceGoalPotential : public Reward {
 static inline std::atomic<int64_t> globalGoalsFor{64};
 static inline std::atomic<int64_t> globalGoalsAgainst{64};
 float gamma, winScale;
 std::array<float, 5> weights;
public:
 WinRateDominanceGoalPotential(float g, std::array<float, 5> w = {.12f, .05f, .10f, .08f, .08f}, float ws = 2.0f)
  : gamma(g), winScale(ws), weights(w) {
  if (!(gamma > 0 && gamma < 1)) throw std::runtime_error("Invalid shaping gamma");
  if (!std::isfinite(winScale) || winScale < 0 || winScale > 10) throw std::runtime_error("Invalid win scale");
  for (float x : w) if (!std::isfinite(x) || std::abs(x) > 1) throw std::runtime_error("Invalid potential coefficient");
 }

 static void ResetStats() {
  globalGoalsFor.store(64, std::memory_order_relaxed);
  globalGoalsAgainst.store(64, std::memory_order_relaxed);
 }

 static float CurrentWinRate() {
  int64_t gf = globalGoalsFor.load(std::memory_order_relaxed);
  int64_t ga = globalGoalsAgainst.load(std::memory_order_relaxed);
  return float(gf) / std::max(1.f, float(gf + ga));
 }

 float Phi(const Player& p, const GameState& s) const {
  auto b = GoalPotential::Basis(p, s);
  float value = 0;
  for (int i = 0; i < 5; i++) value += weights[i] * b[i];
  float oppBoost = p.boost;
  for (const auto& x : s.players) if (x.team != p.team) oppBoost = x.boost;
  value += 0.04f * ((p.boost - oppBoost) / 100.f);
  return value;
 }

 float GetReward(const Player& p, const GameState& s, bool final) override {
  if (!s.prev || !p.prev) return 0;
  float goal = 0.f;
  if (s.goalScored) {
   bool scored = ((s.ball.pos.y > 0) == (p.team == Team::BLUE));
   if (scored) {
    globalGoalsFor.fetch_add(1, std::memory_order_relaxed);
   } else {
    globalGoalsAgainst.fetch_add(1, std::memory_order_relaxed);
   }
   int64_t gf = globalGoalsFor.load(std::memory_order_relaxed);
   int64_t ga = globalGoalsAgainst.load(std::memory_order_relaxed);
   if (gf + ga > 512) {
    globalGoalsFor.store(gf / 2, std::memory_order_relaxed);
    globalGoalsAgainst.store(ga / 2, std::memory_order_relaxed);
   }

   float w = float(gf) / std::max(1.f, float(gf + ga));
   float deltaW = w - 0.50f;

   if (scored) {
    goal = 10.0f * std::clamp(1.0f + winScale * deltaW, 0.2f, 2.0f);
   } else {
    goal = -10.0f * std::clamp(1.0f - winScale * deltaW, 0.2f, 2.0f);
   }
  }

  float bonus = 0.f;
  Vec delta = s.ball.pos - p.pos;
  float dist = delta.Length();
  Vec dirToBall = MechanicsGoalPotential::UnitVec(delta);
  float closingSpeed = p.vel.Dot(dirToBall);
  if (dist < 2600.f && closingSpeed > 1350.f && p.isFlipping && p.prevAction.pitch < -0.5f && std::abs(p.prevAction.yaw + p.prevAction.roll) > 0.5f) {
   bonus += 0.008f * std::clamp(closingSpeed / 2200.f, 0.5f, 1.2f);
  }
  if (p.ballTouchedStep) {
   float dir = p.team == Team::BLUE ? 1.f : -1.f;
   float dvy = dir * (s.ball.vel.y - s.prev->ball.vel.y);
   if (p.vel.Length() > 1550.f && dvy > 200.f) {
    bonus += 0.04f * std::clamp(dvy / 1500.f, 0.f, 1.5f);
   }
  }

  return goal + gamma * (s.goalScored ? 0.f : Phi(p, s)) - Phi(*p.prev, *s.prev) + bonus;
 }

 std::string GetName() override { return "winrate-dominance-v1"; }
};

// Apply a specific defensive or counterattack scenario to an Arena using a provided RNG.
inline void ApplyDefensiveScenario(Arena* arena,Team defenderTeam,int scenarioType,std::mt19937& rng){
 arena->ResetToRandomKickoff();
 auto unif=[&](float a,float b){return std::uniform_real_distribution<float>(a,b)(rng);};
 float dir=(defenderTeam==Team::BLUE)?1.f:-1.f; // Defender defends -dir*5120, attacks +dir*5120
 float sideSign=(unif(-1.f,1.f)>=0.f)?1.f:-1.f;

 BallState bs={};
 CarState defCs={},oppCs={};
 defCs.isOnGround=true;oppCs.isOnGround=true;
 defCs.boost=unif(35.f,85.f);oppCs.boost=unif(45.f,90.f);
 float defYaw=dir>0.f?float(M_PI/2):-float(M_PI/2);
 float oppYaw=-defYaw;

 switch(scenarioType%6){
  case 0: {
   // 0. Opponent midfield dribble & flick threat toward defender's net
   float bx=sideSign*unif(100.f,1300.f);
   float by=dir*unif(-400.f,1500.f);
   float bvy=-dir*unif(650.f,1150.f);
   float bvx=-bx*unif(0.08f,0.22f);
   bs.pos=Vec(bx,by,unif(95.f,145.f));
   bs.vel=Vec(bvx,bvy,unif(0.f,80.f));
   oppCs.pos=Vec(bx-bvx*0.12f,by-dir*unif(135.f,240.f),17.f);
   oppCs.vel=Vec(bvx,bvy*unif(0.92f,1.05f),0.f);
   oppYaw=std::atan2(bs.pos.y-oppCs.pos.y,bs.pos.x-oppCs.pos.x);
   // Defender at shadow standoff, either retreating or slightly off-angle
   defCs.pos=Vec(bx+sideSign*unif(-450.f,450.f),by-dir*unif(900.f,1650.f),17.f);
   defCs.pos.y=std::clamp(defCs.pos.y,-4750.f,4750.f);
   defYaw=std::atan2(-dir*4800.f-defCs.pos.y,0.f-defCs.pos.x)+unif(-0.45f,0.45f);
   float defSpd=unif(450.f,1150.f);
   defCs.vel=Vec(std::cos(defYaw)*defSpd,std::sin(defYaw)*defSpd,0.f);
   break;
  }
  case 1: {
   // 1. Overcommitted / lost possession recovery (defender even with or slightly behind the ball)
   float bx=sideSign*unif(300.f,2100.f);
   float by=dir*unif(-600.f,1800.f);
   float bvy=-dir*unif(550.f,1200.f);
   bs.pos=Vec(bx,by,unif(93.f,220.f));
   bs.vel=Vec(-bx*0.12f,bvy,unif(0.f,180.f));
   oppCs.pos=Vec(bx+sideSign*unif(-200.f,200.f),by+dir*unif(180.f,480.f),17.f);
   oppYaw=std::atan2(-dir*5120.f-oppCs.pos.y,0.f-oppCs.pos.x);
   float oppSpd=unif(700.f,1350.f);
   oppCs.vel=Vec(std::cos(oppYaw)*oppSpd,std::sin(oppYaw)*oppSpd,0.f);
   // Defender is slightly behind or lateral to the ball and must recover goalside without diving into a flick
   defCs.pos=Vec(bx-sideSign*unif(450.f,1100.f),by+dir*unif(-250.f,420.f),17.f);
   defYaw=std::atan2(-dir*5120.f-defCs.pos.y,0.f-defCs.pos.x)+unif(-0.6f,0.6f);
   float defSpd=unif(600.f,1300.f);
   defCs.vel=Vec(std::cos(defYaw)*defSpd,std::sin(defYaw)*defSpd,0.f);
   break;
  }
  case 2: {
   // 2. Wide attack / corner cut / near-post threat
   float bx=sideSign*unif(1850.f,3350.f);
   float by=-dir*unif(1100.f,3500.f);
   bs.pos=Vec(bx,by,unif(93.f,260.f));
   Vec toSlot=Vec(sideSign*unif(0.f,400.f),-dir*4950.f,120.f)-bs.pos;
   Vec slotDir=MechanicsGoalPotential::UnitVec(toSlot);
   float bSpd=unif(750.f,1450.f);
   bs.vel=slotDir*bSpd;
   oppCs.pos=bs.pos-slotDir*unif(180.f,380.f);oppCs.pos.z=17.f;
   oppYaw=std::atan2(slotDir.y,slotDir.x);
   oppCs.vel=slotDir*unif(700.f,1350.f);
   defCs.pos=Vec(sideSign*unif(200.f,1400.f),-dir*unif(3400.f,4750.f),17.f);
   defYaw=std::atan2(bs.pos.y-defCs.pos.y,bs.pos.x-defCs.pos.x)+unif(-0.35f,0.35f);
   float defSpd=unif(300.f,950.f);
   defCs.vel=Vec(std::cos(defYaw)*defSpd,std::sin(defYaw)*defSpd,0.f);
   break;
  }
  case 3: {
   // 3. Direct power shot / high bounce / backboard threat
   float bx=sideSign*unif(0.f,1600.f);
   float by=-dir*unif(1200.f,2800.f);
   bs.pos=Vec(bx,by,unif(160.f,680.f));
   Vec targetGoal=Vec(unif(-780.f,780.f),-dir*5140.f,unif(180.f,580.f));
   Vec shotDir=MechanicsGoalPotential::UnitVec(targetGoal-bs.pos);
   float shotSpd=unif(1150.f,1850.f);
   bs.vel=shotDir*shotSpd;
   oppCs.pos=bs.pos-shotDir*unif(350.f,800.f);oppCs.pos.z=17.f;
   oppYaw=std::atan2(shotDir.y,shotDir.x);
   oppCs.vel=shotDir*unif(800.f,1400.f);
   defCs.pos=Vec(unif(-900.f,900.f),-dir*unif(3600.f,4850.f),17.f);
   defYaw=std::atan2(bs.pos.y-defCs.pos.y,bs.pos.x-defCs.pos.x)+unif(-0.4f,0.4f);
   float defSpd=unif(200.f,850.f);
   defCs.vel=Vec(std::cos(defYaw)*defSpd,std::sin(defYaw)*defSpd,0.f);
   break;
  }
  case 4: {
   // 4. Low-boost defense under pressure (resist boost detour)
   float bx=sideSign*unif(200.f,1800.f);
   float by=-dir*unif(600.f,2400.f);
   bs.pos=Vec(bx,by,unif(93.f,180.f));
   Vec toNet=MechanicsGoalPotential::UnitVec(Vec(unif(-600.f,600.f),-dir*5120.f,93.f)-bs.pos);
   bs.vel=toNet*unif(750.f,1350.f);
   oppCs.pos=bs.pos-toNet*unif(160.f,320.f);oppCs.pos.z=17.f;
   oppYaw=std::atan2(toNet.y,toNet.x);
   oppCs.vel=toNet*unif(750.f,1300.f);
   oppCs.boost=unif(60.f,100.f);
   defCs.pos=Vec(sideSign*unif(600.f,1900.f),-dir*unif(2600.f,4200.f),17.f);
   defYaw=std::atan2(-dir*4950.f-defCs.pos.y,0.f-defCs.pos.x);
   float defSpd=unif(400.f,1000.f);
   defCs.vel=Vec(std::cos(defYaw)*defSpd,std::sin(defYaw)*defSpd,0.f);
   defCs.boost=unif(6.f,24.f);
   break;
  }
  default: {
   // 5. Heavy opponent touch / loose ball: early safe challenge & counterattack opportunity
   float bx=sideSign*unif(0.f,1700.f);
   float by=dir*unif(-1800.f,600.f);
   bs.pos=Vec(bx,by,unif(93.f,240.f));
   bs.vel=Vec(unif(-250.f,250.f),-dir*unif(350.f,800.f),unif(0.f,220.f));
   // Opponent made a heavy touch and is 850-1350 uu behind the ball
   oppCs.pos=Vec(bx+unif(-300.f,300.f),by+dir*unif(850.f,1350.f),17.f);
   oppYaw=std::atan2(bs.pos.y-oppCs.pos.y,bs.pos.x-oppCs.pos.x);
   oppCs.vel=Vec(std::cos(oppYaw)*unif(500.f,1050.f),std::sin(oppYaw)*unif(500.f,1050.f),0.f);
   // Defender is closer (550-850 uu) and facing the ball -> early challenge wins cleanly!
   defCs.pos=Vec(bx+unif(-250.f,250.f),by-dir*unif(520.f,850.f),17.f);
   defYaw=std::atan2(bs.pos.y-defCs.pos.y,bs.pos.x-defCs.pos.x);
   defCs.vel=Vec(std::cos(defYaw)*unif(650.f,1200.f),std::sin(defYaw)*unif(650.f,1200.f),0.f);
   break;
  }
 }
 defCs.rotMat=Angle(defYaw,0.f,0.f).ToRotMat();
 oppCs.rotMat=Angle(oppYaw,0.f,0.f).ToRotMat();
 arena->ball->SetState(bs);
 for(Car* car:arena->_cars){
  if(car->team==defenderTeam)car->SetState(defCs);
  else car->SetState(oppCs);
 }
}

class DefensiveCurriculumStateSetter : public StateSetter {
 float defProb;
 Team learnerTeam;
 std::mt19937 rng;
public:
 DefensiveCurriculumStateSetter(float prob,Team team,unsigned seed):defProb(prob),learnerTeam(team),rng(seed){}
 void ResetArena(Arena* arena) override {
  std::uniform_real_distribution<float> u(0.f,1.f);
  if(defProb<=0.f || u(rng)>=defProb){
   arena->ResetToRandomKickoff();
   return;
  }
  int scen=std::uniform_int_distribution<int>(0,5)(rng);
  ApplyDefensiveScenario(arena,learnerTeam,scen,rng);
 }
};
}
