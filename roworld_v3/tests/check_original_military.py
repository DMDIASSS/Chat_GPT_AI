"""Opt-in contracts and isolated missile trials against the user's private original engine.

No game source is bundled. These synthetic trials do not measure multiplayer strength.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training"))
from bridge import engine_source, build


CHECKS = r'''
local Sim,WorldMap,Rules,Defs=load('Core/Sim'),load('Core/WorldMap'),load('Core/Rules'),load('Core/Defs')
assert(Defs.N_SCATTER==5 and Defs.UNLOCK.scatter==2)
assert(Rules.nuke_cost('scatter',0)==3750000 and Rules.nuke_cost('scatter',20)==3750000)
assert(Rules.SCATTER_MIN==4 and Rules.SCATTER_MAX==6 and Rules.SCATTER_FAR_FULL==46)
assert(Rules.NUKE_OUTER_FULL[3]==18 and Rules.NUKE_OUTER_FULL[5]==30)
assert(Rules.SAM_COOLDOWN_TICKS==90 and Rules.SILO_COOLDOWN_TICKS==90)
print('PASS original Scattershot cost, unlock, payload, radii and reload contracts')
local function trial(seed,level,baseline)
 local W,H=192,128;local raw=buffer.create(W*H);buffer.fill(raw,0,128)
 local meta={id='military-contract',width=W,height=H,k_lin=4,terrain=raw,nations={}}
 local native=WorldMap.from_terrain(meta)
 local sim=Sim.new(native,{seed=seed,tribes=0,nations=false,max_humans=2,spawn_ticks=1,solo_countdown_ticks=1})
 local me,enemy=sim:add_human('a','A'),sim:add_human('b','B')
 assert(sim:human_start(me,64*W+30));assert(sim:human_start(enemy,64*W+130))
 for _=1,12 do sim:step() end
 for y=30,95 do for x=90,180 do sim:set_owner(y*W+x,enemy) end end
 local silo=sim:add_struct(5,me,64*W+30)
 for _=2,6 do sim:upgrade_struct(silo) end
 local sam=sim:add_struct(4,enemy,64*W+130)
 for _=2,level do sim:upgrade_struct(sam) end
 silo.shots={};sam.shots={};silo.active_tick=0;sam.active_tick=0;sim:construction_tick()
 -- Drain setup events before taking the baseline snapshot; replaying old
 -- upgrade shot stamps after it would manufacture unavailable silo slots.
 sim:step()
 sim.o_gold[me]=100000000;sim:set_unlocks(me,2)
 local snapshot=sim:snapshot();local map=Mirror.map(meta,raw,snapshot)
 local s=Mirror.snapshot(snapshot,map,me)
 local session={state=s,connected=true,mode=2,state_mode=2}
 function session:has_unlock(key) return key=='scatter' end
 function session:multiplayer_available() return true end
 function session:send_intent(intent) assert(sim:submit(me,intent)~=false) end
 local ctx=Mirror.context(session);local agent=Agent.new();local count,planned=0,0
 local frame={state=s,map=map,me=me,info=s.owners[me],ctx=ctx,session=session,now=s.tick/10}
 local sender=Adapter.new({},nil,function() return frame.now end);sender.main={session=session,ui={ctx=ctx}}
 if baseline then
  assert(sim:launch_nuke(me,'scatter',sam.tile));count=1;planned=1
 else
  local o=agent:prepare(frame);local a
  for _,c in ipairs(Arsenal.generate(frame,o,agent)) do if c.kind=='scatter' then a=c;break end end
  assert(a,'A funded useful suppression plan should exist')
  planned=a.plan.salvo.total
  assert(sender:send(a,frame));agent:sent(a,frame.now);count+=1
 end
 for tick=1,220 do
  Mirror.delta(s,sim:step());frame.now=s.tick/10
  if tick%10==0 and not baseline and agent.salvoPlan then
   local o=agent:prepare(frame);local a
   for _,c in ipairs(Arsenal.generate(frame,o,agent)) do if c.kind=='scatter' then a=c;break end end
   if a then assert(sender:send(a,frame));agent:sent(a,frame.now);count+=1 end
  end
 end
 assert(count<=planned and planned<=6)
 return sam.dead==true,count,planned
end
local results={}
for _,level in ipairs({1,5,10}) do
 local killed,shots,planned=0,0,0
 for seed=1,12 do local dead,count,n=trial(seed,level,false);if dead then killed+=1 end;shots+=count;planned+=n end
 results[level]=killed
 print('TRIAL',level,killed,12,shots,planned)
 assert(killed>0,'Suppression should work in at least some original-engine seeds')
end
local baseline=0
for seed=1,12 do local dead=trial(seed,1,true);if dead then baseline+=1 end end
print('BASELINE_CENTERED_SINGLE',baseline,12)
assert(results[1]>baseline,'Offset suppression must improve on centered single-shot targeting in this fixture')
print('PASS finite, revalidated salvos in the original simulator; synthetic isolated targets only')
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--engine", required=True)
    p.add_argument("--luau", default="luau")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    source, digest = engine_source(args.engine)
    with tempfile.TemporaryDirectory(prefix="roworld-military-") as directory:
        path = Path(directory) / "check.luau"
        path.write_text(source + build.modules_source() + CHECKS, encoding="utf8")
        result = subprocess.run([args.luau, str(path)], capture_output=True, text=True, timeout=90)
    print(result.stdout, end="")
    if result.returncode:
        raise RuntimeError(result.stderr)
    if args.output:
        trials = []
        baseline = None
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and parts[0] == "TRIAL":
                trials.append(dict(zip(("sam_level", "destroyed", "seeds", "launches", "planned_launches"), map(int, parts[1:]))))
            elif parts and parts[0] == "BASELINE_CENTERED_SINGLE":
                baseline = {"destroyed": int(parts[1]), "seeds": int(parts[2])}
        args.output.write_text(json.dumps({"version": "3.2.0", "engine_sha256": digest,
            "trials": trials, "centered_single_baseline": baseline,
            "scope": "Isolated synthetic original-engine trials; not multiplayer win rates"}, indent=2) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
