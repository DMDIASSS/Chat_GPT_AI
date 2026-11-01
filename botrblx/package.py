"""Maintainer build from a Git checkout; only verified public Nexto is bundled."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

APP=Path(__file__).resolve().parent
ROOT=APP.parent

def main():
    subprocess.run([sys.executable,str(APP/'build_nexto.py')],cwd=ROOT,check=True)
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--','botrblx'],cwd=ROOT).decode().split('\0')
    paths=sorted({name for name in names if name})
    assert not any(Path(name).suffix in {'.pt','.pth','.ckpt','.rbxl','.rbxlx'}or Path(name).name=='botrblx_standalone.lua'for name in paths)
    contents={name:(ROOT/name).read_bytes()for name in paths}
    contents['botrblx/TurboBall_Nexto.lua']=(ROOT/'downloads/TurboBall_Nexto.lua').read_bytes()
    assert contents['botrblx/NEXTO_LICENSE.txt']==(ROOT/'vendor/nexto/LICENSE.txt').read_bytes()
    hashes={name:hashlib.sha256(data).hexdigest()for name,data in contents.items()}
    contents['SOURCE_HASHES.json']=(json.dumps(hashes,indent=2)+'\n').encode()
    output=ROOT/'downloads/botrblx.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for name,data in sorted(contents.items()):
            item=zipfile.ZipInfo(name,(2026,11,1,0,0,0));item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16
            z.writestr(item,data,compresslevel=9)
    with zipfile.ZipFile(output)as z:
        assert z.testzip()is None
        for name,data in contents.items():assert z.read(name)==data
    print(json.dumps({'zip':str(output),'files':len(contents),'bytes':output.stat().st_size,
        'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}))

if __name__=='__main__':main()
