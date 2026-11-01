"""Package this independent assist and verify every archived source byte."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT.parent/"downloads/Backseat_Rally_Assist.zip"


def main():
    spec=importlib.util.spec_from_file_location("rally_build",ROOT/"build.py")
    build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
    (ROOT/"Backseat_Rally_Assist.lua").write_text(build.source(),encoding="utf-8",newline="\n")
    files=sorted(p for p in ROOT.rglob("*")if p.is_file()and p.suffix in {".lua",".py",".md",".json"}
                 and "__pycache__"not in p.parts and p.name not in {"SOURCE_INFO.json","BackseatRally_Report.json","BackseatRally_Ghosts.json"})
    manifest={"version":"1.1.0","entrypoint":"Backseat_Rally_Assist.lua","place_id":94278659624110,
        "uploaded_place_sha256":"be6b8add4aff71085492872588a7440427438bbec01710e1d2b3a61dad90ef93",
        "reference":"Numeric stage geometry and menu showcase samples from the user-provided place. Not a verified world record.",
        "includes_original_game_sources":False,"includes_personal_ghosts":False,"files":{
        p.relative_to(ROOT).as_posix():{"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size}for p in files}}
    info=ROOT/"SOURCE_INFO.json";info.write_text(json.dumps(manifest,indent=2)+"\n");files.append(info)
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(OUTPUT,"w",zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for p in files:
            item=zipfile.ZipInfo("Backseat_Rally_Assist/"+p.relative_to(ROOT).as_posix(),(2026,11,1,0,0,0))
            item.compress_type=zipfile.ZIP_DEFLATED;item.external_attr=0o100644<<16
            z.writestr(item,p.read_bytes(),compresslevel=9)
    with zipfile.ZipFile(OUTPUT)as z:
        assert z.testzip()is None
        for p in files:assert z.read("Backseat_Rally_Assist/"+p.relative_to(ROOT).as_posix())==p.read_bytes()
    print(json.dumps({"zip":str(OUTPUT),"bytes":OUTPUT.stat().st_size,"files":len(files),
        "sha256":hashlib.sha256(OUTPUT.read_bytes()).hexdigest()},indent=2))


if __name__=="__main__":main()
