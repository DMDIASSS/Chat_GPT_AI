"""Maintainer tool: sample the analytic arena into an inspectable OBJ preview.

Needs a Luau CLI (--luau or LUAU_BIN). The Windows bot does not need this tool;
its runtime queries the more precise analytic surface instead of this mesh.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np

from export_standalone import literal,load_arena_profile

HERE=Path(__file__).resolve().parent
CORNERS=np.array([(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)])
TETRA=((0,1,2,6),(0,2,3,6),(0,3,7,6),(0,7,4,6),(0,4,5,6),(0,5,1,6))
EDGES=((0,1),(0,2),(0,3),(1,2),(1,3),(2,3))


def triangulate(axes,field):
    values=np.stack([field[c[0]:field.shape[0]-1+c[0],c[1]:field.shape[1]-1+c[1],c[2]:field.shape[2]-1+c[2]] for c in CORNERS])
    cells=np.argwhere((values.max(axis=0)>0)&(values.min(axis=0)<=0))
    vertices=[];faces=[];index={};seen=set()
    def vertex(point):
        key=tuple(np.round(point,6))
        if key not in index:index[key]=len(vertices)+1;vertices.append(key)
        return index[key]
    for cell in cells:
        grid=cell+CORNERS
        positions=np.array([[axes[i][p[i]] for i in range(3)] for p in grid])
        distance=field[tuple(grid.T)]
        for tetra in TETRA:
            p=positions[list(tetra)];d=distance[list(tetra)];inside=d>0
            if inside.all() or not inside.any():continue
            polygon=[]
            for a,b in EDGES:
                if inside[a]!=inside[b]:polygon.append(p[a]+(p[b]-p[a])*d[a]/(d[a]-d[b]))
            polygon=np.unique(np.round(polygon,6),axis=0)
            if len(polygon)<3:continue
            normal=np.cross(polygon[1]-polygon[0],polygon[2]-polygon[0])
            magnitude=np.linalg.norm(normal)
            if magnitude<1e-8:continue
            normal/=magnitude
            toward_free=p[inside].mean(axis=0)-p[~inside].mean(axis=0)
            if normal@toward_free<0:normal=-normal
            center=polygon.mean(axis=0);u=polygon[0]-center;u/=np.linalg.norm(u);v=np.cross(normal,u)
            polygon=polygon[np.argsort(np.arctan2((polygon-center)@v,(polygon-center)@u))]
            ids=[vertex(point) for point in polygon]
            for i in range(1,len(ids)-1):
                face=(ids[0],ids[i],ids[i+1]);key=tuple(sorted(face))
                if len(set(face))==3 and key not in seen:seen.add(key);faces.append(face)
    return vertices,faces


def build(profile,luau,step):
    a=profile["arena"]
    x=np.ceil((a["EXTENT_X"]+step)/step)*step
    y=np.ceil((a["GOAL_BACK_Y"]+step)/step)*step
    z=np.ceil((a["HEIGHT"]+step)/step)*step
    axes=[np.arange(-x,x+step/2,step),np.arange(-y,y+step/2,step),np.arange(-step,z+step/2,step)]
    source="local Arena=(function()\n"+(HERE/"templates/local_arena.lua").read_text()+"\nend)()\n"
    source+="local arena=Arena.new("+literal(profile)+")\n"
    source+="local axes="+literal([v.tolist() for v in axes])+"\n"
    source+="for _,x in ipairs(axes[1])do for _,y in ipairs(axes[2])do for _,z in ipairs(axes[3])do print(arena:distance({x,y,z}))end end end\n"
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/"sample.luau";path.write_text(source,encoding="utf-8")
        result=subprocess.run([luau,str(path)],capture_output=True,text=True,check=True,timeout=120)
    field=np.fromstring(result.stdout,sep=" ").reshape(tuple(map(len,axes)))
    return triangulate(axes,field)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--luau",default=os.environ.get("LUAU_BIN")or shutil.which("luau"))
    parser.add_argument("--profile",type=Path,default=HERE/"arena_profile.json")
    parser.add_argument("--step",type=float,default=128)
    parser.add_argument("--output",type=Path,default=HERE/"arena_collision_preview.obj")
    args=parser.parse_args()
    if not args.luau:parser.error("Set --luau or LUAU_BIN to a Luau CLI")
    if args.step<32:parser.error("Preview grid step must be at least 32 simulation units")
    profile=load_arena_profile(args.profile)
    vertices,faces=build(profile,args.luau,args.step)
    with args.output.open("w",encoding="ascii") as out:
        out.write("# Collision preview only. Runtime uses the analytic arena; actor has no mesh input.\n")
        out.write("# Axes: simulator X/Y horizontal, Z up; 1 Roblox stud = 10 simulation units.\n")
        for p in vertices:out.write("v %.6f %.6f %.6f\n"%p)
        for face in faces:out.write("f %d %d %d\n"%face)
    metadata={"profile":profile["name"],"profile_sha256":hashlib.sha256(args.profile.read_bytes()).hexdigest(),
        "step_sim_units":args.step,"vertices":len(vertices),"triangles":len(faces),
        "purpose":"Approximate inspection mesh; runtime uses exact analytic collision maths; not a model input"}
    args.output.with_suffix(".json").write_text(json.dumps(metadata,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(metadata))


if __name__=="__main__":main()
