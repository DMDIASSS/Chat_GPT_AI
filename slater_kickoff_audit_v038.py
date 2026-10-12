"""v038 source-grounded, read-only Nexto scripted-kickoff parity risk audit.

Does NOT run a rocket league match or claim perfect RLBot equivalence.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import slater_fidelity_v038 as utils

KNOWN_BOT_SHA='1d9d4537ee846cbdf670079fde831e4078feb1f8fefb34911399ac4a7bb186d1'
KNOWN_V037A_SHA='a647823c227602f9c658a58a3e32b0d18a8dfe0dd1b144eadd93aaf9a856fd44'


def kickoff_audit(ref_bot,sim_file,obs_file):
    ref_hash=utils.sha256(ref_bot)
    if ref_hash!=KNOWN_BOT_SHA:raise ValueError('Unverified Nexto bot.py source SHA '+ref_hash)
    reference=Path(ref_bot).read_text(encoding='utf-8-sig')
    sim_hash=utils.sha256(sim_file)
    if sim_hash!=KNOWN_V037A_SHA:
        raise ValueError('v037a simulator source differs from audited release: '+sim_hash+'; do not assume the listed mismatches still apply.')
    simulator=Path(sim_file).read_text(encoding='utf-8-sig')
    tree=ast.parse(reference)
    ctor={}
    for cls in tree.body:
        if isinstance(cls,ast.ClassDef) and cls.name=='Nexto':
            for node in cls.body:
                if isinstance(node,ast.FunctionDef) and node.name=='__init__':
                    args=[x.arg for x in node.args.args]
                    for key,value in zip(args[-len(node.args.defaults):],node.args.defaults):
                        if key in {'beta','hardcoded_kickoffs','stochastic_kickoffs'}:
                            ctor[key]=ast.literal_eval(value)
    if not ctor:raise ValueError('No verifiable constructor defaults')
    documented=[
        {'check':'model_checkpoint_hash','observed':'independent frozen Nexto SHA must be verified from Windows installation','confidence':'requires user hash comparison'},
        {'check':'script_controls_physics_ticks','reference':'168 tick sequence with 4-tick stage boundaries',
         'simulator':'v037a grouped_control(8 physics ticks) splits script per physics tick',
         'status':'SOURCE_MECHANICS_COMPATIBLE_NOT_ENGINE_PROVEN'},
        {'check':'kickoff_pause_flag','reference':'packet.game_info.is_kickoff_pause',
         'simulator':'ball_y≈0 and not kickoff_ball_touched and t*8 <168',
         'status':'KNOWN_SEMANTIC_MISMATCH'},
        {'check':'kickoff_taker_selection','reference':'only nearest car, ties use left-goes',
         'simulator':'opponent always overrides with script in scripted mode',
         'status':'KNOWN_SEMANTIC_MISMATCH_IN_NON_1V1_AND_RESPAWNS'},
        {'check':'script_clock','reference':'kickoff_index advances by round(ticks_elapsed) from actual packet elapsed seconds',
         'simulator':'t*8 relative to episode reset',
         'status':'KNOWN_SCHEDULING_MISMATCH'},
        {'check':'stochastic_action_selection','reference':'beta=0.5 if packet.is_kickoff_pause even if script is not active',
         'simulator':'beta=0.5 only if active ball-center/predicted kickoff predicate',
         'status':'KNOWN_SEMANTIC_MISMATCH'},
        {'check':'script_interruption','reference':'if packet.ball.location.y != 0 script override stops, script counter can keep advancing',
         'simulator':'ball touched or y moved; may differ if ball y==0 but touch occurred',
         'status':'KNOWN_SEMANTIC_MISMATCH'},
        {'check':'previous_action_observation','reference':'RLBot obs receives self.action from previous decision, including scripted override',
         'simulator':'previous uses opponent_commands[-1] from preceding 8-tick step',
         'status':'NEEDS_SAME_STATE_TRACE_VALIDATION'}
    ]
    return {'version':'v0.3.8','kind':'source_based_nexto_kickoff_audit',
            'reference_bot_sha256':ref_hash,'reference_obs_sha256':utils.sha256(obs_file),
            'reference_defaults':ctor,'reference_source':str(ref_bot),
            'simulator_source':str(sim_file),'simulator_sha256':sim_hash,'findings':documented,
            'known_mismatches':sum(z['status'].startswith('KNOWN_') for z in documented if 'status' in z),
            'decision':'DO_NOT_ASSUME_NEXT0_STOCK_PARITY; DO_NOT_PROMOTE_U62',
            'note':'Based on RLBotPack v4 Nexto and v037a source, not an executed RLBot-vs-RocketSim trace.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-bot',default='slater_v038_reference/nexto_bot.py')
    p.add_argument('--reference-obs',default='slater_v038_reference/nexto_obs.py')
    p.add_argument('--simulator',default='slater_nexto_kickoff_v037a.py')
    p.add_argument('--out',required=True)
    a=p.parse_args(); root=Path.cwd().resolve()
    utils.guarded_path(root,a.out)
    result=kickoff_audit(root/a.reference_bot,root/a.simulator,root/a.reference_obs)
    utils.write_report(root,a.out,result)
    print('V038_KICKOFF_KNOWN_MISMATCHES',result['known_mismatches'])
    for finding in result['findings']:
        if finding.get('status','').startswith('KNOWN_'):print('V038_MISMATCH',finding['check'])

if __name__=='__main__':main()
