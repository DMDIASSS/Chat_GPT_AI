// AFK_HUB_EVALUATOR_V1
// Read-only GigaLearn .lt competitive evaluator (first-goal, seeded kickoff, 1v1).
// The built trainer's ExampleMain.cpp is intentionally reused for the exact
// AdvancedObs, DefaultAction and network architecture. NO PPO updates here.
#define main afk_hub_trainer_main_unused
#include "ExampleMain.cpp"
#undef main

#include <GigaLearnCPP/Util/InferUnit.h>
#include <RLGymCPP/EnvSet/EnvSet.h>
#include <RLGymCPP/StateSetters/StateSetter.h>
#include <nlohmann/json.hpp>

#include <filesystem>
#include <fstream>
#include <iostream>
#include <cstdlib>
#include <string>
#include <stdexcept>
#include <algorithm>
#include <memory>
#include <cstdint>
#include <vector>
#include <cmath>

using nlohmann::json;
namespace fs = std::filesystem;

static int fixedSeed = 734891;
class FixedSeedKickoff : public RLGC::StateSetter {
public:
    void ResetArena(RocketSim::Arena* arena) override {
        arena->ResetToRandomKickoff(fixedSeed);
        // Avoid leaking action inputs between swapped-side episodes.
        for (auto* car : arena->_cars) car->controls = RocketSim::CarControls{};
    }
};

static RLGC::EnvCreateResult MakeEvaluationEnv(int idx) {
    auto result = EnvCreateFunc(idx); // same obs/action setup as patched training
    // RLGymCPP StateSetter has no virtual destructor: do not delete via base pointer.
    // This replaces one short-lived original setter (one arena per process).
    result.stateSetter = new FixedSeedKickoff();
    return result;
}

static bool SameAction(const RLGC::Action& a, const RLGC::Action& b) {
    for (size_t i=0;i<RLGC::Action::ELEM_AMOUNT;i++)
        if (a[i] != b[i]) return false;
    return true;
}
static int ToIndex(const RLGC::Action& a, const RLGC::DefaultAction& parser) {
    for (int i=0;i<(int)parser.actions.size();i++)
        if (SameAction(a,parser.actions[i]))return i;
    throw std::runtime_error("Model action not found in default discrete action lookup");
}

struct MatchStats {
    int goal=-1; // 0 blue, 1 orange, -1 none
    int steps=0;
    int shots[2]={0,0};
    int saves[2]={0,0};
    int touches[2]={0,0};
    int demos[2]={0,0};
    double ballSpeedSum=0;
    double peakBallSpeed=0;
};

static MatchStats OneMatch(RLGC::EnvSet& env,
                           GGL::InferUnit& a, GGL::InferUnit& b,
                           bool aBlue, int seed, int maxDecisions) {
    fixedSeed=seed;
    env.ResetArena(0);
    a.obsBuilder->Reset(env.state.gameStates[0]);
    b.obsBuilder->Reset(env.state.gameStates[0]);
    auto* parser=dynamic_cast<RLGC::DefaultAction*>(env.actionParsers[0]);
    if (!parser) throw std::runtime_error("Evaluator requires DefaultAction");
    MatchStats result;
    for(int step=0;step<maxDecisions;step++) {
        // Infer before stepping. GigaLearn training does this too.
        const auto& state=env.state.gameStates[0];
        std::vector<int> actions;
        actions.reserve(state.players.size());
        for (const auto& player:state.players) {
            bool aPlayer = (player.team==RocketSim::Team::BLUE)==aBlue;
            auto act=(aPlayer ? a : b).InferAction(player,state,true);
            actions.push_back(ToIndex(act,*parser));
        }
        env.StepFirstHalf(false);
        env.StepSecondHalf(actions,false);
        const auto& next=env.state.gameStates[0];
        result.steps++;
        double sp=next.ball.vel.Length();
        result.ballSpeedSum+=sp;
        result.peakBallSpeed=std::max(result.peakBallSpeed,sp);
        for(const auto& player:next.players) {
            int side=player.team==RocketSim::Team::BLUE?0:1;
            result.shots[side]+=player.eventState.shot?1:0;
            result.saves[side]+=player.eventState.save?1:0;
            result.touches[side]+=player.ballTouchedStep?1:0;
            result.demos[side]+=player.eventState.demo?1:0;
        }
        if(next.goalScored) {
            // Orange goal is at positive Y; a goal there scores for BLUE.
            result.goal=(next.ball.pos.y>0)?0:1;
            break;
        }
        // Max decision cap is the only other termination for evaluation.
    }
    return result;
}

static std::string Arg(int argc,char**argv,const std::string& k, const std::string& d="") {
    for(int i=1;i+1<argc;i++)if(k==argv[i])return argv[i+1];
    return d;
}
static void CheckModels(const fs::path& path) {
    if(!fs::is_directory(path) || !fs::is_regular_file(path/"POLICY.lt") ||
       !fs::is_regular_file(path/"SHARED_HEAD.lt"))
        throw std::runtime_error("Model directory missing POLICY.lt or SHARED_HEAD.lt: "+path.string());
}

int main(int argc,char**argv) {
    try {
        if(argc<3 || Arg(argc,argv,"--help")=="1") {
            std::cout << "GigaLearnEval --a CHECKPOINT_DIR --b CHECKPOINT_DIR --out REPORT.json"
                         " [--pairs 12] [--decisions 900] [--seed 734891] [--cpu 1]\n";
            return argc<3?2:0;
        }
        fs::path pathA=Arg(argc,argv,"--a"),pathB=Arg(argc,argv,"--b"),out=Arg(argc,argv,"--out");
        if(pathA.empty()||pathB.empty()||out.empty())throw std::runtime_error("Missing --a/--b/--out");
        CheckModels(pathA);CheckModels(pathB);
        int pairs=std::stoi(Arg(argc,argv,"--pairs","12"));
        int decisions=std::stoi(Arg(argc,argv,"--decisions","900"));
        int baseSeed=std::stoi(Arg(argc,argv,"--seed","734891"));
        if(pairs<1||pairs>1000||decisions<60||decisions>5000||baseSeed<1)
            throw std::runtime_error("Invalid evaluation limits");
        // GigaLearn's training example has a fixed architecture: shared head 256x2,
        // actor 256x3, layernorm, ReLU, DefaultAction.
        GGL::PartialModelConfig shared={},actor={};
        shared.layerSizes={256,256};shared.addOutputLayer=false;
        actor.layerSizes={256,256,256};
        shared.optimType=actor.optimType=GGL::ModelOptimType::ADAM;
        shared.activationType=actor.activationType=GGL::ModelActivationType::RELU;
        shared.addLayerNorm=actor.addLayerNorm=true;
        const bool gpu=Arg(argc,argv,"--cpu","1")=="0";
        const char* mesh=std::getenv("GIGALEARN_MESHES");
        if(!mesh||!fs::is_directory(mesh))throw std::runtime_error("Set GIGALEARN_MESHES to RocketSim Soccar meshes folder");
        RocketSim::Init(mesh);
        RLGC::EnvSetConfig envcfg={};
        envcfg.envCreateFn=MakeEvaluationEnv;
        envcfg.numArenas=1;envcfg.tickSkip=8;envcfg.actionDelay=7;envcfg.saveRewards=false;
        RLGC::EnvSet env(envcfg);
        if(env.state.gameStates[0].players.size()!=2)
            throw std::runtime_error("Only one-versus-one checkpoints can be evaluated in v1");
        int obsSize=env.obsSize;
        GGL::InferUnit modelA(new RLGC::AdvancedObs(),obsSize,new RLGC::DefaultAction(),shared,actor,pathA,gpu);
        GGL::InferUnit modelB(new RLGC::AdvancedObs(),obsSize,new RLGC::DefaultAction(),shared,actor,pathB,gpu);
        json report;
        report["kind"]="gigalearn_head_to_head_first_goal_v1";
        report["note"]="Real RocketSim games; seeded kickoff pairs with swapped model sides; not full 5-minute matches";
        report["a"]=pathA.string();report["b"]=pathB.string();report["pairs"]=pairs;
        report["decisions_cap"]=decisions;report["seed"]=baseSeed;
        report["tick_skip"]=8;report["gpu_inference"]=gpu;
        int wins=0,losses=0,draws=0;
        int shotsA=0,shotsB=0,savesA=0,savesB=0,touchesA=0,touchesB=0,demosA=0,demosB=0;
        double ballSpeedSum=0,ballSpeedCount=0,peakSpeed=0;
        json matches=json::array();
        for(int i=0;i<pairs;i++) {
            const int seed=baseSeed+i*9973;
            for(int side=0;side<2;side++) {
                bool aBlue=side==0;
                auto result=OneMatch(env,modelA,modelB,aBlue,seed,decisions);
                int aTeam=aBlue?0:1,bTeam=1-aTeam;
                int outcome=result.goal<0?0:(result.goal==aTeam?1:-1);
                if(outcome>0)wins++;else if(outcome<0)losses++;else draws++;
                shotsA+=result.shots[aTeam];shotsB+=result.shots[bTeam];
                savesA+=result.saves[aTeam];savesB+=result.saves[bTeam];
                touchesA+=result.touches[aTeam];touchesB+=result.touches[bTeam];
                demosA+=result.demos[aTeam];demosB+=result.demos[bTeam];
                ballSpeedSum+=result.ballSpeedSum;ballSpeedCount+=result.steps;
                peakSpeed=std::max(peakSpeed,result.peakBallSpeed);
                matches.push_back({{"seed",seed},{"a_blue",aBlue},{"goal_team",result.goal},
                    {"a_outcome",outcome},{"decisions",result.steps},
                    {"a_shots",result.shots[aTeam]},{"b_shots",result.shots[bTeam]},
                    {"a_saves",result.saves[aTeam]},{"b_saves",result.saves[bTeam]}});
            }
            std::cout << "[EVAL] paired starts " << (i+1) << "/" << pairs
                      << " score A=" << wins << "-" << losses << "-" << draws << std::endl;
        }
        report["wins_a"]=wins;report["wins_b"]=losses;report["draws"]=draws;
        report["score_a"]=(wins+draws*0.5)/(2.0*pairs);
        report["a_shot_events"]=shotsA;report["b_shot_events"]=shotsB;
        report["a_save_events"]=savesA;report["b_save_events"]=savesB;
        report["a_touches"]=touchesA;report["b_touches"]=touchesB;
        report["a_demos"]=demosA;report["b_demos"]=demosB;
        report["avg_ball_speed_uu_s"]=(ballSpeedCount?ballSpeedSum/ballSpeedCount:0);
        report["max_ball_speed_uu_s"]=peakSpeed;
        report["matches"]=matches;
        if(!out.parent_path().empty())fs::create_directories(out.parent_path());
        if(fs::exists(out))throw std::runtime_error("Report already exists; refusing overwrite: "+out.string());
        std::ofstream of(out);
        if(!of)throw std::runtime_error("Cannot write output report");
        of<<report.dump(2)<<std::endl;
        std::cout<<"[EVAL] Completed. A "<<wins<<"W-"<<losses<<"L-"<<draws<<"D score="<<report["score_a"]
                 <<" Report: "<<out<<std::endl;
        return 0;
    }catch(const std::exception&e) {
        std::cerr<<"[EVAL ERROR] "<<e.what()<<std::endl;
        return 2;
    }
}
