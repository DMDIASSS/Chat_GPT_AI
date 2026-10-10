import argparse,json,sys,pathlib
import curriculum_core as c

def run():
    p=argparse.ArgumentParser(description='GigaLearn staged curriculum (isolated; no unsafe silent promotions)')
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('check');sub.add_parser('stages');sub.add_parser('run-all')
    x=sub.add_parser('extract-replays');x.add_argument('--input',nargs='+',required=True);x.add_argument('--output');x.add_argument('--max-files',type=int,default=500)
    t=sub.add_parser('audit-tas');t.add_argument('--input',nargs='+',required=True);t.add_argument('--output')
    b=sub.add_parser('train-replays');b.add_argument('--dataset',required=True);b.add_argument('--epochs',type=int,default=4);b.add_argument('--lr',type=float,default=0.00008);b.add_argument('--seed-checkpoint')
    y=sub.add_parser('branch-to-hub');y.add_argument('--checkpoint',required=True);y.add_argument('--name',required=True);y.add_argument('--preset',default='Balanced 1v1')
    a=p.parse_args()
    try:
        if a.cmd=='check':out=c.readiness()
        elif a.cmd=='stages':out=c.stage_states()
        elif a.cmd=='run-all':c.can_run_all();out={'ready':True}
        elif a.cmd=='extract-replays':
            from replay_export import convert
            dest=a.output or str(c.HERE/'run_data'/c.new_id())
            out=convert(a.input,dest,max_files=a.max_files)
            out['folder']=str(pathlib.Path(dest).resolve())
        elif a.cmd=='audit-tas':
            from tas_audit import audit
            out=audit(a.input,a.output or str(c.HERE/'results'/('tas_audit_'+c.new_id()+'.json')))
        elif a.cmd=='train-replays':out=c.run_replay_bc(a.dataset,epochs=a.epochs,lr=a.lr,seed_checkpoint=a.seed_checkpoint)
        elif a.cmd=='branch-to-hub':out={'experiment':str(c.branch_replay_to_hub(a.checkpoint,a.name,a.preset))}
        print(json.dumps(out,indent=2,default=str))
    except Exception as exc:
        print('BLOCKED/FAILED:',str(exc),file=sys.stderr);sys.exit(1)
if __name__=='__main__':run()
