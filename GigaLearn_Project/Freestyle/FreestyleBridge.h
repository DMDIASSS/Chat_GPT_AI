#pragma once
#include <GigaLearnCPP/Learner.h>
namespace at { class Tensor; }

#ifdef _WIN32
#define FREESTYLE_DLL_API RG_IMEXPORT
#elif defined(__GNUC__)
#define FREESTYLE_DLL_API __attribute__((visibility("default")))
#else
#define FREESTYLE_DLL_API
#endif

// Only these entry points cross the DLL boundary. PPOLearner is an upstream
// internal class whose methods are not exported by the Windows GigaLearn DLL.
extern "C" {
FREESTYLE_DLL_API void SlaterFreestyleSetReportHook(void (*fn)(GGL::Learner*, const GGL::Report&));
FREESTYLE_DLL_API void SlaterFreestyleSetCheckpointHook(void (*fn)(GGL::Learner*));
FREESTYLE_DLL_API void SlaterFreestyleReportHook(GGL::Learner*, const GGL::Report&);
FREESTYLE_DLL_API void SlaterFreestyleCheckpointHook(GGL::Learner*);
FREESTYLE_DLL_API void SlaterFreestyleSetLearningRates(GGL::Learner*, float actor, float critic);
FREESTYLE_DLL_API void SlaterFreestyleInfer(GGL::Learner*, const at::Tensor& observations,
                                          const at::Tensor& masks, at::Tensor* actions);
}
#undef FREESTYLE_DLL_API
