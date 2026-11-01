"""RLBot v4 entry point for a self-contained offline-imitation policy export."""
from pathlib import Path
import hashlib
import json
import numpy as np
import torch
from rlbot.agents.base_agent import BaseAgent,SimpleControllerState
from replay_rlbot_core import PacketObserver,ReplayController

HERE=Path(__file__).resolve().parent


class ReplayBot(BaseAgent):
    def initialize_agent(self):
        torch.set_num_threads(1)
        metadata=json.loads((HERE/'EXPORT_INFO.json').read_text(encoding='utf8'))
        for name,digest in metadata['runtime_sha256'].items():
            if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest:raise ValueError('Export file changed: '+name)
        settings=json.loads((HERE/'runtime.json').read_text(encoding='utf8'));device=settings.get('device','auto')
        if device not in ('auto','cpu','cuda'):raise ValueError('Runtime device must be auto, cpu or cuda')
        if device=='auto':device='cuda' if torch.cuda.is_available() else 'cpu'
        if device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA requested but unavailable in RLBot Python')
        kernel=torch.jit.load(str(HERE/'policy.pt'),map_location=device).eval()
        book=np.load(HERE/'tokens.npy',allow_pickle=False)
        self.controller=ReplayController(kernel,book,PacketObserver(self.get_field_info()),history=metadata['history'],device=device,
            scripted_kickoff=bool(settings.get('scripted_kickoff',False)))
        self.reported_error=False;self.last_output_log=None;self.diagnostics_write_error=False
        self.diagnostic_identity={'checkpoint_sha256':metadata['checkpoint_sha256'],'book_sha256':metadata['book_sha256'],
            'name':metadata['name'],'device':device}
        self.control_counts={source:{'control_samples':0,'jump_pressed_samples':0,'boost_pressed_samples':0,
            'handbrake_pressed_samples':0,'no_throttle_boost_samples':0} for source in ('policy','scripted_kickoff','neutral')}
        self.vocabulary_buttons={name:int((book[:,:8,axis]>.5).any(1).sum()) for name,axis in (('jump',5),('boost',6),('handbrake',7))}
        print('REPLAY_BOOST_MAP_READY: 34 pads | maximum XY error',round(self.controller.observer.pad_xy_error,3),flush=True)
        print('REPLAY_MODEL_READY:',metadata['name'],'device',device,'| policy inference, 8-tick replanning | no training',flush=True)
        print('REPLAY_VOCABULARY_FIRST8: tokens with buttons',json.dumps(self.vocabulary_buttons),flush=True)

    def record_diagnostics(self,packet,action):
        counts=self.control_counts[self.controller.control_source]
        counts['control_samples']+=1
        for name,axis in (('jump',5),('boost',6),('handbrake',7)):counts[name+'_pressed_samples']+=int(bool(action[axis]))
        counts['no_throttle_boost_samples']+=int(abs(float(action[0]))<=.05 and not bool(action[6]))

    def save_diagnostics(self,packet):
        report={'schema':'replay-rlbot-control-diagnostics-v1',**self.diagnostic_identity,
            'car_index':int(self.index),
            'game_seconds':float(packet.game_info.seconds_elapsed),'control_counts':self.control_counts,
            'vocabulary_first8_tokens_with_button':self.vocabulary_buttons,
            'last_token':self.controller.selected,'last_source':self.controller.control_source,
            'policy_decisions':self.controller.policy_decisions,'last_inference_ms':self.controller.last_inference_ms,
            'max_inference_ms':self.controller.max_inference_ms,'over_66_7ms_decisions':self.controller.over_budget_decisions,
            'max_packet_gap_ticks':self.controller.max_packet_gap_ticks,'history_gap_resets':self.controller.gap_resets,
            'note':'Counts include every wrapper callback, not just five-second log snapshots. '
                'Pressed samples are commands sent to RLBot, not proof of an in-game jump/boost effect. '
                'Gap resets can also come from pauses or debugger stops; no model weights are changed.'}
        print('REPLAY_CONTROL_COUNTS:',json.dumps({'policy':self.control_counts['policy'],
            'last_inference_ms':report['last_inference_ms'],'history_gap_resets':report['history_gap_resets']}),flush=True)
        try:
            temp=HERE/('CONTROL_DIAGNOSTICS_'+str(self.index)+'.json.partial');temp.write_text(json.dumps(report,indent=2),encoding='utf8')
            temp.replace(HERE/'CONTROL_DIAGNOSTICS.json');self.diagnostics_write_error=False
        except OSError as error:
            if not self.diagnostics_write_error:print('REPLAY_DIAGNOSTICS_WRITE_FAILED:',str(error),flush=True)
            self.diagnostics_write_error=True

    def get_output(self,packet):
        try:
            action=self.controller.output(packet,self.index);self.reported_error=False
        except (ValueError,RuntimeError,IndexError) as error:
            self.controller.reset();action=np.zeros(8,np.float32)
            if not self.reported_error:print('REPLAY_MODEL_PAUSED:',str(error),flush=True)
            self.reported_error=True
        self.record_diagnostics(packet,action)
        now=float(packet.game_info.seconds_elapsed)
        if self.last_output_log is None or now<self.last_output_log or now-self.last_output_log>=5:
            self.last_output_log=now
            print('REPLAY_OUTPUT: time',round(now,2),'token',self.controller.selected,
                  'source',self.controller.control_source,
                  'throttle',round(float(action[0]),3),'steer',round(float(action[1]),3),
                  'jump',bool(action[5]),'boost',bool(action[6]),
                  'round_active',bool(packet.game_info.is_round_active),flush=True)
            self.save_diagnostics(packet)
        return SimpleControllerState(throttle=float(action[0]),steer=float(action[1]),pitch=float(action[2]),
            yaw=float(action[3]),roll=float(action[4]),jump=bool(action[5]),boost=bool(action[6]),handbrake=bool(action[7]))
