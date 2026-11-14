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
 int goal=-1,ticks=0,noTouch=0;float potential=0;std::vector<int> lastTouch;std::vector<CarControls> previous;
 Env(int team,unsigned seed):rng(seed),physics(seed){ArenaConfig cfg;cfg.noBallRot=false;arena=Arena::Create(GameMode::SOCCAR,cfg,120);for(int t=0;t<2;t++)for(int k=0;k<team;k++)cars.push_back(arena->AddCar(t?Team::ORANGE:Team::BLUE,CAR_CONFIG_OCTANE));lastTouch.resize(cars.size(),-100000);previous.resize(cars.size());arena->SetGoalScoreCallback([](Arena*,Team t,void*ptr){((Env*)ptr)->goal=int(t);},this);}
 ~Env(){delete arena;}
 float phi(){auto b=arena->ball->GetState();float v[2]={0,0};for(size_t i=0;i<cars.size();i++){auto s=cars[i]->GetState();float c=s.isDemoed?0:std::exp(-(s.pos-b.pos).Length()/1500.f);int t=i>=cars.size()/2;v[t]=std::max(v[t],c);}return v[0]-v[1];}
 void reset(bool kickoffOnly){Math::GetRandEngine()=physics;arena->ResetToRandomKickoff(int(rng()%1000000000));if(!kickoffOnly&&(rng()%2)){BallState b;b.pos={float(int(rng()%5001)-2500),float(int(rng()%7001)-3500),94};arena->ball->SetState(b);for(size_t i=0;i<cars.size();i++){CarState s;float x=std::clamp(b.pos.x+float(int(rng()%2401)-1200),-3500.f,3500.f),y=std::clamp(b.pos.y+float(int(rng()%2401)-1200),-4500.f,4500.f);s.pos={x,y,17};float yaw=float(rng()%6284)/1000-3.14159f;s.rotMat=Angle(yaw,0,0).ToRotMat();s.boost=float(rng()%101);cars[i]->SetState(s);}}
 physics=Math::GetRandEngine();goal=-1;ticks=noTouch=0;std::fill(lastTouch.begin(),lastTouch.end(),-100000);std::fill(previous.begin(),previous.end(),CarControls{});for(auto*c:cars)c->controls=CarControls{};potential=phi();}
 void write(float*w,float*p){auto b=arena->ball->GetState();vec(w,b.pos);vec(w+3,b.vel);vec(w+6,b.angVel);vec(w+9,b.rotMat.forward);vec(w+12,b.rotMat.up);for(size_t i=0;i<cars.size();i++){auto s=cars[i]->GetState();float*q=w+32*(i+1);vec(q,s.pos);vec(q+3,s.vel);vec(q+6,s.angVel);vec(q+9,s.rotMat.forward);vec(q+12,s.rotMat.up);q[15]=s.boost;q[16]=s.isOnGround;q[17]=s.hasJumped;q[18]=s.hasDoubleJumped||s.hasFlipped;q[19]=s.isSupersonic;q[20]=s.isDemoed;controls(q+21,previous[i]);}int j=0;for(auto*pad:arena->GetBoostPads()){auto s=pad->GetState();p[j++]=s.isActive;p[j++]=s.cooldown;}}
};
// See REWARD_SOURCES.md: native ports of three established RLGym reward definitions.
class Batch {
 int count,team,agents,skip,delay,maxTicks,noTouchTicks;float gamma,goalW,approachW,touchW,controlW;bool kickoffOnly; bool simpleRewards=false;
 std::vector<std::unique_ptr<Env>> envs;std::vector<CarControls> table;Pool pool;
public:
 Batch(std::string meshes,int n,int teamSize,int threads,unsigned seed,int tickSkip,int actionDelay,float discount,float maxSeconds,float noTouchSeconds,py::dict reward,bool kickoffs):count(n),team(teamSize),agents(teamSize*2),skip(tickSkip),delay(actionDelay),maxTicks(int(maxSeconds*120)),noTouchTicks(int(noTouchSeconds*120)),gamma(discount),kickoffOnly(kickoffs),table(actions()),pool(std::clamp(threads,1,8)){
 if(n<1||n>512||team<1||team>3||skip<1||skip>16||delay<0||delay>=skip||maxTicks<skip||noTouchTicks<skip||gamma<=0||gamma>1)throw std::invalid_argument("Invalid native batch contract");
 simpleRewards=reward.contains("profile")&&py::cast<std::string>(reward["profile"])=="rlgym_simple_v1";
 goalW=py::cast<float>(reward["goal"]);approachW=py::cast<float>(reward["approach"]);touchW=py::cast<float>(reward["touch"]);controlW=py::cast<float>(reward["control_progress"]);
 static std::once_flag init;std::call_once(init,[&]{RocketSim::Init(meshes,true);});for(int i=0;i<count;i++){envs.emplace_back(new Env(team,seed+7919*i));envs.back()->reset(kickoffOnly);}}
 py::array_t<float> locations(){py::array_t<float>r({34,4});float*p=r.mutable_data();for(auto*b:envs[0]->arena->GetBoostPads()){vec(p,b->config.pos);p[3]=b->config.isBig;p+=4;}return r;}
 py::dict observe(){py::array_t<float>w({count,agents+1,32}),p({count,34,2});std::fill(w.mutable_data(),w.mutable_data()+w.size(),0.f);for(int i=0;i<count;i++)envs[i]->write(w.mutable_data()+i*(agents+1)*32,p.mutable_data()+i*68);py::dict d;d["world"]=w;d["pads"]=p;return d;}
 py::dict step(py::array_t<int64_t,py::array::c_style|py::array::forcecast> ac){if(ac.ndim()!=2||ac.shape(0)!=count||ac.shape(1)!=agents)throw std::invalid_argument("actions must have shape [arenas, cars]");auto ap=ac.data();for(int i=0;i<count*agents;i++)if(ap[i]<0||ap[i]>=int(table.size()))throw std::invalid_argument("action outside table");
 py::array_t<float>w({count,agents+1,32}),p({count,34,2}),fw({count,agents+1,32}),fp({count,34,2}),rw({count,agents}),info({count,8});py::array_t<bool>term(count),trunc(count);
 float*wp=w.mutable_data(),*pp=p.mutable_data(),*fwp=fw.mutable_data(),*fpp=fp.mutable_data(),*rp=rw.mutable_data(),*ip=info.mutable_data();bool*te=term.mutable_data(),*tr=trunc.mutable_data();std::fill(wp,wp+w.size(),0);std::fill(fwp,fwp+fw.size(),0);std::fill(ip,ip+info.size(),0);
 {py::gil_scoped_release release;pool.run(count,[&](int i){Env&e=*envs[i];Math::GetRandEngine()=e.physics;uint64_t before=e.arena->tickCount;bool touched[2]={false,false};bool carTouched[6]={};float touches[2]={0,0};
 // One physics tick holds the previous decision, then the new action is applied.
 for(int k=0;k<skip;k++){if(k==delay)for(int a=0;a<agents;a++)e.cars[a]->controls=table[ap[i*agents+a]];e.arena->Step(1);e.ticks++;e.noTouch++;for(int a=0;a<agents;a++){auto s=e.cars[a]->GetState();if(s.ballHitInfo.isValid&&s.ballHitInfo.tickCountWhenHit>=before&&s.ballHitInfo.tickCountWhenHit==e.arena->tickCount-1){int t=a>=team;touched[t]=true;carTouched[a]=true;e.noTouch=0;if(e.ticks-e.lastTouch[a]>=30){touches[t]+=1;e.lastTouch[a]=e.ticks;}}}if(e.goal>=0)break;}
 for(int a=0;a<agents;a++)e.previous[a]=table[ap[i*agents+a]];e.physics=Math::GetRandEngine();te[i]=e.goal>=0;tr[i]=!te[i]&&(e.ticks>=maxTicks||e.noTouch>=noTouchTicks);
 float g=e.goal<0?0:(e.goal==0?1.f:-1.f);float ph=e.phi();float shaping=approachW*(gamma*(te[i]?0:ph)-e.potential);e.potential=ph;float ctrl[2]={0,0};auto ball=e.arena->ball->GetState();for(int a=0;a<agents;a++){auto s=e.cars[a]->GetState();int t=a>=team;Vec target(0,t?-5120:5120,300);Vec dir=target-ball.pos;float den=std::max(1.f,dir.Length());float progress=std::clamp(ball.vel.Dot(dir)/den/2300.f,0.f,1.f);float close=std::clamp(1-(s.pos-ball.pos).Length()/600.f,0.f,1.f);float match=std::exp(-(s.vel-ball.vel).Length()/800.f);if(!s.isDemoed)ctrl[t]=std::max(ctrl[t],close*match*progress);}
 float touch=touchW*(std::min(1.f,touches[0])-std::min(1.f,touches[1]));float control=controlW*(float(e.arena->tickCount-before)/120)*(ctrl[0]-ctrl[1]);float r=goalW*g+shaping+touch+control;for(int a=0;a<agents;a++)rp[i*agents+a]=(a<team?r:-r);
 if(simpleRewards){
  float vpbBlue=0,touchBlue=0;float dt=float(e.arena->tickCount-before)/120;
  for(int a=0;a<agents;a++){
   auto cs=e.cars[a]->GetState();Vec d=ball.pos-cs.pos;
   float toward=d.Length()>1e-6f?std::max(0.f,cs.vel.Dot(d)/d.Length()/2300.f):0.f;
   float vpb=approachW*dt*toward;float hit=touchW*(carTouched[a]?1.f:0.f);
   rp[i*agents+a]=(a<team?goalW*g:-goalW*g)+vpb+hit;
   if(a<team){vpbBlue+=vpb;touchBlue+=hit;}
  }
  shaping=vpbBlue;touch=touchBlue;control=0;
 }
 ip[i*8]=g;ip[i*8+1]=touched[0];ip[i*8+2]=touched[1];ip[i*8+3]=goalW*g;ip[i*8+4]=shaping;ip[i*8+5]=touch;ip[i*8+6]=control;ip[i*8+7]=float(e.arena->tickCount-before);
 e.write(fwp+i*(agents+1)*32,fpp+i*68);if(te[i]||tr[i])e.reset(kickoffOnly);e.write(wp+i*(agents+1)*32,pp+i*68);
 });}
 py::dict d;d["world"]=w;d["pads"]=p;d["final_world"]=fw;d["final_pads"]=fp;d["rewards"]=rw;d["terminated"]=term;d["truncated"]=trunc;d["info"]=info;return d;
 }
 // Controlled, bounded state injection for contract tests only; not used during training.
 void test_state(int i,py::array_t<float,py::array::c_style|py::array::forcecast> data){if(i<0||i>=count||data.ndim()!=2||data.shape(0)!=agents+1||data.shape(1)!=32)throw std::invalid_argument("bad test state");auto& e=*envs[i];auto p=data.data();BallState b;b.pos={p[0],p[1],p[2]};b.vel={p[3],p[4],p[5]};e.arena->ball->SetState(b);for(int a=0;a<agents;a++){auto q=p+(a+1)*32;CarState s;s.pos={q[0],q[1],q[2]};s.vel={q[3],q[4],q[5]};s.rotMat=Angle(0,0,0).ToRotMat();s.boost=q[15];e.cars[a]->SetState(s);}e.goal=-1;e.potential=e.phi();}
};
#include "features.h"
PYBIND11_MODULE(_attention_native,m){m.def("encode",&encode_native);m.attr("feature_version")=2;m.doc()="AttentionForge RocketSim vector environment v1; Octane, 120Hz";m.attr("contract")="attentionforge-v1-raw32-delay1";m.def("action_table",[]{auto a=actions();py::array_t<float>r({int(a.size()),8});for(size_t i=0;i<a.size();i++)controls(r.mutable_data()+i*8,a[i]);return r;});py::class_<Batch>(m,"Batch").def(py::init<std::string,int,int,int,unsigned,int,int,float,float,float,py::dict,bool>()).def("observe",&Batch::observe).def("step",&Batch::step).def("pad_locations",&Batch::locations).def("test_state",&Batch::test_state);}
