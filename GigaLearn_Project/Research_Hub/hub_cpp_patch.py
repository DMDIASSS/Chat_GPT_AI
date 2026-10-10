"""Conservative idempotent C++ source patch for archived GigaLearn example.
Requires exact recognizable upstream markers. Makes sibling backups before changing any source.
Must REBUILD build_py311 after patch. No native Nexto checkpoint is touched.
"""
from pathlib import Path
import re
import shutil
import os

PROJECT=Path(__file__).resolve().parent.parent
MAIN=PROJECT/'upstream/src/ExampleMain.cpp'
LEARNER=PROJECT/'upstream/GigaLearnCPP/src/public/GigaLearnCPP/Learner.cpp'
TAG='AFK_RESEARCH_HUB_PATCH_V1'

HELPERS=r'''
// AFK_RESEARCH_HUB_PATCH_V1: experimental configs; no Nexto .pt support.
static int HubInt(const char* key, int fallback, int low, int high) {
    const char* v = std::getenv(key);
    if (!v || !*v) return fallback;
    return std::max(low, std::min(high, std::atoi(v)));
}
static float HubFloat(const char* key, float fallback, float low, float high) {
    const char* v = std::getenv(key);
    if (!v || !*v) return fallback;
    return std::max(low, std::min(high, (float)std::atof(v)));
}
static std::string HubText(const char* key, const char* fallback) {
    const char* v = std::getenv(key);
    return (v && *v) ? std::string(v) : std::string(fallback);
}

// Practice incentive ONLY: give credit for maintaining proximity to an airborne ball.
// Combined with goals and a fixed episode cap; never used alone for competitive ranking.
class HubAirControlReward : public RLGC::Reward {
public:
    float GetReward(const RLGC::Player& p, const RLGC::GameState& state, bool isFinal) override {
        if (isFinal || state.goalScored || state.ball.pos.z < 230.f) return 0.f;
        const float distance = (state.ball.pos - p.pos).Length();
        if (distance > 1000.f) return 0.f;
        return 0.003f * (1.f - distance / 1000.f);
    }
};
'''

REWARDS='''    const std::string hubMode = HubText("GL_HUB_MODE", "balanced");
    // All modes include an outcome reward; isolated labs never select a champion automatically.
    std::vector<WeightedReward> rewards = {
        { new GoalReward(), 150.f },
        { new ZeroSumReward(new VelocityBallToGoalReward(), 1.f), 2.5f },
        { new FaceBallReward(), 0.04f },
        { new VelocityPlayerToBallReward(), 0.5f },
        { new SaveBoostReward(), 0.02f },
    };
    if (hubMode == "defense") {
        rewards.push_back({new ZeroSumReward(new SaveReward(), 0.9f), 8.f});
        rewards.push_back({new ZeroSumReward(new ShotReward(), 0.9f), 1.f});
    } else if (hubMode == "shooting") {
        rewards.push_back({new ZeroSumReward(new ShotReward(), 0.9f), 5.f});
        rewards.push_back({new ZeroSumReward(new TouchAccelReward(), 0.9f), 5.f});
    } else if (hubMode == "air") {
        rewards.push_back({new HubAirControlReward(), 1.f});
        rewards.push_back({new ZeroSumReward(new TouchBallReward(), 0.9f), 0.4f});
    } else if (hubMode == "power") {
        rewards.push_back({new ZeroSumReward(new TouchAccelReward(), 0.9f), 7.f});
        rewards.push_back({new ZeroSumReward(new ShotReward(), 0.9f), 3.f});
    } else if (hubMode == "recovery") {
        rewards.push_back({new WavedashReward(), 0.5f});
        rewards.push_back({new VelocityReward(), 0.02f});
    } else if (hubMode == "balanced") {
        rewards.push_back({new ZeroSumReward(new ShotReward(), 0.9f), 0.6f});
        rewards.push_back({new ZeroSumReward(new SaveReward(), 0.9f), 0.6f});
    } else {
        throw std::runtime_error("Unsupported GL_HUB_MODE: " + hubMode);
    }
'''


def _replace_one(src,pattern,replacement,label):
    result,n=re.subn(pattern,lambda m: replacement,src,count=1,flags=re.S)
    if n!=1:raise RuntimeError('Could not safely locate '+label+'; source untouched')
    return result

def patch_main(s):
    if TAG in s:return s,False
    anchor='#include <GigaLearnCPP/Learner.h>'
    if anchor not in s:raise RuntimeError('Unsupported ExampleMain.cpp, missing include')
    s=s.replace(anchor, '#include <cstdlib>\n#include <iostream>\n#include <algorithm>\n#include <string>\n#include <stdexcept>\n'+anchor,1)
    obs_anchor='using namespace RLGC; // RLGymCPP'
    if obs_anchor not in s:raise RuntimeError('Unexpected upstream namespace block')
    s=s.replace(obs_anchor,obs_anchor+'\n'+HELPERS,1)
    s=_replace_one(s,r'std::vector<WeightedReward> rewards\s*=\s*\{.*?\n\s*\};', REWARDS,'reward declaration')
    s=_replace_one(s,r'int playersPerTeam = 1;.*?arena->AddCar\(Team::ORANGE\);\s*\}', '''int blue = HubInt("GL_HUB_BLUE", 1, 1, 3);
    int orange = HubInt("GL_HUB_ORANGE", 1, 1, 3);
    auto arena = Arena::Create(GameMode::SOCCAR);
    for (int i=0; i<blue; i++) arena->AddCar(Team::BLUE);
    for (int i=0; i<orange; i++) arena->AddCar(Team::ORANGE);''','team count')
    s=s.replace('result.stateSetter = new KickoffState();','result.stateSetter = HubText("GL_HUB_SETUP", "random") == "kickoff" ? static_cast<StateSetter*>(new KickoffState()) : static_cast<StateSetter*>(new RandomState(true, true, true));',1)
    if 'cfg.deviceType = LearnerDeviceType::GPU_CUDA;' not in s:raise RuntimeError('Original CUDA config missing')
    s=s.replace('cfg.deviceType = LearnerDeviceType::GPU_CUDA;', 'cfg.deviceType = LearnerDeviceType::AUTO; // GTX 1650 uses CUDA when available; CPU fallback')
    s=_replace_one(s,r'cfg\.numGames\s*=\s*\d+;', 'cfg.numGames = HubInt("GL_HUB_GAMES", 12, 1, 64);','parallel games')
    s=_replace_one(s,r'int tsPerItr\s*=\s*[\d\']+;', 'int tsPerItr = HubInt("GL_HUB_STEPS_PER_ITER", 4096, 512, 200000);','training iteration size')
    s=_replace_one(s,r'cfg\.ppo\.miniBatchSize\s*=\s*[\d\']+;', '''// AFK_RESEARCH_HUB_PPO_BATCH_FIX_V1: align effective PPO batch to a whole number of minibatches.
    const int hubMiniBatchSize = std::min(tsPerItr, 2048);
    tsPerItr = (tsPerItr / hubMiniBatchSize) * hubMiniBatchSize;
    cfg.ppo.tsPerItr = tsPerItr;
    cfg.ppo.batchSize = tsPerItr;
    cfg.ppo.miniBatchSize = hubMiniBatchSize;
    std::cout << "[Research Hub] PPO samples/iteration=" << tsPerItr << " minibatch=" << hubMiniBatchSize << std::endl;''','PPO minibatch size')
    s=_replace_one(s,r'cfg\.ppo\.epochs\s*=\s*\d+;', 'cfg.ppo.epochs = 1;','PPO epochs')
    s=_replace_one(s,r'cfg\.ppo\.entropyScale\s*=\s*[-+.\deEfF]+;', 'cfg.ppo.entropyScale = HubFloat("GL_HUB_ENTROPY", 0.035f, 0.f, 0.25f);','entropy')
    s=_replace_one(s,r'cfg\.ppo\.policyLR\s*=\s*[-+.\deEfF]+;', 'cfg.ppo.policyLR = HubFloat("GL_HUB_LR", 1.5e-4f, 1e-6f, 0.001f);','actor learning rate')
    s=_replace_one(s,r'cfg\.ppo\.criticLR\s*=\s*[-+.\deEfF]+;', 'cfg.ppo.criticLR = HubFloat("GL_HUB_LR", 1.5e-4f, 1e-6f, 0.001f);','critic learning rate')
    if 'cfg.sendMetrics = true;' not in s:raise RuntimeError('Unexpected metric sender declaration')
    s=s.replace('cfg.sendMetrics = true;', '''cfg.sendMetrics = false; // Offline: no W&B login or API key required
    cfg.tsPerSave = HubInt("GL_HUB_SAVE_EVERY", 50000, 5000, 20000000);
    cfg.checkpointsToKeep = -1; // Never auto-delete research checkpoints
    cfg.trainAgainstOldVersions = HubInt("GL_HUB_HISTORY", 0, 0, 1) != 0;
    cfg.trainAgainstOldChance = 0.2f;
    cfg.tsPerVersion = 100000;
    cfg.maxOldVersions = 8;
    cfg.randomSeed = HubInt("GL_HUB_SEED", 734891, 1, 2000000000);
    std::cout << "[Research Hub] mode=" << HubText("GL_HUB_MODE", "balanced")
              << " teams=" << HubInt("GL_HUB_BLUE",1,1,3) << "v" << HubInt("GL_HUB_ORANGE",1,1,3)
              << " lr=" << cfg.ppo.policyLR << " games=" << cfg.numGames << std::endl;''',1)
    if TAG not in s:raise RuntimeError('Patch sentinel missing')
    return s,True

def patch_learner(s):
    if TAG in s:return s,False
    idx=s.find('void GGL::Learner::Start()')
    if idx<0:raise RuntimeError('Missing Learner::Start; no patch')
    m=re.search(r'\n\s*if \(saveQueued\) \{',s[idx:])
    if not m:raise RuntimeError('Missing saveQueued check in Learner::Start; no patch')
    at=idx+m.start()
    # The GUI starts this process without a console. Disable console polling in headless mode.
    start_segment=s[idx:at]
    key_anchor='StartQuitKeyThread(saveQueued, keyPressThread);'
    if key_anchor not in start_segment:raise RuntimeError('Expected console key thread missing from Learner::Start')
    s=s[:idx]+start_segment.replace(key_anchor, 'if (!std::getenv("GL_HUB_HEADLESS")) StartQuitKeyThread(saveQueued, keyPressThread);\n        else saveQueued = false;')+s[at:]
    idx=s.find('void GGL::Learner::Start()')
    m=re.search(r'\n\s*if \(saveQueued\) \{',s[idx:])
    at=idx+m.start()
    insertion='''
                // AFK_RESEARCH_HUB_PATCH_V1: safe GUI pause after full PPO iteration.
                // Each process gets its own cwd and checkpoints directory.
                if (std::filesystem::exists("request_safe_stop.flag")) {
                    RG_LOG("[Research Hub] Safe stop requested: saving at PPO boundary...");
                    if (!config.checkpointFolder.empty()) Save();
                    std::filesystem::remove("request_safe_stop.flag");
                    RG_LOG("[Research Hub] Checkpoint saved; stopping.");
                    exit(0);
                }
'''
    s=s[:at]+insertion+s[at:]
    if '#include <cstdlib>' not in s:s='#include <cstdlib>\n'+s
    return s,True

def patch():
    if not MAIN.is_file() or not LEARNER.is_file():raise RuntimeError('Missing upstream source: use GL_1_GET_SOURCE first')
    src1=MAIN.read_text(encoding='utf-8-sig');src2=LEARNER.read_text(encoding='utf-8-sig')
    out1,ch1=patch_main(src1);out2,ch2=patch_learner(src2)
    for path,orig,replaced,changed in [(MAIN,src1,out1,ch1),(LEARNER,src2,out2,ch2)]:
        if changed:
            bak=path.with_name(path.name+'.research_hub_original.bak')
            if bak.exists():raise RuntimeError('Existing research patch backup: '+str(bak)+'; refusing to modify source')
            bak.write_text(orig,encoding='utf8')
            tmp=path.with_suffix(path.suffix+'.research_tmp');tmp.write_text(replaced,encoding='utf8')
            os.replace(tmp,path)
    return {'example_modified':ch1,'learner_modified':ch2,'requires_rebuild':ch1 or ch2,
            'notes':'No checkpoint changed; if previously patched files existed, backups are sibling .bak files.'}

if __name__=='__main__':print(patch())
