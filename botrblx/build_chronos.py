"""Build a standalone TurboBall_Chronos.lua from the pinned public Chronos model."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

import torch

from chronos import APP, MANIFEST, MIRROR_PADS, PADS, Chronos, asset_digest, download_assets, prepare_model
from export_standalone import literal, load_arena_profile, render_standalone

RUNTIME_MODEL=json.loads((APP/'chronos_runtime.json').read_text())

def model_data(tensors):
    layout={};parts=[];offset=1
    for name,array in tensors.items():
        layout[name]=[offset,array.size];offset+=array.size;parts.append(array.tobytes())
    return b''.join(parts),layout,offset-1


def tensor_source(tensors):
    data,layout,count=model_data(tensors)
    encoded=base64.b64encode(data).decode('ascii')
    chunks='\n'.join(json.dumps(encoded[i:i+16384])+',' for i in range(0,len(encoded),16384))
    return f'return Policy.loadChunks({{\n{chunks}\n}},{literal(layout)},{count},loadingYield,loadingProgress)'


def remote_tensor_source(tensors,revision):
    if len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('Model download must use an immutable Git commit')
    data,layout,count=model_data(tensors)
    if len(data)!=RUNTIME_MODEL['bytes'] or hashlib.sha256(data).hexdigest()!=RUNTIME_MODEL['sha256']:
        raise ValueError('Raw model does not match the published FP32 data')
    url=f'https://raw.githubusercontent.com/{RUNTIME_MODEL["repository"]}/{revision}/{RUNTIME_MODEL["path"]}'
    return f'return downloadModel({literal(url)},{literal(layout)},{count})'


def source(folder,model_revision=None):
    model = Chronos(folder)
    tensors, cases = prepare_model(model)
    profile = load_arena_profile(APP / "arena_profile.json")
    profile["policy_boost_limit"] = 34
    return notice() + render_standalone(tensors, cases, asset_digest(), profile=profile,
        model_name=MANIFEST["name"], physics_assist=False, policy_file="local_chronos.lua",
        runtime_options={"cooperative":True,"light_graphics":True,"latency":True,"version":"6.10"},
        tensor_writer=(lambda tensors:remote_tensor_source(tensors,model_revision))if model_revision else tensor_source,
        policy_replacements={"-- CHRONOS_PADS_HERE": literal(PADS.tolist()),
                             "-- CHRONOS_MIRROR_PADS_HERE": literal([i + 1 for i in MIRROR_PADS])})


def notice():
    return f'''-- Chronos V2.1 by KingJake: https://github.com/{MANIFEST["repository"]}
-- Pinned release: {MANIFEST["revision"]}
-- Actual SHARED_HEAD.lt and POLICY.lt weights; no Nexto model is embedded.
-- Model pair digest: {asset_digest()}
-- Roblox adapter derived from botrblx local v6.8. See CHRONOS_NOTICE.md.
-- Frame-budgeted local inference, latency compensation, reversible light graphics.
-- Rocket League rankings do not establish playing strength in Turbo Soccer.
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=APP / "models/chronos")
    parser.add_argument("--download", action="store_true", help="Fetch the checksum-pinned public inference weights")
    parser.add_argument("--output", type=Path, default=APP.parent / "downloads/TurboBall_Chronos.lua")
    parser.add_argument("--model-revision",help="Write a small loader that fetches raw FP32 data from this immutable commit")
    parser.add_argument("--model-output",type=Path,help="Also export the exact raw FP32 model bytes")
    parser.add_argument("--fast-output",type=Path,help="Also write the lightweight loader using the pinned raw model")
    args = parser.parse_args()
    torch.set_num_threads(1)
    if args.download:
        download_assets(args.assets)
    text = source(args.assets,args.model_revision)
    if args.model_output:
        tensors,_=prepare_model(Chronos(args.assets))
        data,_,_=model_data(tensors)
        args.model_output.parent.mkdir(parents=True,exist_ok=True)
        args.model_output.write_bytes(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    if args.fast_output:
        args.fast_output.parent.mkdir(parents=True,exist_ok=True)
        args.fast_output.write_text(source(args.assets,RUNTIME_MODEL['revision']),encoding='utf-8',newline='\n')
    print(json.dumps({"output": str(args.output), "bytes": args.output.stat().st_size,
                      "script_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "model_pair_sha256": asset_digest(), "model": MANIFEST["name"]}))


if __name__ == "__main__":
    main()
