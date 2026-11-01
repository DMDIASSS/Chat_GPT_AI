"""Build the public Nexto preset; refuse every unrecognized/private checkpoint."""
import argparse
import hashlib
import json
from pathlib import Path
import torch
from export_standalone import NEXTO_SHA256,load_model,standalone_source

APP=Path(__file__).resolve().parent
NOTICE='''-- Original Nexto model: Nexto contributors, https://github.com/Rolv-Arild/Necto
-- Source model: https://raw.githubusercontent.com/Rolv-Arild/Necto/master/rlbot-support/Nexto/nexto-model.pt
-- Model SHA256: bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa
-- Adapted to numeric Luau inference, rendered Roblox state and keyboard controls.
-- This generated adaptation is CC BY-NC-SA 4.0; attribution, noncommercial and
-- share-alike terms: https://creativecommons.org/licenses/by-nc-sa/4.0/
-- Full license and adaptation notes are included in the accompanying ZIP.
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset',type=Path,default=APP.parent/'vendor/nexto/nexto-model.pt')
    parser.add_argument('--output',type=Path,default=APP.parent/'downloads/TurboBall_Nexto.lua')
    args=parser.parse_args()
    sha=hashlib.sha256(args.asset.read_bytes()).hexdigest()
    if sha!=NEXTO_SHA256:raise ValueError('Refusing public export: this is not the verified upstream Nexto asset')
    torch.set_num_threads(1)
    source=NOTICE+standalone_source(load_model(args.asset,args.asset),sha,model_name='Nexto',physics_assist=False)
    args.output.write_text(source,encoding='utf-8',newline='\n')
    print(json.dumps({'output':str(args.output),'model_sha256':sha,'bytes':args.output.stat().st_size,
        'script_sha256':hashlib.sha256(args.output.read_bytes()).hexdigest()}))

if __name__=='__main__':main()
