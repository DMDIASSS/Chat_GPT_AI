"""Deterministic, reviewable changes to the pinned public GigaLearn source.

Always apply to a fresh extraction. No fast-math, unsafe precision, actor resize,
reward clipping, or reduced PPO epochs are enabled for headline throughput.
"""
from pathlib import Path
import sys

def patch(root):
 root=Path(root)
 def change(relative,before,after,count=-1):
  p=root/relative;s=p.read_text(encoding='utf-8-sig')
  if before not in s:raise ValueError('Upstream context changed: '+relative+' / '+before[:50])
  p.write_text(s.replace(before,after,count),encoding='utf8')
 def change_start(relative,before,after):
  p=root/relative;s=p.read_text(encoding='utf8');start=s.index('void GGL::Learner::Start()')
  tail=s[start:]
  if before not in tail:raise ValueError('Start context changed: '+before[:40])
  p.write_text(s[:start]+tail.replace(before,after),encoding='utf8')
 for p in root.rglob('*'):
  if p.suffix in {'.h','.hpp','.cpp'}:
   s=p.read_text(encoding='utf-8-sig')
   p.write_text(s.replace('/OBSBuilders/','/ObsBuilders/').replace('/GameStates/','/Gamestates/').replace('/OBSBuilder.h','/ObsBuilder.h'),encoding='utf8')
 change('GigaLearnCPP/CMakeLists.txt','add_library(GigaLearnCPP SHARED ${FILES_SRC})',
  'add_library(GigaLearnCPP STATIC ${FILES_SRC})\ntarget_compile_definitions(GigaLearnCPP PUBLIC GIGAFORGE_STATIC)')
 change('GigaLearnCPP/src/public/GigaLearnCPP/Framework.h','#ifdef WITHIN_GGL',
  '#if defined(GIGAFORGE_STATIC)\n#define RG_IMEXPORT\n#elif defined(WITHIN_GGL)')
 change('GigaLearnCPP/CMakeLists.txt','find_package(PythonLibs REQUIRED)',
  'set(PYTHON_LIBRARIES ${Python_LIBRARIES})\nset(PYTHON_INCLUDE_DIRS ${Python_INCLUDE_DIRS})\nset(PYTHON_EXECUTABLE ${Python_EXECUTABLE})')
 change('GigaLearnCPP/RLGymCPP/src/RLGymCPP/CommonValues.h','#include "../Framework.h"','#include "Framework.h"')
 change('GigaLearnCPP/src/private/GigaLearnCPP/Util/Models.h','typename Model*','Model*')
 change('GigaLearnCPP/src/public/GigaLearnCPP/Util/Timer.h','high_resolution_clock','steady_clock')
 change('GigaLearnCPP/RLGymCPP/src/RLGymCPP/ThreadPool.h','_tp = new dp::thread_pool();',
  '''auto text = std::getenv("GIGAFORGE_SIM_THREADS");
            int count = text ? std::stoi(text) : int(std::min(8u,std::max(1u,std::thread::hardware_concurrency()/2)));
            if(count<1 || count>64) throw std::runtime_error("Invalid simulation thread count");
            _tp = new dp::thread_pool(count);''')
 # Pointer-hash iteration gives different arenas different car update orders
 # on Windows. Use stable car IDs for physics, boost claims and player arrays.
 arena='GigaLearnCPP/RLGymCPP/RocketSim/src/Sim/Arena/Arena.h'
 change(arena,'#include "../../BaseInc.h"','#include "../../BaseInc.h"\n#include <set>')
 change(arena,'std::unordered_set<Car*> _cars;', '''struct StableCarOrder {
        bool operator()(const Car* a,const Car* b)const{return a->id<b->id;}
    };
    using CarCollection=std::set<Car*,StableCarOrder>;
    CarCollection _cars;''')
 change(arena,'const std::unordered_set<Car*>& GetCars()', 'const CarCollection& GetCars()')
 env='GigaLearnCPP/RLGymCPP/src/RLGymCPP/EnvSet/EnvSet.cpp'
 change(env,'userInfo->arenaIdx = idx;','userInfo->arenaIdx = int(arenas.size()) - 1;')
 change(env,'g_ThreadPool.StartBatchedJobs(fnCreateArenas, config.numArenas, false);',
  'for(int i=0;i<config.numArenas;i++) fnCreateArenas(i); // Stable seeds, team roles and callback indices.')
 config='GigaLearnCPP/src/public/GigaLearnCPP/LearnerConfig.h'
 change(config,'int numGames = 300;', '''int numGames = 300;
        std::filesystem::path stopFile, reportFile;
        uint64_t maxTimesteps = 0, maxIterations = 0;
        bool fixedRollout = false;
        std::function<void(const std::vector<RLGC::GameState>&, const IList&)> prepareOpponent;
        std::function<IList()> inferOpponent;''')
 learner='GigaLearnCPP/src/public/GigaLearnCPP/Learner.cpp'
 change(learner,'StartQuitKeyThread(saveQueued, keyPressThread);','saveQueued = false; // Safe file stop; no stdin thread/data race.')
 change(learner,'std::filesystem::path saveFolder = config.checkpointFolder / std::to_string(totalTimesteps);',
  '''auto finalFolder = config.checkpointFolder / std::to_string(totalTimesteps);
    auto saveFolder = config.checkpointFolder / ("saving_" + std::to_string(totalTimesteps));
    if (std::filesystem::exists(saveFolder)) std::filesystem::remove_all(saveFolder);''')
 change(learner,'ppo->SaveTo(saveFolder);','''ppo->SaveTo(saveFolder);
    std::ofstream(saveFolder / "COMPLETE") << totalTimesteps << std::endl;
    if (std::filesystem::exists(finalFolder)) throw std::runtime_error("Checkpoint generation already exists");
    std::filesystem::rename(saveFolder, finalFolder);''')
 change(learner,'auto trajectories = std::vector<Trajectory>(numPlayers, Trajectory{});',
  'auto trajectories = std::vector<Trajectory>(numPlayers, Trajectory{});\n        std::vector<bool> previousLearning(numPlayers,true);')
 needle='int numRealPlayers = oldVersion ? newPlayerIndices.size() : envSet->state.numPlayers;'
 change(learner,needle,'''if (config.prepareOpponent) {
                newPlayerIndices.clear(); oldPlayerIndices.clear();
                int index=0;
                for(size_t arena=0;arena<envSet->state.gameStates.size();arena++) {
                    for(const auto& player:envSet->state.gameStates[arena].players) {
                        if(int(player.team)==int(arena%2)) newPlayerIndices.push_back(index);
                        else oldPlayerIndices.push_back(index);
                        index++;
                    }
                }
                tNewPlayerIndices=torch::tensor(newPlayerIndices);
                tOldPlayerIndices=torch::tensor(oldPlayerIndices);
            }
            std::vector<bool> learning(numPlayers,false);
            for(int i:newPlayerIndices) learning[i]=true;
            for(int i=0;i<numPlayers;i++) if(learning[i]!=previousLearning[i]) trajectories[i].Clear();
            previousLearning=learning;
            int numRealPlayers = (oldVersion || config.prepareOpponent) ? newPlayerIndices.size() : envSet->state.numPlayers;''')
 change_start(learner,'envSet->StepFirstHalf(true);','''if(config.prepareOpponent) config.prepareOpponent(envSet->state.gameStates,oldPlayerIndices);
                        envSet->StepFirstHalf(true);''')
 change(learner,'if (oldVersion) {','if (oldVersion || config.prepareOpponent) {')
 change(learner,'ppo->InferActions(tdOldStates, tdOldActionMasks, &tOldActions, NULL, &oldVersion->models);',
  '''if(config.inferOpponent) tOldActions=torch::tensor(config.inferOpponent());
                            else ppo->InferActions(tdOldStates, tdOldActionMasks, &tOldActions, NULL, &oldVersion->models);''')
 change(learner,'envSet->state.lastRewards[i];','envSet->state.lastRewards[arenaIdx];')
 change_start(learner,'report["Collected Timesteps"] = stepsCollected;',
  'report["Collected Timesteps"] = stepsCollected;\n                    report["Used Timesteps"] = combinedTraj.Length();')
 change(learner,'report["Overall Steps/Second"] = stepsCollected / (collectionTime + consumptionTime);',
  '''report["Overall Steps/Second"] = stepsCollected / (collectionTime + consumptionTime);
                report["Useful Samples/Second"] = report["Used Timesteps"] / (collectionTime + consumptionTime);''')
 change(learner,'ppo->Learn(experience, report, isFirstIteration);','''ppo->Learn(experience, report, isFirstIteration);
                if(ppo->config.useGuidingPolicy) {
                    RG_NO_GRAD;
                    auto probe=experience.data.states.slice(0,0,512).to(ppo->device);
                    auto mask=experience.data.actionMasks.slice(0,0,512).to(ppo->device);
                    auto q=PPOLearner::InferPolicyProbsFromModels(ppo->guidingPolicyModels,probe,mask,1,false);
                    auto p=PPOLearner::InferPolicyProbsFromModels(ppo->models,probe,mask,1,false);
                    double kl=(q*(q.clamp_min(1e-12).log()-p.clamp_min(1e-12).log())).sum(-1).mean().item<double>();
                    report["Guard Anchor KL"]=kl;
                    report["Guard Halt"]=(!std::isfinite(kl) || kl>0.08);
                }''')
 change(learner,'report["Total Iterations"] = totalIterations;','''report["Total Iterations"] = totalIterations;
                report.Finish();
                if(!config.reportFile.empty()) {
                    std::ofstream output(config.reportFile,std::ios::app);
                    output << nlohmann::json(report.data).dump() << std::endl;
                }''')
 change(learner,'if (saveQueued) {', '''if(saveQueued || report.data["Guard Halt"] ||
                   (!config.stopFile.empty() && std::filesystem::exists(config.stopFile)) ||
                   (config.maxTimesteps && totalTimesteps>=config.maxTimesteps) ||
                   (config.maxIterations && totalIterations>=config.maxIterations)) {''')
 change(learner,'exit(0);','return;')
 # Bound GPU memory even when hundreds of trajectories time out together.
 change(learner,'''// This really just should never happen
							// If this is ever actually a real problem in a legitimate use case, ping Zealan in the dead of night
							RG_ASSERT(tNextTruncStates.size(0) <= ppo->config.miniBatchSize);

							tTruncValPreds = ppo->InferCritic(tNextTruncStates.to(ppo->device, true, true)).cpu();''',
 '''tTruncValPreds=torch::zeros({tNextTruncStates.size(0)});
                            for(int64_t start=0;start<tNextTruncStates.size(0);start+=ppo->config.miniBatchSize){
                                auto end=std::min<int64_t>(start+ppo->config.miniBatchSize,tNextTruncStates.size(0));
                                tTruncValPreds.slice(0,start,end).copy_(ppo->InferCritic(tNextTruncStates.slice(0,start,end).to(ppo->device)).cpu());
                            }''')
 ppo='GigaLearnCPP/src/private/GigaLearnCPP/PPO/PPOLearner.cpp'
 change(ppo,'auto guidingLoss = (guidingProbs - probs).abs().mean();',
  'auto guidingLoss = (guidingProbs * (guidingProbs.clamp_min(1e-12).log() - probs.clamp_min(1e-12).log())).sum(-1).mean();')
 change(ppo,'guidingLoss = guidingLoss * config.guidingStrength;',
  'guidingLoss = guidingLoss * config.guidingStrength * batchSizeRatio;')
 change(ppo,'if (model->modelName == "critic")','if (std::string(model->modelName) == "critic")')
 change(ppo,'auto batchAdvantages = batch.advantages;',
  'auto batchAdvantages = batch.advantages;\n            if(batchAdvantages.numel()>1)batchAdvantages=(batchAdvantages-batchAdvantages.mean())/(batchAdvantages.std()+1e-8);')
 # Policy and critic are pure LayerNorm/MLP branches; share their one trunk
 # forward and combine losses before backward. No precision/shape changes.
 change(ppo,'torch::Tensor probs, logProbs, entropy, ratio, clipped, policyLoss, ppoLoss;',
  'auto encoded=models["shared_head"]?models["shared_head"]->Forward(obs,false):obs;\n                torch::Tensor probs, logProbs, entropy, ratio, clipped, policyLoss, ppoLoss;')
 change(ppo,'probs = InferPolicyProbsFromModels(models, obs, actionMasks, config.policyTemperature, false);',
  'probs=torch::softmax(models["policy"]->Forward(encoded,false)/config.policyTemperature-1e10f*actionMasks.to(torch::kBool).logical_not(),-1).clamp(1e-11f,1.f);')
 change(ppo,'auto vals = InferCritic(obs);','auto vals = models["critic"]->Forward(encoded,false).flatten();')
 change(ppo,'criticLoss = mseLoss(vals, targetValues) * batchSizeRatio;',
  'criticLoss = mseLoss(vals, targetValues) * batchSizeRatio * 0.5f;')
 gae='GigaLearnCPP/src/private/GigaLearnCPP/PPO/GAE.cpp'
 change(gae,'if (terminal == RLGC::TerminalType::TRUNCATED) {',
  'if (terminal == RLGC::TerminalType::NORMAL) {\n            nextValPred=0.f;\n        } else if (terminal == RLGC::TerminalType::TRUNCATED) {')
 change(gae,'nextValPred = _truncValPreds[truncCount];','nextValPred = _truncValPreds[numTruncs-1-truncCount];')
 change(ppo,'float batchSizeRatio = (stop - start) / (float)config.batchSize;',
  'float batchSizeRatio = (stop - start) / (float)batch.actions.size(0);')
 change(ppo,'fnRunMinibatch(0, config.batchSize);','fnRunMinibatch(0, int(batch.actions.size(0)));')
 change(ppo,'mbs < config.batchSize;','mbs < batch.actions.size(0);')
 change(ppo,'int stop = start + config.miniBatchSize;','int stop = std::min<int64_t>(start + config.miniBatchSize,batch.actions.size(0));')
 change(ppo,'for (int epoch = 0; epoch < config.epochs; epoch++) {',
  'bool earlyStop=false; int optimizerSteps=0;\n    for (int epoch = 0; epoch < config.epochs && !earlyStop; epoch++) {')
 change(ppo,'avgDivergence += klTensor.mean().detach().cpu().item<float>();',
  'float kl=klTensor.mean().detach().cpu().item<float>();\n                        avgDivergence += kl;\n                        if(!std::isfinite(kl) || kl>0.015f){earlyStop=true;return;}')
 change(ppo,'if (trainPolicy)\n\t\t\t\tnn::utils::clip_grad_norm_',
  'if(earlyStop){for(auto model:models)model->optim->zero_grad();break;}\n            if (trainPolicy)\n\t\t\t\tnn::utils::clip_grad_norm_')
 change(ppo,'models.StepOptims();','models.StepOptims(); optimizerSteps++;',1)
 change(ppo,'report["Policy Entropy"] = avgEntropy.Get();',
  'report["Policy Entropy"] = avgEntropy.Get();\n    report["Actor Optimizer Steps"]=trainPolicy?optimizerSteps:0;\n    report["Critic Optimizer Steps"]=trainCritic?optimizerSteps:0;\n    report["PPO Early Stop"]=earlyStop;')
 # Fixed fragments: keep all current-policy samples, bootstrap unfinished
 # paths, and never carry old-policy trajectory tails into a new PPO update.
 change_start(learner,'combinedTraj.Length() < config.ppo.tsPerItr || render',
  '(config.fixedRollout ? stepsCollected < config.ppo.tsPerItr : combinedTraj.Length() < config.ppo.tsPerItr) || render')
 change_start(learner,'!terminalType && traj.Length() >= maxEpisodeLength',
  '!terminalType && (traj.Length() >= maxEpisodeLength || (config.fixedRollout && (step+1)*numRealPlayers>=config.ppo.tsPerItr))')
 change_start(learner,'report["Used Timesteps"] = combinedTraj.Length();',
  'report["Used Timesteps"] = combinedTraj.Length();\n                    report["Data Use Fraction"]=double(combinedTraj.Length())/std::max(1,stepsCollected);\n                    if(config.fixedRollout && combinedTraj.Length()!=stepsCollected)throw std::runtime_error("Fixed rollout lost or reused samples");')
 change(ppo,'bool earlyStop=false; int optimizerSteps=0;',
  'bool earlyStop=false; int optimizerSteps=0; int64_t optimizerSamples=0;')
 change(ppo,'models.StepOptims(); optimizerSteps++;',
  'models.StepOptims(); optimizerSteps++; optimizerSamples+=batch.actions.size(0);',1)
 change(ppo,'report["PPO Early Stop"]=earlyStop;',
  'report["PPO Early Stop"]=earlyStop;\n    report["Optimizer Sample Uses"]=optimizerSamples;\n    report["Actor Sample Uses"]=trainPolicy?optimizerSamples:0;')
 print('Pinned GigaLearn patches applied:',root)
if __name__=='__main__':patch(sys.argv[1])
