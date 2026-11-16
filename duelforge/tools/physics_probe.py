"""Bounded RAW RocketSim physics probe, not neural gameplay or training SPS."""
import argparse,json,time,os
from pathlib import Path

def meshes(explicit=None):
    candidates=[explicit,os.environ.get('ATTENTIONFORGE_MESHES'),os.environ.get('REPLICAR_MESHES')]
    try:
        import rlgym.rocket_league.sim
        candidates.append(str(Path(rlgym.rocket_league.sim.__file__).parent/'collision_meshes'))
    except ImportError:pass
    for value in candidates:
        if value and Path(value).is_dir() and next(Path(value).rglob('*.cmf'),None):return value
    raise FileNotFoundError('Provide --meshes with your existing soccar collision_meshes directory; no assets are downloaded')

def run(output,seconds=1,mesh_dir=None):
    import RocketSim as rs
    rs.init(meshes(mesh_dir));rows=[]
    for count in (1,16,64):
        arenas=[]
        for i in range(count):
            arena=rs.Arena();blue=arena.add_car(rs.Team.BLUE);orange=arena.add_car(rs.Team.ORANGE);arena.reset_kickoff(123+i)
            for c in (blue,orange):
                action=rs.CarControls();action.throttle=1;action.boost=True;action.steer=.2 if i%2 else -.2;c.set_controls(action)
            arenas.append(arena)
        def advance():
            for arena in arenas:arena.step(8)
        for _ in range(3):advance()
        start=time.perf_counter();steps=0
        while time.perf_counter()-start<seconds:
            advance();steps+=1
        elapsed=time.perf_counter()-start
        row={'arenas':count,'car_count_per_arena':2,'ticks_per_step':8,'seconds':elapsed,'raw_physics_ticks_per_second':steps*count*8/elapsed,'raw_environment_steps_per_second':steps*count/elapsed,'raw_player_decisions_per_second':steps*count*2/elapsed,'execution':'explicit serial loop, warmed up; native trainer worker-pool comparison still required','scope':'RAW physics via Python bindings, scripted constant inputs. No obs/rewards/inference/PPO; no framework or learning speed claim.'}
        rows.append(row);print(json.dumps(row),flush=True)
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps({'kind':'raw_physics_probe','bindings':rs.__file__,'results':rows},indent=2));return rows

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=1);p.add_argument('--meshes');p.add_argument('--output',default='results/physics_probe.json');a=p.parse_args()
    if not .1<=a.seconds<=3:p.error('seconds must be 0.1..3')
    run(a.output,a.seconds,a.meshes)
