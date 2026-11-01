"""Persistent CPU forecast worker; this entry point intentionally avoids Torch."""
import os
import sys


def main():
    # Preserve the private binary pipe, then move Python/native stdout logs to
    # stderr so a RocketSim banner cannot corrupt the framed transport.
    output=os.fdopen(os.dup(sys.stdout.fileno()),'wb',buffering=0)
    if os.name=='nt':
        import msvcrt
        msvcrt.setmode(output.fileno(),os.O_BINARY);msvcrt.setmode(sys.stdin.fileno(),os.O_BINARY)
    os.dup2(sys.stderr.fileno(),sys.stdout.fileno())
    import numpy as np
    from rlgym.rocket_league.sim import RocketSimEngine
    from replay_il_forecast import controls,compile_controls,advance_branch,native_encoded
    from replay_il_pipe import read_frame,write_frame
    engine=RocketSimEngine(rlbot_delay=False);branches=[];book=plans=None
    write_frame(output,{'status':'ready','pid':os.getpid(),'torch_loaded':'torch' in sys.modules})
    try:
        while True:
            try:message=read_frame(sys.stdin.buffer)
            except EOFError:return
            try:
                command=message['command']
                if command=='book':
                    book=np.asarray(message['book'],np.float32);plans=compile_controls(book)
                    if message.get('fast_snapshot'):
                        from replay_il_snapshot import encoded as snapshot
                    else:snapshot=native_encoded
                    write_frame(output,{'status':'ok'})
                elif command=='prepare':
                    initial=message['state'];ours=message['ours'];sign=message['sign']
                    ordered=sorted(initial.cars,key=lambda aid:(bool(initial.cars[aid].is_orange),str(aid)))
                    previous=message['previous']
                    opponent_controls={aid:controls(previous.get(aid,np.zeros(8))) for aid in initial.cars if aid!=ours}
                    branches=[{'index':int(index),'state':initial,'token':int(token),'tick':initial.tick_count,
                        'goal':None,'last':None} for index,token in zip(message['indices'],message['tokens'])]
                    write_frame(output,{'status':'ok'})
                elif command=='step':
                    count=int(message['ticks']);tokens=message['tokens'];snapshots=[];calls=0
                    if not 1<=count<=len(book[0]) or len(tokens)!=len(branches):
                        raise ValueError('Invalid forecast chunk or branch count')
                    for branch,token in zip(branches,tokens):
                        branch['token']=int(token)
                        if not 0<=branch['token']<len(book):raise ValueError('Invalid forecast token index')
                        if branch['goal'] is not None:continue
                        engine.set_state(branch['state'],{})
                        branch.update(cars=engine._cars,arena=engine._arena,last=None)
                        for aid,value in opponent_controls.items():engine._cars[aid].set_controls(value)
                        rows,steps=advance_branch(branch,ours,book,count,ordered,sign,plans,snapshot);calls+=steps
                        snapshots.extend((branch['index'],row,action) for _,row,action in rows)
                        if message['retain_state'] and branch['goal'] is None:
                            engine._tick_count=branch['tick'];branch['state']=engine._get_state()
                    width=55+38*len(ordered)
                    # Three contiguous arrays avoid pickling hundreds of tiny
                    # arrays individually, and do not require shared-memory APIs.
                    write_frame(output,{'status':'ok',
                        'indices':np.asarray([index for index,_,_ in snapshots],np.int16),
                        'rows':np.stack([row for _,row,_ in snapshots]) if snapshots else np.empty((0,width),np.float64),
                        'actions':np.stack([action for _,_,action in snapshots]) if snapshots else np.empty((0,8),np.float32),
                        'branches':[(branch['index'],branch['tick'],branch['goal']) for branch in branches],
                        'native_step_calls':calls})
                else:raise ValueError('Unknown private forecast command')
            except Exception as error:
                write_frame(output,{'status':'error','error':type(error).__name__+': '+str(error)})
    finally:engine.close();output.close()


if __name__=='__main__':
    if sys.argv[1:]!=['--private-forecast-worker']:
        raise SystemExit('Internal CPU worker. Run REPLAY_IL_MULTICORE_BENCHMARK.bat instead.')
    main()
