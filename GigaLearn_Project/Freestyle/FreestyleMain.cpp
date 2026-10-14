#include <GigaLearnCPP/Learner.h>
#include <GigaLearnCPP/PPO/PPOLearner.h>
#include <RLGymCPP/ActionParsers/DefaultAction.h>
#include <RLGymCPP/TerminalConditions/GoalScoreCondition.h>
#include <RLGymCPP/ThreadPool.h>
#include <torch/torch.h>
#include <ATen/CPUGeneratorImpl.h>
#ifdef FREESTYLE_HAS_CUDA
#include <ATen/cuda/CUDAGeneratorImpl.h>
#endif
#include "FreestyleConfig.h"
#include "FreestyleCurriculum.h"
#include "FreestyleObs.h"
#include "FreestyleRewards.h"
#include "FreestyleActions.h"
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <vector>

using namespace GGL;
using namespace RLGC;
using namespace SlaterFreestyle;
using Json=nlohmann::json;
namespace fs=std::filesystem;
extern "C" RG_IMEXPORT void SlaterFreestyleSetReportHook(void (*fn)(GGL::Learner*, const GGL::Report&));
extern "C" RG_IMEXPORT void SlaterFreestyleSetCheckpointHook(void (*fn)(GGL::Learner*));

namespace {
constexpr int STATE_SCHEMA=1;
std::unique_ptr<NativeSettings> settings;
std::shared_ptr<CurriculumControl> curriculum=std::make_shared<CurriculumControl>();
std::shared_ptr<FreestyleTelemetry> telemetry=std::make_shared<FreestyleTelemetry>();
std::vector<std::shared_ptr<FreestyleContext>> contexts;
fs::path output,pauseMarker;
Json inputConfig;
RewardConfig rewardConfig;
uint64_t stageStartedUpdate=0,evaluations=0;
int masteryPassCount=0;
float currentActorLR=0;
std::map<std::string,double> lastTelemetry;
volatile std::sig_atomic_t signalPause=0;

void SignalPause(int) { signalPause=1; }
void SetEnv(const char* name,const std::string& value) {
#ifdef _WIN32
    _putenv_s(name,value.c_str());
#else
    setenv(name,value.c_str(),1);
#endif
}
Json ReadJson(const fs::path& path) {
    std::ifstream file(path);
    if(!file) throw std::runtime_error("Cannot read "+path.string());
    Json result;file>>result;return result;
}
void AtomicJson(const fs::path& path,const Json& value) {
    const fs::path tmp=path.string()+".tmp";
    { std::ofstream file(tmp,std::ios::trunc);
      if(!file) throw std::runtime_error("Cannot write "+tmp.string());
      file<<value.dump(2)<<'\n';file.flush();
      if(!file) throw std::runtime_error("Failed to flush "+tmp.string()); }
#ifdef _WIN32
    // A completed old manifest remains authoritative until its replacement is
    // ready. remove+rename is needed because Windows rename won't replace.
    if(fs::exists(path)) fs::remove(path);
#endif
    fs::rename(tmp,path);
}
void AppendEvent(const Json& event,const char* prefix) {
    {std::ofstream file(output/"events.jsonl",std::ios::app);
     if(!file) throw std::runtime_error("Cannot append freestyle telemetry");
     file<<event.dump()<<'\n';file.flush();}
    std::cout<<prefix<<' '<<event.dump()<<std::endl;
}
Json State(Learner* learner) {
    Json rng=Json::array();
    for(const auto& context:contexts) {std::ostringstream stream;stream<<context->rng;rng.push_back(stream.str());}
    return {{"schema",STATE_SCHEMA},{"update",learner->totalIterations},{"timesteps",learner->totalTimesteps},
            {"stage",StageName(Stage(curriculum->stage.load()))},{"difficulty",curriculum->difficulty.load()},
            {"stage_started_update",stageStartedUpdate},{"mastery_passes",masteryPassCount},
            {"evaluations",evaluations},{"actor_lr",currentActorLR},{"environment_rng",rng},
            {"source_sha",FREESTYLE_SOURCE_SHA},{"initialization","RANDOM_FROM_SCRATCH"},
            {"episode_resume","new episodes; model, optimizers, normalization, curriculum and RNG retained"}};
}
void CheckpointHook(Learner* learner) {
    fs::path folder=learner->config.checkpointFolder/std::to_string(learner->totalTimesteps);
    for(const char* name:{"POLICY.lt","POLICY_OPTIM.lt","CRITIC.lt","CRITIC_OPTIM.lt","RUNNING_STATS.json"})
        if(!fs::is_regular_file(folder/name)||fs::file_size(folder/name)==0)
            throw std::runtime_error("Incomplete freestyle checkpoint: "+(folder/name).string());
    torch::save(at::detail::getDefaultCPUGenerator().get_state(),(folder/"CPU_RNG.lt").string());
#ifdef FREESTYLE_HAS_CUDA
    if(learner->ppo->device.is_cuda())
        torch::save(at::cuda::detail::getDefaultCUDAGenerator(learner->ppo->device.index()).get_state(),(folder/"CUDA_RNG.lt").string());
#endif
    AtomicJson(folder/"FREESTYLE_STATE.json",State(learner));
    Json complete={{"schema",STATE_SCHEMA},{"update",learner->totalIterations},{"timesteps",learner->totalTimesteps},
                   {"source_sha",FREESTYLE_SOURCE_SHA},{"state_file","FREESTYLE_STATE.json"}};
    AtomicJson(folder/"FREESTYLE_COMPLETE.json",complete);
    Json latest=complete;latest["checkpoint"]=folder.string();
    AtomicJson(output/"latest.json",latest);
    AtomicJson(output/"curriculum.json",State(learner));
}
bool DefenderActive(const std::shared_ptr<FreestyleContext>& context) {
    return settings->defender=="scripted_goalie"&&int(context->stage)>=int(ParseStage(settings->defenderAfterStage));
}
void ApplyGoalie(const std::shared_ptr<FreestyleContext>& context,Arena* arena) {
    if(settings->defender=="none") return;
    auto ball=arena->ball->GetState();
    for(auto* car:arena->GetCars()) if(car->id!=context->learnerId) {
        auto state=car->GetState();
        if(!DefenderActive(context)) {
            state.isDemoed=true;state.demoRespawnTimer=999;state.vel={0,0,0};
            car->SetState(state);car->controls={};continue;
        }
        // A deliberately simple, labeled scripted defender. It intercepts the
        // projected ball along its goal line and drives into nearby shots.
        const float goalSign=car->team==Team::ORANGE?1.f:-1.f;
        const float toward=goalSign*ball.vel.y;
        const float arrival=toward>100?Clip((goalSign*4700-goalSign*ball.pos.y)/toward,0,.9f):.3f;
        const float targetX=Clip(ball.pos.x+ball.vel.x*arrival,-950,950);
        Vec target{targetX,goalSign*4550,17};
        if((ball.pos-state.pos).Length()<1100&&ball.pos.z<450) target={ball.pos.x,ball.pos.y,17};
        Vec direction=Unit(target-state.pos);float angle=std::atan2(state.rotMat.right.Dot(direction),state.rotMat.forward.Dot(direction));
        CarControls controls{};controls.steer=Clip(angle*3,-1,1);
        const float distance=(target-state.pos).Length();
        controls.throttle=distance>75?settings->defenderStrength:0;
        if(state.rotMat.forward.Dot(direction)<-.25f) controls.throttle=-settings->defenderStrength;
        controls.boost=distance>1300&&std::abs(angle)<.15f&&settings->defenderStrength>.7f;
        controls.jump=(ball.pos-state.pos).Length()<400&&ball.pos.z>130&&ball.pos.z<450;
        car->controls=controls;
    }
}
class FreestyleSetter : public FreestyleStateSetter {
    std::shared_ptr<FreestyleContext> context_;
public:
    explicit FreestyleSetter(std::shared_ptr<FreestyleContext> context):FreestyleStateSetter(context),context_(std::move(context)){}
    void ResetArena(Arena* arena) override {
        FreestyleStateSetter::ResetArena(arena);
        for(auto* car:arena->GetCars()) if(car->id!=context_->learnerId) {
            auto state=car->GetState();const float sign=car->team==Team::ORANGE?1.f:-1.f;
            state.pos={context_->Rand(-650,650),sign*4600,17};state.vel={0,0,0};
            state.rotMat=Angle(-sign*1.5707963f,0,0).ToRotMat();state.boost=60;
            state.isDemoed=!DefenderActive(context_);state.demoRespawnTimer=state.isDemoed?999:0;
            car->SetState(state);
        }
    }
};
class FreestyleAction : public FreestyleControls {
    std::shared_ptr<FreestyleContext> context_;
public:
    explicit FreestyleAction(std::shared_ptr<FreestyleContext> context):context_(std::move(context)){}
    void ApplyPhysicsControls(Arena* arena) override {FreestyleObservePhysics(context_,arena);ApplyGoalie(context_,arena);}
};
EnvCreateResult CreateEnv(int index) {
    auto context=std::make_shared<FreestyleContext>(curriculum,telemetry,settings->seed+uint64_t(index)*100003);
    contexts.at(index)=context;
    EnvCreateResult result{};result.arena=Arena::Create(GameMode::SOCCAR);
    context->learnerId=result.arena->AddCar(Team::BLUE)->id;
    if(settings->defender!="none") result.arena->AddCar(Team::ORANGE);
    result.obsBuilder=new FreestyleObs(context);result.actionParser=new FreestyleAction(context);
    result.stateSetter=new FreestyleSetter(context);
    result.terminalConditions={new GoalScoreCondition(),new FreestyleDeadline(context)};
    result.rewards={{new FreestyleReward(context,rewardConfig),1.f}};
    return result;
}
struct EvaluationWorld {
    std::unique_ptr<Arena> arena;
    std::shared_ptr<FreestyleContext> context;
    std::unique_ptr<FreestyleSetter> setter;
    std::unique_ptr<FreestyleObs> obs;
    std::unique_ptr<FreestyleReward> reward;
    std::unique_ptr<FreestyleAction> action;
    std::unique_ptr<FreestyleDeadline> deadline;
    GameState state,previous;
    bool done=false,success=false;
};
const Player& EvaluationLearner(const EvaluationWorld& world) {
    for(const auto& player:world.state.players)
        if(player.carId==world.context->learnerId) return player;
    throw std::runtime_error("Evaluation learner ID missing from game state");
}
Car* EvaluationLearnerCar(const EvaluationWorld& world) {
    for(auto* car:world.arena->GetCars())
        if(car->id==world.context->learnerId) return car;
    throw std::runtime_error("Evaluation learner ID missing from arena");
}
Json Evaluate(Learner* learner) {
    torch::NoGradGuard noGrad;
    auto evalControl=std::make_shared<CurriculumControl>();
    evalControl->stage=curriculum->stage.load();evalControl->difficulty=curriculum->difficulty.load();
    evalControl->episodeSeconds=settings->episodeSeconds;evalControl->evaluation=true;
    evalControl->privilegedDropout=settings->privilegedDropout;
    auto evalTelemetry=std::make_shared<FreestyleTelemetry>();
    std::vector<std::unique_ptr<EvaluationWorld>> worlds;
    const uint64_t seed=settings->evalSeed+evaluations*100003+uint64_t(evalControl->stage.load())*100000007;
    for(int i=0;i<settings->evalEpisodes;i++) {
        auto world=std::make_unique<EvaluationWorld>();
        world->arena.reset(Arena::Create(GameMode::SOCCAR));auto* learnerCar=world->arena->AddCar(Team::BLUE);
        if(settings->defender!="none")world->arena->AddCar(Team::ORANGE);
        world->context=std::make_shared<FreestyleContext>(evalControl,evalTelemetry,seed+uint64_t(i)*15485863);
        world->context->learnerId=learnerCar->id;
        world->setter=std::make_unique<FreestyleSetter>(world->context);
        world->obs=std::make_unique<FreestyleObs>(world->context);
        world->reward=std::make_unique<FreestyleReward>(world->context,rewardConfig);
        world->action=std::make_unique<FreestyleAction>(world->context);
        world->deadline=std::make_unique<FreestyleDeadline>(world->context);
        world->setter->ResetArena(world->arena.get());world->state=GameState(world->arena.get());
        world->obs->Reset(world->state);world->reward->Reset(world->state);world->deadline->Reset(world->state);
        worlds.push_back(std::move(world));
    }
    const int limit=int(std::ceil(settings->episodeSeconds*120/settings->tickSkip))+1;
    int completed=0,success=0;
    for(int step=0;step<limit&&completed<int(worlds.size());step++) {
        if(signalPause||(!pauseMarker.empty()&&fs::exists(pauseMarker))) break;
        std::vector<float> observations;std::vector<uint8_t> masks;
        for(auto& world:worlds) {
            auto observation=world->obs->BuildObs(EvaluationLearner(*world),world->state);
            if(int(observation.size())!=learner->obsSize) throw std::runtime_error("Evaluation observation shape changed");
            observations.insert(observations.end(),observation.begin(),observation.end());
            auto mask=world->action->GetActionMask(EvaluationLearner(*world),world->state);
            masks.insert(masks.end(),mask.begin(),mask.end());
        }
        auto states=torch::tensor(observations).reshape({int64_t(worlds.size()),learner->obsSize}).to(learner->ppo->device);
        auto actionMasks=torch::tensor(masks).reshape({int64_t(worlds.size()),learner->numActions}).to(learner->ppo->device);
        torch::Tensor actions;
        PPOLearner::InferActionsFromModels(learner->ppo->models,states,actionMasks,true,
            learner->ppo->config.policyTemperature,false,&actions,nullptr);
        auto chosen=actions.cpu().contiguous();
        for(size_t i=0;i<worlds.size();i++) {
            auto& world=*worlds[i];if(world.done) continue;
            const Action action=world.action->ParseAction(chosen[i].item<int>(),EvaluationLearner(world),world.state);
            auto* car=EvaluationLearnerCar(world);
            world.previous=world.state;world.previous.prev=nullptr;world.state.ResetBeforeStep();
            for(int tick=0;tick<settings->tickSkip;tick++) {
                if(tick==settings->actionDelay) car->controls=static_cast<CarControls>(action);
                world.action->ApplyPhysicsControls(world.arena.get());world.arena->Step(1);
            }
            std::vector<Action> applied;for(auto* appliedCar:world.arena->GetCars())applied.emplace_back(appliedCar->controls);
            world.state.UpdateFromArena(world.arena.get(),applied,&world.previous);
            const bool final=world.state.goalScored||world.deadline->IsTerminal(world.state);
            world.reward->PreStep(world.state);world.reward->GetReward(EvaluationLearner(world),world.state,final);
            if(final) {
                world.success=world.reward->IsSuccess(EvaluationLearner(world).carId);
                world.reward->FinishEpisode();world.done=true;completed++;success+=world.success;
            }
        }
    }
    ++evaluations;
    return {{"stage",StageName(Stage(evalControl->stage.load()))},{"difficulty",evalControl->difficulty.load()},
            {"evaluation",evaluations},{"seed_base",seed},{"episodes",completed},{"requested_episodes",settings->evalEpisodes},
            {"successes",success},{"success_rate",completed?double(success)/completed:0},
            {"complete",completed==settings->evalEpisodes},{"deterministic",true},{"telemetry",evalTelemetry->Snapshot()},
            {"defender",int(evalControl->stage.load())>=int(ParseStage(settings->defenderAfterStage))?settings->defender:"none"},
            {"scope","synthetic drill objective; proxy stages do not certify the named trick"}};
}
Json NumericReport(const Report& report) {
    Json metrics=Json::object();
    for(const auto& item:report.data) if(std::isfinite(item.second)) metrics[item.first]=item.second;
    return metrics;
}
void ReportHook(Learner* learner,const Report& report) {
    const Stage trainedStage=Stage(curriculum->stage.load());
    Json metrics=NumericReport(report);
    auto values=telemetry->Snapshot();Json components=Json::object(),events=Json::object();
    for(const auto& item:values) {
        double delta=item.second-lastTelemetry[item.first];
        if(item.first.rfind("raw_sum/",0)==0||item.first.rfind("weighted_sum/",0)==0) components[item.first]=delta;
        else events[item.first]=delta;
    }
    lastTelemetry=values;
    // LR adapts only to actual sampled policy drift, not teacher agreement.
    if(settings->adaptiveLR&&report.Has("Post-update PPO KL")) {
        const double kl=report["Post-update PPO KL"];
        if(std::isfinite(kl)&&kl>settings->targetKL*1.5) currentActorLR=std::max(settings->minLR,currentActorLR*.7f);
        else if(std::isfinite(kl)&&kl<settings->targetKL*.35) currentActorLR=std::min(settings->actorLR,currentActorLR*1.02f);
        learner->ppo->SetLearningRates(currentActorLR,settings->criticLR);
    }
    Json evaluation=nullptr;
    if(settings->evalEvery&&learner->totalIterations%settings->evalEvery==0) {
        evaluation=Evaluate(learner);
        if(evaluation["complete"].get<bool>()&&settings->curriculum&&
           learner->totalIterations-stageStartedUpdate>=settings->minStageUpdates) {
            if(evaluation["success_rate"].get<double>()>=settings->masteryRate) masteryPassCount++;
            else masteryPassCount=0;
            if(masteryPassCount>=settings->masteryPasses) {
                masteryPassCount=0;
                float difficulty=curriculum->difficulty.load();
                if(difficulty<.999f) curriculum->difficulty=std::min(1.f,difficulty+settings->difficultyStep);
                else if(curriculum->stage.load()+1<STAGE_COUNT) {
                    curriculum->stage=curriculum->stage.load()+1;curriculum->difficulty=0;
                    stageStartedUpdate=learner->totalIterations;
                }
            }
        }
    }
    auto weightContext=std::make_shared<FreestyleContext>();weightContext->stage=trainedStage;
    metrics["weights"]=FreestyleReward(weightContext,rewardConfig).ActiveWeights();
    metrics["reward_components"]=components;metrics["outcomes"]=events;
    metrics["training/learner_rows_per_step"]=settings->games;
    metrics["training/scripted_defender_rows_excluded"]=settings->defender=="none"?0:settings->games;
    metrics["learning_rate/actor"]=currentActorLR;metrics["learning_rate/critic"]=settings->criticLR;
    metrics["curriculum/difficulty"]=curriculum->difficulty.load();metrics["curriculum/mastery_passes"]=masteryPassCount;
    Json event={{"type","update"},{"schema",STATE_SCHEMA},{"update",learner->totalIterations},
                {"timesteps",learner->totalTimesteps},{"stage",StageName(trainedStage)},
                {"next_stage",StageName(Stage(curriculum->stage.load()))},{"metrics",metrics},
                {"evaluation",evaluation},{"initialization","RANDOM_FROM_SCRATCH"}};
    AppendEvent(event,"FREESTYLE_UPDATE");
    if(learner->totalIterations%settings->saveEvery==0) learner->Save();
}
fs::path LatestComplete() {
    fs::path best;uint64_t highest=0;bool found=false;
    fs::path folder=output/"checkpoints";
    if(!fs::exists(folder)) return {};
    for(const auto& entry:fs::directory_iterator(folder)) {
        std::string name=entry.path().filename().string();
        if(!entry.is_directory()||name.empty()||name.find_first_not_of("0123456789")!=std::string::npos||
           !fs::is_regular_file(entry.path()/"FREESTYLE_COMPLETE.json")) continue;
        uint64_t step=std::stoull(name);
        if(!found||step>highest){highest=step;best=entry.path();found=true;}
    }
    return best;
}
void RestoreState(Learner* learner,const fs::path& folder) {
    Json saved=ReadJson(folder/"FREESTYLE_STATE.json");
    if(saved.value("schema",-1)!=STATE_SCHEMA||saved.value("source_sha","")!=FREESTYLE_SOURCE_SHA||saved.value("initialization","")!="RANDOM_FROM_SCRATCH"||
       saved.value("update",uint64_t(-1))!=learner->totalIterations||
       saved.value("timesteps",uint64_t(-1))!=learner->totalTimesteps)
        throw std::runtime_error("Freestyle checkpoint/curriculum state mismatch; original Slater actors cannot be resumed here");
    curriculum->stage=int(ParseStage(saved.at("stage")));curriculum->difficulty=saved.at("difficulty");
    stageStartedUpdate=saved.at("stage_started_update");masteryPassCount=saved.at("mastery_passes");
    evaluations=saved.at("evaluations");currentActorLR=saved.at("actor_lr");
    const auto& rng=saved.at("environment_rng");
    if(rng.size()!=contexts.size()) throw std::runtime_error("Environment count differs from freestyle checkpoint");
    for(size_t i=0;i<contexts.size();i++) {std::istringstream stream(rng[i].get<std::string>());stream>>contexts[i]->rng;
        if(!stream) throw std::runtime_error("Invalid saved environment RNG");}
    torch::Tensor cpuRng;torch::load(cpuRng,(folder/"CPU_RNG.lt").string());
    auto cpuGenerator=at::detail::getDefaultCPUGenerator();cpuGenerator.set_state(cpuRng);
#ifdef FREESTYLE_HAS_CUDA
    if(learner->ppo->device.is_cuda()) {torch::Tensor cudaRng;torch::load(cudaRng,(folder/"CUDA_RNG.lt").string());
        auto cudaGenerator=at::cuda::detail::getDefaultCUDAGenerator(learner->ppo->device.index());cudaGenerator.set_state(cudaRng);}
#endif
    learner->ppo->SetLearningRates(currentActorLR,settings->criticLR);
    // Already-running physical episodes aren't serialized. Restart them using
    // saved generator streams instead of pretending to continue their history.
    for(size_t i=0;i<learner->envSet->arenas.size();i++) learner->envSet->ResetArena(i);
    lastTelemetry=telemetry->Snapshot();
}
}

int main(int argc,char** argv) {
    try {
        fs::path configFile,meshes;bool resume=false;std::string mode="train";
        for(int i=1;i<argc;i++) {
            std::string argument=argv[i];
            if(argument=="--resume") {resume=true;continue;}
            if(i+1==argc) throw std::invalid_argument("Missing argument for "+argument);
            std::string value=argv[++i];
            if(argument=="--config") configFile=value;else if(argument=="--out") output=value;
            else if(argument=="--meshes") meshes=value;else if(argument=="--pause") pauseMarker=value;
            else if(argument=="--mode") mode=value;else throw std::invalid_argument("Unknown argument "+argument);
        }
        if(configFile.empty()||output.empty()||meshes.empty()||(mode!="train"&&mode!="evaluate"))
            throw std::invalid_argument("Provide --config --out --meshes [--pause] [--resume] [--mode train|evaluate]");
        inputConfig=ReadJson(configFile);settings=std::make_unique<NativeSettings>(inputConfig);
        if(!settings->rewardSettings.is_object()) throw std::invalid_argument("rewards must be an object");
        if(settings->rewardSettings.contains("weights")) {
            auto weights=settings->rewardSettings.at("weights").get<std::map<std::string,float>>();
            for(const auto& item:weights) {
                if(!rewardConfig.weights.count(item.first)) throw std::invalid_argument("Unknown reward component "+item.first);
                rewardConfig.weights[item.first]=item.second;
            }
        }
        rewardConfig.maxEpisodePositive=settings->rewardSettings.value("max_episode_positive",rewardConfig.maxEpisodePositive);
        rewardConfig.touchSpacing=settings->rewardSettings.value("touch_spacing",rewardConfig.touchSpacing);
        rewardConfig.carryTouchDeadline=settings->rewardSettings.value("carry_touch_deadline",rewardConfig.carryTouchDeadline);
        rewardConfig.resetUseDeadline=settings->rewardSettings.value("reset_use_deadline",rewardConfig.resetUseDeadline);
        rewardConfig.flipTouchDeadline=settings->rewardSettings.value("flip_touch_deadline",rewardConfig.flipTouchDeadline);
        rewardConfig.finishDeadline=settings->rewardSettings.value("finish_deadline",rewardConfig.finishDeadline);
        rewardConfig.Validate();
        currentActorLR=settings->actorLR;curriculum->stage=int(ParseStage(settings->stage));
        curriculum->difficulty=settings->difficulty;curriculum->episodeSeconds=settings->episodeSeconds;
        curriculum->privilegedDropout=settings->privilegedDropout;ParseStage(settings->defenderAfterStage);
        fs::create_directories(output/"checkpoints");contexts.resize(settings->games);
        fs::path previous=LatestComplete();
        if(!resume&&!previous.empty()) throw std::invalid_argument("Existing freestyle run: use --resume or a fresh output folder");
        if(resume&&previous.empty()) throw std::invalid_argument("No complete freestyle checkpoint to resume");
        if(mode=="evaluate"&&!resume) throw std::invalid_argument("Evaluation requires --resume and a complete checkpoint");
        SetEnv("SLATER_GL_NO_KEY_THREAD","1");
        SetEnv("SLATER_GL_STOP_ITERATION",std::to_string(settings->maxUpdates?settings->maxUpdates:std::numeric_limits<uint64_t>::max()));
        SetEnv("SLATER_GL_FIXED_FROZEN_TEAM","-1");
        if(!pauseMarker.empty()) SetEnv("SLATER_GL_PAUSE_FILE",pauseMarker.string());
        torch::set_num_threads(settings->threads);torch::set_num_interop_threads(1);
        delete RLGC::g_ThreadPool._tp;RLGC::g_ThreadPool._tp=new dp::thread_pool<>(settings->simThreads);
        RocketSim::Init(meshes);
        LearnerConfig config{};config.numGames=settings->games;config.tickSkip=settings->tickSkip;
        config.actionDelay=settings->actionDelay;config.randomSeed=settings->seed;
        config.deviceType=settings->device=="cpu"?LearnerDeviceType::CPU:
            settings->device=="cuda"?LearnerDeviceType::GPU_CUDA:LearnerDeviceType::AUTO;
        config.checkpointFolder=output/"checkpoints";config.checkpointsToKeep=-1;
        // Explicit full-state saves are made by ReportHook after curriculum and
        // telemetry are updated. Upstream also saves on finite finish/pause.
        config.tsPerSave=std::numeric_limits<int64_t>::max();
        config.sendMetrics=false;config.renderMode=false;config.addRewardsToMetrics=false;
        config.savePolicyVersions=false;config.trainAgainstOldVersions=false;
        config.standardizeObs=false;config.standardizeReturns=true;
        config.ppo.tsPerItr=settings->steps;config.ppo.batchSize=settings->steps;
        config.ppo.miniBatchSize=settings->minibatch;config.ppo.epochs=settings->epochs;
        config.ppo.policyLR=settings->actorLR;config.ppo.criticLR=settings->criticLR;
        config.ppo.entropyScale=settings->entropy;config.ppo.clipRange=settings->clip;
        config.ppo.gaeGamma=settings->gamma;config.ppo.gaeLambda=settings->lambda;
        config.ppo.rewardClipRange=settings->rewardClip;config.ppo.maxEpisodeDuration=settings->episodeSeconds;
        config.ppo.useHalfPrecision=settings->halfPrecision;config.ppo.useGuidingPolicy=false;
        config.ppo.sharedHead.layerSizes={};
        config.ppo.policy.layerSizes=std::vector<int>(settings->depth,settings->width);
        config.ppo.critic.layerSizes=config.ppo.policy.layerSizes;
        SlaterFreestyleSetReportHook(ReportHook);SlaterFreestyleSetCheckpointHook(CheckpointHook);
        std::unique_ptr<Learner> learner(new Learner(CreateEnv,config,
            [](Learner*,const std::vector<GameState>&,Report&){
                if(signalPause&&!pauseMarker.empty()&&!fs::exists(pauseMarker)) {std::ofstream marker(pauseMarker);marker<<"signal\n";}
            }));
        if(resume) RestoreState(learner.get(),previous);
        else {stageStartedUpdate=0;learner->Save();}
        std::signal(SIGINT,SignalPause);std::signal(SIGTERM,SignalPause);
        Json begin={{"initialization","RANDOM_FROM_SCRATCH"},{"teacher",nullptr},{"device",learner->ppo->device.str()},
                    {"observation_size",learner->obsSize},{"observation_schema",FreestyleObs::SCHEMA},{"actions",learner->numActions},{"action_schema",FreestyleControls::SCHEMA},{"width",settings->width},
                    {"depth",settings->depth},{"tick_skip",settings->tickSkip},{"update",learner->totalIterations},
                    {"source_sha",FREESTYLE_SOURCE_SHA},{"mode",mode},{"defender",settings->defender},
                    {"defender_after_stage",settings->defenderAfterStage},{"learner_rows",settings->games},
                    {"scripted_defenders_excluded_from_ppo",settings->defender!="none"}};
        std::cout<<"FREESTYLE_BEGIN "<<begin.dump()<<std::endl;
        if(mode=="evaluate") {
            Json evaluation=Evaluate(learner.get());AtomicJson(output/"evaluation.json",evaluation);
            std::cout<<"FREESTYLE_EVALUATION "<<evaluation.dump()<<std::endl;
        } else learner->Start();
        const bool paused=signalPause||(!pauseMarker.empty()&&fs::exists(pauseMarker));
        Json result={{"status",paused?"PAUSED":"COMPLETE"},{"total_updates",learner->totalIterations},{"updates",learner->totalIterations},
                     {"timesteps",learner->totalTimesteps},{"stage",StageName(Stage(curriculum->stage.load()))},
                     {"difficulty",curriculum->difficulty.load()},{"checkpoint",LatestComplete().string()}};
        AtomicJson(output/"status.json",result);std::cout<<"FREESTYLE_COMPLETE "<<result.dump()<<std::endl;
        SlaterFreestyleSetReportHook(nullptr);SlaterFreestyleSetCheckpointHook(nullptr);
        return 0;
    } catch(const std::exception& error) {
        std::cerr<<"FREESTYLE_ERROR "<<error.what()<<std::endl;return 1;
    }
}
