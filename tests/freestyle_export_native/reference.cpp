#include <GigaLearnCPP/Learner.h>
#include <GigaLearnCPP/PPO/PPOLearner.h>
#include <RLGymCPP/ThreadPool.h>
#include "GigaLearn_Project/Freestyle/FreestyleObs.h"
#include "GigaLearn_Project/Freestyle/FreestyleRewards.h"
#include "GigaLearn_Project/Freestyle/FreestyleActions.h"
#include "GigaLearn_Project/Freestyle/FreestyleBridge.h"
#include <torch/torch.h>
#include <fstream>
using namespace SlaterFreestyle;
using namespace GGL;
using namespace RLGC;
using Json=nlohmann::json;

RocketSim::Vec V(const Json& a) {return {a.at(0),a.at(1),a.at(2)};}
RLGC::Player ReadPlayer(const Json& j) {
    RLGC::Player p;p.carId=j.at("carId");p.team=RocketSim::Team(j.at("team").get<int>());
    p.pos=V(j.at("pos"));p.vel=V(j.at("vel"));p.angVel=V(j.at("angVel"));
    p.rotMat=RocketSim::RotMat(V(j.at("forward")),V(j.at("right")),V(j.at("up")));
#define FIELD(name) p.name=j.at(#name)
    FIELD(boost);FIELD(isOnGround);FIELD(hasJumped);FIELD(hasDoubleJumped);FIELD(hasFlipped);
    FIELD(isFlipping);FIELD(isJumping);FIELD(isDemoed);FIELD(isSupersonic);FIELD(airTime);
    FIELD(airTimeSinceJump);FIELD(jumpTime);FIELD(flipTime);FIELD(handbrakeVal);FIELD(demoRespawnTimer);FIELD(ballTouchedStep);
#undef FIELD
    p.worldContact.hasContact=j.at("worldContact").at("hasContact");
    p.worldContact.contactNormal=V(j.at("worldContact").at("contactNormal"));
    for(int k=0;k<8;k++)p.prevAction[k]=j.at("prevAction").at(k);
    return p;
}
RLGC::GameState State(const Json& j) {
    RLGC::GameState s;for(const auto& p:j.at("players"))s.players.push_back(ReadPlayer(p));
    s.ball.pos=V(j.at("ball").at("pos"));s.ball.vel=V(j.at("ball").at("vel"));s.ball.angVel=V(j.at("ball").at("angVel"));
    s.boostPads=j.at("boostPads").get<std::vector<bool>>();s.boostPadTimers=j.at("boostPadTimers").get<std::vector<float>>();
    s.goalScored=j.at("goalScored");s.lastTouchCarID=j.at("lastTouchCarID");s.deltaTime=j.value("deltaTime",1.f/30);
    return s;
}
std::shared_ptr<FreestyleContext> Context(const Json& j) {
    auto ctx=std::make_shared<FreestyleContext>();ctx->stage=Stage(j.at("stage").get<int>());
    ctx->difficulty=j.at("difficulty");ctx->episodeSeconds=j.at("episodeSeconds");ctx->privilegedVisible=false;
    return ctx;
}
void Chain(ChainState& c,const Json& j) {
#define FIELD(name) c.name=j.value(#name,c.name)
    FIELD(lastTouch);FIELD(lastNoseTouch);FIELD(carry);FIELD(bestCarry);FIELD(carryDistance);FIELD(wall);
    FIELD(pop);FIELD(wallAt);FIELD(popAt);FIELD(noseTouches);FIELD(pinch);FIELD(board);FIELD(retouch);
    FIELD(ownBoard);FIELD(recovered);FIELD(wallDashes);
#undef FIELD
}
EnvCreateResult Environment(int) {
    auto ctx=std::make_shared<FreestyleContext>();EnvCreateResult r;
    r.arena=RocketSim::Arena::Create(RocketSim::GameMode::SOCCAR);ctx->learnerId=r.arena->AddCar(RocketSim::Team::BLUE)->id;
    r.obsBuilder=new FreestyleObs(ctx);r.actionParser=new FreestyleControls();r.stateSetter=new FreestyleStateSetter(ctx);
    r.terminalConditions={new FreestyleDeadline(ctx)};r.rewards={{new FreestyleReward(ctx),1}};return r;
}
int main(int argc,char** argv) {
    if(argc!=6)return 2;
    Json cases,config;{std::ifstream f(argv[1]);f>>cases;}{std::ifstream f(argv[3]);f>>config;}
    RocketSim::Init(argv[4],false);torch::set_num_threads(1);torch::set_num_interop_threads(1);
    delete RLGC::g_ThreadPool._tp;RLGC::g_ThreadPool._tp=new dp::thread_pool<>(1);
    LearnerConfig cfg;cfg.numGames=1;cfg.sendMetrics=false;cfg.savePolicyVersions=false;cfg.trainAgainstOldVersions=false;
    cfg.checkpointFolder="";cfg.deviceType=LearnerDeviceType::CPU;cfg.ppo.sharedHead.layerSizes={};
    cfg.ppo.policy.layerSizes=std::vector<int>(config.at("depth"),config.at("width"));cfg.ppo.critic.layerSizes=cfg.ppo.policy.layerSizes;
    Learner learner(Environment,cfg);SlaterFreestyleLoadPolicy(&learner,argv[2]);torch::NoGradGuard guard;
    Json out=Json::array();FreestyleControls parser;
    for(const auto& sample:cases) {
        auto ctx=Context(sample.at("context"));auto state=State(sample.at("state"));
        state.lastTickCount=std::llround(sample.at("context").at("elapsed").get<double>()*120);
        const auto id=sample.at("player_id").get<unsigned>();
        Chain(ctx->chains[id],sample.at("context").value("chain",Json::object()));
        auto p=std::find_if(state.players.begin(),state.players.end(),[&](const auto& p){return p.carId==id;});
        if(p==state.players.end())return 3;
        auto obs=FreestyleObs(ctx).BuildObs(*p,state);auto mask=parser.GetActionMask(*p,state);
        auto input=torch::tensor(obs).reshape({1,512});auto masks=torch::tensor(mask).reshape({1,94});
        auto logits=learner.ppo->models["policy"]->Forward(input,false).contiguous();
        torch::Tensor action;SlaterFreestyleInfer(&learner,input,masks,&action);
        std::vector<float> scores(logits.data_ptr<float>(),logits.data_ptr<float>()+94);
        out.push_back({{"observation",obs},{"mask",mask},{"logits",scores},{"action",action.item<int>()}});
    }
    Json result={{"cases",out},{"actions",Json::array()}};
    for(const auto& action:parser.actions){std::vector<float>a;for(float v:action)a.push_back(v);result["actions"].push_back(a);}
    std::ofstream output(argv[5]);output<<result.dump();return 0;
}
