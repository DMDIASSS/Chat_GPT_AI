#pragma once
#include "Campaign.h"
inline std::vector<std::string> focusStages={"touch_warmup","ground_score","kickoff","boost_pickup","wall_roll","wall_pop","air_carry","air_finish","wall_to_air_finish","reset_acquire","reset_use","reset_finish","reset_double_tap"};
inline bool focusDrill=false;
inline float focusDifficulty=0;
class FocusSetter : public RLGC::StateSetter {
    RLGC::KickoffState kickoff;
public:
    void ResetArena(RocketSim::Arena* arena)override{
        kickoff.ResetArena(arena);if(campaignFocus=="kickoff")return;
        RocketSim::BallState b;float x=randomRange(-600,600),y=randomRange(-1200,1200);b.pos={x,y,93};b.vel={0,0,0};
        bool wall=campaignFocus=="wall_roll"||campaignFocus=="wall_pop"||campaignFocus=="wall_to_air_finish";bool air=campaignFocus=="air_carry"||campaignFocus=="air_finish"||campaignFocus.rfind("reset",0)==0;
        if(wall){b.pos={randomRange(0,1)<.5f?-3200.f:3200.f,y,93};if(campaignFocus=="wall_pop"){b.pos.x=b.pos.x>0?3900:-3900;b.pos.z=500;b.vel={0,0,200};}}
        if(air){b.pos={randomRange(-150-800*focusDifficulty,150+800*focusDifficulty),y,randomRange(530,740+400*focusDifficulty)};b.vel={randomRange(-80,80)*focusDifficulty,randomRange(450,700),randomRange(60,140)};}
        int chosen=fixedLearnerTeam>=0?fixedLearnerTeam:std::rand()%2;float sign=chosen==0?1.f:-1.f;if(air){b.vel.y*=sign;b.pos.y=sign*(campaignFocus=="air_finish"||campaignFocus=="reset_finish"||campaignFocus=="reset_double_tap"?1800:800);}
        arena->ball->SetState(b);bool placed=false;
        for(auto* car:arena->GetCars()){
            RocketSim::CarState c;bool own=int(car->team)==chosen&&!placed;float s=car->team==RocketSim::Team::BLUE?1.f:-1.f;
            c.pos={own?b.pos.x:randomRange(-2500,2500),own?b.pos.y-sign*(250+randomRange(0,500)*focusDifficulty):-s*3500,17};c.boost=80;c.isOnGround=true;
            RocketSim::Vec forward=(b.pos-c.pos);forward.z=0;forward=forward.Normalized();c.rotMat=RocketSim::RotMat(forward,{-forward.y,forward.x,0},{0,0,1});
            if(campaignFocus=="boost_pickup"&&own){float side=randomRange(0,1)<.5f?-1.f:1.f;c.pos={side*2600,-s*3600,17};c.boost=5;auto d=(RocketSim::Vec(side*3072,-s*4096,17)-c.pos).Normalized();c.rotMat=RocketSim::RotMat(d,{-d.y,d.x,0},{0,0,1});}
            if(wall&&own){float side=b.pos.x>0?1.f:-1.f;c.pos={b.pos.x-side*250,b.pos.y,17};c.rotMat=RocketSim::RotMat({side,0,0},{0,side,0},{0,0,1});
                if(campaignFocus=="wall_pop"){c.pos={side*3980,b.pos.y,b.pos.z-170};c.isOnGround=false;c.rotMat=RocketSim::RotMat({0,0,1},{0,side,0},{-side,0,0});c.vel={0,0,350};}}
            if(air&&own){c.pos=b.pos-RocketSim::Vec(randomRange(-15,15)*(1+4*focusDifficulty),sign*(145+randomRange(0,100)*focusDifficulty),110+randomRange(0,60)*focusDifficulty);c.vel=b.vel;c.vel.x+=randomRange(-100,100)*focusDifficulty;c.isOnGround=false;c.hasJumped=true;c.hasDoubleJumped=true;c.airTimeSinceJump=2;
                c.rotMat=RocketSim::RotMat({0,sign*.8f,.6f},{-sign,0,0},{0,-sign*.6f,.8f});
                if(campaignFocus=="reset_acquire"||campaignFocus=="reset_use"){c.pos=b.pos-RocketSim::Vec(0,0,150+randomRange(0,120)*focusDifficulty);c.rotMat=RocketSim::RotMat({0,sign,0},{sign,0,0},{0,0,-1});}}
            car->SetState(c);if(own)placed=true;
        }practiceResets++;
    }
};
class FocusReward : public RLGC::Reward {
    struct Progress {bool boost=false,wall=false,pop=false,reset=false,used=false,backboard=false,retouch=false;float carry=0,best=0,travel=0;int contacts=0,noseContacts=0;bool noseEdge=false,carryBeforeReset=false,active=false;float age=0,lastContact=-100,lastNose=-100,lastCarry=-100,resetTime=-100,flipTime=-100;float credit=0;};
    std::map<uint32_t,Progress> progress;
public:
    void Reset(const RLGC::GameState&)override{progress.clear();}
    float GetReward(const RLGC::Player& car,const RLGC::GameState& s,bool)override{
        auto& p=progress[car.carId];float sign=car.team==RocketSim::Team::BLUE?1:-1,dt=s.deltaTime;p.age+=dt;float r=0;
        auto delta=s.ball.pos-car.pos;float distance=delta.Length();auto goal=RocketSim::Vec(0,sign*5120,300);
        for(int j=0;j<8;j++)p.active=p.active||std::abs(car.prevAction[j])>1e-6;
        if(car.prev){float oldDistance=(s.prev?s.prev->ball.pos-car.prev->pos:delta).Length();r+=.1f*std::clamp((oldDistance-distance)/1000.f,-.1f,.1f);}
        // Dense approach is limited to foundational stages. No reward for consuming boost.
        if(campaignFocus=="touch_warmup"||campaignFocus=="ground_score"||campaignFocus=="kickoff")r+=.3f*std::max(0.f,car.vel.Dot(delta.Normalized())/2300)*dt;
        if(car.ballTouchedStep){p.contacts++;p.lastContact=p.age;if(campaignFocus=="touch_warmup"&&p.contacts<=3)r+=.4f;
            if(campaignFocus=="kickoff"&&p.contacts==1)r+=sign*s.ball.vel.y>0?1.f:.3f;}
        if(car.prev&&!p.boost&&car.boost-car.prev->boost>5){p.boost=true;if(campaignFocus=="boost_pickup")r+=1;}
        if(car.ballTouchedStep&&std::abs(s.ball.pos.x)>3300){p.wall=true;if(campaignFocus=="wall_roll"&&s.ball.pos.z>180&&!p.pop){p.pop=true;r+=1;}}
        if(p.wall&&!p.pop&&car.ballTouchedStep&&s.ball.pos.z>300&&s.prev&&std::abs(s.prev->ball.pos.x)>3700&&s.ball.pos.x*s.ball.vel.x<0&&std::abs(s.ball.vel.x)>150){p.pop=true;if(campaignFocus=="wall_pop"||campaignFocus=="wall_to_air_finish")r+=1;}
        bool nose=car.ballTouchedStep&&car.pos.z>220&&s.ball.pos.z>300&&car.rotMat.forward.Dot(delta)>40&&std::abs(car.rotMat.right.Dot(delta))<105&&car.rotMat.up.Dot(delta)>-30&&car.rotMat.up.Dot(delta)<150;
        if(nose&&(!p.noseEdge||p.age-p.lastNose>.12f)){p.noseContacts++;p.lastNose=p.age;}p.noseEdge=nose;
        bool carry=car.pos.z>220&&s.ball.pos.z>300&&distance<235&&(s.ball.vel-car.vel).Length()<550&&car.rotMat.forward.Dot(delta.Normalized())>.4f&&p.age-p.lastNose<.3f&&sign*s.ball.vel.y>80;
        if(carry){p.carry+=dt;p.lastCarry=p.age;p.best=std::max(p.best,p.carry);p.travel+=std::max(0.f,sign*s.ball.vel.y)*dt;
            if(campaignFocus=="air_carry"||campaignFocus=="air_finish"||campaignFocus=="wall_to_air_finish"||campaignFocus.rfind("reset",0)==0){float pay=std::min(dt,std::max(0.f,2.5f-p.credit));r+=.4f*pay;p.credit+=pay;}}
        else p.carry=0;
        bool wheels=car.wheelsWithContact[0]&&car.wheelsWithContact[1]&&car.wheelsWithContact[2]&&car.wheelsWithContact[3];
        bool geometry=car.pos.z>250&&std::abs(car.pos.x)<3200&&std::abs(car.pos.y)<4500&&distance<160&&(-car.rotMat.up).Dot(delta.Normalized())>.7f;
        if(!p.reset&&car.prev&&!car.prev->HasFlipOrJump()&&car.HasFlipReset()&&wheels&&geometry){p.reset=true;p.resetTime=p.age;p.carryBeforeReset=p.best>=1&&p.noseContacts>=2&&p.travel>=250&&p.age-p.lastCarry<1.5f;if(campaignFocus.rfind("reset",0)==0)r+=.5f;}
        if(p.reset&&car.prev&&car.prev->HasFlipOrJump()&&!car.HasFlipOrJump()&&car.hasFlipped)p.flipTime=p.age;
        if(p.reset&&!p.used&&p.age-p.flipTime<.45f&&car.ballTouchedStep&&sign*s.ball.vel.y>150&&s.prev&&sign*(s.ball.vel.y-s.prev->ball.vel.y)>100){p.used=true;if(campaignFocus.rfind("reset",0)==0)r+=.75f;}
        if(p.used&&s.prev&&std::abs(s.ball.pos.y)>4900&&s.ball.pos.z>750&&std::abs(s.ball.pos.x)<1000&&sign*s.prev->ball.vel.y>0&&sign*s.ball.vel.y<0)p.backboard=true;
        if(p.backboard&&car.ballTouchedStep&&sign*s.ball.vel.y>150)p.retouch=true;
        if(s.goalScored){bool own=sign*s.ball.pos.y>0;
            bool carried=p.best>=1&&p.noseContacts>=2&&p.travel>=250;
            bool qualified=(campaignFocus=="touch_warmup"||campaignFocus=="ground_score"||campaignFocus=="kickoff")?p.contacts>0:
                campaignFocus=="boost_pickup"?p.boost:campaignFocus=="wall_roll"?p.wall:campaignFocus=="wall_pop"?p.pop:
                campaignFocus=="air_carry"||campaignFocus=="air_finish"?carried:campaignFocus=="wall_to_air_finish"?carried&&p.wall&&p.pop:
                campaignFocus=="reset_acquire"?p.reset:campaignFocus=="reset_use"?p.used:
                p.carryBeforeReset&&p.used&&p.age-p.flipTime<5&&(campaignFocus!="reset_double_tap"||p.retouch);
            r+=own?(qualified&&p.active?10:0):-10;
            if(own&&(campaignFocus=="air_finish"||campaignFocus=="wall_to_air_finish")&&qualified)r+=5;
            if(own&&(campaignFocus=="reset_finish"||campaignFocus=="reset_double_tap")&&p.carryBeforeReset&&p.used&&p.age-p.flipTime<5&&
                (campaignFocus!="reset_double_tap"||p.retouch))r+=6;
        }
        return r;
    }
};
class FocusDeadline : public RLGC::TerminalCondition {
    uint64_t origin=0;
public:
    void Reset(const RLGC::GameState&s)override{origin=s.lastTickCount;}
    bool IsTerminal(const RLGC::GameState&s)override{return s.lastTickCount-origin>=1440;}
    bool IsTruncation()override{return true;}
};
