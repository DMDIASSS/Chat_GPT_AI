"""Conservative idempotent patch: GigaLearnReplayBC accepts an optional 54th TAS-cadence weight.
Backs up source once; refuses unknown modifications. Does not patch GigaLearn trainer.
"""
from pathlib import Path
import json,shutil
ROOT=Path(__file__).resolve().parent
SRC=ROOT.parents[2]/'upstream'/'src'/'HubReplayBC.cpp'
MARK='// TAS_LNK_V1: optional replay-context TAS cadence weight'
OLD_CHECK='if(a.size()!=53)throw std::runtime_error("Dataset record width invalid (expected 53 floats)");'
NEW_CHECK='if(a.size()!=53 && a.size()!=54)throw std::runtime_error("Dataset record width invalid (expected 53 or 54 floats)");'
OLD_WEIGHT='sample.weight=std::clamp(1.f/(1.f+std::max(a[3],0.f)),0.15f,1.f);'
NEW_WEIGHT=MARK+'\n        sample.weight=std::clamp(1.f/(1.f+std::max(a[3],0.f)),0.15f,1.f) * (a.size()==54 ? std::clamp(a[53],1.f,1.25f) : 1.f);'

def patch(source=SRC):
    source=Path(source)
    if not source.is_file():raise FileNotFoundError('HubReplayBC.cpp absent; install Curriculum_V2 C++ replay BC first: '+str(source))
    text=source.read_text(encoding='utf-8-sig')
    if MARK in text:
        if NEW_CHECK not in text or NEW_WEIGHT not in text:raise RuntimeError('Partial/modified patch, manual review required')
        return {'status':'already_patched','source':str(source),'rebuild':False}
    if text.count(OLD_CHECK)!=1 or text.count(OLD_WEIGHT)!=1:raise RuntimeError('Unexpected BC source; no changes made')
    b=source.with_suffix('.cpp.before_tas_link_v1.bak')
    if b.exists():
        if b.read_text(encoding='utf-8')!=text:raise RuntimeError('A different backup already exists; refusing change')
    else:shutil.copyfile(source,b)
    new=text.replace(OLD_CHECK,NEW_CHECK).replace(OLD_WEIGHT,NEW_WEIGHT)
    source.write_text(new,encoding='utf-8')
    return {'status':'patched','source':str(source),'backup':str(b),'rebuild':True}
if __name__=='__main__':print(json.dumps(patch(),indent=2))
