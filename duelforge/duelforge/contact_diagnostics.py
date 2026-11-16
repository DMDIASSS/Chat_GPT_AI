"""Read-only close-approach outcomes from actual watch frames."""
from pathlib import Path
import numpy as np
from .observation import ACTIONS

def analyze(path):
    path=Path(path)
    with np.load(path,allow_pickle=False) as z:
        before=z['before_world'];touch=z['touches'];actions=z['actions'];goals=z['goals'];resets=z['resets'] if 'resets' in z else goals!=0;rows=[]
        for color in (0,1):
            next_event=0
            for k,w in enumerate(before):
                if k<next_event:continue
                car=w[color+1];ball=w[0];delta=ball[:3]-car[:3];distance=np.linalg.norm(delta)
                closing=float(np.dot(car[3:6]-ball[3:6],delta)/max(1.,distance))
                if not (170<distance<500 and abs(delta[2])<180 and closing>400):continue
                end=min(len(before),k+11)
                for j in range(k,end-1):
                    if resets[j] or np.linalg.norm(before[j+1,0,:3]-before[j,0,:3])>1500:end=j+1;break
                made_contact=bool(touch[k:end,color].any());steer=ACTIONS[actions[k:end,color],1]
                rows.append({'frame':k,'team':'blue' if color==0 else 'orange','distance_uu':float(distance),'closing_uu_s':closing,'contact_within_window':made_contact,'max_abs_steer_command':float(np.abs(steer).max()),'window_decisions':end-k});next_event=end
    return {'recording':str(path.parent.name),'close_approaches':len(rows),'contact_windows':sum(v['contact_within_window'] for v in rows),'no_contact_windows':sum(not v['contact_within_window'] for v in rows),'scope':'Heuristic episode-aware close-approach windows, not a certified whiff count. Steer commands can be appropriate; a causal failure diagnosis needs the recording.','events':rows}
