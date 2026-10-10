"""Strict TAS structural audit. Never treats controller-only streams as demonstrations."""
import argparse,collections,hashlib,json,math,pathlib,struct

def audit_file(path):
    path=pathlib.Path(path);data=path.read_bytes()
    if len(data)<136:raise ValueError('TAS file is too small')
    version,count=struct.unpack_from('<II',data)
    if version!=1 or count<1 or count>5_000_000:raise ValueError('Unsupported TAS header')
    if len(data)!=8+32*count+128:raise ValueError('Unexpected TAS frame size')
    flags=collections.Counter();invalid=0
    for i in range(count):
        bits,*values=struct.unpack_from('<I7f',data,8+32*i)
        flags[bits]+=1
        if not all(math.isfinite(x) for x in values):invalid+=1
    if invalid:raise ValueError('Nonfinite TAS analog inputs')
    return {'filename':path.name,'sha256':hashlib.sha256(data).hexdigest(),
            'format_version':version,'frames':count,'seconds_if_120hz':round(count/120,2),
            'distinct_flag_values':len(flags),'record_bytes':32,'trailer_bytes':128,
            'training_ready':False,
            'blocker':'No validated frame-aligned physics states, controller field mapping, or initial simulator state. Do not train from this file yet.'}

def audit(paths,out):
    samples=[]
    for p in paths:
        p=pathlib.Path(p)
        if p.is_dir():samples.extend(p.rglob('*.data'))
        elif p.is_file() and p.suffix.lower()=='.data':samples.append(p)
    samples=sorted(set(samples));results=[];failed=[]
    for p in samples:
        try:results.append(audit_file(p))
        except Exception as e:failed.append({'name':p.name,'error':str(e)})
    obj={'files':results,'failed':failed,'tas_imitation_enabled':False,
         'reason':'No verified TAS simulator trajectory and state-action alignment.'}
    out=pathlib.Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():raise FileExistsError('Refusing to overwrite '+str(out))
    out.write_text(json.dumps(obj,indent=2),encoding='utf8')
    return obj

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',nargs='+',required=True);ap.add_argument('--output',required=True)
    a=ap.parse_args();print(json.dumps(audit(a.input,a.output),indent=2))
if __name__=='__main__':main()
