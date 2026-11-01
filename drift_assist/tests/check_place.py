"""Optional private-source contract / planar physics checks. Never packages game source."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def make_harness(directory):
    scripts = json.loads((directory / "scripts.json").read_text(encoding="utf8"))

    def script(name):
        record = next(s for s in scripts if s["path"] == name)
        return (directory / record["file"]).read_text(encoding="utf8")

    text = (ROOT / "tests/roblox_fixture.lua").read_text(encoding="utf8")
    for name, filename in (("Controller", "controller.lua"), ("Roads", "roads.lua"), ("InputLease", "input_lease.lua")):
        text += f"\nlocal {name}=(function()\n{(ROOT/filename).read_text(encoding='utf8')}\nend)()\n"
    text += "\nlocal cfg=(function()\n" + script("ReplicatedStorage.Drift.DriftConfig") + "\nend)()\n"
    text += "\nlocal GarageConfig=(function()\n" + script("ReplicatedStorage.Drift.GarageConfig") + "\nend)()\n"
    text += r'''
local drift=object('Folder',services.ReplicatedStorage,'Drift')
object('ModuleScript',drift,'GarageConfig')
local require=function(_) return GarageConfig end
'''
    text += "\nlocal CarPhysics=(function()\n" + script("ReplicatedStorage.Drift.CarPhysics") + "\nend)()\n"
    client = script("StarterPlayer.StarterPlayerScripts.DriftClient")
    native_read = client[client.index("local function readInput()"):client.index("\nlocal n11 = 0")]
    text += r'''
do
local UserInputService, LocalPlayer = input, player
local Settings={get=function(key) if key=='tcRWD' then return 'off' end;return true end}
local t2,v42,n2,v44={},{awd=false,race=0},0,false
local gamepadInput=function() return 0,0,0,false end
local t13={}
'''
    text += native_read
    text += r'''
local lease=InputLease.new(player)
assert(lease:write({throttle=.75,brake=.125,steer=-.6,handbrake=true}))
local parsed=readInput()
assert(parsed.throttle==.75 and parsed.brake==.125 and parsed.steer==-.6 and parsed.handbrake and parsed.analogSteer)
lease:release();assert(player:GetAttribute('DebugInput')==nil)
print('CONTRACT input_override original_readInput passed')
end
'''
    # Only numeric public-format map records are inserted into the temporary local harness.
    nodes = json.loads((directory / "tree.json").read_text(encoding="utf8"))
    minimaps = [n for n in nodes if n["class"] == "StringValue" and n["path"].startswith("ReplicatedStorage.Minimap.")]
    courses = [n for n in nodes if n["class"] == "StringValue" and n["path"].startswith("ReplicatedStorage.RaceCourses.") and n["name"] == "Points"]
    text += "\nlocal realMaps={}\nlocal mapLines, raceLines=0,0\n"
    for n in minimaps:
        value = json.dumps(n["properties"]["Value"], ensure_ascii=True)
        name = json.dumps(n["path"].split(".")[-1])
        text += f"do local paths=Roads.parseMinimap({value},{name});assert(#paths>0);mapLines+=#paths;for _,p in ipairs(paths) do table.insert(realMaps,p) end end\n"
    for n in courses:
        value = json.dumps(n["properties"]["Value"], ensure_ascii=True)
        name = json.dumps(n["path"].split(".")[-2])
        text += f"assert(Roads.parseRace({value},{name},36));raceLines+=1\n"
    text += r'''
print('CONTRACT real_map_lines '..mapLines..' race_courses '..raceLines)
local function makeRig(carId)
    local car,root=spawnCar()
    car:SetAttribute('CarId',carId)
    local effects=GarageConfig.effects(car)
    local engine=CarPhysics.new(car,cfg)
    for _,name in ipairs({'FL','FR','RL','RR'}) do
        local a=root:FindFirstChild(name)
        local front=name:sub(1,1)=='F'
        local ride=if front then effects.rideHeightF else effects.rideHeightR
        local height=cfg.suspensionRest+ride+cfg.wheelRadius-cfg.gravity/(2*math.pi*cfg.springFreq)^2
        a.localPosition=Vector3.new(a.localPosition.X,height-2,a.localPosition.Z)
    end
    return car,root,engine
end
local function simulate(carId,angle,side,hz,path,direction)
    local car,root,engine=makeRig(carId)
    local yaw=0
    if path then
        local p,h=Roads.point(path,0)
        yaw=h+(if direction<0 then math.pi else 0)
        root.Position=Vector3.new(p.x,2,p.z)
        root.AssemblyLinearVelocity=Vector3.new(-math.sin(yaw)*25,0,-math.cos(yaw)*25)
    else root.AssemblyLinearVelocity=Vector3.zero end
    root.CFrame=cf(yaw,root.Position)
    local state=Controller.new()
    local settings=Controller.settings({mode=if path then 'road' else 'manual',side=side,angle=angle,power=1.25,cruiseKmh=80})
    local previousS,maxCross,errorSum,count=nil,0,0,0
    local last
    local seconds=if path then 30 else 12
    for i=1,hz*seconds do
        local dt=1/hz;now+=dt
        local s={x=root.Position.X,y=2,z=root.Position.Z,vx=root.AssemblyLinearVelocity.X,vz=root.AssemblyLinearVelocity.Z,
            yaw=yaw,yawRate=root.AssemblyAngularVelocity.Y,grounded=4,upY=1}
        local m=Controller.measure(s)
        local guide=if path then Roads.guide(path,direction,s,m.speed,yaw,previousS) else nil
        if guide then previousS=guide.s;maxCross=math.max(maxCross,guide.crossTrack);assert(not guide.offRoad,'Departed road') end
        local driver={throttle=1,brake=0,steer=0,handbrake=false,analogSteer=true}
        local out=Controller.step(state,settings,s,if path then {} else driver,guide,dt)
        local native=if path then {throttle=out.throttle or 0,brake=out.brake or 0,steer=out.steer or 0,
            handbrake=out.handbrake,analogSteer=true} else driver
        engine:step(dt,native)
        root:ApplyImpulse(Vector3.new(out.ax,0,out.az)*root.AssemblyMass*dt)
        if out.yawRate then root.AssemblyAngularVelocity=Vector3.new(0,out.yawRate,0) end
        -- Planar rig: no collisions, suspension motion, roll/pitch, streaming or network corrections.
        yaw=Controller.wrap(yaw+root.AssemblyAngularVelocity.Y*dt)
        root.Position+=Vector3.new(root.AssemblyLinearVelocity.X,0,root.AssemblyLinearVelocity.Z)*dt
        root.CFrame=cf(yaw,root.Position)
        if i>hz*8 then errorSum+=math.abs(math.deg(m.beta)-(out.targetAngle or 0));count+=1 end
        last=out
    end
    local mean=errorSum/math.max(count,1)
    assert(mean<4,'Angle error '..mean)
    if path then assert(maxCross<path.width/2-2,'Road tracking '..maxCross) end
    assert(root.AssemblyLinearVelocity.Magnitude*1.2<90,'Unexpected speed')
    car:Destroy()
    return mean,maxCross
end
local manualCount,autoCount,worstManual,worstAuto,cross=0,0,0,0,0
for _,carId in ipairs({'S13','GTR'}) do
    for _,angle in ipairs({15,30,50}) do
        for _,side in ipairs({'left','right'}) do
            for _,hz in ipairs({30,60}) do
                local error=simulate(carId,angle,side,hz,nil,1)
                manualCount+=1;worstManual=math.max(worstManual,error)
            end
        end
    end
end
for _,radius in ipairs({40,80,140}) do
    local points={}
    for i=0,240 do local a=i/240*math.pi*2;table.insert(points,{x=radius*math.cos(a),z=radius*math.sin(a)}) end
    local path=Roads.path('Circle',points,true,30)
    for _,angle in ipairs({15,30,50}) do
        for _,direction in ipairs({1,-1}) do
            local error,offset=simulate('S13',angle,'auto',60,path,direction)
            autoCount+=1;worstAuto=math.max(worstAuto,error);cross=math.max(cross,offset)
        end
    end
end
print(string.format('METRICS manual_cases %d auto_cases %d manual_max_mean_angle_error %.8f auto_max_mean_angle_error %.8f auto_max_cross_track %.8f',
    manualCount,autoCount,worstManual,worstAuto,cross))
'''
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scripts-dir", type=Path, required=True)
    parser.add_argument("--luau", default="luau")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "private_place_check.luau"
        path.write_text(make_harness(args.scripts_dir), encoding="utf8")
        result = subprocess.run([args.luau, str(path)], capture_output=True, text=True, timeout=90)
    print(result.stdout, end="")
    if result.returncode:
        raise SystemExit(result.stderr)
    line = next(s for s in result.stdout.splitlines() if s.startswith("METRICS "))
    values = line.split()[1:]
    metrics = {values[i]: float(values[i+1]) for i in range(0, len(values), 2)}
    report = {"source": "User-supplied How To Drift place", "test": "Original CarPhysics / GarageConfig on planar fixture",
              "limitations": "Not Roblox, real 3D collision/suspension, networking, streaming or a live executor test", "metrics": metrics}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")


if __name__ == "__main__":
    main()
