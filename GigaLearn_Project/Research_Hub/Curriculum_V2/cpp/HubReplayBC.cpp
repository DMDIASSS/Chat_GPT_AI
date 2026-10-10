// Experimental GigaLearn-compatible replay-action imitation.
// Reconstructed replay actions are APPROXIMATE, not actual controller telemetry.
// Loads only GL_REPLAY_1 format, builds native AdvancedObs inside RocketSim.
// Saves GigaLearn POLICY/SHARED_HEAD/CRITIC .lt files to an isolated directory.
#define main hub_existing_main_disabled
#include "ExampleMain.cpp"
#undef main

#include <private/GigaLearnCPP/Util/Models.h>
#include <RLGymCPP/OBSBuilders/AdvancedObs.h>
#include <RLGymCPP/ActionParsers/DefaultAction.h>
#include <nlohmann/json.hpp>
#include <torch/torch.h>
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <numeric>
#include <random>
#include <sstream>
#include <vector>

namespace fs=std::filesystem;
using nlohmann::json;

static std::string Arg(int argc,char**argv,const char* name,const char* def="") {
    for(int i=1;i+1<argc;i++)if(std::string(argv[i])==name)return argv[i+1];
    return def;
}
static RocketSim::Vec VecAt(const std::vector<float>& a,int i){return {a.at(i),a.at(i+1),a.at(i+2)};}
struct Sample{std::vector<float> obs;int action;float weight;};

static std::vector<Sample> ReadDataset(const fs::path& path, RocketSim::Arena* arena,
                  RLGC::AdvancedObs& obs,RLGC::DefaultAction& parser,int& obsSize,int maxCount) {
    std::ifstream in(path);
    if(!in)throw std::runtime_error("Cannot open dataset "+path.string());
    std::string line;
    if(!std::getline(in,line))throw std::runtime_error("Empty dataset: "+path.string());
    if(!line.empty() && line.back()=='\r')line.pop_back();
    if(line!="GL_REPLAY_1")throw std::runtime_error("Unsupported dataset header: "+path.string());
    RocketSim::Car *blue=nullptr,*orange=nullptr;
    for(auto* car:arena->_cars){if(car->team==RocketSim::Team::BLUE)blue=car;else orange=car;}
    if(!blue||!orange||arena->_cars.size()!=2)throw std::runtime_error("Replay cloning requires exactly 1v1 cars");
    std::vector<Sample> result;
    int bad=0;
    while(std::getline(in,line)) {
        if(line.empty())continue;
        std::istringstream s(line);std::vector<float> a;float x;
        while(s>>x)a.push_back(x);
        if(a.size()!=53)throw std::runtime_error("Dataset record width invalid (expected 53 floats)");
        bool good=std::all_of(a.begin(),a.end(),[](float v){return std::isfinite(v);});
        int team=(int)a[1],act=(int)a[2];
        if(!good||team<0||team>1||act<0||act>=parser.GetActionAmount()) {bad++;continue;}
        arena->ResetToRandomKickoff(1);
        RocketSim::BallState ball;
        ball.pos=VecAt(a,4);ball.vel=VecAt(a,7);ball.angVel=VecAt(a,10);
        arena->ball->SetState(ball);
        for(int k=0;k<2;k++) {
            int p=13+20*k;
            RocketSim::CarState c;
            c.pos=VecAt(a,p);c.vel=VecAt(a,p+3);c.angVel=VecAt(a,p+6);
            c.rotMat.forward=VecAt(a,p+9);
            c.rotMat.right=VecAt(a,p+12);
            c.rotMat.up=VecAt(a,p+15);
            c.boost=std::clamp(a[p+18],0.f,100.f);
            c.isOnGround=a[p+19]>0.5f;
            c.hasJumped=!c.isOnGround;
            (k==0?blue:orange)->SetState(c);
        }
        // Native RocketSim -> RLGymCPP -> AdvancedObs: NOT a guessed Python observation mapping.
        RLGC::GameState game(arena);
        const RLGC::Player* actor=nullptr;
        for(const auto& car:game.players)
            if((int)car.team==team){actor=&car;break;}
        if(!actor)throw std::runtime_error("No actor on requested team");
        auto features=obs.BuildObs(*actor,game);
        if(obsSize<0)obsSize=(int)features.size();
        if(features.size()!=(size_t)obsSize)throw std::runtime_error("Inconsistent native observation dimension");
        const auto mask=parser.GetActionMask(*actor,game);
        if(!mask.at(act)){bad++;continue;}
        Sample sample;sample.obs=std::move(features);sample.action=act;
        sample.weight=std::clamp(1.f/(1.f+std::max(a[3],0.f)),0.15f,1.f);
        result.push_back(std::move(sample));
        if((int)result.size()>=maxCount)break;
    }
    std::cout<<"[REPLAY BC] "<<path.filename()<<": accepted "<<result.size()<<", rejected "<<bad<<" samples\n";
    return result;
}
static std::pair<float,float> Evaluate(std::vector<Sample>& records,GGL::Model& head,GGL::Model& policy,int obsSize) {
    torch::NoGradGuard guard;
    float loss=0,agreement=0;int n=0;
    for(size_t off=0;off<records.size();off+=512) {
        size_t stop=std::min(off+512,records.size());
        std::vector<float> obs;std::vector<int64_t> labels;
        for(size_t j=off;j<stop;j++) {obs.insert(obs.end(),records[j].obs.begin(),records[j].obs.end());labels.push_back(records[j].action);}
        auto X=torch::from_blob(obs.data(),{(int64_t)labels.size(),obsSize},torch::kFloat32).clone();
        auto Y=torch::from_blob(labels.data(),{(int64_t)labels.size()},torch::kInt64).clone();
        auto logits=policy.Forward(head.Forward(X,false),false);
        loss+=torch::nn::functional::cross_entropy(logits,Y).item<float>()*labels.size();
        agreement+=logits.argmax(1).eq(Y).sum().item<int64_t>();n+=(int)labels.size();
    }
    return {loss/std::max(1,n),agreement/std::max(1,n)};
}
int main(int argc,char**argv){
    try{
        fs::path train=Arg(argc,argv,"--train"),val=Arg(argc,argv,"--val"),out=Arg(argc,argv,"--out");
        fs::path seed=Arg(argc,argv,"--seed-checkpoint");
        int epochs=std::stoi(Arg(argc,argv,"--epochs","4"));
        float lr=std::stof(Arg(argc,argv,"--lr","0.00008"));
        int maxRows=std::stoi(Arg(argc,argv,"--max-records","250000"));
        if(train.empty()||val.empty()||out.empty()||epochs<1||epochs>40||lr<1e-7f||lr>5e-4f||maxRows<100||maxRows>1000000)
            throw std::runtime_error("Usage: --train FILE --val FILE --out NEW_FOLDER [--seed-checkpoint NUMERIC_DIR] [--epochs 4] [--lr 0.00008]");
        if(fs::exists(out))throw std::runtime_error("Destination exists: refuse overwriting "+out.string());
        auto mesh=std::getenv("GIGALEARN_MESHES");
        if(!mesh||!fs::is_directory(mesh))throw std::runtime_error("Set GIGALEARN_MESHES first");
        RocketSim::Init(mesh);
        auto arena=std::unique_ptr<RocketSim::Arena>(RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR));
        arena->AddCar(RocketSim::Team::BLUE);arena->AddCar(RocketSim::Team::ORANGE);
        RLGC::AdvancedObs obs;
        RLGC::DefaultAction parser;
        int obsSize=-1;
        auto training=ReadDataset(train,arena.get(),obs,parser,obsSize,maxRows);
        auto validation=ReadDataset(val,arena.get(),obs,parser,obsSize,maxRows/3);
        if(training.size()<100||validation.size()<20)throw std::runtime_error("Insufficient accepted native-observation samples");
        GGL::PartialModelConfig hc;hc.layerSizes={256,256};hc.addOutputLayer=false;hc.addLayerNorm=true;
        GGL::PartialModelConfig pc;pc.layerSizes={256,256,256};pc.addLayerNorm=true;
        GGL::ModelConfig h(hc),p(pc),c(pc);
        h.numInputs=obsSize;h.numOutputs=0;
        p.numInputs=256;p.numOutputs=parser.GetActionAmount();
        c.numInputs=256;c.numOutputs=1;
        GGL::Model head("shared_head",h,torch::kCPU),policy("policy",p,torch::kCPU),critic("critic",c,torch::kCPU);
        if(!seed.empty()) {
            if(!fs::exists(seed/"RUNNING_STATS.json"))throw std::runtime_error("Seed lacks RUNNING_STATS.json");
            head.Load(seed,false,false);policy.Load(seed,false,false);critic.Load(seed,false,false);
        }
        head.SetOptimLR(lr);policy.SetOptimLR(lr);
        std::mt19937 gen(817249);
        std::vector<size_t> order(training.size());std::iota(order.begin(),order.end(),0);
        auto first=Evaluate(validation,head,policy,obsSize);
        std::cout<<"[REPLAY BC] Initial validation CE="<<first.first<<" accuracy="<<first.second<<"\n";
        float best=first.first;int bestEpoch=0;
        fs::path staging=out.string()+".partial";
        if(fs::exists(staging))throw std::runtime_error("A partial run exists; inspect before retrying: "+staging.string());
        fs::create_directories(staging);
        std::vector<json> history;
        auto saveBest=[&](){
            head.Save(staging);policy.Save(staging);critic.Save(staging);
        };
        try {
            for(int epoch=1;epoch<=epochs;epoch++) {
                std::shuffle(order.begin(),order.end(),gen);
                float avgLoss=0;int seen=0;
                for(size_t offset=0;offset<order.size();offset+=512){
                    size_t stop=std::min(offset+512,order.size());
                    std::vector<float> Xv;std::vector<int64_t> Yv;std::vector<float> Wv;
                    for(size_t j=offset;j<stop;j++){
                        auto& sample=training[order[j]];
                        Xv.insert(Xv.end(),sample.obs.begin(),sample.obs.end());Yv.push_back(sample.action);Wv.push_back(sample.weight);
                    }
                    auto X=torch::from_blob(Xv.data(),{(int64_t)Yv.size(),obsSize},torch::kFloat32).clone();
                    auto Y=torch::from_blob(Yv.data(),{(int64_t)Yv.size()},torch::kInt64).clone();
                    auto W=torch::from_blob(Wv.data(),{(int64_t)Yv.size()},torch::kFloat32).clone();
                    auto logits=policy.Forward(head.Forward(X,false),false);
                    auto per=torch::nn::functional::cross_entropy(logits,Y,torch::nn::functional::CrossEntropyFuncOptions().reduction(torch::kNone));
                    auto loss=(per*W).mean();
                    loss.backward();
                    torch::nn::utils::clip_grad_norm_(head.parameters(),0.5);
                    torch::nn::utils::clip_grad_norm_(policy.parameters(),0.5);
                    head.StepOptim();policy.StepOptim();
                    avgLoss+=loss.item<float>()*Yv.size();seen+=(int)Yv.size();
                }
                auto metrics=Evaluate(validation,head,policy,obsSize);
                history.push_back({{"epoch",epoch},{"train_loss",avgLoss/std::max(1,seen)},
                                   {"validation_cross_entropy",metrics.first},{"val_argmax_agreement",metrics.second}});
                std::cout<<"[REPLAY BC] Epoch "<<epoch<<" train_loss="<<(avgLoss/std::max(1,seen))
                          <<" val_ce="<<metrics.first<<" agreement="<<metrics.second<<std::endl;
                if(metrics.first<best-0.0001f) {best=metrics.first;bestEpoch=epoch;saveBest();}
            }
            if(bestEpoch==0)throw std::runtime_error("No validation improvement. Rejecting candidate; no checkpoint promoted.");
            json stats;
            if(!seed.empty()) {
                std::ifstream f(seed/"RUNNING_STATS.json");f>>stats;
            } else stats={{"total_timesteps",0},{"total_iterations",0},
                         {"return_stat",{{"count",0},{"mean",0.0},{"var",0.0}}}};
            int64_t ts=stats.value("total_timesteps",int64_t(0));
            fs::path cp=staging/"checkpoint"/std::to_string(ts);
            fs::create_directories(cp);
            for(auto& name:{"POLICY.lt","POLICY_OPTIM.lt","SHARED_HEAD.lt","SHARED_HEAD_OPTIM.lt","CRITIC.lt","CRITIC_OPTIM.lt"})
                fs::rename(staging/name,cp/name);
            std::ofstream(cp/"RUNNING_STATS.json")<<stats.dump(2);
            json report={{"kind","gigalearn_replay_bc_v1"},{"status","experimental_checkpoint"},
                {"training_samples",training.size()},{"validation_samples",validation.size()},
                {"observation_size",obsSize},{"actions",parser.GetActionAmount()},
                {"best_epoch",bestEpoch},{"initial_val_ce",first.first},
                {"best_val_ce",best},{"history",history},
                {"checkpoint",(out/"checkpoint"/std::to_string(ts)).string()},
                {"caveat","Approximate replay controls and reconstructed physics. Not verified competitive skill. No Nexto vs opponent training or TAS imitation."}};
            std::ofstream(staging/"report.json")<<report.dump(2);
            fs::rename(staging,out);
            std::cout<<"[REPLAY BC] SUCCESS: isolated checkpoint="<<(out/"checkpoint"/std::to_string(ts))<<std::endl;
        } catch (...) {throw;}
        return 0;
    }catch(const std::exception& e){std::cerr<<"[REPLAY BC] FAILED: "<<e.what()<<std::endl;return 1;}
}
