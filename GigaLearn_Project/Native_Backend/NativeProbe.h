#pragma once
#include <nlohmann/json.hpp>
#include <fstream>
// Read-only probe of the same model, observation builder and mask used by PPO.
inline void nativeProbe(GGL::Learner* learner,const std::string& input,const std::string& output){
    using nlohmann::json;json samples;std::ifstream(input)>>samples;json results=json::array();
    PaddedObs builder;RLGC::DefaultAction parser;
    auto fillPhys=[](RocketSim::PhysState& b,const json& j){
        auto v=[](const json& x){return RocketSim::Vec(x[0].get<float>(),x[1].get<float>(),x[2].get<float>());};
        b.pos=v(j["pos"]);b.vel=v(j["vel"]);b.angVel=v(j["ang"]);auto r=j["rot"].get<std::vector<float>>();
        b.rotMat=RocketSim::RotMat({r[0],r[1],r[2]},{r[3],r[4],r[5]},{r[6],r[7],r[8]});
    };
    torch::NoGradGuard guard;
    for(auto& sample:samples){auto p=sample["packet"];RLGC::GameState s;fillPhys(s.ball,p["ball"]);
        s.boostPadTimers=p["timers"].get<std::vector<float>>();
        for(int i=0;i<34;i++){s.boostPads[i]=s.boostPadTimers[i]<=0;s.boostPadTimersInv[33-i]=s.boostPadTimers[i];s.boostPadsInv[33-i]=s.boostPads[i];}
        for(auto& c:p["cars"]){RLGC::Player player;fillPhys(player,c);player.carId=c["id"];player.team=RocketSim::Team(c["team"].get<int>());
            player.boost=c["boost"];player.isOnGround=c["ground"];player.hasJumped=c["jumped"];player.hasDoubleJumped=c["double_jumped"];
            player.hasFlipped=c["flipped"];player.airTimeSinceJump=c["air_time"];player.isDemoed=c["demo"];
            player.worldContact.hasContact=c["world_contact"];auto n=c["contact_normal"].get<std::vector<float>>();player.worldContact.contactNormal={n[0],n[1],n[2]};
            for(int i=0;i<8;i++)player.prevAction[i]=c["previous"][i];s.players.push_back(player);
        }
        auto it=std::find_if(s.players.begin(),s.players.end(),[&](auto& c){return c.carId==sample["query"].get<int>();});
        if(it==s.players.end())throw std::runtime_error("Probe query absent");auto obs=builder.BuildObs(*it,s);auto mask=parser.GetActionMask(*it,s);
        auto x=torch::tensor(obs).reshape({1,230}).to(learner->ppo->device);
        auto logits=learner->ppo->models["policy"]->Forward(learner->ppo->models["shared_head"]->Forward(x,false),false).cpu();
        auto probs=(logits+torch::tensor(mask).reshape({1,90}).logical_not().to(torch::kFloat32)*-1e10).softmax(-1).clamp(1e-11,1).contiguous();
        results.push_back({{"obs",obs},{"timers",s.boostPadTimers},{"mask",mask},{"probs",std::vector<float>(probs.data_ptr<float>(),probs.data_ptr<float>()+90)},
            {"action",probs.argmax(-1).item<int>()}});
    }
    std::ofstream(output)<<results.dump();std::cout<<"SLATER_NATIVE_PROBE_COMPLETE count="<<results.size()<<std::endl;
}
