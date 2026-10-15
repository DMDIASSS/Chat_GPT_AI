#include "FreestyleBridge.h"
#include <GigaLearnCPP/PPO/PPOLearner.h>

namespace {
void (*reportCallback)(GGL::Learner*, const GGL::Report&) = nullptr;
void (*saveCallback)(GGL::Learner*) = nullptr;
}

extern "C" void SlaterFreestyleSetReportHook(void (*fn)(GGL::Learner*, const GGL::Report&)) {
    reportCallback=fn;
}
extern "C" void SlaterFreestyleSetCheckpointHook(void (*fn)(GGL::Learner*)) {
    saveCallback=fn;
}
extern "C" void SlaterFreestyleReportHook(GGL::Learner* learner, const GGL::Report& report) {
    if(reportCallback) reportCallback(learner,report);
}
extern "C" void SlaterFreestyleCheckpointHook(GGL::Learner* learner) {
    if(saveCallback) saveCallback(learner);
}
extern "C" void SlaterFreestyleSetLearningRates(GGL::Learner* learner, float actor, float critic) {
    learner->ppo->SetLearningRates(actor,critic);
}
extern "C" void SlaterFreestyleInfer(GGL::Learner* learner, const at::Tensor& observations,
                                     const at::Tensor& masks, at::Tensor* actions) {
    GGL::PPOLearner::InferActionsFromModels(learner->ppo->models,observations,masks,true,
        learner->ppo->config.policyTemperature,false,actions,nullptr);
}
extern "C" void SlaterFreestyleLoadPolicy(GGL::Learner* learner, const char* folder) {
    // Keep architecture validation inside the upstream loader and the DLL.
    // A new reward objective needs a fresh critic/optimizer/return normalizer.
    learner->ppo->models["policy"]->Load(std::filesystem::u8path(folder),false,false);
}
