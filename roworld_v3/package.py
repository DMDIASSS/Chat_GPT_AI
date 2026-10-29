"""Rebuild a source/standalone ZIP without private engines, models, reports or environments."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import build

ROOT=Path(__file__).resolve().parent
EXCLUDE={"private","runs","tools","__pycache__",".venv",".git"}


def main():
    target=ROOT/"RoWorld_V3.lua"
    target.write_text(build.source(),encoding="utf8",newline="\n")
    files=sorted(p for p in ROOT.rglob("*") if p.is_file() and not any(x in EXCLUDE for x in p.relative_to(ROOT).parts)
                 and p.name!="SOURCE_INFO.json" and p.suffix not in (".pyc",".pt",".pth",".log",".zip",".tmp")
                 and p.name not in ("RoWorld_V3_Trained.lua","evaluation.json")
                 and not p.name.startswith("RoWorld_Match_Report"))
    info={"version":"3.0.0","observation_schema":"roworld-observation-v1","default_policy":"built-in; no neural weights bundled",
          "place_id":137151641329864,"inspected_place_version":111,
          "place_sha256":"8be1727d80e44d4c1b0045b7ff7f19c39f8251e58efedca18f2243676f988399",
          "inspiration":"https://github.com/djmango/openfront-ai",
          "reference_commit":"474536340480659c53d9a9e497b08fa1fefb9589",
          "upstream_source_or_weights_bundled":False,
          "retained_infrastructure":"Our own RoWorld v2.4 connection, mirror, protocol, rule helpers, cooperation, profiles, recorder and UI; decision core independently rewritten",
          "infrastructure_parent_commit":"18015f7c3a16ad35be18746653353eb9f332d5e8",
          "parameters_if_trained":9250,"live_jjsploit_verified":False,"competitive_strength_verified":False,
          "files":{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    manifest=ROOT/"SOURCE_INFO.json";manifest.write_text(json.dumps(info,indent=2)+"\n",encoding="utf8")
    archive=ROOT.parent/"downloads/RoWorld_V3.zip";archive.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(archive,"w",ZIP_DEFLATED,compresslevel=9) as z:
        for p in files+[manifest]:z.write(p,"roworld_v3/"+str(p.relative_to(ROOT)).replace('\\','/'))
    with ZipFile(archive) as z:
        assert z.testzip() is None
        for p in files+[manifest]:assert z.read("roworld_v3/"+str(p.relative_to(ROOT)).replace('\\','/'))==p.read_bytes()
    print(archive,archive.stat().st_size,hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__=='__main__':main()
