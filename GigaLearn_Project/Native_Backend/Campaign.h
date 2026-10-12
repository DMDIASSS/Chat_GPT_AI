#pragma once
#include "ReplayBank.h"
#include <RLGymCPP/Rewards/Reward.h>
#include <map>
inline std::string campaignFocus="mixed";
inline std::atomic<uint64_t> practiceResets{0},frozenScriptTicks{0};
inline float randomRange(float low,float high){return low+(high-low)*(float(std::rand())/RAND_MAX);}
class CampaignSetter : public RLGC::StateSetter {
    RLGC::KickoffState kickoff;
public:
    void ResetArena(RocketSim::Arena* arena)override{
        kickoff.ResetArena(arena);float draw=randomRange(0,1);
        if(draw<.2f&&replayBank){replayBank->restore(arena,replayBank->train[std::rand()%replayBank->train.size()]);replayResetCount++;return;}
        if(draw<.6f)return; // Majority full-match/replay practice; focused starts stay mixed.
        std::vector<std::string> tasks={"ground","defense","recovery","low_boost","aerial","wall","air_dribble","reset_use"};
        auto task=campaignFocus=="mixed"?tasks[std::rand()%tasks.size()]:campaignFocus;
        RocketSim::BallState ball;ball.pos={randomRange(-900,900),randomRange(-2200,2200),93};ball.vel={randomRange(-200,200),randomRange(-600,600),0};
        if(task=="defense"){ball.pos={randomRange(-600,600),-2800,randomRange(93,500)};ball.vel={0,-900,0};}
        if(task=="aerial"||task=="air_dribble"||task=="reset_use"){ball.pos={randomRange(-700,700),800,700};ball.vel={0,500,80};}
        if(task=="wall"){ball.pos={3700,randomRange(-2000,2000),600};ball.vel={0,500,50};}
        int focusedTeam=std::rand()%2;float orientation=focusedTeam==0?1.f:-1.f;
        ball.pos.x*=orientation;ball.pos.y*=orientation;ball.vel.x*=orientation;ball.vel.y*=orientation;
        arena->ball->SetState(ball);bool placedFocus=false;
        for(auto* car:arena->GetCars()){
            RocketSim::CarState state;float sign=car->team==RocketSim::Team::BLUE?1.f:-1.f;
            state.pos={randomRange(-2200,2200),randomRange(-3600,3600),17};state.boost=task=="low_boost"?randomRange(0,20):randomRange(40,100);
            state.rotMat=RocketSim::RotMat({0,sign,0},{-sign,0,0},{0,0,1});state.isOnGround=true;
            if(task=="defense")state.pos={randomRange(-700,700),sign==orientation?-orientation*4200:-orientation*1200,17};
            if(task=="recovery"){state.pos.z=randomRange(200,900);state.rotMat=RocketSim::RotMat({0,sign,0},{sign,0,0},{0,0,-1});state.isOnGround=false;state.vel={0,sign*600,-100};}
            bool primary=int(car->team)==focusedTeam&&!placedFocus;
            if((task=="aerial"||task=="air_dribble"||task=="reset_use")&&primary){
                state.pos=ball.pos-RocketSim::Vec(0,orientation*145,110);state.vel=ball.vel;state.isOnGround=false;
                state.hasJumped=true;state.hasDoubleJumped=true;state.airTimeSinceJump=2;
                state.rotMat=RocketSim::RotMat({0,orientation*.8f,.6f},{-orientation,0,0},{0,-orientation*.6f,.8f});
                if(task=="reset_use"){state.pos=ball.pos-RocketSim::Vec(0,0,150);state.rotMat=RocketSim::RotMat({0,orientation,0},{orientation,0,0},{0,0,-1});}
            }
            if(task=="wall"&&primary){state.pos={orientation*3550,ball.pos.y-orientation*350,400};state.isOnGround=false;}
            car->SetState(state);if(primary)placedFocus=true;
        }
        practiceResets++;
    }
};
class SkillReward : public RLGC::Reward {
    struct Progress {float carry=0,bestCarry=0;bool reset=false,used=false,recovered=false,bump=false;};
    std::map<uint32_t,Progress> progress;
public:
    void Reset(const RLGC::GameState&)override{progress.clear();}
    float GetReward(const RLGC::Player& car,const RLGC::GameState& state,bool)override{
        auto& p=progress[car.carId];float reward=0,sign=car.team==RocketSim::Team::BLUE?1.f:-1.f;
        auto difference=state.ball.pos-car.pos;bool carry=car.pos.z>250&&state.ball.pos.z>250&&difference.Length()<230&&
            car.rotMat.forward.Dot(difference.Normalized())>.4f&&(state.ball.vel-car.vel).Length()<500&&sign*state.ball.vel.y>100;
        if(carry){p.carry+=state.deltaTime;p.bestCarry=std::max(p.bestCarry,p.carry);
            reward+=(campaignFocus=="air_dribble"?.5f:.25f)*state.deltaTime;}else p.carry=0;
        bool wheelContact=car.wheelsWithContact[0]&&car.wheelsWithContact[1]&&car.wheelsWithContact[2]&&car.wheelsWithContact[3];
        if(car.prev&&!car.prev->HasFlipOrJump()&&car.HasFlipReset()&&car.ballTouchedStep&&wheelContact&&car.pos.z>250&&!p.reset){p.reset=true;reward+=campaignFocus=="reset_use"?.5f:.25f;}
        if(p.reset&&car.hasFlipped&&car.flipTime<1.25f&&car.ballTouchedStep&&sign*state.ball.vel.y>100&&!p.used){p.used=true;reward+=campaignFocus=="reset_use"?.5f:.25f;}
        if(!p.recovered&&car.prev&&!car.prev->isOnGround&&car.isOnGround&&car.rotMat.up.z>.8f){p.recovered=true;reward+=campaignFocus=="recovery"?.2f:.1f;}
        if(car.ballTouchedStep&&sign*state.ball.vel.y>150){
            if(campaignFocus=="defense"&&sign*car.pos.y<0)reward+=.1f;
            if((campaignFocus=="aerial"||campaignFocus=="wall")&&car.pos.z>250)reward+=.1f;
            if(campaignFocus=="low_boost"&&car.boost<20)reward+=.05f;
        }
        if(p.bestCarry>.4f&&(car.eventState.bump||car.eventState.demo)&&sign*(car.pos.y-state.ball.pos.y)>0)p.bump=true;
        if(state.goalScored&&sign*state.ball.pos.y>0){
            if(p.bestCarry>.7f)reward+=1.f;if(p.used)reward+=1.f;if(p.bump)reward+=.5f;
        }
        return reward; // Sparse bonuses remain below the 10-point scoring objective.
    }
};
class CampaignAction : public RLGC::DefaultAction {
    uint64_t kickoffOrigin=0;bool active=false;
public:
    void ApplyPhysicsControls(RocketSim::Arena* arena)override{
        auto marker=std::getenv("SLATER_GL_FROZEN_TEAM");if(!marker||std::atoi(marker)<0){active=false;return;}
        int team=std::atoi(marker);auto ball=arena->ball->GetState();bool proxy=ball.pos.Length2D()<1&&ball.pos.z<100;
        if(!proxy){active=false;return;}if(!active){active=true;kickoffOrigin=arena->tickCount;}
        auto tick=arena->tickCount-kickoffOrigin;if(tick>=168||ball.pos.y!=0)return;
        const int duration[]={44,16,8,4,4,52,40};const float stages[][8]={{1,0,0,0,0,0,1,0},{1,-1,0,0,0,0,1,0},
            {1,0,0,0,0,1,1,0},{1,0,0,0,0,0,1,0},{1,0,-.7f,.8f,0,1,1,0},{1,0,1,0,0,0,1,0},{1,0,.5f,0,1,0,0,0}};
        int stage=0;for(;stage<6&&tick>=duration[stage];stage++)tick-=duration[stage];
        float closest=1e20;for(auto* c:arena->GetCars())closest=std::min(closest,c->GetState().pos.Dist2D(ball.pos));
        for(auto* car:arena->GetCars())if(int(car->team)==team){
            auto state=car->GetState();float distance=state.pos.Dist2D(ball.pos);if(std::abs(distance-closest)>10)continue;
            bool taking=true;for(auto* other:arena->GetCars())if(other!=car&&other->team==car->team&&std::abs(other->GetState().pos.Dist2D(ball.pos)-distance)<=10){
                bool left=team==0?other->GetState().pos.x<state.pos.x:other->GetState().pos.x>state.pos.x;if(!left)taking=false;
            }
            if(taking){auto& a=stages[stage];car->controls.throttle=a[0];car->controls.steer=a[1];car->controls.pitch=a[2];car->controls.yaw=a[3];
                car->controls.roll=a[4];car->controls.jump=a[5];car->controls.boost=a[6];car->controls.handbrake=a[7];frozenScriptTicks++;}
        }
    }
};
