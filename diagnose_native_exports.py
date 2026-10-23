"""Read-only native export diagnostics. Does not train or modify checkpoint files."""
import importlib.util,json,sys
from collections import Counter
from pathlib import Path
import numpy as np
import torch
from slater_native_eval import probe_samples,parity
from slater_native_actor import NativeActor,observation,action_mask,checkpoint_identity
from nexto_teacher import nexto_actions
ROOT=Path(__file__).resolve().parent

def main():
    torch.set_num_threads(1);report=[];samples=probe_samples();actions=nexto_actions()
    for info in (ROOT/'data/rlbot_exports').glob('*/EXPORT_INFO.json'):
        doc=json.loads(info.read_text(encoding='utf8'))
        if doc.get('format')!='RLBot v4 native 230/90':continue
        folder=info.parent;item={'export':str(folder),'scripted_kickoff':doc['hardcoded_kickoffs']}
        try:
            model=NativeActor(folder/'checkpoint');actual=checkpoint_identity(folder/'checkpoint')['files']
            item['copied_weights_match_manifest']=actual==doc['source']['files']
            source=Path(doc['source']['path'])
            item['original_weights_unchanged']=checkpoint_identity(source)['files']==actual if source.exists() else None
            # Load the actual portable actor module, not only the repository adapter.
            spec=importlib.util.spec_from_file_location('portable_native_actor',folder/'native_actor.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);portable=module.NativeActor(folder/'checkpoint')
            counts=Counter();idle=0;rows=[];max_error=0.0
            with torch.no_grad():
                for sample in samples:
                    packet=sample['packet'];query=sample['query'];car=next(c for c in packet['cars'] if c['id']==query)
                    obs=torch.from_numpy(observation(packet,query)[None]);mask=torch.from_numpy(action_mask(car)[None])
                    probabilities=model.probabilities(obs,mask).numpy()[0]
                    portable_prob=portable.probabilities(torch.from_numpy(module.observation(packet,query)[None]),torch.from_numpy(module.action_mask(car)[None])).numpy()[0]
                    max_error=max(max_error,float(np.max(np.abs(portable_prob-probabilities))))
                    selected=int(probabilities.argmax());controls=actions[selected];counts[selected]+=1
                    idle+=int(np.all(controls==0))
                    if len(rows)<12:
                        top=np.argsort(probabilities)[-3:][::-1]
                        rows.append({'team':car['team'],'ground':car['ground'],'boost':car['boost'],
                            'selected':selected,'controls':controls.tolist(),'top3':[{'action':int(i),'probability':float(probabilities[i]),'controls':actions[i].tolist()} for i in top]})
            item.update(samples=len(samples),zero_control_choices=idle,selected_action_counts=dict(counts),portable_probability_max_error=max_error,examples=rows)
            try:item['cpp_parity']=parity(source)['passed'] if source.exists() else None
            except Exception as exc:item['cpp_parity_error']=str(exc)
            print('EXPORT',folder.name,'weights_match',item['copied_weights_match_manifest'],'original_unchanged',item['original_weights_unchanged'],flush=True)
            print('POLICY',len(samples),'test states; zero-control choices',idle,'action counts',dict(counts),'portable error',max_error,flush=True)
            print('CPP_PARITY',item.get('cpp_parity',item.get('cpp_parity_error')),flush=True)
        except Exception as exc:item['error']=str(exc);print('DIAGNOSTIC_ERROR',folder.name,str(exc),flush=True)
        report.append(item)
    output=ROOT/'data/rlbot_exports/native_diagnostic.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'exports':report,'note':'Synthetic state diagnostics, not a playing-strength test. No checkpoint files modified.'},indent=2),encoding='utf8')
    print('REPORT',output,flush=True)
    if not report:print('No native exports found. Expected data/rlbot_exports/*/EXPORT_INFO.json',flush=True)
if __name__=='__main__':main()
