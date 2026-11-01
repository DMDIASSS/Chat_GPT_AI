#pragma once
#include <nlohmann/json.hpp>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>

namespace SlaterFreestyle {
struct NativeSettings {
    int games=16, tickSkip=4, actionDelay=1, threads=2, simThreads=4;
    int width=768, depth=3, epochs=2, steps=32768, minibatch=2048;
    float actorLR=.0002f, criticLR=.00025f, gamma=.9975f, lambda=.95f;
    float entropy=.018f, clip=.2f, rewardClip=10, episodeSeconds=12;
    std::string device="auto", stage="contact_pop", defender="scripted_goalie", defenderAfterStage="reset_use";
    uint64_t seed=20261014, maxUpdates=0, saveEvery=10, evalEvery=10;
    uint64_t evalSeed=910000000, minStageUpdates=20;
    int evalEpisodes=16, masteryPasses=3;
    uint64_t criticWarmup=0;
    float difficulty=0, difficultyStep=.1f, masteryRate=.7f;
    bool curriculum=true, halfPrecision=false, adaptiveLR=true;
    float targetKL=.02f, minLR=.00002f, privilegedDropout=.5f, defenderStrength=.7f;
    nlohmann::json rewardSettings=nlohmann::json::object();
    explicit NativeSettings(const nlohmann::json& j) {
        if(!j.is_object()) throw std::invalid_argument("Native freestyle config must be an object");
        games=j.value("games",games); tickSkip=j.value("tick_skip",tickSkip);
        actionDelay=j.value("action_delay",actionDelay); threads=j.value("threads",threads);
        simThreads=j.value("sim_threads",simThreads); width=j.value("width",width);
        depth=j.value("depth",depth); epochs=j.value("epochs",epochs);
        steps=j.value("steps_per_update",steps); minibatch=j.value("minibatch",minibatch);
        actorLR=j.value("actor_lr",actorLR); criticLR=j.value("critic_lr",criticLR);
        gamma=j.value("gamma",gamma); lambda=j.value("lambda",lambda);
        entropy=j.value("entropy",entropy); clip=j.value("clip",clip);
        rewardClip=j.value("reward_clip",rewardClip); episodeSeconds=j.value("max_episode_seconds",episodeSeconds);
        device=j.value("device",device); stage=j.value("stage",stage);
        defender=j.value("defender",defender);defenderAfterStage=j.value("defender_after_stage",defenderAfterStage);
        defenderStrength=j.value("defender_strength",defenderStrength);
        privilegedDropout=j.value("privileged_dropout",privilegedDropout);
        seed=j.value("seed",seed); maxUpdates=j.value("max_updates",maxUpdates);
        saveEvery=j.value("save_every_updates",saveEvery); evalEvery=j.value("eval_every_updates",evalEvery);
        evalSeed=j.value("eval_seed_base",evalSeed); minStageUpdates=j.value("min_stage_updates",minStageUpdates);
        evalEpisodes=j.value("eval_episodes",evalEpisodes); masteryPasses=j.value("mastery_passes",masteryPasses);
        difficulty=j.value("difficulty",difficulty); difficultyStep=j.value("difficulty_step",difficultyStep);
        masteryRate=j.value("mastery_success_rate",masteryRate); curriculum=j.value("curriculum_enabled",curriculum);
        halfPrecision=j.value("half_precision",halfPrecision); targetKL=j.value("target_kl",targetKL);
        adaptiveLR=j.value("adaptive_lr",adaptiveLR); minLR=j.value("min_actor_lr",minLR);
        criticWarmup=j.value("critic_warmup_updates",criticWarmup);
        rewardSettings=j.value("rewards",rewardSettings);
        if(games<1||games>256||threads<1||threads>32||simThreads<1||simThreads>32||
           width<64||width>2048||depth<1||depth>6||epochs<1||epochs>8||
           steps<512||steps>1000000||minibatch<128||minibatch>steps||
           std::find(std::begin(validTicks),std::end(validTicks),tickSkip)==std::end(validTicks)||
           actionDelay<0||actionDelay>=tickSkip||saveEvery<1||evalEpisodes<2||evalEpisodes>256||
           masteryPasses<1||masteryPasses>20||minStageUpdates<1||criticWarmup>1000||
           (device!="auto"&&device!="cuda"&&device!="cpu"))
            throw std::invalid_argument("Invalid freestyle architecture/budget/device/timing setting (tick1 requires delay0)");
        for(float x:{actorLR,criticLR,gamma,lambda,entropy,clip,rewardClip,episodeSeconds,difficulty,difficultyStep,masteryRate,targetKL,minLR,privilegedDropout,defenderStrength})
            if(!std::isfinite(x)) throw std::invalid_argument("Nonfinite freestyle setting");
        if(actorLR<=0||actorLR>.01f||criticLR<=0||criticLR>.01f||gamma<=0||gamma>=1||
           lambda<=0||lambda>1||entropy<0||entropy>1||clip<=0||clip>=1||rewardClip<0||
           episodeSeconds<1||episodeSeconds>120||difficulty<0||difficulty>1||
           difficultyStep<=0||difficultyStep>1||masteryRate<=0||masteryRate>1||
           targetKL<=0||targetKL>1||minLR<=0||minLR>actorLR||privilegedDropout<0||privilegedDropout>1||
           defenderStrength<0||defenderStrength>1||(defender!="none"&&defender!="scripted_goalie"))
            throw std::invalid_argument("Invalid freestyle optimizer/curriculum setting");
    }
    static constexpr int validTicks[4]={1,2,4,8};
};
}
