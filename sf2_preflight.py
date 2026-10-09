"""Real RocketSim checks. If a check fails, do not trust the new viewer/search."""
from sf2_core import SoloSimulator, Script, rollout, HeightTriggeredDodge, FORWARD


def main():
    sim=SoloSimulator()
    try:
        for seed in (700,701,702):
            state=sim.reset(seed, nose=.16)
            assert len(state.cars)==1
            car=state.cars[sim.ours]
            assert not car.on_ground and car.has_jumped and not car.has_flipped
            assert state.ball.position[1]>car.physics.position[1]+1000
            assert car.physics.linear_velocity[1]>0
            assert car.physics.rotation_mtx[1,0]>.85, 'car is not pointing toward ball'
            print('GOOD seed',seed,'car_y=',round(float(car.physics.position[1])),
                  'ball_y=',round(float(state.ball.position[1])),
                  'nose_up=',round(float(car.physics.rotation_mtx[2,0]),3))
        m=rollout(sim,700,Script(threshold=39.,nose=.16), max_ticks=115)
        print('SCRIPTED ATTEMPT:',m.reason,'dodge=',m.dodge,
              'landed_during_dodge=',m.landing_during_dodge,
              'speed_delta=',round(m.final_speed-m.initial_speed,1),
              'min_center_z=',round(m.lowest_center_z,1))
        assert m.dodge, 'Script did not trigger a dodge. Send log to ChatGPT.'
        assert m.lowest_center_z>0, 'Car center penetrated world floor. Check spawn/physics.'
        print('PASS: one car, ahead-facing ball, real dodge and positive center height.')
        print('A successful wavedash is NOT required for this preflight.')
    finally:
        sim.close()


if __name__ == '__main__':
    main()
