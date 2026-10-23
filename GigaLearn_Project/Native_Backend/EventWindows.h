#pragma once
#include "Campaign.h"
#include <nlohmann/json.hpp>
#include <RLGymCPP/TerminalConditions/TerminalCondition.h>
struct EventWindow {size_t row=0;int team=0,split=0;std::string kind;std::vector<std::array<float,16>> controls;};
inline std::vector<EventWindow> eventWindows;
inline int fixedLearnerTeam=-1;
inline bool useEventWindows=false;
inline void loadEventWindows(const std::string& path,bool requireVerified=true){
    std::ifstream f(path);nlohmann::json data;f>>data;if(data.at("version")!=1||!replayBank||replayBank->players!=2)throw std::runtime_error("Need duel event windows and matching bank");
    if(requireVerified&&!data.value("cpp_verified",false))throw std::runtime_error("Event windows need C++ outcome verification before training");
    for(const auto& raw:data.at("windows")){
        EventWindow w;w.row=raw.at("start_row").get<size_t>();w.team=raw.at("query_team");w.split=raw.at("split");w.kind=raw.at("kind");
        if(w.row>=replayBank->count||w.team<0||w.team>1||w.split<0||w.split>2||(w.kind!="replay_attack"&&w.kind!="replay_save"))throw std::runtime_error("Invalid window metadata");
        if(raw.at("controls").size()<8||raw.at("controls").size()>180)throw std::runtime_error("Invalid control horizon");
        for(const auto& frame:raw.at("controls")){
            if(frame.size()!=2)throw std::runtime_error("Invalid control roster");std::array<float,16>a{};
            for(int car=0;car<2;car++){if(frame[car].size()!=8)throw std::runtime_error("Invalid control vector");for(int k=0;k<8;k++){
                float x=frame[car][k];if(!std::isfinite(x)||std::abs(x)>1.001f||(k>=5&&x!=0&&x!=1))throw std::runtime_error("Invalid controller value");a[car*8+k]=x;
            }}w.controls.push_back(a);
        }eventWindows.push_back(std::move(w));
    }
    if(eventWindows.empty())throw std::runtime_error("No verified event windows");
}
struct EventSession {size_t selected=0;uint64_t origin=0;bool active=false;};
class EventSetter : public RLGC::StateSetter {
    std::shared_ptr<EventSession> session;std::vector<size_t> options;
public:
    EventSetter(std::shared_ptr<EventSession>s):session(s){
        for(size_t i=0;i<eventWindows.size();i++)if(eventWindows[i].split==0&&eventWindows[i].kind==campaignFocus&&eventWindows[i].team==fixedLearnerTeam)options.push_back(i);
        if(options.empty())throw std::runtime_error("No verified training windows for requested role/color");
    }
    void ResetArena(RocketSim::Arena* arena)override{
        session->selected=options[std::rand()%options.size()];session->origin=arena->tickCount;session->active=true;
        replayBank->restore(arena,eventWindows[session->selected].row);replayResetCount++;
    }
};
class EventAction : public CampaignAction {
    std::shared_ptr<EventSession> session;
public:
    EventAction(std::shared_ptr<EventSession>s):session(s){}
    void ApplyPhysicsControls(RocketSim::Arena* arena)override{
        if(!session->active)return;auto& window=eventWindows[session->selected];size_t step=(arena->tickCount-session->origin)/8;
        if(step>=window.controls.size())return;
        for(auto* car:arena->GetCars())if(int(car->team)!=fixedLearnerTeam){
            auto& a=window.controls[step];int i=int(car->team)*8;car->controls.throttle=a[i];car->controls.steer=a[i+1];car->controls.pitch=a[i+2];car->controls.yaw=a[i+3];
            car->controls.roll=a[i+4];car->controls.jump=a[i+5];car->controls.boost=a[i+6];car->controls.handbrake=a[i+7];
        }
    }
};
class EventDeadline : public RLGC::TerminalCondition {
    std::shared_ptr<EventSession> session;
public:
    EventDeadline(std::shared_ptr<EventSession>s):session(s){}
    bool IsTerminal(const RLGC::GameState&s)override{return s.lastTickCount-session->origin>=eventWindows[session->selected].controls.size()*8;}
    bool IsTruncation()override{return true;}
};
class EventReward : public RLGC::Reward {
    bool intercepted=false,paid=false,active=false;int contacts=0;
public:
    void Reset(const RLGC::GameState&)override{intercepted=false;paid=false;active=false;contacts=0;}
    float GetReward(const RLGC::Player& car,const RLGC::GameState& s,bool terminal)override{
        if(int(car.team)!=fixedLearnerTeam)return 0;float sign=car.team==RocketSim::Team::BLUE?1:-1;float reward=0;
        for(int k=0;k<8;k++)active=active||std::abs(car.prevAction[k])>1e-6;
        if(car.ballTouchedStep){intercepted=true;if(contacts++<2)reward+=.2f;}
        if(campaignFocus=="replay_save"&&intercepted&&active&&!paid&&sign*s.ball.vel.y>200&&sign*s.ball.pos.y>-3800&&!s.goalScored){reward+=2;paid=true;}
        if(s.goalScored)reward+=sign*s.ball.pos.y>0?(intercepted&&active?10:0):-10;
        return reward;
    }
};
inline nlohmann::json auditEventWindows(const std::string& input){
    std::ifstream f(input);nlohmann::json data;f>>data;nlohmann::json records=nlohmann::json::array();
    auto* arena=RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR);arena->AddCar(RocketSim::Team::BLUE);arena->AddCar(RocketSim::Team::ORANGE);
    for(size_t i=0;i<data.at("windows").size();i++){
        const auto& w=data["windows"][i];auto cars=replayBank->restore(arena,w.at("start_row").get<size_t>());int goal=-1;
        bool touched=false;uint64_t origin=arena->tickCount;int query=w.at("query_team");bool save=w.at("kind")=="replay_save";
        for(const auto& frame:w.at("controls")){
            for(auto* c:cars){int team=int(c->team);auto& v=frame[team];auto& a=c->controls;
                a.throttle=save&&team==query?0:v[0].get<float>();a.steer=save&&team==query?0:v[1].get<float>();a.pitch=save&&team==query?0:v[2].get<float>();a.yaw=save&&team==query?0:v[3].get<float>();a.roll=save&&team==query?0:v[4].get<float>();
                a.jump=save&&team==query?false:v[5].get<float>()!=0;a.boost=save&&team==query?false:v[6].get<float>()!=0;a.handbrake=save&&team==query?false:v[7].get<float>()!=0;
            }arena->Step(8);for(auto* c:cars)if(int(c->team)==query&&c->GetState().ballHitInfo.isValid&&c->GetState().ballHitInfo.tickCountWhenHit>=origin)touched=true;auto ball=arena->ball->GetState();if(arena->IsBallScored()){goal=ball.pos.y>0?0:1;break;}
        }
        int passiveGoal=-1;
        if(!save){
            replayBank->restore(arena,w.at("start_row").get<size_t>());
            for(const auto& frame:w.at("controls")){
                for(auto* c:cars){int team=int(c->team);auto& v=frame[team];auto& a=c->controls;
                    a.throttle=team==query?0:v[0].get<float>();a.steer=team==query?0:v[1].get<float>();a.pitch=team==query?0:v[2].get<float>();a.yaw=team==query?0:v[3].get<float>();a.roll=team==query?0:v[4].get<float>();
                    a.jump=team==query?false:v[5].get<float>()!=0;a.boost=team==query?false:v[6].get<float>()!=0;a.handbrake=team==query?false:v[7].get<float>()!=0;
                }arena->Step(8);if(arena->IsBallScored()){passiveGoal=arena->ball->GetState().pos.y>0?0:1;break;}
            }
        }
        records.push_back({{"index",i},{"accepted",goal==(save?1-query:query)&&(save||touched)&& (save||passiveGoal!=query)},{"goal_team",goal},{"passive_attacker_goal_team",passiveGoal},{"kind",w["kind"]},{"split",w["split"]}});
    }delete arena;return records;
}
