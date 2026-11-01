#pragma once
#include <RLGymCPP/ActionParsers/DefaultAction.h>

namespace SlaterFreestyle {
// The upstream 90-action table removes jump+yaw combinations. Opposing yaw and
// roll while jumping is needed to attempt stalls, so this scratch architecture
// adds those controls explicitly. Existing Slater actors keep their own table.
class FreestyleControls : public RLGC::DefaultAction {
public:
    static constexpr const char* SCHEMA="slater_freestyle_94_stall_v1";
    FreestyleControls() {
        for(float yaw:{-1.f,1.f}) for(float boost:{0.f,1.f}) {
            actions.push_back({boost,yaw,0,yaw,-yaw,1,boost,1});
            groundMask.push_back(false);airMask.push_back(false);
            jumpMask.push_back(true);boostMask.push_back(boost!=0);
        }
    }
    std::vector<uint8_t> GetActionMask(const RLGC::Player& player,
                                     const RLGC::GameState& state) override {
        auto mask=RLGC::DefaultAction::GetActionMask(player,state);
        // Upstream adds jump actions after its boost exclusion. Apply the
        // resource mask last so boost+jump actions cannot bypass empty boost.
        if(player.boost<=0) for(size_t i=0;i<mask.size();++i)
            if(boostMask[i]) mask[i]=false;
        return mask;
    }
};
}
