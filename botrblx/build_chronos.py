"""Build a standalone TurboBall_Chronos.lua from the pinned public Chronos model."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

import torch

from chronos import APP, MANIFEST, MIRROR_PADS, PADS, Chronos, asset_digest, download_assets, prepare_model
from export_standalone import literal, load_arena_profile, render_standalone


def tensor_source(tensors):
    layout={};parts=[];offset=1
    for name,array in tensors.items():
        layout[name]=[offset,array.size];offset+=array.size;parts.append(array.tobytes())
    encoded=base64.b64encode(b''.join(parts)).decode('ascii')
    chunks='\n'.join(json.dumps(encoded[i:i+16384])+',' for i in range(0,len(encoded),16384))
    return f'return Policy.loadChunks({{\n{chunks}\n}},{literal(layout)},{offset-1},loadingYield)'


def source(folder):
    model = Chronos(folder)
    tensors, cases = prepare_model(model)
    profile = load_arena_profile(APP / "arena_profile.json")
    profile["policy_boost_limit"] = 34
    return notice() + render_standalone(tensors, cases, asset_digest(), profile=profile,
        model_name=MANIFEST["name"], physics_assist=False, policy_file="local_chronos.lua",
        runtime_options={"cooperative":True,"light_graphics":True,"latency":True,"version":"6.9"},
        tensor_writer=tensor_source,
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
    args = parser.parse_args()
    torch.set_num_threads(1)
    if args.download:
        download_assets(args.assets)
    text = source(args.assets)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"output": str(args.output), "bytes": args.output.stat().st_size,
                      "script_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "model_pair_sha256": asset_digest(), "model": MANIFEST["name"]}))


if __name__ == "__main__":
    main()
