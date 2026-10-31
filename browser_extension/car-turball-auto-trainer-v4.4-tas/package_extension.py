"""Package only our extension sources. Never include captures, game code or model weights."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import json

ROOT=Path(__file__).resolve().parent
SUFFIXES={'.js','.mjs','.json','.html','.md','.txt','.bat','.py'}


def main():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    files=sorted(p for p in ROOT.iterdir() if p.is_file() and p.suffix in SUFFIXES and p.name!='SOURCE_INFO.json')
    info={'version':manifest['version'],'gameplay_compatibility':{'car_soccer':'main-B95SF9Gf.js: actual bundle and native physics checked offline','turball':'new release awaits missing gameplay module; capture tools ready'},
          'private_game_assets_or_weights_bundled':False,
          'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    source_info=ROOT/'SOURCE_INFO.json';source_info.write_text(json.dumps(info,indent=2)+'\n')
    target=ROOT.parents[1]/'downloads'/f"Car_Turball_Auto_Trainer_v{manifest['version']}_Update.zip"
    folder=f"Car_Turball_Auto_Trainer_v{manifest['version']}/"
    with ZipFile(target,'w',ZIP_DEFLATED,compresslevel=9) as z:
        for p in files+[source_info]:z.write(p,folder+p.name)
    with ZipFile(target) as z:
        assert z.testzip() is None
        for p in files+[source_info]:assert z.read(folder+p.name)==p.read_bytes()
    print(target,len(files)+1,'files',target.stat().st_size,'bytes',hashlib.sha256(target.read_bytes()).hexdigest())


if __name__=='__main__':main()
