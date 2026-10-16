#pragma once
#include "Campaign.h"
#include <GigaLearnCPP/PPO/PPOLearner.h>
#include <set>

// Scripted cars generate demonstrations. They never enter the PPO buffer.
// Only the policy head is optimized; shared mechanics features and critic stay fixed.
inline void kickoffBC(GGL::Learner* learner,int epochs,int demos){
    if(epochs<=0)return;
    auto arena=RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR);
    int roster=replayBank?replayBank->players:2;
    for(int i=0;i<roster/2;i++){arena->AddCar(RocketSim::Team::BLUE);arena->AddCar(RocketSim::Team::ORANGE);}
    PaddedObs builder;RLGC::DefaultAction parser;RLGC::KickoffState setter;
    std::vector<float> features,masks,anchor;std::vector<int64_t> labels,train,val;
    uint64_t scriptTicks=0;bool stages[7]={};
    for(int demo=0;demo<demos;demo++){
        setter.ResetArena(arena);std::map<uint32_t,RLGC::Action> previous;
        std::set<uint32_t> takers;for(int team=0;team<2;team++){
            RocketSim::Car* best=nullptr;float distance=1e20;
            for(auto* car:arena->GetCars())if(int(car->team)==team){
                float d=car->GetState().pos.Length2D();if(d<distance){distance=d;best=car;}
            }
            if(best)takers.insert(best->id);
        }
        for(int tick=0;tick<168;tick++){
            auto ball=arena->ball->GetState();if(ball.pos.Length2D()>=1||ball.pos.y!=0)break;
            auto controls=CampaignAction::ScriptAction(tick);
            auto cars=arena->GetCars();
            if(tick%4==0){
                RLGC::GameState state(arena);
                for(auto& player:state.players){
                    if(!takers.count(player.carId))continue;
                    player.prevAction=previous[player.carId];
                    auto obs=builder.BuildObs(player,state);auto mask=parser.GetActionMask(player,state);
                    float best=1e20;int target=0;
                    for(int index=0;index<parser.actions.size();index++)if(mask[index]){
                        float error=0;for(int k=0;k<8;k++){
                            float difference=parser.actions[index][k]-controls[k];
                            error+=difference*difference*(k==5||k==6?4.f:1.f);
                        }
                        if(error<best){best=error;target=index;}
                    }
                    size_t index=labels.size();features.insert(features.end(),obs.begin(),obs.end());
                    for(auto value:mask)masks.push_back(value?1.f:0.f);
                    labels.push_back(target);(demo%5==4?val:train).push_back(index);
                }
            }
            for(auto* car:cars){
                if(!takers.count(car->id))continue;
                car->controls.throttle=controls[0];car->controls.steer=controls[1];car->controls.pitch=controls[2];car->controls.yaw=controls[3];
                car->controls.roll=controls[4];car->controls.jump=controls[5];car->controls.boost=controls[6];car->controls.handbrake=controls[7];
                previous[car->id]=controls;scriptTicks++;
            }
            stages[CampaignAction::ScriptStage(tick)]=true;arena->Step(1);
        }
    }
    // A train-only replay-state KL anchor limits damage to previously learned play.
    if(replayBank){
        for(size_t i=0;i<replayBank->count&&anchor.size()<512*learner->obsSize;i++){
            auto* row=&replayBank->rows[i*replayBank->width];if(row[replayBank->width-1]!=0)continue;
            auto cars=replayBank->restore(arena,i);int query=int(row[52+43*replayBank->players]);
            RLGC::GameState state(arena);auto id=cars[query]->id;
            for(auto& player:state.players)if(player.carId==id){
                for(int k=0;k<8;k++)player.prevAction[k]=row[52+43*query+27+k];
                auto obs=builder.BuildObs(player,state);anchor.insert(anchor.end(),obs.begin(),obs.end());break;
            }
        }
    }
    delete arena;
    if(train.size()<32||val.size()<8)throw std::runtime_error("Insufficient kickoff demonstration groups");
    auto opts=torch::TensorOptions().dtype(torch::kFloat32);auto device=learner->ppo->device;
    auto x=torch::from_blob(features.data(),{int64_t(labels.size()),learner->obsSize},opts).clone().to(device);
    auto m=torch::from_blob(masks.data(),{int64_t(labels.size()),90},opts).clone().to(device);
    auto y=torch::tensor(labels,torch::kInt64).to(device);auto& models=learner->ppo->models;
    torch::Tensor hidden,anchorHidden,anchorTarget;
    {torch::NoGradGuard guard;hidden=models["shared_head"]->Forward(x,false).detach();
        if(!anchor.empty()){
            auto a=torch::from_blob(anchor.data(),{int64_t(anchor.size()/learner->obsSize),learner->obsSize},opts).clone().to(device);
            anchorHidden=models["shared_head"]->Forward(a,false).detach();
            anchorTarget=models["policy"]->Forward(anchorHidden,false).softmax(-1).detach();
        }
    }
    auto logprobs=[&](const std::vector<int64_t>& indices){
        auto ix=torch::tensor(indices,torch::kInt64).to(device);
        auto logits=models["policy"]->Forward(hidden.index_select(0,ix),false);
        return std::make_pair(logits.masked_fill(m.index_select(0,ix)==0,-1e10).log_softmax(-1),y.index_select(0,ix));
    };
    auto measure=[&](){torch::NoGradGuard guard;auto pair=logprobs(val);
        return -pair.first.gather(1,pair.second.unsqueeze(1)).mean().item<float>();};
    auto folder=learner->config.checkpointFolder/"_kickoff_best";std::filesystem::create_directories(folder);
    float best=measure();models.Save(folder);int stageCount=0;for(bool stage:stages)stageCount+=stage;
    std::cout<<"SLATER_KICKOFF_BC baseline_ce="<<best<<" train="<<train.size()<<" validation="<<val.size()
        <<" script_ticks="<<scriptTicks<<" stages="<<stageCount<<" shared_frozen=1 anchor_train_only=1"<<std::endl;
    for(int epoch=0;epoch<epochs;epoch++){
        std::shuffle(train.begin(),train.end(),std::mt19937(710124+epoch));
        for(size_t offset=0;offset<train.size();offset+=128){
            std::vector<int64_t> part(train.begin()+offset,train.begin()+std::min(offset+128,train.size()));
            auto pair=logprobs(part);auto loss=-pair.first.gather(1,pair.second.unsqueeze(1)).mean();
            if(anchorHidden.defined()){
                auto z=models["policy"]->Forward(anchorHidden,false).log_softmax(-1);
                loss+=.5f*(anchorTarget*(anchorTarget.clamp_min(1e-11).log()-z)).sum(-1).mean();
            }
            if(!torch::isfinite(loss).item<bool>())throw std::runtime_error("Nonfinite kickoff imitation loss");
            auto model=models["policy"];model->optim->zero_grad();loss.backward();model->optim->step();model->optim->zero_grad();model->_seqHalfOutdated=true;
        }
        float ce=measure();std::cout<<"SLATER_KICKOFF_BC epoch="<<epoch+1<<" validation_ce="<<ce<<std::endl;
        if(std::isfinite(ce)&&ce<best){best=ce;models.Save(folder);}else break;
    }
    models.Load(folder,false,true);learner->Save();
}
