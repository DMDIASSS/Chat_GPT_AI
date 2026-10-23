#pragma once
#include <RLGymCPP/StateSetters/KickoffState.h>
#include <RLGymCPP/ActionParsers/DefaultAction.h>
#include <fstream>
#include <algorithm>
#include <cmath>
#include <memory>
#include <iostream>
#include <atomic>
// Portable little-endian bank: header, action table, pad positions, fixed float rows.
// Each row is ball(18), timers(34), cars(43 each), query index, target(90), weight, split.
struct ReplayBank {
    uint32_t players=0,count=0,width=0;std::vector<float> rows,pads;std::vector<size_t> train,val;
    ReplayBank(const std::string& path){
        std::ifstream f(path,std::ios::binary);char magic[4];uint32_t version=0;
        f.read(magic,4);f.read((char*)&version,4);f.read((char*)&players,4);f.read((char*)&count,4);f.read((char*)&width,4);
        if(!f||std::string(magic,4)!="SGRB"||version!=1||players<2||players>6||players%2||count>100000||width!=52+43*players+93)
            throw std::runtime_error("Invalid replay bank header");
        std::vector<float> table(720);f.read((char*)table.data(),table.size()*4);
        RLGC::DefaultAction parser;
        if(parser.actions.size()!=90)throw std::runtime_error("GigaLearn actions are not 90");
        for(size_t i=0;i<90;i++)for(int j=0;j<8;j++)if(parser.actions[i][j]!=table[i*8+j])throw std::runtime_error("Replay/GigaLearn action table mismatch");
        pads.resize(102);f.read((char*)pads.data(),pads.size()*4);
        rows.resize(size_t(count)*width);f.read((char*)rows.data(),rows.size()*4);
        if(!f||f.peek()!=EOF)throw std::runtime_error("Replay bank length mismatch");
        for(float x:rows)if(!std::isfinite(x))throw std::runtime_error("Nonfinite replay bank");
        for(size_t i=0;i<count;i++){
            const float* r=&rows[i*width];int query=int(r[52+43*players]);float sum=0;
            for(int j=0;j<90;j++){float p=r[53+43*players+j];if(p<0)throw std::runtime_error("Negative target");sum+=p;}
            if(query<0||query>=players||std::abs(sum-1)>1e-4||r[width-2]<=0||r[width-2]>1)throw std::runtime_error("Invalid replay target");
            if(r[width-1]==0)train.push_back(i);else if(r[width-1]==1)val.push_back(i);else if(r[width-1]!=2)throw std::runtime_error("Invalid replay split");
        }
        if(train.empty()||val.empty())throw std::runtime_error("Replay bank needs independent train/validation rows");
    }
    static RocketSim::Vec vec(const float* p){return {p[0],p[1],p[2]};}
    static void physics(RocketSim::PhysState& s,const float* p){
        s.pos=vec(p);s.rotMat=RocketSim::RotMat(vec(p+3),vec(p+6),vec(p+9));s.vel=vec(p+12);s.angVel=vec(p+15);
    }
    std::vector<RocketSim::Car*> restore(RocketSim::Arena* arena,size_t index)const{
        const float* r=&rows.at(index*width);
        RocketSim::BallState b;physics(b,r);arena->ball->SetState(b);
        std::vector<RocketSim::Car*> cars(arena->GetCars().begin(),arena->GetCars().end());
        std::sort(cars.begin(),cars.end(),[](auto* a,auto* b){return a->team!=b->team?a->team<b->team:a->id<b->id;});
        if(cars.size()!=players)throw std::runtime_error("Replay reset roster mismatch");
        for(size_t i=0;i<cars.size();i++){
            const float* p=r+52+43*i;RocketSim::CarState s;physics(s,p);
            s.boost=p[18];s.isOnGround=p[19];s.hasJumped=p[20];s.hasDoubleJumped=p[21];s.hasFlipped=p[22];s.isJumping=p[23];
            s.jumpTime=p[24];s.flipTime=p[25];s.airTimeSinceJump=p[26];
            s.lastControls.throttle=p[27];s.lastControls.steer=p[28];s.lastControls.pitch=p[29];s.lastControls.yaw=p[30];s.lastControls.roll=p[31];
            s.lastControls.jump=p[32];s.lastControls.boost=p[33];s.lastControls.handbrake=p[34];
            s.flipRelTorque=vec(p+35);for(int j=0;j<4;j++)s.wheelsWithContact[j]=p[38+j];s.isFlipping=p[42];cars[i]->SetState(s);
        }
        for(auto* pad:arena->GetBoostPads()){
            size_t closest=0;float distance=1e20;
            for(size_t i=0;i<34;i++){
                float d=(pad->config.pos-vec(pads.data()+i*3)).Length();if(d<distance){distance=d;closest=i;}
            }
            if(distance>2)throw std::runtime_error("Replay pad layout differs from arena");
            RocketSim::BoostPadState s;s.cooldown=r[18+closest];s.isActive=s.cooldown<=0;pad->SetState(s);
        }
        return cars;
    }
};
inline std::shared_ptr<ReplayBank> replayBank;
inline std::atomic<uint64_t> replayResetCount{0};
class ReplayMixedSetter : public RLGC::StateSetter {
    RLGC::KickoffState kickoff;
public:
    void ResetArena(RocketSim::Arena* arena)override{
        kickoff.ResetArena(arena);
        if(replayBank&&std::rand()%5==0){size_t i=replayBank->train[std::rand()%replayBank->train.size()];replayBank->restore(arena,i);replayResetCount++;}
    }
};
