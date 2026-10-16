"""Forecast simulation helpers shared by the parent and lightweight CPU workers.

Keep this module free of Torch/model imports: workers only run RocketSim.
"""
import numpy as np
import RocketSim as rs
from vendor.nexto.nexto_obs import rotation_to_quaternion


def native_encoded(arena,cars,ordered):
    """Encode native snapshots using the training observation contract.

    Only fields consumed by batched_build_obs are populated. The unused legacy
    inverse-physics blocks stay zero; they are never passed to a learned layer.
    """
    row=np.zeros(55+38*len(ordered),np.float64)
    row[3:37]=[pad.get_state().cooldown<=1e-6 for pad in arena.get_boost_pads()]
    ball=arena.ball.get_state();row[37:40]=ball.pos.as_numpy();row[40:43]=ball.vel.as_numpy();row[43:46]=ball.ang_vel.as_numpy()
    for i,aid in enumerate(ordered):
        car=cars[aid];state=car.get_state();offset=55+38*i
        row[offset:offset+2]=i,int(car.team)
        # get_gym_state zeroes demoed car poses. Training retains them, so read
        # native physics directly and preserve its double-precision quaternion
        # round trip rather than changing the observation contract.
        row[offset+2:offset+5]=state.pos.as_numpy()
        row[offset+5:offset+9]=rotation_to_quaternion(np.asarray(state.rot_mat.as_numpy().reshape(3,3).T,np.float64))
        row[offset+9:offset+12]=state.vel.as_numpy();row[offset+12:offset+15]=state.ang_vel.as_numpy()
        row[offset+33]=state.demo_respawn_timer>0
        row[offset+34]=sum(state.wheels_with_contact)>=3
        row[offset+36]=not state.has_double_jumped and not state.has_flipped and state.air_time_since_jump<1.25
        row[offset+37]=float(state.boost)/100.
    return row


def controls(values):
    c=rs.CarControls()
    c.throttle,c.steer,c.pitch,c.yaw,c.roll=map(float,values[:5])
    c.jump,c.boost,c.handbrake=map(bool,values[5:])
    return c


def compile_controls(book):
    """Cache exact control edges and immutable native controls for every token."""
    plans=[]
    for token in book:
        parts=[]
        for offset in range(0,len(token),8):
            part=token[offset:offset+8]
            edges=np.flatnonzero(np.any(part[1:]!=part[:-1],axis=1))+1
            bounds=[0,*edges.tolist(),len(part)];segments=[]
            for left,right in zip(bounds,bounds[1:]):
                absolute=offset+left
                changed=absolute==0 or not np.array_equal(token[absolute],token[absolute-1])
                segments.append((left,right,controls(part[left]) if changed else None))
            parts.append(segments)
        plans.append(parts)
    return plans


def advance_batch(active,ours,commands):
    """Apply every exact control edge; batch only intervals with held controls."""
    count=commands.shape[1]
    changed=np.flatnonzero(np.any(commands[:,1:]!=commands[:,:-1],axis=(0,2)))+1
    boundaries=[0,*changed.tolist(),count]
    for left,right in zip(boundaries,boundaries[1:]):
        for b,command in zip(active,commands[:,left]):
            if b['last'] is None or not np.array_equal(b['last'],command):
                b['cars'][ours].set_controls(controls(command));b['last']=command.copy()
        rs.Arena.multi_step([b['arena'] for b in active],right-left)
    return len(boundaries)-1


def advance_branch(branch,ours,book,count,ordered,sign,plans=None):
    """One worker owns one arena for a chunk; no per-tick task scheduling."""
    from rlgym.rocket_league.common_values import GOAL_THRESHOLD
    commands=book[branch['token']];snapshots=[];steps=0
    for offset in range(0,count,8):
        part=commands[offset:min(offset+8,count)]
        if plans is None:
            edges=np.flatnonzero(np.any(part[1:]!=part[:-1],axis=1))+1
            boundaries=[0,*edges.tolist(),len(part)]
            for left,right in zip(boundaries,boundaries[1:]):
                command=part[left]
                if branch['last'] is None or not np.array_equal(branch['last'],command):
                    branch['cars'][ours].set_controls(controls(command));branch['last']=command.copy()
                branch['arena'].step(right-left);steps+=1
        else:
            for left,right,command in plans[branch['token']][offset//8]:
                if left>=len(part):break
                if command is not None:branch['cars'][ours].set_controls(command)
                branch['arena'].step(min(right,len(part))-left);steps+=1
        branch['tick']+=len(part)
        row=native_encoded(branch['arena'],branch['cars'],ordered)
        snapshots.append((branch,row,part[-1].copy()))
        if abs(row[38])>GOAL_THRESHOLD:
            branch['goal']=1. if sign*row[38]>0 else -1.;break
    return snapshots,steps
