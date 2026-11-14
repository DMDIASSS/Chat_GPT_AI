#pragma once
// Experimental geometry proxy, not Catalyst's unpublished possession reward.
inline float control_value(float own,float opponent,float radius,float epsilon){
 return std::exp(-std::min(own,opponent)/radius)*(opponent-own)/(own+opponent+epsilon);
}
struct ShotTrace {
 int owner=-1;int64_t touchTick=0;bool floorSeen=true;
 void reset(){owner=-1;touchTick=0;floorSeen=true;}
 void observe(int teamBits,bool floor,int64_t tick){
  if(teamBits==3){owner=-1;floorSeen=true;touchTick=tick;}
  else if(teamBits==1||teamBits==2){owner=teamBits==1?0:1;touchTick=tick;floorSeen=false;}
  if(floor)floorSeen=true;
 }
 bool credited(int scoringTeam,int64_t tick,int maxAgeTicks) const{
  return scoringTeam>=0&&scoringTeam<=1&&owner==scoringTeam&&tick>=touchTick&&tick-touchTick<=maxAgeTicks;
 }
 bool clean(int scoringTeam,int64_t tick,int maxAgeTicks) const{
  return credited(scoringTeam,tick,maxAgeTicks)&&!floorSeen;
 }
};
// Read Bullet's actual ball/static-world contact manifolds. No height-only
// inference: car, ceiling, wall and high-ramp contacts do not count as floor.
inline bool ball_floor_contact(RocketSim::Arena* arena){
 auto*dispatcher=arena->_bulletWorld.getDispatcher();const auto*ball=&arena->ball->_rigidBody;
 for(int k=0;k<dispatcher->getNumManifolds();k++){
  const auto*m=dispatcher->getManifoldByIndexInternal(k);
  const auto*a=static_cast<const btCollisionObject*>(m->getBody0());
  const auto*b=static_cast<const btCollisionObject*>(m->getBody1());
  bool ballA=a==ball;if(!ballA&&b!=ball)continue;
  const auto*other=ballA?b:a;if(!other->isStaticObject())continue;
  for(int j=0;j<m->getNumContacts();j++){
   const auto&p=m->getContactPoint(j);
   const auto&point=ballA?p.getPositionWorldOnB():p.getPositionWorldOnA();
   float nz=float(p.m_normalWorldOnB.z())*(ballA?1.f:-1.f);
   // Floor mesh margin is about 2uu; reject separated/speculative contacts.
   if(p.getDistance()<=1e-4f&&std::abs(float(point.z())*BT_TO_UU)<=4.f&&nz>=.95f)return true;
  }
 }
 return false;
}
