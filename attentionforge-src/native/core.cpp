#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include "RocketSim.h"
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <random>
#include <memory>
#include <functional>
#include <cmath>
namespace py=pybind11;
using namespace RocketSim;
#include "control_rewards.h"
#include "skills.h"
#include "attack.h"

// Persistent arena workers. Each arena owns its random stream, independent of scheduling.
class Pool {
 std::vector<std::thread> ts; std::mutex m; std::condition_variable start,done;
 std::function<void(int)> fn; std::atomic<int> cursor{0}; int n=0,gen=0,pending=0; bool quit=false;
 void work(){while(true){int i=cursor.fetch_add(1);if(i>=n)return;fn(i);}}
public:
 Pool(int threads){for(int k=1;k<threads;k++)ts.emplace_back([this]{int old=0;while(true){std::unique_lock<std::mutex> l(m);start.wait(l,[&]{return quit||gen!=old;});if(quit)return;old=gen;l.unlock();work();l.lock();if(--pending==0)done.notify_one();}});}
 ~Pool(){{std::lock_guard<std::mutex>l(m);quit=true;}start.notify_all();for(auto& t:ts)t.join();}
 void run(int count,std::function<void(int)> f){{std::lock_guard<std::mutex>l(m);fn=std::move(f);n=count;cursor=0;pending=(int)ts.size();++gen;}start.notify_all();work();std::unique_lock<std::mutex>l(m);done.wait(l,[&]{return pending==0;});}
};
std::vector<CarControls> actions(){std::vector<CarControls> a;
 for(int t=-1;t<=1;t++)for(int s=-1;s<=1;s++)for(int b=0;b<2;b++)for(int h=0;h<2;h++){if(b&&t!=1)continue;CarControls c;c.throttle=t;c.steer=c.yaw=s;c.boost=b;c.handbrake=h;a.push_back(c);}
 for(int p=-1;p<=1;p++)for(int y=-1;y<=1;y++)for(int r=-1;r<=1;r++)for(int j=0;j<2;j++)for(int b=0;b<2;b++){if(j&&y)continue;if(p==0&&r==0&&j==0)continue;CarControls c;c.throttle=b;c.steer=c.yaw=y;c.pitch=p;c.roll=r;c.jump=j;c.boost=b;c.handbrake=j&&(p||y||r);a.push_back(c);}return a;
}
void vec(float*p,Vec v){p[0]=v.x;p[1]=v.y;p[2]=v.z;}
void controls(float*p,const CarControls&c){p[0]=c.throttle;p[1]=c.steer;p[2]=c.pitch;p[3]=c.yaw;p[4]=c.roll;p[5]=c.jump;p[6]=c.boost;p[7]=c.handbrake;}
struct Env {
 Arena* arena=nullptr;std::vector<Car*> cars;std::mt19937 rng;std::default_random_engine physics;
 int goal=-1,ticks=0,noTouch=0;float potential=0,goalSpeed=0;float drillFraction=0;bool attackMode=false;int forcedScene=-1,sceneKind=-1;MoveTrace movement[6];bool airPaid[6]={};ComboTrace combo;int airTicks[6]={};bool spent[6]={},ground[6]={};float speeds[6]={};ShotTrace shot;std::vector<int> lastTouch;std::vector<CarControls> previous;
 Env(int team,unsigned seed):rng(seed),physics(seed){ArenaConfig cfg;cfg.noBallRot=false;arena=Arena::Create(GameMode::SOCCAR,cfg,120);for(int t=0;t<2;t++)for(int k=0;k<team;k++)cars.push_back(arena->AddCar(t?Team::ORANGE:Team::BLUE,CAR_CONFIG_OCTANE));lastTouch.resize(cars.size(),-100000);previous.resize(cars.size());arena->SetGoalScoreCallback([](Arena*ar,Team t,void*ptr){auto*e=(Env*)ptr;e->goal=int(t);e->goalSpeed=ar->ball->GetState().vel.Length();},this);}
 ~Env(){delete arena;}
 float control(float radius,float epsilon){
  auto b=arena->ball->GetState();float d[2]={1e9f,1e9f};bool valid[2]={false,false};
  for(size_t a=0;a<cars.size();a++){auto c=cars[a]->GetState();int t=a>=cars.size()/2;if(c.isDemoed)continue;valid[t]=true;d[t]=std::min(d[t],(c.pos-b.pos).Length());}
  return valid[0]&&valid[1]?control_value(d[0],d[1],radius,epsilon):0.f;
 }
 float phi(){auto b=arena->ball->GetState();float v[2]={0,0};for(size_t i=0;i<cars.size();i++){auto s=cars[i]->GetState();float c=s.isDemoed?0:std::exp(-(s.pos-b.pos).Length()/1500.f);int t=i>=cars.size()/2;v[t]=std::max(v[t],c);}return v[0]-v[1];}
 void set_scene(int kind){
 sceneKind=kind;BallState b;
 if(kind>=0&&kind<5){int indices[5]={4,0,1,2,3};auto sp=RLConst::CAR_SPAWN_LOCATIONS_SOCCAR[indices[kind]];
  for(size_t a=0;a<cars.size();a++){int t=a>=cars.size()/2;CarState c;c.pos={sp.x,sp.y,17};float yaw=sp.yawAng;if(t){c.pos.x=-c.pos.x;c.pos.y=-c.pos.y;yaw+=3.14159265f;}c.rotMat=Angle(yaw,0,0).ToRotMat();c.boost=33;cars[a]->SetState(c);}b.pos={0,0,94};arena->ball->SetState(b);return;
 }
 int attacking=rng()%2;float sign=attacking?-1.f:1.f;
 b.pos={float(int(rng()%3001)-1500),sign*(kind==5?float(int(rng()%4001)-2000):float(2600+rng()%1400)),94};
 if(kind==5)b.vel={float(int(rng()%1001)-500),float(int(rng()%1001)-500),0};
 if(kind==7){b.pos.y=sign*float(int(rng()%3001)-1500);b.pos.z=180+float(rng()%450);b.vel={0,sign*float(rng()%500),float(200+rng()%350)};}
 if(kind==8){b.pos.y=float(int(rng()%3001)-1500);b.vel={float(int(rng()%401)-200),float(int(rng()%401)-200),0};}
 arena->ball->SetState(b);
 for(size_t a=0;a<cars.size();a++){int t=a>=cars.size()/2;CarState c;float side=t?-1.f:1.f;float dist=kind==7?float(250+rng()%500):kind==8?float(1800+rng()%1200):float(350+rng()%900);
  c.pos={std::clamp(b.pos.x+float(int(rng()%1201)-600),-3300.f,3300.f),std::clamp(b.pos.y-side*dist,-4450.f,4450.f),17};
  if(kind==6&&t!=attacking)c.pos={float(int(rng()%2201)-1100),-side*4600,17};
  float yaw=std::atan2(b.pos.y-c.pos.y,b.pos.x-c.pos.x)+float(int(rng()%401)-200)/1000;
  if(kind==8)yaw+=3.14159265f;c.rotMat=Angle(yaw,0,0).ToRotMat();c.boost=kind==8?33:float(33+rng()%68);
  if(kind==7)c.vel=c.rotMat.forward*float(400+rng()%600);
  if(kind==8)c.vel=-c.rotMat.forward*float(600+rng()%400);
  cars[a]->SetState(c);
 }
 }
 void reset(bool kickoffOnly){Math::GetRandEngine()=physics;arena->ResetToRandomKickoff(int(rng()%1000000000));if(!attackMode&&forcedScene==-1&&!kickoffOnly&&(rng()%2)){BallState b;b.pos={float(int(rng()%5001)-2500),float(int(rng()%7001)-3500),94};arena->ball->SetState(b);for(size_t i=0;i<cars.size();i++){CarState s;float x=std::clamp(b.pos.x+float(int(rng()%2401)-1200),-3500.f,3500.f),y=std::clamp(b.pos.y+float(int(rng()%2401)-1200),-4500.f,4500.f);s.pos={x,y,17};float yaw=float(rng()%6284)/1000-3.14159f;s.rotMat=Angle(yaw,0,0).ToRotMat();s.boost=float(rng()%101);cars[i]->SetState(s);}}
 if(!attackMode&&forcedScene==-1&&!kickoffOnly&&drillFraction>0&&float(rng()%10000)/10000<drillFraction){
 BallState b;b.pos={float(int(rng()%4001)-2000),float(int(rng()%5001)-2500),94};
 b.vel={float(int(rng()%401)-200),float(int(rng()%401)-200),0};if(rng()%10==0)b.pos.z=200+float(rng()%350);arena->ball->SetState(b);
 for(size_t a=0;a<cars.size();a++){int t=a>=cars.size()/2;float angle=(t?-1.f:1.f)*1.5707963f+float(int(rng()%1201)-600)/1000;float dist=500+float(rng()%1600);CarState c;
 c.pos={std::clamp(b.pos.x-std::cos(angle)*dist,-3600.f,3600.f),std::clamp(b.pos.y-std::sin(angle)*dist,-4600.f,4600.f),17};c.rotMat=Angle(angle,0,0).ToRotMat();c.boost=33+float(rng()%68);cars[a]->SetState(c);}
 }
 if(forcedScene>=0||forcedScene==-2)set_scene(forcedScene==-2?int(rng()%5):forcedScene);
 else if(attackMode&&!kickoffOnly){int choice=rng()%100;set_scene(choice<30?int(rng()%5):choice<65?6:choice<85?7:8);}
 for(size_t a=0;a<cars.size();a++){movement[a].reset(move_frame(cars[a]->GetState()));airPaid[a]=false;}
 combo.reset();std::fill(airTicks,airTicks+6,0);std::fill(spent,spent+6,false);std::fill(ground,ground+6,false);std::fill(speeds,speeds+6,0);
 physics=Math::GetRandEngine();goal=-1;goalSpeed=0;shot.reset();ticks=noTouch=0;std::fill(lastTouch.begin(),lastTouch.end(),-100000);std::fill(previous.begin(),previous.end(),CarControls{});for(auto*c:cars)c->controls=CarControls{};potential=phi();}
 void write(float*w,float*p){auto b=arena->ball->GetState();vec(w,b.pos);vec(w+3,b.vel);vec(w+6,b.angVel);vec(w+9,b.rotMat.forward);vec(w+12,b.rotMat.up);for(size_t i=0;i<cars.size();i++){auto s=cars[i]->GetState();float*q=w+32*(i+1);vec(q,s.pos);vec(q+3,s.vel);vec(q+6,s.angVel);vec(q+9,s.rotMat.forward);vec(q+12,s.rotMat.up);q[15]=s.boost;q[16]=s.isOnGround;q[17]=s.hasJumped;q[18]=s.hasDoubleJumped||s.hasFlipped;q[19]=s.isSupersonic;q[20]=s.isDemoed;controls(q+21,previous[i]);}int j=0;for(auto*pad:arena->GetBoostPads()){auto s=pad->GetState();p[j++]=s.isActive;p[j++]=s.cooldown;}}
};
// See REWARD_SOURCES.md: native ports of three established RLGym reward definitions.
class Batch {
 int count,team,agents,skip,delay,maxTicks,noTouchTicks;float gamma,goalW,approachW,touchW,controlW;bool kickoffOnly; bool simpleRewards=false,controlRewards=false,skillRewards=false,attackRewards=false;float possessionRate=0,goalNoFloor=0,goalSpeedWeight=0,controlRadius=1000,controlEpsilon=100;int shotMaxAge=720;
 std::vector<std::unique_ptr<Env>> envs;std::vector<CarControls> table;Pool pool;
public:
 Batch(std::string meshes,int n,int teamSize,int threads,unsigned seed,int tickSkip,int actionDelay,float discount,float maxSeconds,float noTouchSeconds,py::dict reward,bool kickoffs):count(n),team(teamSize),agents(teamSize*2),skip(tickSkip),delay(actionDelay),maxTicks(int(maxSeconds*120)),noTouchTicks(int(noTouchSeconds*120)),gamma(discount),kickoffOnly(kickoffs),table(actions()),pool(std::clamp(threads,1,8)){
 if(n<1||n>512||team<1||team>3||skip<1||skip>16||delay<0||delay>=skip||maxTicks<skip||noTouchTicks<skip||gamma<=0||gamma>1)throw std::invalid_argument("Invalid native batch contract");
 std::string profile=reward.contains("profile")?py::cast<std::string>(reward["profile"]):"legacy";
 if(profile!="legacy"&&profile!="rlgym_simple_v1"&&profile!="control_shots_v1"&&profile!="skills_v1"&&profile!="attack_v1")throw std::invalid_argument("Unknown reward profile");
 attackRewards=profile=="attack_v1";skillRewards=profile=="skills_v1"||attackRewards;controlRewards=profile=="control_shots_v1";simpleRewards=profile!="legacy";
 if(controlRewards){
  possessionRate=reward.contains("possession_rate")?py::cast<float>(reward["possession_rate"]):.2f;
  goalNoFloor=reward.contains("goal_no_floor")?py::cast<float>(reward["goal_no_floor"]):0.f;
  goalSpeedWeight=reward.contains("goal_speed")?py::cast<float>(reward["goal_speed"]):0.f;
  controlRadius=reward.contains("control_radius")?py::cast<float>(reward["control_radius"]):1000.f;
  controlEpsilon=reward.contains("distance_epsilon")?py::cast<float>(reward["distance_epsilon"]):100.f;
  float ageSeconds=reward.contains("shot_max_age_seconds")?py::cast<float>(reward["shot_max_age_seconds"]):6.f;
  if(!std::isfinite(ageSeconds)||ageSeconds<1.f/120||ageSeconds>600)throw std::invalid_argument("Invalid shot age window");
  shotMaxAge=int(120*ageSeconds);
  if(!std::isfinite(possessionRate)||!std::isfinite(goalNoFloor)||!std::isfinite(goalSpeedWeight)||!std::isfinite(controlRadius)||!std::isfinite(controlEpsilon)||possessionRate<0||goalNoFloor<0||goalSpeedWeight<0||controlRadius<=0||controlEpsilon<=0||shotMaxAge<1)throw std::invalid_argument("Invalid control/shot reward configuration");
 }
 goalW=py::cast<float>(reward["goal"]);approachW=py::cast<float>(reward["approach"]);touchW=py::cast<float>(reward["touch"]);controlW=py::cast<float>(reward["control_progress"]);
 static std::once_flag init;std::call_once(init,[&]{RocketSim::Init(meshes,true);});for(int i=0;i<count;i++){envs.emplace_back(new Env(team,seed+7919*i));if(skillRewards)envs.back()->drillFraction=.6f;envs.back()->attackMode=attackRewards;envs.back()->reset(kickoffOnly);}}
 py::array_t<float> locations(){py::array_t<float>r({34,4});float*p=r.mutable_data();for(auto*b:envs[0]->arena->GetBoostPads()){vec(p,b->config.pos);p[3]=b->config.isBig;p+=4;}return r;}
 py::dict observe(){py::array_t<float>w({count,agents+1,32}),p({count,34,2});std::fill(w.mutable_data(),w.mutable_data()+w.size(),0.f);for(int i=0;i<count;i++)envs[i]->write(w.mutable_data()+i*(agents+1)*32,p.mutable_data()+i*68);py::dict d;d["world"]=w;d["pads"]=p;return d;}
 py::dict step(py::array_t<int64_t,py::array::c_style|py::array::forcecast> ac){if(ac.ndim()!=2||ac.shape(0)!=count||ac.shape(1)!=agents)throw std::invalid_argument("actions must have shape [arenas, cars]");auto ap=ac.data();for(int i=0;i<count*agents;i++)if(ap[i]<0||ap[i]>=int(table.size()))throw std::invalid_argument("action outside table");
 py::array_t<float>w({count,agents+1,32}),p({count,34,2}),fw({count,agents+1,32}),fp({count,34,2}),rw({count,agents}),info({count,8}),rewardInfo({count,10}),skillInfo({count,6}),attackInfo({count,10});py::array_t<bool>term(count),trunc(count);
 float*wp=w.mutable_data(),*pp=p.mutable_data(),*fwp=fw.mutable_data(),*fpp=fp.mutable_data(),*rp=rw.mutable_data(),*ip=info.mutable_data(),*xp=rewardInfo.mutable_data();float*at=attackInfo.mutable_data();std::fill(at,at+attackInfo.size(),0.f);float*sp=skillInfo.mutable_data();std::fill(sp,sp+skillInfo.size(),0.f);bool*te=term.mutable_data(),*tr=trunc.mutable_data();std::fill(wp,wp+w.size(),0);std::fill(fwp,fwp+fw.size(),0);std::fill(ip,ip+info.size(),0);std::fill(xp,xp+rewardInfo.size(),0);
 {py::gil_scoped_release release;pool.run(count,[&](int i){Env&e=*envs[i];Math::GetRandEngine()=e.physics;uint64_t before=e.arena->tickCount;bool touched[2]={false,false};bool carTouched[6]={};float touches[2]={0,0};int floorTicks=0;float airHits[6]={},resets[6]={};Vec ballBefore=e.arena->ball->GetState().vel;Vec ballPosBefore=e.arena->ball->GetState().pos;float launch[6]={},flip[6]={},recover[6]={},jumpContact[6]={};
 // One physics tick holds the previous decision, then the new action is applied.
 for(int k=0;k<skip;k++){
  if(k==delay)for(int a=0;a<agents;a++)e.cars[a]->controls=table[ap[i*agents+a]];
  e.arena->Step(1);e.ticks++;e.noTouch++;int teamBits=0;
  for(int a=0;a<agents;a++){
   auto state=e.cars[a]->GetState();
   if(state.ballHitInfo.isValid&&state.ballHitInfo.tickCountWhenHit>=before&&state.ballHitInfo.tickCountWhenHit==e.arena->tickCount-1){
    int t=a>=team;touched[t]=true;carTouched[a]=true;teamBits|=1<<t;e.noTouch=0;
    if(e.ticks-e.lastTouch[a]>=30){touches[t]+=1;e.lastTouch[a]=e.ticks;}
   }
  }
  if(skillRewards){
   e.combo.touch(teamBits,e.ticks);auto bs=e.arena->ball->GetState();
   for(int a=0;a<agents;a++){auto cs=e.cars[a]->GetState();int t=a>=team;bool hit=cs.ballHitInfo.isValid&&cs.ballHitInfo.tickCountWhenHit==e.arena->tickCount-1;bool used=cs.hasDoubleJumped||cs.hasFlipped;
    e.airTicks[a]=cs.isOnGround?0:e.airTicks[a]+1;
    if(hit&&cs.pos.z>200&&bs.pos.z>200&&e.airTicks[a]>=18){airHits[a]=1;e.combo.event(t,2,e.ticks);}
    if(hit&&e.spent[a]&&!used&&!cs.isOnGround){resets[a]=1;e.combo.event(t,4,e.ticks);}
    if(cs.isOnGround&&!e.ground[a]&&e.spent[a]&&cs.vel.Length2D()>e.speeds[a]+80)e.combo.event(t,8,e.ticks);
    if(attackRewards){auto reward=e.movement[a].update(move_frame(cs),bs.pos,e.ticks);launch[a]+=reward.launch;flip[a]+=reward.flip;recover[a]+=reward.recovery;
     if(cs.isOnGround)e.airPaid[a]=false;
     if(hit&&!e.airPaid[a]&&(cs.hasJumped||e.airTicks[a]>=18)&&!cs.isOnGround&&cs.pos.z>90&&bs.pos.z>140&&e.airTicks[a]>=12){jumpContact[a]=2.f*std::min(1.f,std::min((bs.pos.z-90)/300.f,e.airTicks[a]/30.f));e.airPaid[a]=true;}
    }
    e.spent[a]=used;e.ground[a]=cs.isOnGround;e.speeds[a]=cs.vel.Length2D();
   }
  }
  if(controlRewards){
   // Same-tick floor + touch is conservatively classified as a floor contact.
   e.shot.observe(teamBits,false,e.ticks);
   if(goalNoFloor>0&&e.shot.owner>=0&&!e.shot.floorSeen){bool floor=ball_floor_contact(e.arena);if(floor){e.shot.floorSeen=true;floorTicks++;}}
  }
  if(e.goal>=0)break;
 }
 for(int a=0;a<agents;a++)e.previous[a]=table[ap[i*agents+a]];e.physics=Math::GetRandEngine();te[i]=e.goal>=0;tr[i]=!te[i]&&(e.ticks>=maxTicks||e.noTouch>=noTouchTicks);
 float g=e.goal<0?0:(e.goal==0?1.f:-1.f);float ph=e.phi();float shaping=approachW*(gamma*(te[i]?0:ph)-e.potential);e.potential=ph;float ctrl[2]={0,0};auto ball=e.arena->ball->GetState();for(int a=0;a<agents;a++){auto s=e.cars[a]->GetState();int t=a>=team;Vec target(0,t?-5120:5120,300);Vec dir=target-ball.pos;float den=std::max(1.f,dir.Length());float progress=std::clamp(ball.vel.Dot(dir)/den/2300.f,0.f,1.f);float close=std::clamp(1-(s.pos-ball.pos).Length()/600.f,0.f,1.f);float match=std::exp(-(s.vel-ball.vel).Length()/800.f);if(!s.isDemoed)ctrl[t]=std::max(ctrl[t],close*match*progress);}
 float touch=touchW*(std::min(1.f,touches[0])-std::min(1.f,touches[1]));float control=controlW*(float(e.arena->tickCount-before)/120)*(ctrl[0]-ctrl[1]);float r=goalW*g+shaping+touch+control;for(int a=0;a<agents;a++)rp[i*agents+a]=(a<team?r:-r);
 if(simpleRewards){
  float vpbBlue=0,touchBlue=0;float dt=float(e.arena->tickCount-before)/120;
  for(int a=0;a<agents;a++){
   auto cs=e.cars[a]->GetState();Vec d=ball.pos-cs.pos;
   float toward=d.Length()>1e-6f?std::max(0.f,cs.vel.Dot(d)/d.Length()/2300.f):0.f;
   if(attackRewards)toward*=std::max(0.f,cs.rotMat.forward.Dot(d.Normalized()));
   float vpb=approachW*dt*toward;float hit=touchW*(carTouched[a]?1.f:0.f);
   rp[i*agents+a]=(a<team?goalW*g:-goalW*g)+vpb+hit;
   if(a<team){vpbBlue+=vpb;touchBlue+=hit;}
  }
  shaping=vpbBlue;touch=touchBlue;control=0;
 }
 if(skillRewards){
  float dt=float(e.arena->tickCount-before)/120;float accel=(ball.vel-ballBefore).Length()/6000;
  for(int a=0;a<agents;a++){auto cs=e.cars[a]->GetState();int t=a>=team;Vec dir=(ball.pos-cs.pos).Normalized();
   float face=.05f*dt*std::max(0.f,cs.rotMat.forward.Dot(dir))*std::clamp(cs.vel.Dot(dir)/500.f,0.f,1.f);
   Vec goalDir=(Vec(0,t?-5120:5120,300)-ball.pos).Normalized();
   float shot=carTouched[a]?.5f*std::max(0.f,ball.vel.Dot(goalDir)/2300.f):0;
   float strength=carTouched[a]?.5f*accel:0;float air=.5f*airHits[a];
   float bonus=e.goal>=0?e.combo.goal(e.goal,e.ticks)*(t==e.goal?1.f:-1.f):0;
   if(attackRewards){
    float q=attack_shot_quality(ball.pos,ball.vel,t),oldq=attack_shot_quality(ballPosBefore,ballBefore,t);
    float aim=carTouched[a]?std::max(0.f,q-oldq):0;
    float airApproach=bsafe_air(cs,ball,dt);
    shot=carTouched[a]?.1f*q:0;air=jumpContact[a];
    rp[i*agents+a]+=aim+launch[a]+flip[a]+recover[a]+airApproach;
    at[i*10]+=aim;at[i*10+1]+=launch[a];at[i*10+2]+=flip[a];at[i*10+3]+=recover[a];at[i*10+4]+=jumpContact[a];at[i*10+5]+=airApproach;at[i*10+6]+=carTouched[a]&&q>.2f;
   }
   rp[i*agents+a]+=face+shot+strength+air+bonus;
   sp[i*6]+=carTouched[a];sp[i*6+1]+=strength;sp[i*6+2]+=airHits[a];sp[i*6+3]+=resets[a];sp[i*6+4]+=std::max(0.f,bonus);sp[i*6+5]+=shot;
  }
 }
 if(controlRewards){
  float score=e.control(controlRadius,controlEpsilon);float possession=possessionRate*float(e.arena->tickCount-before)/120*score;
  bool credited=e.goal>=0&&e.shot.credited(e.goal,e.ticks,shotMaxAge);
  bool clean=credited&&!e.shot.floorSeen;
  float cleanBonus=clean?goalNoFloor*g:0.f;
  float speedBonus=credited?goalSpeedWeight*std::clamp(e.goalSpeed/6000.f,0.f,1.f)*g:0.f;
  for(int a=0;a<agents;a++)rp[i*agents+a]+=(a<team?1.f:-1.f)*(possession+cleanBonus+speedBonus);
  xp[i*10]=score;xp[i*10+1]=possession;xp[i*10+2]=cleanBonus;xp[i*10+3]=speedBonus;
  xp[i*10+4]=(clean&&goalNoFloor>0)?1.f:0.f;xp[i*10+5]=e.goal>=0?e.goalSpeed:0;
  xp[i*10+6]=credited?1.f:0.f;xp[i*10+7]=float(floorTicks);xp[i*10+8]=float(e.shot.owner);xp[i*10+9]=e.shot.owner>=0?(e.ticks-e.shot.touchTick)/120.f:-1.f;
 }
 if(attackRewards){at[i*10+7]=e.goal>=0&&e.sceneKind>=0&&e.sceneKind<5;at[i*10+8]=e.goal>=0&&e.sceneKind>=5;at[i*10+9]=float(e.sceneKind);}
 ip[i*8]=g;ip[i*8+1]=touched[0];ip[i*8+2]=touched[1];ip[i*8+3]=goalW*g;ip[i*8+4]=shaping;ip[i*8+5]=touch;ip[i*8+6]=control;ip[i*8+7]=float(e.arena->tickCount-before);
 e.write(fwp+i*(agents+1)*32,fpp+i*68);if(te[i]||tr[i])e.reset(kickoffOnly);e.write(wp+i*(agents+1)*32,pp+i*68);
 });}
 py::dict d;d["world"]=w;d["pads"]=p;d["final_world"]=fw;d["final_pads"]=fp;d["rewards"]=rw;d["terminated"]=term;d["truncated"]=trunc;d["info"]=info;d["reward_info"]=rewardInfo;d["skill_info"]=skillInfo;d["attack_info"]=attackInfo;return d;
 }
 void scenario(int kind){if(kind< -2||kind>8)throw std::invalid_argument("Invalid scenario");for(auto&e:envs){e->forcedScene=kind;e->reset(true);}}
 void skill_stage(float progress){if(!std::isfinite(progress)||progress<0||progress>1)throw std::invalid_argument("Invalid skill schedule");if(attackRewards){touchW=.1f;approachW=.3f;}else if(skillRewards){touchW=1.f-.8f*progress;approachW=1.f-.6f*progress;}}
 void drill_fraction(float fraction){if(!std::isfinite(fraction)||fraction<0||fraction>1)throw std::invalid_argument("Invalid drill fraction");for(auto&e:envs)e->drillFraction=fraction;}
 // Complete public pose injection for bounded ground-driving diagnostics.
 void set_ground(int i,py::array_t<float,py::array::c_style|py::array::forcecast> data){
  if(i<0||i>=count)throw std::invalid_argument("bad arena index");envs[i]->reset(true);test_state(i,data);auto&e=*envs[i];auto p=data.data();
  for(int a=0;a<agents;a++){auto q=p+(a+1)*32;auto c=e.cars[a]->GetState();Vec f(q[9],q[10],q[11]),u(q[12],q[13],q[14]);
   if(f.Length()<.99f||u.Length()<.99f||std::abs(f.Dot(u))>.01f)throw std::invalid_argument("Ground diagnostic requires orthonormal public orientation");
   c.rotMat=RotMat(f.Normalized(),u.Cross(f).Normalized(),u.Normalized());c.angVel={q[6],q[7],q[8]};e.cars[a]->SetState(c);e.movement[a].reset(move_frame(c));e.airPaid[a]=false;e.airTicks[a]=0;
  }
 }
 py::dict inspect(int i){if(i<0||i>=count)throw std::invalid_argument("bad arena index");auto&e=*envs[i];py::dict d;d["scenario_id"]=e.sceneKind;d["floor_contact"]=ball_floor_contact(e.arena);d["floor_tracking_enabled"]=controlRewards&&goalNoFloor>0;d["last_touch_team"]=e.shot.owner;d["floor_since_touch"]=e.shot.floorSeen;d["age_ticks"]=e.ticks-e.shot.touchTick;return d;}
 // Controlled, bounded state injection for contract tests only; not used during training.
 void test_state(int i,py::array_t<float,py::array::c_style|py::array::forcecast> data){if(i<0||i>=count||data.ndim()!=2||data.shape(0)!=agents+1||data.shape(1)!=32)throw std::invalid_argument("bad test state");auto& e=*envs[i];auto p=data.data();BallState b;b.pos={p[0],p[1],p[2]};b.vel={p[3],p[4],p[5]};e.arena->ball->SetState(b);for(int a=0;a<agents;a++){auto q=p+(a+1)*32;CarState s;s.pos={q[0],q[1],q[2]};s.vel={q[3],q[4],q[5]};s.rotMat=Angle(0,0,0).ToRotMat();s.boost=q[15];e.cars[a]->SetState(s);}e.goal=-1;e.goalSpeed=0;e.shot.reset();e.potential=e.phi();}
};
#include "features.h"
PYBIND11_MODULE(_attention_native,m){m.def("encode",&encode_native);m.attr("reward_version")=3;
 m.def("attack_shot_quality",[](float x,float y,float z,float vx,float vy,float vz,int team){return attack_shot_quality({x,y,z},{vx,vy,vz},team);});
 py::class_<MoveTrace>(m,"MoveTrace").def(py::init<>()).def("probe",[](MoveTrace& trace,std::vector<float> row,std::vector<float> ball,bool flipping,int tick){if(row.size()!=32||ball.size()!=3)throw std::invalid_argument("bad movement frame");MoveFrame f{{row[0],row[1],row[2]},{row[3],row[4],row[5]},{row[9],row[10],row[11]},{row[12],row[13],row[14]},row[16]>.5f,row[17]>.5f,flipping};auto r=trace.update(f,{ball[0],ball[1],ball[2]},tick);return std::vector<float>{r.launch,r.flip,r.recovery};});
 py::class_<ComboTrace>(m,"ComboTrace").def(py::init<>()).def("touch",&ComboTrace::touch).def("event",&ComboTrace::event).def("goal",&ComboTrace::goal);
 m.def("control_value",&control_value);
 py::class_<ShotTrace>(m,"ShotTrace").def(py::init<>()).def("reset",&ShotTrace::reset).def("observe",&ShotTrace::observe).def("credited",&ShotTrace::credited).def("clean",&ShotTrace::clean);
m.attr("feature_version")=2;m.doc()="AttentionForge RocketSim vector environment v1; Octane, 120Hz";m.attr("contract")="attentionforge-v1-raw32-delay1";m.def("action_table",[]{auto a=actions();py::array_t<float>r({int(a.size()),8});for(size_t i=0;i<a.size();i++)controls(r.mutable_data()+i*8,a[i]);return r;});py::class_<Batch>(m,"Batch").def(py::init<std::string,int,int,int,unsigned,int,int,float,float,float,py::dict,bool>()).def("observe",&Batch::observe).def("inspect",&Batch::inspect).def("set_ground",&Batch::set_ground).def("scenario",&Batch::scenario).def("skill_stage",&Batch::skill_stage).def("drill_fraction",&Batch::drill_fraction).def("step",&Batch::step).def("pad_locations",&Batch::locations).def("test_state",&Batch::test_state);}
