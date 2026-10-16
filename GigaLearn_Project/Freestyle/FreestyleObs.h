#pragma once
#include "FreestyleCurriculum.h"
#include <RLGymCPP/ObsBuilders/ObsBuilder.h>
#include <vector>

namespace SlaterFreestyle {

// Flat 512-float schema: own/ball world and car-local physics, resource state,
// wall/goal geometry, actual prior controls, task+timers, bounded chain history,
// 34 pad entities, up to five other cars, and short ballistic ball predictions.
// All absent roster slots are zero with explicit presence bits. Simulator-only
// contact/wheel/reset evidence carries a visibility mask and is randomly hidden
// per episode; live adapters can set privilegedDropout=1 and omit those fields.
class FreestyleObs : public RLGC::ObsBuilder {
    std::shared_ptr<FreestyleContext> context_;
    static void Add(RLGC::FList& obs,float value) {
        if(!std::isfinite(value))throw std::invalid_argument("Nonfinite freestyle observation");
        obs.push_back(Clip(value,-4,4));
    }
    static void AddVec(RLGC::FList& obs,const RocketSim::Vec& v,float scale) {
        Add(obs,v.x*scale);Add(obs,v.y*scale);Add(obs,v.z*scale);
    }
    static RocketSim::Vec Invert(const RocketSim::Vec& v,float sign) {
        return {v.x*sign,v.y*sign,v.z};
    }
    static RocketSim::Vec Local(const RocketSim::Vec& v,const RocketSim::RotMat& basis) {
        return {v.Dot(basis.forward),v.Dot(basis.right),v.Dot(basis.up)};
    }
    static void PlayerPhysics(RLGC::FList& obs,const RLGC::Player& p,float sign) {
        AddVec(obs,Invert(p.pos,sign),1/6000.f);AddVec(obs,Invert(p.vel,sign),1/2300.f);
        AddVec(obs,Invert(p.angVel,sign),1/5.5f);
        AddVec(obs,Invert(p.rotMat.forward,sign),1);AddVec(obs,Invert(p.rotMat.right,sign),1);
        AddVec(obs,Invert(p.rotMat.up,sign),1);
    }
public:
    static constexpr size_t SIZE=512;
    inline static constexpr const char* SCHEMA="slater_freestyle_flat512_v1";
    explicit FreestyleObs(std::shared_ptr<FreestyleContext> context):context_(std::move(context)){}
    void Reset(const RLGC::GameState&) override {}
    RLGC::FList BuildObs(const RLGC::Player& player,const RLGC::GameState& state) override {
        if(state.players.empty()||state.players.size()>6||state.boostPads.size()!=34||state.boostPadTimers.size()!=34)
            throw std::invalid_argument("Freestyle observation requires 1..6 cars and 34 boost pads");
        const float sign=player.team==RocketSim::Team::BLUE?1.f:-1.f;
        const bool priv=context_->privilegedVisible;
        RLGC::FList obs;obs.reserve(SIZE);
        AddVec(obs,Invert(state.ball.pos,sign),1/6000.f);
        AddVec(obs,Invert(state.ball.vel,sign),1/6000.f);
        AddVec(obs,Invert(state.ball.angVel,sign),1/6.f);
        PlayerPhysics(obs,player,sign);
        const auto relative=state.ball.pos-player.pos;
        const auto relativeVelocity=state.ball.vel-player.vel;
        AddVec(obs,Invert(relative,sign),1/6000.f);AddVec(obs,Invert(relativeVelocity,sign),1/6000.f);
        AddVec(obs,Local(relative,player.rotMat),1/2300.f);
        AddVec(obs,Local(relativeVelocity,player.rotMat),1/2300.f);
        AddVec(obs,Local(player.vel,player.rotMat),1/2300.f);
        AddVec(obs,Local(player.angVel,player.rotMat),1/5.5f);
        for(float value:{player.boost/100.f,float(player.isOnGround),float(player.hasJumped),
                         float(player.hasDoubleJumped),float(player.hasFlipped),float(player.isFlipping),
                         float(player.isJumping),float(player.HasFlipOrJump()),float(player.isDemoed),
                         float(player.isSupersonic),Clip(player.airTime/5),Clip(player.airTimeSinceJump/1.25f),
                         Clip(player.jumpTime/.2f),Clip(player.flipTime/1.5f),player.handbrakeVal,
                         Clip(player.demoRespawnTimer/3),float(player.ballTouchedStep)})Add(obs,value);
        // Exact contact/reset information is optional rather than required to
        // interpret the ordinary jump, dodge, orientation and ball geometry.
        Add(obs,priv?1:0);
        for(bool wheel:player.wheelsWithContact)Add(obs,priv?float(wheel):0);
        Add(obs,priv?float(player.worldContact.hasContact):0);
        AddVec(obs,priv?Local(player.worldContact.contactNormal,player.rotMat):RocketSim::Vec(),1);
        Add(obs,priv?float(player.HasFlipReset()):0);
        for(float value:{(4096-std::abs(player.pos.x))/4096,
                         (5120-std::abs(player.pos.y))/5120,
                         player.pos.z/2044,(2044-player.pos.z)/2044,
                         float(std::abs(player.pos.x)>3750&&player.pos.z>150),
                         float(std::abs(player.pos.y)>4800&&player.pos.z>650)})Add(obs,value);
        const RocketSim::Vec target{0,sign*5120,320},home{0,-sign*5120,320};
        AddVec(obs,Local(target-player.pos,player.rotMat),1/6000.f);
        AddVec(obs,Local(home-player.pos,player.rotMat),1/6000.f);
        for(float input:player.prevAction)Add(obs,input);
        for(int stage=0;stage<STAGE_COUNT;++stage)Add(obs,int(context_->stage)==stage?1.f:0.f);
        Add(obs,context_->difficulty);
        const float elapsed=float(state.lastTickCount-context_->startTick)/120.f;
        Add(obs,Clip(elapsed/context_->episodeSeconds));
        Add(obs,Clip((context_->episodeSeconds-elapsed)/context_->episodeSeconds));
        auto chain=context_->chains.find(player.carId);
        const ChainState empty{};const auto& c=chain==context_->chains.end()?empty:chain->second;
        for(float value:{Clip((elapsed-c.lastTouch)/2),Clip((elapsed-c.lastNoseTouch)/2),
                         c.carry/3,c.bestCarry/3,c.carryDistance/2000,
                         float(c.wall),float(c.pop),Clip((elapsed-c.wallAt)/3),Clip((elapsed-c.popAt)/3),
                         Clip(c.noseTouches/4.f),priv?Clip(c.resets/3.f):0,
                         priv?Clip(c.resetUses/3.f):0,priv?float(c.pendingReset):0,
                         priv?Clip((elapsed-c.resetAt)/3):0,
                         float(c.pinch),float(c.board),float(c.retouch),float(c.ownBoard),
                         float(c.recovered),Clip(c.wallDashes/3.f)})Add(obs,value);
        for(size_t pad=0;pad<34;++pad) {
            // Canonical pad slots rotate with team perspective. RLGym's
            // orange boost array is the original physical pad order reversed.
            const size_t physical=sign>0?pad:33-pad;
            const auto location=RLGC::CommonValues::BOOST_LOCATIONS[physical];
            AddVec(obs,Local(location-player.pos,player.rotMat),1/6000.f);
            Add(obs,state.boostPads[physical]?1.f:0.f);
            Add(obs,Clip(state.boostPadTimers[physical]/10));
        }
        std::vector<const RLGC::Player*> others;
        for(const auto& p:state.players)if(p.carId!=player.carId)others.push_back(&p);
        std::sort(others.begin(),others.end(),[&](const auto* a,const auto* b){
            if((a->team==player.team)!=(b->team==player.team))return a->team==player.team;
            return a->carId<b->carId;
        });
        constexpr size_t OTHER_BLOCK=33;
        for(size_t slot=0;slot<5;++slot) {
            const size_t begin=obs.size();
            if(slot<others.size()) {
                const auto& p=*others[slot];Add(obs,1);Add(obs,p.team==player.team?1.f:-1.f);
                AddVec(obs,Local(p.pos-player.pos,player.rotMat),1/6000.f);
                AddVec(obs,Local(p.vel-player.vel,player.rotMat),1/2300.f);
                AddVec(obs,Local(p.rotMat.forward,player.rotMat),1);
                AddVec(obs,Local(p.rotMat.up,player.rotMat),1);
                AddVec(obs,Local(p.angVel,player.rotMat),1/5.5f);
                for(float value:{p.boost/100.f,float(p.isOnGround),float(p.HasFlipOrJump()),float(p.isDemoed),
                                 Clip(p.demoRespawnTimer/3),float(p.ballTouchedStep),
                                 (p.pos-state.ball.pos).Length()/6000,p.vel.Length()/2300})Add(obs,value);
                for(float value:{float(p.hasJumped),float(p.hasDoubleJumped),float(p.hasFlipped),
                                 float(p.isFlipping),Clip(p.airTime/5),float(p.isSupersonic),p.handbrakeVal})Add(obs,value);
            }
            if(obs.size()>begin+OTHER_BLOCK)throw std::logic_error("Freestyle roster block overflow");
            obs.resize(begin+OTHER_BLOCK,0);
        }
        // Ballistic forecasts are explicitly simple estimates: collisions and
        // car interactions are not predicted. Flight state remains observable.
        for(float horizon:{.15f,.35f,.7f}) {
            auto position=state.ball.pos+state.ball.vel*horizon+RocketSim::Vec(0,0,-325*horizon*horizon);
            auto velocity=state.ball.vel+RocketSim::Vec(0,0,-650*horizon);
            AddVec(obs,Local(position-player.pos,player.rotMat),1/6000.f);
            AddVec(obs,Local(velocity-player.vel,player.rotMat),1/6000.f);
        }
        Add(obs,(state.ball.pos-player.pos).Length()/6000);
        Add(obs,player.rotMat.forward.Dot(Unit(relative)));
        Add(obs,-player.rotMat.up.Dot(Unit(relative)));
        Add(obs,Clip((2044-state.ball.pos.z)/2044));
        Add(obs,float(state.goalScored));Add(obs,float(state.lastTouchCarID==int(player.carId)));
        if(obs.size()>SIZE)throw std::logic_error("Freestyle observation schema overflow");
        obs.resize(SIZE,0);return obs;
    }
};

} // namespace SlaterFreestyle
