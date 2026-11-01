"""Run the documented synthetic driving checks and save machine-readable results."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def run():
    spec=importlib.util.spec_from_file_location("rally_build",ROOT/"build.py")
    build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
    source=""
    for name,file in (("Route","route.lua"),("Driver","controller.lua")):
        source+="local "+name+"=(function()\n"+(ROOT/file).read_text()+"\nend)()\n"
    source+="local stages="+build.literal(json.loads((ROOT/"stage_profiles.json").read_text()))+"\n"
    source+="local reels="+build.literal(json.loads((ROOT/"showcase_lines.json").read_text()))+"\n"
    source+="local simulate=(function()\n"+(ROOT/"tests/planar.lua").read_text()+"\nend)()\n"
    source+='''for _,r in ipairs(simulate(Route,Driver,stages,reels))do
 print(r.stage,r.hz,r.seconds,r.max_center_deviation,r.min_body_edge_clearance,r.complete)
end
'''
    luau=os.environ.get("LUAU_BIN")or shutil.which("luau")or "/tmp/roworld-luau-source/luau"
    with tempfile.TemporaryDirectory()as directory:
        path=Path(directory)/"planar.luau";path.write_text(source)
        result=subprocess.run([luau,str(path)],capture_output=True,text=True,timeout=60)
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    reports=[]
    for line in result.stdout.splitlines():
        stage,hz,seconds,cross,clearance,complete=line.split("\t")
        reports.append(dict(stage=stage,hz=int(hz),seconds=float(seconds),max_center_deviation=float(cross),min_body_edge_clearance=float(clearance),complete=complete=="true"))
    return {"model":"Independent planar bicycle; actuator lag and grip cap; no Roblox suspension/collisions/networking",
            "results":reports,"all_complete":all(r["complete"]for r in reports)}


if __name__=="__main__":
    report=run()
    print(json.dumps(report,indent=2))
