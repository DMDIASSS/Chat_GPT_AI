#pragma once
#include <RLGymCPP/ObsBuilders/AdvancedObs.h>
#include <RLGymCPP/Gamestates/StateUtil.h>
// Fixed roles: self, two teammate slots, three opponent slots, plus presence bits.
// The same MLP input shape supports 1v1, 2v2 and 3v3.
class PaddedObs : public RLGC::AdvancedObs {
public:
    RLGC::FList BuildObs(const RLGC::Player& player,const RLGC::GameState& state)override{
        bool inv=player.team==RocketSim::Team::ORANGE;auto ball=RLGC::InvertPhys(state.ball,inv);
        RLGC::FList obs{};obs+=ball.pos*POS_COEF;obs+=ball.vel*VEL_COEF;obs+=ball.angVel*ANG_VEL_COEF;
        for(int i=0;i<8;i++)obs+=player.prevAction[i];
        auto& pads=state.GetBoostPads(inv);auto& timers=state.GetBoostPadTimers(inv);
        for(int i=0;i<34;i++)obs+=pads[i]?1.f:1.f/(1.f+timers[i]);
        auto before=obs.size();AddPlayerToObs(obs,player,inv,ball);size_t block=obs.size()-before;
        std::vector<const RLGC::Player*> mates,enemies;
        for(auto& p:state.players)if(p.carId!=player.carId)(p.team==player.team?mates:enemies).push_back(&p);
        auto order=[](auto* a,auto* b){return a->carId<b->carId;};std::sort(mates.begin(),mates.end(),order);std::sort(enemies.begin(),enemies.end(),order);
        for(int side=0;side<2;side++){
            auto& list=side==0?mates:enemies;int slots=side==0?2:3;
            if(list.size()>slots)throw std::runtime_error("Padded observation roster exceeds 3v3");
            for(int i=0;i<slots;i++){
                if(i<list.size()){AddPlayerToObs(obs,*list[i],inv,ball);obs+=1.f;}
                else{for(size_t j=0;j<block;j++)obs+=0.f;obs+=0.f;}
            }
        }
        return obs;
    }
};
