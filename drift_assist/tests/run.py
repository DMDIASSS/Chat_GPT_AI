"""Pure control/roads, compile and full standalone UI / physics lifecycle regressions."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--luau", default="luau")
    parser.add_argument("--compiler", default="luau-compile")
    args = parser.parse_args()
    for name in ("test_controller.lua", "test_roads.lua", "test_input_lease.lua", "test_driving.lua", "test_autorail.lua", "test_surface.lua", "test_elevation.lua"):
        subprocess.run([args.luau, str(ROOT / "tests" / name)], check=True, timeout=40)
    spec = importlib.util.spec_from_file_location("drift_build", ROOT / "build.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    source = builder.source()
    assert source == (ROOT / "HowToDrift_Assist.lua").read_text(encoding="utf8")
    compiled = subprocess.run([args.compiler, str(ROOT / "HowToDrift_Assist.lua")], capture_output=True, text=True, timeout=30)
    assert compiled.returncode == 0, compiled.stderr
    for prohibited in (":FireServer(", ":InvokeServer(", "HttpGet(", "loadstring(", "setthreadidentity", "getgc("):
        assert prohibited not in source, prohibited
    fixture = (ROOT / "tests" / "roblox_fixture.lua").read_text(encoding="utf8")
    checks = r'''
local first=assert(env.__HowToDriftAssist)
assert(first.alive and first.enabled and first.version=='1.2.0' and first.settings.mode=='road')
local car,root,seat=spawnCar()
car:SetAttribute('HomeCF',cf(0,Vector3.new(0,2,80)))
local maps=object('Folder',services.ReplicatedStorage,'Minimap')
local road=object('StringValue',maps,'TestRoad');road.Value='line|36|0,100;0,-300'
first.settings.angle=75
for _=1,120 do step() end
assert(not first.lastError,first.lastError)
assert(first.physicsWrites>0 and math.abs(first.lastCommand.targetAngle-60)<1e-6)
assert(player:GetAttribute('DebugInput') and root.pivots>0)
assert(math.abs(first.loopAnchor.s-20)<1)
local writes=first.physicsWrites
input.focus=object('TextBox');step();assert(first.physicsWrites==writes and player:GetAttribute('DebugInput')==nil)
input.focus=nil;step();assert(first.physicsWrites>writes)
root.Position=Vector3.new(500,100,500);step()
assert(root.Position.Y<5 and first.enabled and not first.lastError)
local n=first.physicsWrites
car:SetAttribute('NetOwner',999);step();assert(first.physicsWrites==n)
car:SetAttribute('NetOwner',player.UserId)
findCreated('Side').Activated:Fire();step();assert(first.enabled)
findCreated('FarmTravel').Activated:Fire();step();assert(first.enabled and first.settings.farmTravel=='area')
findCreated('Mode').Activated:Fire();step();assert(first.enabled and first.settings.style=='cool')
services.Workspace.clockOffset=1793290000
player:SetAttribute('RaceGoAt',services.Workspace:GetServerTimeNow()+10)
n=first.physicsWrites;step();assert(first.physicsWrites==n)
player:SetAttribute('RaceGoAt',nil)
step()
first.setStyle('farm');first.settings.farmTravel='loop'
first.rail.s=first.path.total-.01;first.rail.direction=1;first.rail.speed=50
step();assert(first.rail.loops>=1 and first.enabled and first.lastCommand.contacts==4)
assert(root.Position.Z>75 and root.Position.Z<85,'Loop must return to the recorded spawn')
first.stop();assert(not first.enabled and player:GetAttribute('DebugInput')==nil)
n=first.physicsWrites;step();assert(first.physicsWrites==n)
findCreated('Diagnostics').Activated:Fire();assert(savedFiles['HowToDrift_Diagnostics.json'])
local oldConnections=first.connections
'''
    after = r'''
local second=assert(env.__HowToDriftAssist)
assert(second~=first and not first.alive and second.alive and second.enabled)
for _,c in ipairs(oldConnections) do assert(not c.active) end
for _=1,5 do step() end
assert(not second.lastError,second.lastError)
-- Sloping/banked floor with both a tunnel roof and a mountain above it.
car:Destroy()
local tunnelCar,tunnelRoot=spawnCar()
local grade,bank=.12,.3
local normal=Vector3.new(-grade,1,-bank).Unit
services.Workspace.raycastOverride=function(origin,direction,_params)
 local denominator=direction.Y-grade*direction.X-bank*direction.Z
 if math.abs(denominator)<1e-8 then return nil end
 local best
 for _,level in ipairs({0,3,50}) do
  local t=(grade*origin.X+bank*origin.Z+level-origin.Y)/denominator
  if t>=0 and t<=1 and (not best or t<best.t) then
   best={t=t,Position=origin+direction*t,Normal=normal,Distance=direction.Magnitude*t,
    Material=Enum.Material.Asphalt,Instance=floorPart}
  end
 end
 return best
end
second.settings.style='farm';second.settings.farmTravel='area';second.settings.cruiseKmh=500
local signs={}
for _=1,360 do
 step()
 assert(not second.lastError,second.lastError)
 assert(second.lastCommand and second.lastCommand.contacts==4,second.status)
 local p=tunnelRoot.Position
 local floor=grade*p.X+bank*p.Z
 assert(p.Y-floor>1 and p.Y-floor<2.8,'Must stay on the tunnel floor')
 assert(math.abs(tunnelRoot.CFrame.UpVector.X)>.05 and math.abs(tunnelRoot.CFrame.UpVector.Z)>.1)
 assert(math.abs(tunnelRoot.AssemblyLinearVelocity.Magnitude*1.2-500)<1e-4)
 signs[math.sign(second.lastCommand.targetAngle)]=true
end
assert(signs[1] and signs[-1])
print('PASS standalone banked tunnel: floor below roof/mountain, four supports and 500 km/h forward/reverse')
services.Workspace.raycastOverride=nil
local map2=object('StringValue',maps,'MapTwo');map2.Value='line|36|1000,100;1000,-300'
tunnelCar:SetAttribute('HomeCF',cf(0,Vector3.new(1000,2,80)))
tunnelRoot.Position=Vector3.new(1000,2,0)
step()
assert(second.enabled and not second.lastError,second.lastError)
assert(second.path.name:find('MapTwo') and tunnelRoot.Position.X>990)
local previousPath=second.path
map2.Value='line|36|1000,100;1000,-500'
step()
assert(second.path~=previousPath and second.loopAnchor.path~=previousPath and second.enabled)
print('PASS official map teleport and changed road data reselect without a restart or stale loop anchor')
player:SetAttribute('DebugInput','external');step();assert(not second.enabled)
second.destroy();assert(env.__HowToDriftAssist==nil and player:GetAttribute('DebugInput')=='external')
assert(#warnings==0,warnings[1])
print('PASS armed autorun, Farm/Cool/Area UI, four-wheel pose, recovery, pauses, spawn loop, stop and reinjection')
'''
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "lifecycle.luau"
        path.write_text(fixture + "\ndo\n" + source + "\nend\n" + checks + "\ndo\n" + source + "\nend\n" + after, encoding="utf8")
        subprocess.run([args.luau, str(path)], check=True, timeout=40)
    print("PASS generated file, compile and no remote/admin calls")


if __name__ == "__main__":
    main()
