#pragma once
#include "ReplayBank.h"
#include <GigaLearnCPP/PPO/PPOLearner.h>
#include <RLGymCPP/ObsBuilders/AdvancedObs.h>
inline void replayBC(GGL::Learner* learner,int epochs){
    if(!replayBank||epochs<=0)return;
    auto arena=RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR);
    for(uint32_t i=0;i<replayBank->players/2;i++){arena->AddCar(RocketSim::Team::BLUE);arena->AddCar(RocketSim::Team::ORANGE);}
    PaddedObs builder;RLGC::DefaultAction parser;
    std::vector<float> features,targets,weights;std::vector<int64_t> train,val;
    for(size_t i=0;i<replayBank->count;i++){
        auto cars=replayBank->restore(arena,i);const float* row=&replayBank->rows[i*replayBank->width];int q=int(row[52+43*replayBank->players]);
        RLGC::GameState state(arena);
        auto it=std::find_if(state.players.begin(),state.players.end(),[&](const auto& p){return p.carId==cars[q]->id;});
        if(it==state.players.end())throw std::runtime_error("Query car absent");
        auto& player=*it;const float* raw=row+52+43*q;
        for(int j=0;j<8;j++)player.prevAction[j]=raw[27+j];
        auto obs=builder.BuildObs(player,state);if(obs.size()!=learner->obsSize)throw std::runtime_error("Replay observation dimensions differ");
        auto mask=parser.GetActionMask(player,state);std::vector<float> target(90);float sum=0;
        for(int j=0;j<90;j++){target[j]=row[53+43*replayBank->players+j]*mask[j];sum+=target[j];}
        if(sum<.5)continue;for(float& p:target)p/=sum;
        size_t sample=weights.size();features.insert(features.end(),obs.begin(),obs.end());targets.insert(targets.end(),target.begin(),target.end());
        weights.push_back(row[replayBank->width-2]);
        if(row[replayBank->width-1]==0)train.push_back(sample);else if(row[replayBank->width-1]==1)val.push_back(sample);
    }
    delete arena;
    if(train.size()<32||val.size()<8)throw std::runtime_error("Too few feasible replay BC train/validation samples");
    auto opts=torch::TensorOptions().dtype(torch::kFloat32);
    auto x=torch::from_blob(features.data(),{int64_t(weights.size()),learner->obsSize},opts).clone().to(learner->ppo->device);
    auto y=torch::from_blob(targets.data(),{int64_t(weights.size()),90},opts).clone().to(learner->ppo->device);
    auto w=torch::from_blob(weights.data(),{int64_t(weights.size())},opts).clone().to(learner->ppo->device);
    auto& models=learner->ppo->models;
    auto measure=[&](){torch::NoGradGuard guard;auto ix=torch::tensor(val,torch::kInt64).to(learner->ppo->device);
        auto z=models["policy"]->Forward(models["shared_head"]->Forward(x.index_select(0,ix),false),false).log_softmax(-1);
        return (-(y.index_select(0,ix)*z).sum(-1)).mean().item<float>();};
    auto bestFolder=learner->config.checkpointFolder/"_bc_best";std::filesystem::create_directories(bestFolder);
    float bestCE=measure();models.Save(bestFolder);
    std::cout<<"SLATER_REPLAY_BC baseline_ce="<<bestCE<<" train="<<train.size()<<" validation="<<val.size()<<std::endl;
    for(int epoch=0;epoch<epochs;epoch++){
        std::shuffle(train.begin(),train.end(),std::mt19937(20261012+epoch));
        for(size_t i=0;i<train.size();i+=256){
            std::vector<int64_t> part(train.begin()+i,train.begin()+std::min(i+256,train.size()));
            auto ix=torch::tensor(part,torch::kInt64).to(learner->ppo->device);
            auto z=models["policy"]->Forward(models["shared_head"]->Forward(x.index_select(0,ix),false),false).log_softmax(-1);
            auto loss=(-(y.index_select(0,ix)*z).sum(-1)*w.index_select(0,ix)).sum()/w.index_select(0,ix).sum();
            if(!torch::isfinite(loss).item<bool>())throw std::runtime_error("Nonfinite replay BC loss");
            models["policy"]->optim->zero_grad();models["shared_head"]->optim->zero_grad();loss.backward();
            models["policy"]->StepOptim();models["shared_head"]->StepOptim();
        }
        float ce=measure();std::cout<<"SLATER_REPLAY_BC epoch="<<epoch+1<<" validation_ce="<<ce<<std::endl;
        if(std::isfinite(ce)&&ce<bestCE){bestCE=ce;models.Save(bestFolder);}else break;
    }
    models.Load(bestFolder,false,true);learner->Save();
}
