"""Low-allocation snapshots with the original double-precision quaternion math."""
import numpy as np


def quaternion(rotation):
    """RocketSim column-major rotation -> training's negated wxyz quaternion.

    Scalar double arithmetic avoids NumPy trace/transpose/temporary arrays for
    every car, preserving the original branch rules and normalization contract.
    """
    a,d,g,b,e,h,c,f,i=map(float,rotation.reshape(-1))
    trace=a+e+i
    if trace>0:
        s=(trace+1)**.5;inv=.5/s
        return (-.5*s,-(h-f)*inv,-(c-g)*inv,-(d-b)*inv)
    if a>=e and a>=i:
        s=(1+a-e-i)**.5;inv=.5/s
        return (-(h-f)*inv,-.5*s,-(d+b)*inv,-(g+c)*inv)
    if e>i:
        s=(1+e-a-i)**.5;inv=.5/s
        return (-(c-g)*inv,-(b+d)*inv,-.5*s,-(h+f)*inv)
    s=(1+i-a-e)**.5;inv=.5/s
    return (-(d-b)*inv,-(c+g)*inv,-(f+h)*inv,-.5*s)


def encoded(arena,cars,ordered):
    row=np.zeros(55+38*len(ordered),np.float64)
    row[3:37]=[pad.get_state().cooldown<=1e-6 for pad in arena.get_boost_pads()]
    ball=arena.ball.get_state();row[37:40]=ball.pos.as_numpy();row[40:43]=ball.vel.as_numpy();row[43:46]=ball.ang_vel.as_numpy()
    for index,aid in enumerate(ordered):
        car=cars[aid];state=car.get_state();offset=55+38*index
        row[offset:offset+2]=index,int(car.team)
        row[offset+2:offset+5]=state.pos.as_numpy()
        row[offset+5:offset+9]=quaternion(state.rot_mat.as_numpy())
        row[offset+9:offset+12]=state.vel.as_numpy();row[offset+12:offset+15]=state.ang_vel.as_numpy()
        row[offset+33]=state.demo_respawn_timer>0;row[offset+34]=sum(state.wheels_with_contact)>=3
        row[offset+36]=not state.has_double_jumped and not state.has_flipped and state.air_time_since_jump<1.25
        row[offset+37]=float(state.boost)/100.
    return row
