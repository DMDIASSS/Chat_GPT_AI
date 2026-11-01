#pragma once
#include "FreestyleCurriculum.h"
#include <RLGymCPP/Rewards/Reward.h>
#include <limits>
#include <vector>

namespace SlaterFreestyle {

// Every raw component is bounded and individually budgeted per episode.
// Smooth stage gates keep later discoveries useful without letting ground
// touching, free flight or static proximity dominate a developed policy.
struct RewardConfig {
    static constexpr int VERSION = 2;
    std::map<std::string,float> weights = {
        {"approach",.15f}, {"jump_explore",.025f}, {"ball_touch",.6f},
        {"wall_roll",.7f}, {"wall_pop",1.1f}, {"air_touch",1.3f},
        {"nose_control",.8f}, {"air_carry",2.f}, {"reset_acquire",3.f},
        {"reset_use",4.f}, {"multi_reset",5.f}, {"pinch_proxy",3.f},
        {"double_tap_proxy",4.f}, {"psycho_proxy",5.f}, {"wall_recovery",1.5f},
        {"walldash_proxy",2.5f}, {"shot_progress",.5f}, {"goal",2.f},
        {"qualified_finish",6.f}, {"concede",.15f}, {"idle",.02f}
        ,{"lift_progress",1.5f}, {"pop_retouch",2.f}
    };
    float maxEpisodePositive = 36.f;
    float touchSpacing = .12f;
    float carryTouchDeadline = .35f;
    float resetUseDeadline = 2.5f;
    float flipTouchDeadline = .55f;
    float finishDeadline = 5.f;
    void Validate() const {
        for (const auto& pair:weights)
            if (!std::isfinite(pair.second)||pair.second<0||pair.second>30)
                throw std::invalid_argument("Invalid freestyle reward weight: "+pair.first);
        for (float value:{maxEpisodePositive,touchSpacing,carryTouchDeadline,
                          resetUseDeadline,flipTouchDeadline,finishDeadline})
            if(!std::isfinite(value)||value<=0) throw std::invalid_argument("Invalid freestyle reward timing/cap");
    }
};

class FreestyleReward : public RLGC::Reward {
    std::shared_ptr<FreestyleContext> context_;
    RewardConfig config_;
    std::unordered_map<uint32_t,float> stepRewards_, positivePaid_;
    std::unordered_map<uint32_t,unsigned> consumedResets_, consumedFlips_;
    std::unordered_map<uint32_t,float> bestShotProgress_;
    bool episodeFinished_ = false;

    float Gate(const std::string& component) const {
        const int stage=int(context_->stage);
        if(component=="approach"||component=="jump_explore")
            return stage==0?1.f:.15f;
        if(component=="ball_touch") return stage==0?1.f:.2f;
        if(component=="reset_acquire") return stage>=2?1.f:.15f;
        if(component=="reset_use") return stage>=3?1.f:.15f;
        if(component=="multi_reset") return stage>=4?1.f:.1f;
        if(component=="pinch_proxy") return context_->stage==Stage::Pinch?1.f:0.f;
        if(component=="double_tap_proxy") return context_->stage==Stage::DoubleTap?1.f:0.f;
        if(component=="psycho_proxy") return context_->stage==Stage::PsychoProxy?1.f:0.f;
        if(component=="goal")return context_->stage==Stage::ContactPop?.25f:1.f;
        if(component=="lift_progress")return context_->stage==Stage::ContactPop?1.f:.15f;
        if(component=="pop_retouch")return context_->stage==Stage::ContactPop?1.f:.3f;
        if(component=="wall_recovery") return context_->stage==Stage::WallRecovery?1.f:.15f;
        if(component=="walldash_proxy") return context_->stage==Stage::WallDashProxy?1.f:.15f;
        return 1.f;
    }
    void Pay(uint32_t id, const std::string& name, float raw, float budget,
             std::map<std::string,double>& metrics, bool penalty=false) {
        auto weight=config_.weights.find(name);
        if(weight==config_.weights.end()||weight->second<=0||raw<=0) return;
        auto& chain=context_->chains.at(id);
        const float remaining=std::max(0.f,budget-chain.rawCredit[name]);
        float scale=weight->second*Gate(name);
        if(scale<=0)return;
        float accepted=std::min(Clip(raw),remaining);
        float weighted=accepted*scale;
        if(!penalty&&scale>0) {
            weighted=std::min(weighted,std::max(0.f,config_.maxEpisodePositive-positivePaid_[id]));
            accepted=weighted/scale; positivePaid_[id]+=weighted;
        }
        chain.rawCredit[name]+=accepted;
        if(penalty)weighted=-weighted;
        stepRewards_[id]+=weighted;
        metrics["raw_sum/"+name]+=penalty?-accepted:accepted;
        metrics["weighted_sum/"+name]+=weighted;
        metrics["payments/"+name]+=accepted>0?1:0;
    }
    void Event(std::map<std::string,double>& metrics,const std::string& name) {
        metrics["events/"+name]+=1;
    }
    bool StageSuccess(const ChainState& c) const {
        const float d=context_->difficulty;
        switch(context_->stage) {
        case Stage::ContactPop:
            if(context_->contactObjective==0)return c.touches>0&&c.active;
            if(context_->contactObjective==1)return c.active&&c.pop;
            return c.active&&c.popRetouch;
        case Stage::AirCarry:return c.bestCarry>=.6f+.9f*d&&c.noseTouches>=2&&c.carryDistance>=180+320*d;
        case Stage::ResetAcquire:return c.resets>=1&&c.active;
        case Stage::ResetUse:return c.resetUses>=1&&(d<.7f||c.ownScored);
        case Stage::MultiReset:return c.bestUsedResetChain>=2&&(d<.7f||c.ownScored);
        case Stage::Pinch:return c.pinch&&(d<.7f||c.ownScored);
        case Stage::DoubleTap:return c.retouch&&!c.ownBoard&&(d<.7f||c.ownScored);
        case Stage::PsychoProxy:return c.retouch&&c.ownBoard&&c.ownScored;
        case Stage::WallRecovery:return c.recovered;
        case Stage::WallDashProxy:return c.wallDashes>=2;
        }
        return false;
    }
    bool QualifiedFinish(const ChainState& c) const {
        // Only the currently trained mechanic can earn the large bonus.
        // A pinch proxy must never unlock an unrelated pop/carry finish.
        switch(context_->stage) {
        case Stage::ContactPop:return c.popRetouch&&c.elapsed-c.lastAirTouch<config_.finishDeadline;
        case Stage::AirCarry:return c.bestCarry>=.6f&&c.noseTouches>=2&&c.elapsed-c.lastAirTouch<config_.finishDeadline;
        case Stage::ResetAcquire:case Stage::ResetUse:case Stage::MultiReset:
            return StageSuccess(c)&&c.resetUses>0&&c.elapsed-c.resetAt<config_.finishDeadline;
        case Stage::Pinch:return c.pinch&&c.elapsed-c.pinchAt<config_.finishDeadline;
        case Stage::DoubleTap:return c.retouch&&!c.ownBoard&&c.elapsed-c.retouchAt<config_.finishDeadline;
        case Stage::PsychoProxy:return c.retouch&&c.ownBoard&&c.elapsed-c.retouchAt<config_.finishDeadline;
        default:return false;
        }
    }
public:
    explicit FreestyleReward(std::shared_ptr<FreestyleContext> context, RewardConfig config={})
        :context_(std::move(context)),config_(std::move(config)){config_.Validate();}
    std::map<std::string,float> ActiveWeights() const {
        auto result=config_.weights;
        for(auto& pair:result)pair.second*=Gate(pair.first);
        return result;
    }

    void Reset(const RLGC::GameState& state) override {
        if(!context_->chains.empty())FinishEpisode();
        context_->chains.clear();context_->physics.clear();context_->startTick=state.lastTickCount;
        context_->rewardTick=~uint64_t(0);stepRewards_.clear();positivePaid_.clear();
        consumedResets_.clear();consumedFlips_.clear();bestShotProgress_.clear();episodeFinished_=false;
        for(const auto& p:state.players) {
            auto& c=context_->chains[p.carId];c.initialBall=c.lastBall=state.ball.pos;c.lastCar=p.pos;
            c.lastHitTick=p.ballHitInfo.isValid?p.ballHitInfo.tickCountWhenHit:~uint64_t(0);
            c.recoveryNeeded=!p.isOnGround||p.rotMat.up.z<.5f;
            c.recoveryStart=c.recoveryNeeded?0:-100;
        }
        FreestyleObservePhysics(context_,state.lastArena);
    }

    void PreStep(const RLGC::GameState& state) override {
        if(context_->rewardTick==state.lastTickCount)return;
        context_->rewardTick=state.lastTickCount;stepRewards_.clear();
        if(episodeFinished_)return;
        FreestyleObservePhysics(context_,state.lastArena);
        const float dt=Clip(state.deltaTime,0.f,.5f);
        std::map<std::string,double> metrics;
        for(const auto& p:state.players) {
            if(context_->learnerId&&p.carId!=context_->learnerId)continue;
            auto found=context_->chains.find(p.carId);
            if(found==context_->chains.end())throw std::runtime_error("Freestyle reward missing episode reset");
            auto& c=found->second;c.elapsed=float(state.lastTickCount-context_->startTick)/120.f;
            const float sign=p.team==RocketSim::Team::BLUE?1.f:-1.f;
            const auto delta=state.ball.pos-p.pos;const float distance=delta.Length();
            const auto direction=Unit(delta);const float speed=p.vel.Length();
            float controlMagnitude=0;for(float input:p.prevAction)controlMagnitude+=std::abs(input);
            c.active=c.active||controlMagnitude>.05f;
            const bool freeAir=!p.isOnGround&&!p.worldContact.hasContact&&p.pos.z>180;
            const bool nearSide=std::abs(p.pos.x)>3750;
            const bool onWall=nearSide&&p.pos.z>150&&
                (p.isOnGround||p.worldContact.hasContact)&&std::abs(p.rotMat.up.x)>.6f;
            const bool touch=p.ballTouchedStep&&p.ballHitInfo.isValid&&
                p.ballHitInfo.tickCountWhenHit!=c.lastHitTick;
            if(touch)c.lastHitTick=p.ballHitInfo.tickCountWhenHit;
            const auto oldBallVel=state.prev?state.prev->ball.vel:state.ball.vel;
            const float impulse=(state.ball.vel-oldBallVel).Length();
            const bool goalward=sign*state.ball.vel.y>120;
            if(c.active&&distance>150) {
                Pay(p.carId,"approach",std::max(0.f,p.vel.Dot(direction)/2300)*dt,.9f,metrics);
                if(freeAir&&distance<1100&&p.airTime<1.5f)
                    Pay(p.carId,"jump_explore",dt,.8f,metrics);
            }
            if(c.elapsed>1&&speed<25&&controlMagnitude<.05f)
                Pay(p.carId,"idle",dt,2.f,metrics,true);
            if(touch&&c.active) {
                const bool wallBeforeTouch=c.wall;
                const float previousWallAt=c.wallAt;
                ++c.touches;c.lastTouch=c.elapsed;Event(metrics,"learner_touch");
                if(c.elapsed-c.lastRewardedTouch>=config_.touchSpacing) {
                    Pay(p.carId,"ball_touch",.2f+.8f*Clip(impulse/1500.f),2.f,metrics);
                    c.lastRewardedTouch=c.elapsed;
                }
                const bool nearBallWall=std::abs(state.ball.pos.x)>3850&&state.ball.pos.z>140;
                if(nearBallWall&&onWall&&state.ball.vel.z>60) {
                    c.wall=true;c.wallAt=c.elapsed;
                    Pay(p.carId,"wall_roll",Clip((state.ball.pos.z-140)/600),1.f,metrics);
                }
                if(wallBeforeTouch&&!c.pop&&c.elapsed-previousWallAt<2.5f&&state.ball.pos.z>250&&
                   state.ball.pos.x*state.ball.vel.x<0&&std::abs(state.ball.vel.x)>180) {
                    c.pop=true;c.popAt=c.elapsed;Pay(p.carId,"wall_pop",1,1,metrics);Event(metrics,"wall_pop");
                }
                // Ground setup can earn a pop too, followed by a separate
                // airborne retouch. A ball spawned high cannot count as a pop.
                if(!c.pop&&state.prev&&state.prev->ball.pos.z<180&&p.pos.z<200&&
                   state.ball.vel.z>80&&state.ball.vel.z-oldBallVel.z>60) {
                    c.pendingLift=true;c.liftAt=c.elapsed;c.liftStartHeight=state.prev->ball.pos.z;
                    Pay(p.carId,"lift_progress",Clip((state.ball.vel.z-oldBallVel.z)/600),1,metrics);
                }
                if(freeAir&&state.ball.pos.z>300) {
                    c.lastAirTouch=c.elapsed;
                    Pay(p.carId,"air_touch",Clip(p.airTime/.8f)*Clip(state.ball.pos.z/1100),3.f,metrics);
                    Event(metrics,"air_touch");
                    if(c.pop&&!c.popRetouch&&c.elapsed-c.popAt>.08f&&c.elapsed-c.popAt<2.5f) {
                        c.popRetouch=true;Pay(p.carId,"pop_retouch",1,1,metrics);Event(metrics,"pop_air_retouch");
                    }
                    const bool nose=p.rotMat.forward.Dot(direction)>.45f&&
                        std::abs(p.rotMat.right.Dot(delta))<110&&p.rotMat.up.Dot(delta)>-40;
                    if(nose&&c.elapsed-c.lastNoseTouch>=config_.touchSpacing) {
                        ++c.noseTouches;c.lastNoseTouch=c.elapsed;
                        Pay(p.carId,"nose_control",Clip(1-(state.ball.vel-p.vel).Length()/1000),2.f,metrics);
                        Event(metrics,"nose_contact");
                    }
                }
            }
            if(c.pendingLift&&!c.pop&&c.elapsed-c.liftAt<=.8f&&state.lastTouchCarID==int(p.carId)&&
               state.ball.pos.z>110&&state.ball.pos.z-c.liftStartHeight>=30+70*context_->difficulty) {
                c.pop=true;c.popAt=c.elapsed;c.pendingLift=false;
                Pay(p.carId,"wall_pop",.6f,1,metrics);Event(metrics,"learner_ground_pop");
            }
            const bool carry=c.active&&freeAir&&state.ball.pos.z>300&&distance<240&&
                (state.ball.vel-p.vel).Length()<650&&c.elapsed-c.lastNoseTouch<config_.carryTouchDeadline&&
                goalward&&p.rotMat.forward.Dot(direction)>.3f;
            if(carry) {
                c.carry+=dt;c.bestCarry=std::max(c.bestCarry,c.carry);
                float progress=std::max(0.f,sign*(state.ball.pos.y-c.lastBall.y));
                c.carryDistance+=progress;
                // Progress and recently verified nose contact are both needed.
                // Hanging beside a stationary ball has no continuous payoff.
                Pay(p.carId,"air_carry",std::min(dt,progress/200.f),1.5f,metrics);
                metrics["measurements/carry_seconds"]+=dt;
            } else c.carry=0;

            auto& physics=context_->physics[p.carId];
            if(physics.resets>consumedResets_[p.carId]) {
                const unsigned count=physics.resets-consumedResets_[p.carId];
                consumedResets_[p.carId]=physics.resets;
                if(c.active) {
                    c.resets+=int(count);c.pendingReset=true;c.resetAt=c.elapsed;
                    c.airborneSinceReset=true;c.resetChain=std::min(3,c.resetChain+int(count));
                    Pay(p.carId,"reset_acquire",1,2,metrics);Event(metrics,"verified_four_wheel_reset");
                }
            }
            if(physics.flipsFromReset>consumedFlips_[p.carId]) {
                consumedFlips_[p.carId]=physics.flipsFromReset;
                if(c.pendingReset&&c.elapsed-c.resetAt<config_.resetUseDeadline)c.flipAt=c.elapsed;
                c.pendingReset=false;
            }
            if(c.active&&touch&&c.flipAt>=0&&c.elapsed-c.flipAt<config_.flipTouchDeadline&&
               impulse>100&&goalward&&c.elapsed-c.resetAt<config_.resetUseDeadline) {
                ++c.resetUses;++c.chainUses;c.bestUsedResetChain=std::max(c.bestUsedResetChain,c.chainUses);
                c.flipAt=-100;Pay(p.carId,"reset_use",1,3,metrics);Event(metrics,"reset_flip_ball_use");
                if(c.resetChain>=2&&c.chainUses>=2) {
                    Pay(p.carId,"multi_reset",1,2,metrics);Event(metrics,"multi_reset_chain_use");
                }
            }
            if(p.pos.z<110||p.worldContact.hasContact||c.elapsed-c.resetAt>config_.finishDeadline) {
                c.resetChain=0;c.chainUses=0;c.pendingReset=false;c.airborneSinceReset=false;
            }

            // These named events are geometry/kinematics proxies, not verified
            // recognizers of stylistic pinches, double taps or psychos.
            const bool groundCompression=state.ball.pos.z<120&&p.pos.z>state.ball.pos.z+25&&
                std::hypot(delta.x,delta.y)<140&&p.vel.z-oldBallVel.z< -150;
            const bool wallCompression=std::abs(state.ball.pos.x)>3960&&
                std::abs(p.pos.x)<std::abs(state.ball.pos.x)-25&&state.ball.pos.x*state.ball.vel.x<0;
            const bool ceilingCompression=state.ball.pos.z>1930&&p.pos.z<state.ball.pos.z-25&&
                std::hypot(delta.x,delta.y)<140&&state.ball.vel.z< -300;
            if(c.active&&touch&&!c.pinch&&(groundCompression||wallCompression||ceilingCompression)&&
               (p.vel-oldBallVel).Dot(direction)>200&&
               distance<220&&impulse>1000&&state.ball.vel.Length()>2000&&goalward) {
                c.pinch=true;c.pinchAt=c.elapsed;
                Pay(p.carId,"pinch_proxy",1,1,metrics);Event(metrics,"pinch_proxy");
            }
            if(state.prev&&!c.board&&c.touches>0&&c.elapsed-c.lastTouch<2.5f&&
               std::abs(state.ball.pos.y)>4880&&state.ball.pos.z>700&&
               std::abs(state.ball.pos.x)<1200&&
               state.prev->ball.vel.y*state.ball.vel.y<0&&std::abs(state.prev->ball.vel.y)>200) {
                c.board=true;c.boardAt=c.elapsed;c.ownBoard=sign*state.ball.pos.y<0;
                Event(metrics,c.ownBoard?"own_backboard_bounce_proxy":"opponent_backboard_bounce_proxy");
            }
            if(c.active&&touch&&c.board&&!c.retouch&&c.elapsed-c.boardAt<3.f&&freeAir&&goalward) {
                c.retouch=true;c.retouchAt=c.elapsed;
                if(!c.ownBoard)Pay(p.carId,"double_tap_proxy",1,1,metrics);
                Event(metrics,c.ownBoard?"psycho_retouch_proxy":"double_tap_retouch_proxy");
            }

            if(c.recoveryNeeded&&!c.recovered&&c.elapsed-c.recoveryStart<4.f&&
               p.isOnGround&&p.angVel.Length()<2&&speed>150&&c.active&&
               ((p.pos.z<100&&p.rotMat.up.z>.75f)||onWall)) {
                c.recovered=true;
                Pay(p.carId,"wall_recovery",.25f+.75f*Clip(1-(c.elapsed-c.recoveryStart)/4),1,metrics);
                Event(metrics,"stable_recovery");
            }
            if(onWall) {
                if(p.prevAction.jump>.5f&&!c.lastJump) {
                    c.wallLaunchAt=c.elapsed;c.wallSpeedBefore=speed;
                }
                if(p.prev&&p.hasFlipped&&!p.prev->hasFlipped&&
                   c.elapsed-c.wallLaunchAt<.7f&&speed-c.wallSpeedBefore>100&&c.active) {
                    ++c.wallDashes;c.wallLaunchAt=-100;
                    Pay(p.carId,"walldash_proxy",1,3,metrics);Event(metrics,"walldash_speed_gain_proxy");
                }
            }
            c.lastJump=p.prevAction.jump>.5f;
            if(c.touches>0&&c.active&&c.elapsed-c.lastTouch<2.5f) {
                const float fraction=Clip((sign*(state.ball.pos.y-c.initialBall.y))/7000);
                const float improvement=std::max(0.f,fraction-bestShotProgress_[p.carId]);
                bestShotProgress_[p.carId]=std::max(bestShotProgress_[p.carId],fraction);
                Pay(p.carId,"shot_progress",improvement,.7f,metrics);
            }
            if(state.goalScored&&!c.goalPaid) {
                c.goalPaid=true;const bool own=sign*state.ball.pos.y>0;
                const bool attributed=state.lastTouchCarID==int(p.carId)&&c.active&&
                    c.elapsed-c.lastTouch<config_.finishDeadline;
                if(own&&attributed) {
                    c.ownScored=true;
                    Pay(p.carId,"goal",1,1,metrics);Event(metrics,"learner_goal");
                    if(QualifiedFinish(c)) {Pay(p.carId,"qualified_finish",1,1,metrics);Event(metrics,"qualified_mechanic_goal");}
                    if(c.ownBoard&&c.retouch&&c.elapsed-c.retouchAt<config_.finishDeadline) {
                        Pay(p.carId,"psycho_proxy",1,1,metrics);Event(metrics,"psycho_finish_proxy");
                    }
                } else if(!own)Pay(p.carId,"concede",1,1,metrics,true);
            }
            c.successful=c.successful||StageSuccess(c);
            c.lastBall=state.ball.pos;c.lastCar=p.pos;c.wasAirborne=freeAir;
            metrics["measurements/learner_seconds"]+=dt;
            metrics["measurements/speed_time_sum"]+=speed*dt;
            if(speed<25)metrics["measurements/idle_seconds"]+=dt;
        }
        context_->telemetry->Add(metrics);
    }

    float GetReward(const RLGC::Player& player,const RLGC::GameState& state,bool isFinal) override {
        PreStep(state);
        const auto found=stepRewards_.find(player.carId);
        const float reward=found==stepRewards_.end()?0.f:found->second;
        if(!std::isfinite(reward))throw std::runtime_error("Nonfinite freestyle reward");
        if(isFinal)FinishEpisode();
        return reward;
    }
    bool IsSuccess(uint32_t carId) const {
        auto found=context_->chains.find(carId);return found!=context_->chains.end()&&found->second.successful;
    }
    void FinishEpisode() {
        if(episodeFinished_)return;episodeFinished_=true;
        std::map<std::string,double> metrics;
        for(auto& pair:context_->chains) {
            if(context_->learnerId&&pair.first!=context_->learnerId)continue;
            auto& c=pair.second;c.finished=true;
            const std::string stage=StageName(context_->stage);
            metrics["episodes/"+stage]+=1;metrics["successes/"+stage]+=c.successful?1:0;
            if(context_->stage==Stage::ContactPop) {
                const std::string objective=context_->contactObjective==0?"touch":context_->contactObjective==1?"pop":"retouch";
                metrics["objectives/"+objective+"/episodes"]+=1;
                metrics["objectives/"+objective+"/successes"]+=c.successful?1:0;
            }
            metrics["measurements/best_carry_seconds_sum"]+=c.bestCarry;
            metrics["measurements/reset_count_sum"]+=c.resets;
            metrics["measurements/reset_uses_sum"]+=c.resetUses;
            metrics["measurements/positive_reward_sum"]+=positivePaid_[pair.first];
        }
        context_->telemetry->Add(metrics);
    }
};

} // namespace SlaterFreestyle
