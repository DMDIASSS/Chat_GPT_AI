"""Dedicated subprocess check against an isolated actual RLBot v4 installation.

Usage: python tests/check_v4_sdk.py --sdk-dir .v4sdk
The v5 training environment is never replaced by the v4 SDK.
"""
import argparse
import dataclasses
import json
from pathlib import Path
import sys
import tempfile
import torch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nova.chronos import ChronosEnv,CHRONOS_CONTRACT
from nova.chronos_training import new_chronos_model
from nova.models import save_ppo
from nova.training import load_config
from nova import chronos_tools
from argparse import Namespace


def main():
    p=argparse.ArgumentParser();p.add_argument('--sdk-dir',required=True);args=p.parse_args()
    sdk_dir=str(Path(args.sdk_dir).resolve());torch.set_num_threads(1)
    cfg=load_config(Path(__file__).resolve().parents[1]/'configs/chronos.json')
    cfg.update(workers=1,device='cpu');cfg['league']['weights']={'scorer':1.}
    cfg['ppo'].update(n_steps=8,batch_size=8,n_epochs=1)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);run=root/'runs/sdk_test';(run/'checkpoints').mkdir(parents=True)
        env=ChronosEnv(cfg,opponent='scorer')
        try:model=new_chronos_model(cfg,env,initialize=False)
        finally:env.close()
        path=run/'checkpoints/step_000000000000.zip';save_ppo(model,path,contract=CHRONOS_CONTRACT)
        (run/'latest.json').write_text(json.dumps({'path':str(path.relative_to(run))}))
        chronos_tools.ROOT=root;chronos_tools.export_chronos(Namespace(run='sdk_test',initial=False))
        package=next(p for p in (root/'exports').iterdir() if p.is_dir())
        # Training/export is finished; the rest runs solely against the old SDK.
        for name in list(sys.modules):
            if name=='rlbot' or name.startswith('rlbot.'):sys.modules.pop(name)
        sys.path.insert(0,sdk_dir)
        from rlbot.parsing.bot_config_bundle import get_bot_config_bundle
        from rlbot.utils.class_importer import import_agent
        from rlbot.utils.structures.game_data_struct import GameTickPacket,FieldInfoPacket
        bundle=get_bot_config_bundle(str(package/'bot.cfg'))
        klass=import_agent(str(package/'bot_v4.py')).get_loaded_class()
        assert klass.__module__=='bot_v4'
        agent=klass('test',0,0)
        field=FieldInfoPacket();field.num_boosts=34
        # Load the actual standalone export's feature constants.
        sys.path.insert(0,str(package))
        from features import BOOSTS
        for i,(x,y,z) in enumerate(BOOSTS):
            field.boost_pads[i].location.x=x;field.boost_pads[i].location.y=y;field.boost_pads[i].location.z=z
        agent.get_field_info=lambda:field;agent.initialize_agent()
        packet=GameTickPacket();packet.num_cars=2;packet.game_info.is_round_active=True
        for i,y in enumerate((-4608,4608)):
            car=packet.game_cars[i];car.team=i;car.has_wheel_contact=True;car.boost=33
            car.physics.location.y=y;car.physics.location.z=17
        for frame in range(10):
            packet.game_info.frame_num=frame;packet.game_info.seconds_elapsed=frame/120
            controls=agent.get_output(packet)
            assert np.isfinite([controls.throttle,controls.steer,controls.pitch,controls.yaw,controls.roll]).all()
        print('V4_CFG_OFFICIAL_CLASS_IMPORT_AND_ACTUAL_PACKET_INFERENCE_PASS',bundle.name)

if __name__=='__main__':main()
