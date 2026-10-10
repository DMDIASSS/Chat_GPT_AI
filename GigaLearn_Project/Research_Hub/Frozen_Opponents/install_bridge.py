"""Strict, backup-first in-place source integration for user-provided Research Hub sources."""
from pathlib import Path
import shutil
import sys

MARK = 'FROZEN_NEXTO_BRIDGE_V1'
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # GigaLearn_Project
LEARNER = ROOT / 'upstream/GigaLearnCPP/src/public/GigaLearnCPP/Learner.cpp'
HEADER = ROOT / 'upstream/GigaLearnCPP/src/public/GigaLearnCPP/Util/FrozenNextoBridge.h'


def exactly_once(text, old, new, label):
    if text.count(old) != 1:
        raise ValueError(f'{label}: expected one exact source anchor; found {text.count(old)}. Stopping safely.')
    return text.replace(old, new, 1)


def patch(source):
    if MARK in source:
        return source
    if 'AFK_RESEARCH_HUB_PATCH_V1' not in source:
        raise ValueError('This source is not the current Research Hub Learner.cpp; patch refused')
    s = source
    s = exactly_once(s, '#include "Learner.h"', '#include "Learner.h"\n#include "Util/FrozenNextoBridge.h" // '+MARK, 'include')
    anchor = '''\t\tint maxEpisodeLength = (int)(config.ppo.maxEpisodeDuration * (120.f / config.tickSkip));'''
    s = exactly_once(s, anchor, anchor + '''

        // FROZEN_NEXTO_BRIDGE_V1: One frozen native Nexto actor on opponent team.
        std::unique_ptr<GGL::FrozenNextoBridge> frozenBridge;
        if (const char* enabled = std::getenv("GL_FROZEN_BRIDGE")) {
            if (std::string(enabled) == "1") {
                if (config.trainAgainstOldVersions)
                    RG_ERR_CLOSE("[FrozenNexto] disable historical self-play while using frozen teachers");
                for (const auto& game : envSet->state.gameStates)
                    if (game.players.size() != 2)
                        RG_ERR_CLOSE("[FrozenNexto] only one blue versus one orange is supported");
                frozenBridge = std::make_unique<GGL::FrozenNextoBridge>(*envSet);
                RG_LOG("[FrozenNexto] FROZEN teacher inference ACTIVE (student gradient only)");
            }
        }
        const char* rotationEnv = std::getenv("GL_FROZEN_STEPS_PER_OPPONENT");
        const int64_t rotationSteps = rotationEnv ? std::stoll(rotationEnv) : 65536;
        if (frozenBridge && rotationSteps < 1)
            RG_ERR_CLOSE("[FrozenNexto] rotation step count must be positive");
        const char* stopEnv = std::getenv("GL_FROZEN_STOP_AFTER_STEPS");
        const int64_t frozenStopAt = stopEnv ? std::stoll(stopEnv) : 0;
''' , 'setup')
    anchor = '''\t\t\tint numRealPlayers = oldVersion ? newPlayerIndices.size() : envSet->state.numPlayers;'''
    insertion = '''
            // FROZEN_NEXTO_BRIDGE_V1: reserve one car per arena for read-only teacher.
            RocketSim::Team frozenTeam = RocketSim::Team::ORANGE;
            if (frozenBridge) {
                static const char* names[] = {"nexto", "cycle9", "wavedash"};
                const int teacherSlot = static_cast<int>((totalTimesteps / rotationSteps) % 3);
                frozenBridge->Select(names[teacherSlot]);
                frozenTeam = (totalIterations % 2 == 0) ? RocketSim::Team::ORANGE : RocketSim::Team::BLUE;
                newPlayerIndices.clear();
                oldPlayerIndices.clear();
                for (const auto& game : envSet->state.gameStates) {
                    const int startIndex = static_cast<int>(newPlayerIndices.size() + oldPlayerIndices.size());
                    for (int i = 0; i < static_cast<int>(game.players.size()); ++i) {
                        if (game.players[i].team == frozenTeam) oldPlayerIndices.push_back(startIndex + i);
                        else newPlayerIndices.push_back(startIndex + i);
                    }
                }
                if (oldPlayerIndices.size() != envSet->state.gameStates.size() ||
                    newPlayerIndices.size() != envSet->state.gameStates.size())
                    RG_ERR_CLOSE("[FrozenNexto] team indexing mismatch");
                tNewPlayerIndices = torch::tensor(newPlayerIndices);
                tOldPlayerIndices = torch::tensor(oldPlayerIndices);
                RG_LOG("[FrozenNexto] PPO cycle=" << totalIterations << " teacher=" << names[teacherSlot]
                       << " student_team=" << (frozenTeam == RocketSim::Team::ORANGE ? "BLUE" : "ORANGE")
                       << " rotation_steps=" << rotationSteps);
            }
'''
    s = exactly_once(s, anchor, insertion + '''\t\t\tint numRealPlayers = (oldVersion || frozenBridge) ? newPlayerIndices.size() : envSet->state.numPlayers;''', 'indices')
    s = exactly_once(s,
        '''\t\t\t\t\t\tenvSet->Reset();''',
        '''                        const auto frozenResetFlags = envSet->state.terminals;
\t\t\t\t\t\tenvSet->Reset();''', 'reset')
    s = exactly_once(s,
        '''\t\t\t\t\t\tif (oldVersion) {''',
        '''\t\t\t\t\t\tif (oldVersion || frozenBridge) {''', 'inference-condition')
    s = exactly_once(s,
        '''\t\t\t\t\t\t\tppo->InferActions(tdOldStates, tdOldActionMasks, &tOldActions, NULL, &oldVersion->models);''',
        '''                        if (frozenBridge) {
                            auto frozenActions = frozenBridge->Infer(envSet->state, frozenResetFlags, frozenTeam);
                            tOldActions = torch::tensor(frozenActions, torch::TensorOptions().dtype(tNewActions.dtype()));
                        } else {
                            ppo->InferActions(tdOldStates, tdOldActionMasks, &tOldActions, NULL, &oldVersion->models);
                        }''', 'teacher-inference')
    anchor = '''\t\t\t\tif (versionMgr)\n\t\t\t\t\tversionMgr->OnIteration(ppo, report, totalTimesteps, prevTimesteps);'''
    s=exactly_once(s, anchor, anchor + '''
                // FROZEN_NEXTO_BRIDGE_V1: bounded smoke run stops only after PPO update and full checkpoint.
                if (frozenBridge && frozenStopAt > 0 && static_cast<int64_t>(totalTimesteps) >= frozenStopAt) {
                    RG_LOG("[FrozenNexto] target student steps reached; saving and exiting cleanly...");
                    Save();
                    RG_LOG("[FrozenNexto] SUCCESS: saved student checkpoint at " << totalTimesteps);
                    return;
                }
''', 'safe-stopper')
    return s


def install():
    if not LEARNER.is_file():
        raise FileNotFoundError(f'Missing {LEARNER}')
    original=LEARNER.read_text(encoding='utf-8-sig')
    updated=patch(original)
    if updated==original:
        print('Already patched; no changes needed')
        return
    if HEADER.exists() and HEADER.read_bytes() != (HERE/'FrozenNextoBridge.h').read_bytes():
        raise RuntimeError(f'Existing header differs, will not overwrite: {HEADER}')
    # All anchors validated before mutating disk.
    backup=LEARNER.with_name('Learner.cpp.before_frozen_nexto_bridge_v1.bak')
    if backup.exists() and backup.read_text(encoding='utf-8-sig') != original:
        raise RuntimeError(f'Backup exists but differs: {backup}. Stop rather than overwrite.')
    if not backup.exists():
        shutil.copy2(LEARNER,backup)
    HEADER.parent.mkdir(parents=True,exist_ok=True)
    if not HEADER.exists():
        shutil.copy2(HERE/'FrozenNextoBridge.h',HEADER)
    # Replace with a temporary file to avoid partial modifications.
    tmp=LEARNER.with_suffix('.cpp.frozen_tmp')
    tmp.write_text(updated, encoding='utf-8')
    tmp.replace(LEARNER)
    print('SUCCESS: Installed frozen Nexto-family opponent bridge')
    print('Backup:',backup)
    print('Header:',HEADER)
    print('Rebuild GigaLearnBot.exe now; older exe is unchanged')

if __name__=='__main__':
    try: install()
    except Exception as e:
        print('ERROR: Source unchanged or backed up; '+str(e), file=sys.stderr)
        raise SystemExit(1)
