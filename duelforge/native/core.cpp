#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include "RocketSim.h"
#include <thread>
#include <mutex>
#include <condition_variable>
#include <atomic>
#include <random>
#include <functional>
#include <memory>
#include <algorithm>
#include <cmath>
namespace py=pybind11;
using namespace RocketSim;
class Pool{
 std::vector<std::thread> workers;std::mutex mutex;std::condition_variable start,done;std::function<void(int)> job;std::atomic<int> cursor{0};int count=0,generation=0,pending=0;bool quit=false;
 void work(){for(;;){int i=cursor.fetch_add(1);if(i>=count)return;job(i);}}
public:
 Pool(int n){for(int k=1;k<n;k++)workers.emplace_back([this]{int old=0;for(;;){std::unique_lock<std::mutex> lock(mutex);start.wait(lock,[&]{return quit||old!=generation;});if(quit)return;old=generation;lock.unlock();work();lock.lock();if(--pending==0)done.notify_one();}});}
 ~Pool(){{std::lock_guard<std::mutex> lock(mutex);quit=true;}start.notify_all();for(auto&t:workers)t.join();}
 void run(int n,std::function<void(int)> fn){{std::lock_guard<std::mutex> lock(mutex);job=std::move(fn);count=n;cursor=0;pending=int(workers.size());generation++;}start.notify_all();work();std::unique_lock<std::mutex> lock(mutex);done.wait(lock,[&]{return pending==0;});}
};
std::vector<CarControls> table(){std::vector<CarControls> out;
 for(int t=-1;t<=1;t++)for(int s=-1;s<=1;s++)for(int b=0;b<2;b++)for(int h=0;h<2;h++){if(b&&t!=1)continue;CarControls c;c.throttle=t;c.steer=c.yaw=s;c.boost=b;c.handbrake=h;out.push_back(c);}
 for(int p=-1;p<=1;p++)for(int y=-1;y<=1;y++)for(int r=-1;r<=1;r++)for(int j=0;j<2;j++)for(int b=0;b<2;b++){if(j&&y)continue;if(p==0&&r==0&&j==0)continue;CarControls c;c.throttle=b;c.steer=c.yaw=y;c.pitch=p;c.roll=r;c.jump=j;c.boost=b;c.handbrake=j&&(p||y||r);out.push_back(c);}return out;}
void vec(float*p,Vec v){p[0]=v.x;p[1]=v.y;p[2]=v.z;}
void control(float*p,const CarControls&c){p[0]=c.throttle;p[1]=c.steer;p[2]=c.pitch;p[3]=c.yaw;p[4]=c.roll;p[5]=c.jump;p[6]=c.boost;p[7]=c.handbrake;}
float phi(Vec b){return std::exp(-(b-Vec(0,5120,200)).Length()/3000.f)-std::exp(-(b-Vec(0,-5120,200)).Length()/3000.f);}
void encode_one(const float*w,const float*p,const int*inv,float*out,bool*mask,int a,const std::vector<CarControls>&acts){
 const float*ego=w+(a+1)*32;float sign=a? -1.f:1.f;float ball[9];for(int j=0;j<9;j++)ball[j]=w[j]*(j%3==2?1:sign);
 int idx=0;for(int j=0;j<9;j++)out[idx++]=ball[j]/(j<3?5000.f:j<6?2300.f:3.f);
 for(int j=0;j<8;j++)out[idx++]=ego[21+j];
 for(int j=0;j<34;j++){int k=a?inv[j]:j;out[idx++]=p[2*k]>.5f?1.f:1.f/(1.f+p[2*k+1]);}
 for(int b: {a,1-a}){const float*c=w+(b+1)*32;float s[15];for(int j=0;j<15;j++)s[j]=c[j]*(j%3==2?1:sign);
  for(int j=0;j<3;j++)out[idx++]=s[j]/5000.f;for(int j=9;j<15;j++)out[idx++]=s[j];for(int j=3;j<6;j++)out[idx++]=s[j]/2300.f;for(int j=6;j<9;j++)out[idx++]=s[j]/3.f;
  Vec f(s[9],s[10],s[11]),u(s[12],s[13],s[14]),right=u.Cross(f);Vec av(s[6],s[7],s[8]),d(ball[0]-s[0],ball[1]-s[1],ball[2]-s[2]),v(ball[3]-s[3],ball[4]-s[4],ball[5]-s[5]);
  for(Vec val:{av/3.f,d/5000.f,v/2300.f}){out[idx++]=f.Dot(val);out[idx++]=right.Dot(val);out[idx++]=u.Dot(val);}
  out[idx++]=c[15]/100.f;out[idx++]=c[16];out[idx++]=c[29];out[idx++]=c[20];out[idx++]=c[17];
 }
 bool ground=ego[16]>.5f,can=ego[29]>.5f,turtle=ego[14]<-.5f&&ego[2]<65;
 for(int j=0;j<90;j++){auto c=acts[j];bool ok=ground?(j<24):((j>=24&&!c.jump)||(j<24&&c.throttle==float(c.boost)&&((c.yaw!=0)==c.handbrake)));
  if(c.jump&&(can||turtle))ok=true;if(c.boost&&ego[15]<=0)ok=false;mask[j]=ok;}
}
struct Env{
 Arena*arena;Car*cars[2];std::mt19937 rng;std::default_random_engine physics;int goal=-1,ticks=0,noTouch=0,scene=-1,forced=-1;float potential=0;CarControls previous[2];
 Env(unsigned seed):rng(seed),physics(seed){ArenaConfig cfg;cfg.noBallRot=false;arena=Arena::Create(GameMode::SOCCAR,cfg,120);cars[0]=arena->AddCar(Team::BLUE,CAR_CONFIG_OCTANE);cars[1]=arena->AddCar(Team::ORANGE,CAR_CONFIG_OCTANE);arena->SetGoalScoreCallback([](Arena*,Team t,void*ptr){((Env*)ptr)->goal=int(t);},this);}
 ~Env(){delete arena;}
 void reset(){Math::GetRandEngine()=physics;arena->ResetToRandomKickoff(int(rng()%1000000000));scene=forced>=0?forced:forced==-2?int(rng()%5):((rng()%100<40)?int(rng()%5):5);
  BallState ball;
  if(scene<5){int keys[5]={4,0,1,2,3};auto sp=RLConst::CAR_SPAWN_LOCATIONS_SOCCAR[keys[scene]];
   for(int a=0;a<2;a++){CarState s;s.pos={sp.x*(a?-1.f:1.f),sp.y*(a?-1.f:1.f),17};s.rotMat=Angle(sp.yawAng+(a?3.14159265f:0),0,0).ToRotMat();s.boost=33;cars[a]->SetState(s);}ball.pos={0,0,94};
  }else{
   ball.pos={float(int(rng()%5001)-2500),float(int(rng()%6501)-3250),94};ball.vel={float(int(rng()%801)-400),float(int(rng()%801)-400),0};
   if(scene==6||(scene==5&&rng()%10==0)){ball.pos.z=200+float(rng()%400);ball.vel.z=200;}
   for(int a=0;a<2;a++){CarState s;float angle=float(rng()%6284)/1000.f;float d=500+float(rng()%1500);s.pos={std::clamp(ball.pos.x+std::cos(angle)*d,-3450.f,3450.f),std::clamp(ball.pos.y+std::sin(angle)*d,-4350.f,4350.f),17};s.rotMat=Angle(float(rng()%6284)/1000.f,0,0).ToRotMat();s.boost=33+float(rng()%68);cars[a]->SetState(s);}
  }
  arena->ball->SetState(ball);for(int a=0;a<2;a++){previous[a]={};cars[a]->controls={};}physics=Math::GetRandEngine();goal=-1;ticks=noTouch=0;potential=phi(ball.pos);
 }
 void write(float*w,float*p){auto b=arena->ball->GetState();vec(w,b.pos);vec(w+3,b.vel);vec(w+6,b.angVel);vec(w+9,b.rotMat.forward);vec(w+12,b.rotMat.up);
  for(int a=0;a<2;a++){auto s=cars[a]->GetState();float*q=w+(a+1)*32;vec(q,s.pos);vec(q+3,s.vel);vec(q+6,s.angVel);vec(q+9,s.rotMat.forward);vec(q+12,s.rotMat.up);q[15]=s.boost;q[16]=s.isOnGround;q[17]=s.hasJumped;q[18]=s.hasDoubleJumped||s.hasFlipped;q[19]=s.isSupersonic;q[20]=s.isDemoed;control(q+21,previous[a]);q[29]=s.HasFlipOrJump();q[30]=s.airTimeSinceJump;q[31]=s.isFlipping;}
  int j=0;for(auto*pad:arena->GetBoostPads()){auto s=pad->GetState();p[j++]=s.isActive;p[j++]=s.cooldown;}
 }
};
class Batch{
 int n,skip,delay,maxTicks,noTouchTicks;float gamma,impulseWeight;Pool pool;std::vector<std::unique_ptr<Env>> envs;std::vector<CarControls>acts=table();int inverse[34];
 void encode(const float*w,const float*p,float*o,bool*m){for(int a=0;a<2;a++)encode_one(w,p,inverse,o+a*109,m+a*90,a,acts);}
public:
 Batch(std::string meshes,int count,int workers,unsigned seed,int repeat,int actionDelay,float discount,float impulse,float maxSec,float noTouchSec):n(count),skip(repeat),delay(actionDelay),maxTicks(int(maxSec*120)),noTouchTicks(int(noTouchSec*120)),gamma(discount),impulseWeight(impulse),pool(std::clamp(workers,1,4)){
  if(n<1||n>256||skip!=8||delay<0||delay>=skip||gamma<=0||gamma>1||impulse<0||impulse>.1||maxTicks<8||noTouchTicks<8)throw std::invalid_argument("Invalid DuelForge native contract");
  static std::once_flag init;std::call_once(init,[&]{RocketSim::Init(meshes,true);});for(int i=0;i<n;i++){envs.emplace_back(new Env(seed+7919*i));envs.back()->reset();}
  auto pads=envs[0]->arena->GetBoostPads();for(int j=0;j<34;j++){float best=1e20f;int kbest=-1;auto v=pads[j]->config.pos;for(int k=0;k<34;k++){auto u=pads[k]->config.pos;float d=(u-Vec(-v.x,-v.y,v.z)).Length();if(d<best){best=d;kbest=k;}}if(best>.1)throw std::runtime_error("Unmatched boost-pad rotation");inverse[j]=kbest;}
 }
 py::array_t<float>locations(){py::array_t<float>x({34,4});int j=0;for(auto*b:envs[0]->arena->GetBoostPads()){vec(x.mutable_data()+4*j,b->config.pos);x.mutable_data()[4*j+3]=b->config.isBig;j++;}return x;}
 py::dict observe(){py::array_t<float>w({n,3,32}),p({n,34,2}),o({n,2,109});py::array_t<bool>m({n,2,90});std::fill(w.mutable_data(),w.mutable_data()+w.size(),0.f);
  for(int i=0;i<n;i++){envs[i]->write(w.mutable_data()+i*96,p.mutable_data()+i*68);encode(w.data()+i*96,p.data()+i*68,o.mutable_data()+i*218,m.mutable_data()+i*180);}py::dict d;d["world"]=w;d["pads"]=p;d["obs"]=o;d["mask"]=m;return d;}
 py::dict step(py::array_t<int64_t,py::array::c_style|py::array::forcecast>ac,py::object remaining=py::none()){
  py::array_t<int64_t,py::array::c_style|py::array::forcecast> budgets;const int64_t*bp=nullptr;if(!remaining.is_none()){budgets=py::cast<decltype(budgets)>(remaining);if(budgets.ndim()!=1||budgets.shape(0)!=n)throw std::invalid_argument("remaining ticks shape");bp=budgets.data();for(int i=0;i<n;i++)if(bp[i]<0)throw std::invalid_argument("negative remaining ticks");}if(ac.ndim()!=2||ac.shape(0)!=n||ac.shape(1)!=2)throw std::invalid_argument("actions shape must be [arenas,2]");auto ap=ac.data();for(int i=0;i<n*2;i++)if(ap[i]<0||ap[i]>=90)throw std::invalid_argument("action outside 90-entry table");
  py::array_t<float>w({n,3,32}),p({n,34,2}),o({n,2,109}),fw({n,3,32}),fp({n,34,2}),fo({n,2,109}),r({n,2}),parts({n,2,3}),info({n,6});py::array_t<bool>m({n,2,90}),fm({n,2,90}),term(n),trunc(n);
  auto wp=w.mutable_data(),pp=p.mutable_data(),op=o.mutable_data(),fwp=fw.mutable_data(),fpp=fp.mutable_data(),fop=fo.mutable_data(),rp=r.mutable_data(),cp=parts.mutable_data(),ip=info.mutable_data();auto mp=m.mutable_data(),fmp=fm.mutable_data(),te=term.mutable_data(),tr=trunc.mutable_data();std::fill(wp,wp+w.size(),0.f);std::fill(fwp,fwp+fw.size(),0.f);
  {py::gil_scoped_release release;pool.run(n,[&](int i){auto&e=*envs[i];Math::GetRandEngine()=e.physics;auto before=e.arena->ball->GetState();bool hits[2]={false,false};uint64_t begin=e.arena->tickCount;
   int limit=bp?int(std::min<int64_t>(skip,bp[i])):skip;for(int k=0;k<limit;k++){if(k==delay)for(int a=0;a<2;a++){e.previous[a]=acts[ap[i*2+a]];e.cars[a]->controls=e.previous[a];}
    e.arena->Step(1);e.ticks++;e.noTouch++;
    if(e.goal>=0)break;
   }
   // BallHitInfo keeps the latest contact tick. Reading it once after the
   // decision avoids copying two complete CarStates on every physics tick.
   // No-touch time retains ticks since the last hit, exactly as the old loop.
   uint64_t end=e.arena->tickCount;
   for(int a=0;a<2;a++){auto state=e.cars[a]->GetState();const auto&hit=state.ballHitInfo;
    if(hit.isValid&&hit.tickCountWhenHit>=begin&&hit.tickCountWhenHit<end){hits[a]=true;e.noTouch=std::min(e.noTouch,int(end-hit.tickCountWhenHit-1));}}
   e.physics=Math::GetRandEngine();te[i]=e.goal>=0;tr[i]=!te[i]&&(e.ticks>=maxTicks||e.noTouch>=noTouchTicks);float g=e.goal<0?0:e.goal==0?1.f:-1.f;auto after=e.arena->ball->GetState();float potential=phi(after.pos),shape=limit?.25f*(gamma*(te[i]?0:potential)-e.potential):0;e.potential=potential;float impulse=std::min(1.f,(after.vel-before.vel).Length()/3000.f);
   for(int a=0;a<2;a++){float*part=cp+(i*2+a)*3;part[0]=a?-g:g;part[1]=a?-shape:shape;part[2]=hits[a]?impulseWeight*impulse:0;rp[i*2+a]=part[0]+part[1]+part[2];}
   ip[i*6]=g;ip[i*6+1]=hits[0];ip[i*6+2]=hits[1];ip[i*6+3]=float(e.arena->tickCount-begin);ip[i*6+4]=float(e.scene);ip[i*6+5]=float(e.ticks);
   e.write(fwp+i*96,fpp+i*68);encode(fwp+i*96,fpp+i*68,fop+i*218,fmp+i*180);if(te[i]||tr[i])e.reset();e.write(wp+i*96,pp+i*68);encode(wp+i*96,pp+i*68,op+i*218,mp+i*180);
  });}py::dict d;d["world"]=w;d["pads"]=p;d["obs"]=o;d["mask"]=m;d["final_world"]=fw;d["final_pads"]=fp;d["final_obs"]=fo;d["final_mask"]=fm;d["rewards"]=r;d["reward_parts"]=parts;d["info"]=info;d["terminated"]=term;d["truncated"]=trunc;return d;
 }
 void scene(int kind){if(kind< -2||kind>6)throw std::invalid_argument("scene must be -1 mixed, 0..4 kickoffs, 5 open play, 6 elevated target");for(auto&e:envs){e->forced=kind;e->reset();}}
 void set_scene(int i,int kind){if(i<0||i>=n||kind< -2||kind>6)throw std::invalid_argument("scene/index");envs[i]->forced=kind;envs[i]->reset();}
 void reset_one(int i){if(i<0||i>=n)throw std::invalid_argument("arena index");envs[i]->reset();}
 void inject(int i,py::array_t<float,py::array::c_style|py::array::forcecast>data){if(i<0||i>=n||data.ndim()!=2||data.shape(0)!=3||data.shape(1)!=32)throw std::invalid_argument("state shape");auto&e=*envs[i];e.reset();auto p=data.data();BallState b;b.pos={p[0],p[1],p[2]};b.vel={p[3],p[4],p[5]};b.angVel={p[6],p[7],p[8]};e.arena->ball->SetState(b);
  for(int a=0;a<2;a++){auto q=p+(a+1)*32;CarState s;s.pos={q[0],q[1],q[2]};s.vel={q[3],q[4],q[5]};s.angVel={q[6],q[7],q[8]};Vec f(q[9],q[10],q[11]),u(q[12],q[13],q[14]);if(f.Length()<.99f||u.Length()<.99f||std::abs(f.Dot(u))>.01)throw std::invalid_argument("state orientation must be orthonormal");s.rotMat=RotMat(f,u.Cross(f),u);s.boost=q[15];e.cars[a]->SetState(s);}e.potential=phi(b.pos);}
};
py::tuple encode_public(py::array_t<float,py::array::c_style|py::array::forcecast>w,py::array_t<float,py::array::c_style|py::array::forcecast>p,py::array_t<float,py::array::c_style|py::array::forcecast>loc){
 if(w.ndim()!=3||w.shape(1)!=3||w.shape(2)!=32||p.ndim()!=3||p.shape(0)!=w.shape(0)||p.shape(1)!=34||p.shape(2)!=2||loc.ndim()!=2||loc.shape(0)!=34||loc.shape(1)!=4)throw std::invalid_argument("public encode shapes");
 int n=int(w.shape(0)),inv[34];for(int j=0;j<34;j++){auto a=loc.data()+j*4;float best=1e20f;for(int k=0;k<34;k++){auto b=loc.data()+k*4;float d=(a[0]+b[0])*(a[0]+b[0])+(a[1]+b[1])*(a[1]+b[1])+(a[2]-b[2])*(a[2]-b[2]);if(d<best){best=d;inv[j]=k;}}if(best>.01f)throw std::invalid_argument("pad rotation");}
 py::array_t<float>o({n,2,109});py::array_t<bool>m({n,2,90});auto acts=table();for(int i=0;i<n;i++)for(int a=0;a<2;a++)encode_one(w.data()+i*96,p.data()+i*68,inv,o.mutable_data()+(i*2+a)*109,m.mutable_data()+(i*2+a)*90,a,acts);return py::make_tuple(o,m);
}
#include "potential.h"
PYBIND11_MODULE(_native,m){m.attr("contract")="duelforge-109-v1-octane-120hz-skip8-delay7";m.attr("version")=1;m.def("predictive_estimate",&predictive_estimate);m.def("encode",&encode_public);
 m.def("action_table",[]{auto a=table();py::array_t<float>x({90,8});for(int i=0;i<90;i++)control(x.mutable_data()+8*i,a[i]);return x;});
 py::class_<Batch>(m,"Batch").def(py::init<std::string,int,int,unsigned,int,int,float,float,float,float>()).def("observe",&Batch::observe).def("step",&Batch::step,py::arg("actions"),py::arg("remaining_ticks")=py::none()).def("pad_locations",&Batch::locations).def("scene",&Batch::scene).def("set_scene",&Batch::set_scene).def("reset_one",&Batch::reset_one).def("inject",&Batch::inject);
}
