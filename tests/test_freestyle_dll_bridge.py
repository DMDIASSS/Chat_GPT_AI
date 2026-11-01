"""Link a real bridge against hidden PPO methods, matching a DLL export boundary."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_bridge_exports_inference_and_learning_rates_without_exporting_private_ppo(tmp_path):
    compiler, nm = shutil.which('g++'), shutil.which('nm')
    if not compiler or not nm:
        pytest.skip('GNU shared-library boundary check unavailable')
    include = tmp_path / 'include/GigaLearnCPP'
    (include / 'PPO').mkdir(parents=True)
    (include / 'Learner.h').write_text('''
#pragma once
namespace at { struct Tensor { int value=0; }; }
namespace GGL {
struct Report { int value=0; };
class PPOLearner;
struct Learner { PPOLearner* ppo; };
}
''')
    (include / 'PPO/PPOLearner.h').write_text('''
#pragma once
#include <GigaLearnCPP/Learner.h>
#include <filesystem>
namespace GGL {
struct Model {bool loaded=false;void Load(std::filesystem::path folder,bool allow,bool optim) {loaded=folder=="parent"&&!allow&&!optim;}};
struct ModelSet {Model policy;Model* operator[](const char*) {return &policy;}};
class PPOLearner {
public:
 ModelSet models;
 struct { float policyTemperature=.7f; } config;
 float actor=0,critic=0;
 void SetLearningRates(float,float);
 static void InferActionsFromModels(ModelSet&,at::Tensor,at::Tensor,bool,float,bool,at::Tensor*,at::Tensor*);
};
}
''')
    private = tmp_path / 'private.cpp'
    private.write_text('''
#include <GigaLearnCPP/PPO/PPOLearner.h>
void GGL::PPOLearner::SetLearningRates(float a,float c) { actor=a;critic=c; }
void GGL::PPOLearner::InferActionsFromModels(ModelSet&,at::Tensor obs,at::Tensor masks,
 bool deterministic,float temperature,bool half,at::Tensor* actions,at::Tensor*) {
 actions->value=deterministic&&!half&&temperature==.7f?obs.value+masks.value:-1;
}
''')
    entry = tmp_path / 'main.cpp'
    entry.write_text('''
#include "FreestyleBridge.h"
#include <GigaLearnCPP/PPO/PPOLearner.h>
int reports=0,saves=0;
void report(GGL::Learner*,const GGL::Report& r) { reports+=r.value; }
void save(GGL::Learner*) { ++saves; }
int main() {
 GGL::PPOLearner p;GGL::Learner learner{&p};at::Tensor obs{21},mask{8},actions;
 SlaterFreestyleSetLearningRates(&learner,.003f,.004f);
 SlaterFreestyleInfer(&learner,obs,mask,&actions);
 if(p.actor!=.003f||p.critic!=.004f||actions.value!=29)return 1;
 SlaterFreestyleLoadPolicy(&learner,"parent");if(!p.models.policy.loaded)return 3;
 SlaterFreestyleSetReportHook(report);SlaterFreestyleSetCheckpointHook(save);
 SlaterFreestyleReportHook(&learner,GGL::Report{3});SlaterFreestyleCheckpointHook(&learner);
 SlaterFreestyleSetReportHook(nullptr);SlaterFreestyleSetCheckpointHook(nullptr);
 SlaterFreestyleReportHook(&learner,GGL::Report{9});SlaterFreestyleCheckpointHook(&learner);
 return reports==3&&saves==1?0:2;
}
''')
    bridge = ROOT / 'GigaLearn_Project/Freestyle'
    library = tmp_path / 'libfreestyle-test.so'
    common = [compiler, '-std=c++20', f'-I{tmp_path / "include"}', f'-I{bridge}']
    result = subprocess.run([*common, '-shared', '-fPIC', '-fvisibility=hidden',
        str(bridge / 'FreestyleBridge.cpp'), str(private), '-o', str(library)],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    symbols = subprocess.check_output([nm, '-D', '--defined-only', str(library)], text=True)
    assert 'SlaterFreestyleInfer' in symbols
    assert 'SlaterFreestyleSetLearningRates' in symbols
    assert 'PPOLearner' not in symbols, 'Test must retain upstream methods as private DLL symbols'
    program = tmp_path / 'bridge-test'
    result = subprocess.run([*common, str(entry), '-L' + str(tmp_path), '-lfreestyle-test',
        '-Wl,-rpath,' + str(tmp_path), '-o', str(program)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    subprocess.run([str(program)], check=True)
