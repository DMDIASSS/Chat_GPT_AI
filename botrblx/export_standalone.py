"""Export the user's local update271 to one private, self-contained Luau script."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch

from bridge271 import APP_DIR, load_model, lookup_table, observations, resolve_paths
from file_transport import select_workspace


def literal(value):
    """JSON-like, finite data only; never interpolate executable model metadata."""
    if isinstance(value, dict):
        return "{" + ",".join("[" + json.dumps(k) + "]=" + literal(v) for k,v in value.items()) + "}"
    if isinstance(value, (list,tuple)):
        return "{" + ",".join(map(literal,value)) + "}"
    if isinstance(value, bool): return "true" if value else "false"
    return json.dumps(value,allow_nan=False,ensure_ascii=True)


def expected_shapes():
    shapes = {}
    def linear(name,rows,cols):
        shapes[name+".weight"]=(rows,cols);shapes[name+".bias"]=(rows,)
    for kind,width in (("query",32),("key_value",24)):
        linear(f"net.earl.{kind}_preprocess.0",128,width)
        linear(f"net.earl.{kind}_preprocess.2",128,128)
    for block in (0,1):
        prefix=f"net.earl.blocks.{block}"
        shapes[prefix+".attention.in_proj_weight"]=(384,128)
        shapes[prefix+".attention.in_proj_bias"]=(384,)
        linear(prefix+".attention.out_proj",128,128)
        linear(prefix+".linear1",512,128);linear(prefix+".linear2",128,512)
        for norm in (1,2,3):
            shapes[f"{prefix}.norm{norm}.weight"]=(128,)
            shapes[f"{prefix}.norm{norm}.bias"]=(128,)
    for i,width in ((0,8),(2,32),(4,32)): linear(f"net.output.net.{i}",32,width)
    linear("net.output.emb_convertor",32,128)
    return shapes


def test_observations():
    result=[]
    rng=np.random.default_rng(271)
    for team in (0,1):
        for ground in (True,False):
            p={"team":team,"boost":float(rng.integers(0,101)),"ground_estimate":ground,
               "car":{"position":[0,-4608,17] if ground else [100,800,750],
                      "velocity":rng.uniform(-900,900,3).tolist(),
                      "forward":[0,1,0] if ground else [.6,.8,0],"up":[0,0,1],
                      "angular_velocity":rng.uniform(-2,2,3).tolist()},
               "ball":{"position":rng.uniform([-1500,-3000,100],[1500,3000,1200]).tolist(),
                       "velocity":rng.uniform(-1800,1800,3).tolist(),
                       "angular_velocity":rng.uniform(-3,3,3).tolist()}}
            previous=lookup_table()[int(rng.integers(90))]
            result.append(observations(p,previous,not ground))
            # Exercise variable entity counts, availability and big/small fields.
            p["boost_pads"]=[{"position":[float(x),float(y),73 if i%2 else 70],
                "is_big":bool(i%2),"active":bool(i%3)}
                for i,(x,y) in enumerate([(0,-4240),(-3584,0),(3584,0),(-3072,4096),(0,2816),(940,3308)])]
            result.append(observations(p,previous,not ground))
    return result


def prepare_model(model):
    state=model.state_dict()
    if {k:tuple(v.shape) for k,v in state.items()} != expected_shapes():
        raise ValueError("Unsupported actor: expected the update271/Nexto 128-wide, two-block network")
    if not all(torch.isfinite(v).all() for v in state.values()):
        raise ValueError("Non-finite model parameters")
    actions=torch.from_numpy(lookup_table())
    constants=model.net.output.code_with_constants[1].const_mapping
    if not torch.equal(constants.get("c0",torch.empty(0)),actions):
        raise ValueError("Policy action ordering differs from the 90-action adapter")
    for i in ("0","1"):
        constants=model.net.earl.blocks._modules[i].attention.code_with_constants[1].const_mapping
        if int(constants["c0"]) != 4 or abs(float(constants["c1"])-32**.5)>1e-8:
            raise ValueError("Unsupported attention heads")
    with torch.inference_mode():
        # These embeddings depend on weights and the fixed action table only.
        # Computing them once is exact; the control policy is not retrained.
        action_embeddings=model.net.output.net(actions).detach().cpu()
        cases=[]
        for q,kv,mask in test_observations():
            full=model((q,kv,mask))[0].reshape(-1)
            keep=mask[0]==0
            reduced=model((q,kv[:,keep],mask[:,keep]))[0].reshape(-1)
            torch.testing.assert_close(full,reduced,atol=3e-5,rtol=3e-5)
            cases.append({"query":q[0,0].tolist(),"entities":kv[0,keep].tolist(),
                          "logits":full.tolist(),"action":int(full.argmax())+1})
    tensors={k:v.detach().cpu().numpy().astype("<f4") for k,v in state.items()
             if not k.startswith("net.output.net.")}
    tensors["action_embeddings"]=action_embeddings.numpy().astype("<f4")
    return tensors,cases


def tensor_source(tensors):
    offsets={};parts=[];offset=1
    for name,array in tensors.items():
        size=array.size;offsets[name]=[offset,size];offset+=size;parts.append(array.tobytes())
    encoded=base64.b64encode(b"".join(parts)).decode("ascii")
    chunks="\n".join(json.dumps(encoded[i:i+16384])+"," for i in range(0,len(encoded),16384))
    return f'''local flat=Policy.decode(table.concat({{\n{chunks}\n}}),{offset-1})
local layout={literal(offsets)}
local tensors={{}}
for name,spec in pairs(layout)do
    local row=table.create(spec[2])
    table.move(flat,spec[1],spec[1]+spec[2]-1,1,row)
    tensors[name]=row
end
return tensors'''


def load_arena_profile(path):
    profile=json.loads(Path(path).read_text(encoding="utf-8"))
    if profile.get("version")!=1: raise ValueError("Unsupported arena profile version")
    if not 0<=profile["policy_boost_limit"]<=34 or type(profile["policy_boost_limit"]) is not int:
        raise ValueError("policy_boost_limit must be an integer from 0 to 34")
    if not .001<=profile["roblox_studs_per_sim_unit"]<=10: raise ValueError("Invalid coordinate scale")
    required=json.loads((APP_DIR/"arena_profile.json").read_text(encoding="utf-8"))
    for section in ("arena","physics","car_presets","recovery"):
        if not set(required[section]).issubset(profile[section]): raise ValueError("Incomplete arena profile: "+section)
    def finite(value):
        if isinstance(value,dict):return all(finite(v) for v in value.values())
        if isinstance(value,list):return all(finite(v) for v in value)
        if isinstance(value,(float,int)):return bool(np.isfinite(value))
        return isinstance(value,(str,bool))
    if not finite(profile):raise ValueError("Non-finite or unsupported profile value")
    return profile


def standalone_source(model,model_sha,app_dir=APP_DIR,profile=None):
    tensors,cases=prepare_model(model)
    policy=(app_dir/"templates/local_policy.lua").read_text(encoding="utf-8")
    keyboard=(app_dir/"templates/local_keyboard.lua").read_text(encoding="utf-8")
    arena=(app_dir/"templates/local_arena.lua").read_text(encoding="utf-8")
    pads=(app_dir/"templates/local_pads.lua").read_text(encoding="utf-8")
    if profile is None:profile=load_arena_profile(app_dir/"arena_profile.json")
    client=(app_dir/"client271.lua").read_text(encoding="utf-8")
    pose=client.split("-- POSE_READER_BEGIN",1)[1].partition("\n")[2].split("-- POSE_READER_END",1)[0]
    template=(app_dir/"templates/standalone.lua").read_text(encoding="utf-8")
    return (template.replace("-- LOCAL_POLICY_HERE", "local Policy=(function()\n"+policy+"\nend)()")
            .replace("-- LOCAL_KEYBOARD_HERE", "local Keyboard=(function()\n"+keyboard+"\nend)()")
            .replace("-- LOCAL_ARENA_HERE", "local Arena=(function()\n"+arena+"\nend)()")
            .replace("-- LOCAL_PADS_HERE", "local Pads=(function()\n"+pads+"\nend)()")
            .replace("-- ARENA_PROFILE_HERE",literal(profile))
            .replace("-- MODEL_TENSORS_HERE",tensor_source(tensors))
            .replace("-- MODEL_CASES_HERE",literal(cases))
            .replace("-- POSE_READER_HERE",pose)
            .replace("__MODEL_SHA__",model_sha))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root",type=Path,default=APP_DIR.parent)
    parser.add_argument("--model",type=Path);parser.add_argument("--base",type=Path)
    parser.add_argument("--workspace",type=Path)
    parser.add_argument("--reset-workspace",action="store_true")
    parser.add_argument("--no-install",action="store_true",help="Only write --output; do not install in an executor workspace")
    parser.add_argument("--output",type=Path,default=APP_DIR/"botrblx_standalone.lua")
    parser.add_argument("--arena-profile",type=Path,default=APP_DIR/"arena_profile.json")
    args=parser.parse_args();args.choose_workspace=True
    root,model_path,base_path=resolve_paths(args)
    torch.set_num_threads(1)
    print("Exporting private model locally:",model_path,flush=True)
    model=load_model(model_path,base_path)
    sha=hashlib.sha256(model_path.read_bytes()).hexdigest()
    profile=load_arena_profile(args.arena_profile)
    source=standalone_source(model,sha,profile=profile)
    args.output.write_text(source,encoding="utf-8")
    print("Saved:",args.output.resolve(),flush=True)
    print("Arena:",profile["name"],"| live boost context limit:",profile["policy_boost_limit"],flush=True)
    if not args.no_install:
        workspace=select_workspace(args,APP_DIR/"file_connection.json")
        target=workspace/"botrblx_standalone.lua"
        target.write_text(source,encoding="utf-8")
        print("Installed:",target,flush=True)
    print("READY STANDALONE: export complete. No Python bridge needs to stay open.")
    print('Execute in JJSploit: loadstring(readfile("botrblx_standalone.lua"))()')
    print("This generated file contains your private weights. Do not upload or commit it.")


if __name__=="__main__":
    try: main()
    except Exception as error:
        print("EXPORT FAILED:",error,file=sys.stderr)
        raise SystemExit(1)
