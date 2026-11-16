"""Reject unsafe coarse-physics speedups using paired trajectories.

This is an optional lab, never a training backend. It needs existing RocketSim
Python bindings. A passing finite fixture suite cannot establish 99.9% Rocket
League fidelity; failures can rule out a proposed shortcut cheaply.
"""
import json,time,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from duelforge.runtime import meshes,atomic_json

def run():
    import RocketSim as rs
    rs.init(meshes());rng=np.random.default_rng(94571);cases=[];timings={}
    controls=[]
    for k in range(30):
        c=rs.CarControls();c.throttle=1;c.boost=k<15;c.steer=.25 if k<12 else -.25;c.jump=k in (4,5,9);c.pitch=-.6 if 4<=k<12 else 0.;controls.append(c)
    for case in range(16):
        traces=[]
        for hz in (120,60):
            arena=rs.Arena(tick_rate=float(hz));cars=[arena.add_car(rs.Team.BLUE),arena.add_car(rs.Team.ORANGE)];arena.reset_kickoff(901+case)
            for a,car in enumerate(cars):
                s=car.get_state();s.pos=rs.Vec((a*2-1)*300,(-1 if a==0 else 1)*(650+case*25),17 if case<8 else 300);s.vel=rs.Vec(0,400 if a==0 else -400,0);s.boost=60;car.set_state(s)
            b=arena.ball.get_state();b.pos=rs.Vec(0,0,94 if case<8 else 450);b.vel=rs.Vec(200,case*40-300,150 if case>=8 else 0);arena.ball.set_state(b)
            trace=[];start=time.perf_counter()
            for c in controls:
                for car in cars:car.set_controls(c)
                arena.step(hz//15)
                states=[arena.ball.get_state()]+[car.get_state() for car in cars]
                trace.append([[s.pos.x,s.pos.y,s.pos.z,s.vel.x,s.vel.y,s.vel.z] for s in states])
            timings.setdefault(hz,[]).append(time.perf_counter()-start);traces.append(np.asarray(trace))
        err=traces[0]-traces[1];pe=np.linalg.norm(err[:,:,:3],axis=-1);ve=np.linalg.norm(err[:,:,3:6],axis=-1)
        cases.append({'case':case,'mode':'ground_contact' if case<8 else 'airborne_contact','position_error_uu_max':float(pe.max()),'position_error_uu_p95':float(np.percentile(pe,95)),'velocity_error_uu_s_max':float(ve.max())})
    speedup=sum(timings[120])/sum(timings[60]);accepted=all(c['position_error_uu_max']<=10 and c['velocity_error_uu_s_max']<=20 for c in cases)
    result={'kind':'coarse_60hz_vs_120hz_physics_lab','cases':cases,'measured_raw_fixture_speedup':speedup,'accepted_for_training':False,'fixture_tolerance_pass':accepted,'decision':'Keep 120Hz production physics. This suite is insufficient to certify a replacement even if its tolerances pass.','scope':'Two seconds per fixture; same controls at 15Hz, no action delay to isolate the physics shortcut. Production seven-tick delay is also unrepresentable exactly at 60Hz. Not a global accuracy percentage.'}
    atomic_json(ROOT/'results/sim_fidelity_lab.json',result);print(json.dumps(result,indent=2));return result
if __name__=='__main__':run()
