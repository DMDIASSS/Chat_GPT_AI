"""Transparent, offline, human-verifiable tournament bookkeeping.
Never invents game results or promotes a champion automatically.
"""
import csv
import json
from pathlib import Path
import math
from datetime import datetime,timezone


def pairings(model_names, rounds=3):
    """Deterministic rotating pairings. No two competitors appear twice in a round."""
    names=sorted(set(model_names))
    if len(names)<2:raise ValueError('Need at least 2 competitors')
    if len(names)%2:names.append('BYE')
    rows=[]
    for r in range(min(rounds,len(names)-1)):
        ordered=[names[0]]+names[-r:]+names[1:-r] if r else names[:]
        for i in range(len(ordered)//2):
            a,b=ordered[i],ordered[-1-i]
            if a=='BYE' or b=='BYE':continue
            rows.append({'round':r+1,'a':a,'b':b,'wins_a':'','wins_b':'','draws':'','episodes':'','note':'unplayed'})
    return rows

def save_schedule(path,model_names,rounds=3):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    rows=pairings(model_names,rounds)
    with path.open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
    return path

def standings_from_csv(path):
    with Path(path).open(newline='',encoding='utf8') as f:rows=list(csv.DictReader(f))
    standings={}
    for row in rows:
        a,b=row['a'],row['b']
        for x in (a,b):
            if x not in standings:standings[x]={'model':x,'played':0,'wins':0,'losses':0,'draws':0,'score':0,'episodes':0}
        if not row.get('wins_a') or not row.get('wins_b') or row.get('draws','')=='':continue
        wa,wb,draw=map(int,(row['wins_a'],row['wins_b'],row['draws']))
        n=wa+wb+draw
        if min(wa,wb,draw)<0 or n<1:raise ValueError('Invalid match scores')
        for model,w,l in [(a,wa,wb),(b,wb,wa)]:
            v=standings[model]
            v['played']+=1;v['wins']+=w;v['losses']+=l;v['draws']+=draw;v['episodes']+=n;v['score']+=w+draw/2
    for v in standings.values():
        v['score_pct']=round(100*v['score']/v['episodes'],2) if v['episodes'] else None
    return sorted(standings.values(),key=lambda v:(v['score_pct'] is not None,v['score_pct'] or -1,v['episodes']),reverse=True)
