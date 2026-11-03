// Harness for the unmodified pinned Chronos observation/action sources.
// Build with their AdvancedObs.cpp, AdvancedObsPadded.cpp, StateUtil.cpp,
// DefaultAction.cpp and RocketSim MathTypes.cpp; include inc/ and Bullet.
#include "RLGymCPP/ObsBuilders/AdvancedObsPadded.h"
#include "RLGymCPP/ActionParsers/DefaultAction.h"
#include <iomanip>
namespace RocketSim {
bool CarState::HasFlipOrJump() const {
 return isOnGround || (!hasFlipped && !hasDoubleJumped && airTimeSinceJump < RLConst::DOUBLEJUMP_MAX_DELAY);
}
namespace Math { std::default_random_engine& GetRandEngine(){static std::default_random_engine rng(42);return rng;} }
}
int main(){
 std::cout<<std::setprecision(10);
 RLGC::DefaultAction parser(true); RLGC::AdvancedObsPadded builder(3);
 for(int team=0;team<2;team++)for(int x: {-1200,1200})for(bool ground: {true,false}){
  RLGC::GameState g; RLGC::Player p;
  p.team=team?Team::ORANGE:Team::BLUE;p.carId=1;
  p.pos=Vec(x,-2200,ground?17:620);p.vel=Vec(350,900,ground?0:280);
  p.angVel=Vec(.2,-.4,.7);p.rotMat.forward=Vec(.6,.8,0);p.rotMat.up=Vec(0,0,1);p.rotMat.right=Vec(-.8,.6,0);
  p.boost=ground?0:63;p.isOnGround=ground;p.hasJumped=!ground;p.hasDoubleJumped=!ground&&x>0;
  p.prevAction=parser.actions[32];
  RLGC::Player other=p;other.carId=2;other.team=team?Team::BLUE:Team::ORANGE;
  other.pos=Vec(-x,1500,17);other.boost=47;other.isOnGround=true;other.hasJumped=false;other.hasDoubleJumped=false;
  g.players={p,other};
  g.ball.pos=Vec(200,-850,140);g.ball.vel=Vec(-240,700,180);g.ball.angVel=Vec(1.1,-.2,2.3);
  for(int i=0;i<34;i++){
   g.boostPads[i]=i%3!=0;g.boostPadTimers[i]=.8f+i%3;
   g.boostPadsInv[33-i]=g.boostPads[i];g.boostPadTimersInv[33-i]=g.boostPadTimers[i];
  }
  auto obs=builder.BuildObs(p,g);for(float v:obs)std::cout<<v<<' ';std::cout<<'\n';
  auto mask=parser.GetActionMask(p,g);for(auto v:mask)std::cout<<(int)v;std::cout<<'\n';
  for(int i=0;i<90;i++)for(int j=0;j<8;j++)std::cout<<parser.ParseAction(i,p,g)[j]<<' ';std::cout<<'\n';
 }
}
