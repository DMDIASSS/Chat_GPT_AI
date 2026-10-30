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
    for name in ("test_controller.lua", "test_roads.lua", "test_input_lease.lua", "test_driving.lua", "test_autorail.lua"):
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
assert(first.alive and first.enabled and first.version=='1.1.0' and first.settings.mode=='road')
local car,root,seat=spawnCar()
local maps=object('Folder',services.ReplicatedStorage,'Minimap')
local road=object('StringValue',maps,'TestRoad');road.Value='line|36|0,100;0,-300'
first.settings.angle=75
for _=1,120 do step() end
assert(not first.lastError,first.lastError)
assert(first.physicsWrites>0 and first.lastCommand.targetAngle==75)
assert(player:GetAttribute('DebugInput') and root.pivots>0)
local writes=first.physicsWrites
input.focus=object('TextBox');step();assert(first.physicsWrites==writes and player:GetAttribute('DebugInput')==nil)
input.focus=nil;step();assert(first.physicsWrites>writes)
root.Position=Vector3.new(500,100,500);step()
assert(root.Position.Y<5 and first.enabled and not first.lastError)
local n=first.physicsWrites
car:SetAttribute('NetOwner',999);step();assert(first.physicsWrites==n)
car:SetAttribute('NetOwner',player.UserId)
findCreated('Side').Activated:Fire();step();assert(first.enabled)
findCreated('Mode').Activated:Fire();step();assert(first.enabled)
services.Workspace.clockOffset=1793290000
player:SetAttribute('RaceGoAt',services.Workspace:GetServerTimeNow()+10)
n=first.physicsWrites;step();assert(first.physicsWrites==n)
player:SetAttribute('RaceGoAt',nil)
step()
first.rail.s=first.path.total-.01;first.rail.direction=1;first.rail.speed=50
step();assert(first.rail.direction==-1 and first.enabled)
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
player:SetAttribute('DebugInput','external');step();assert(not second.enabled)
second.destroy();assert(env.__HowToDriftAssist==nil and player:GetAttribute('DebugInput')=='external')
assert(#warnings==0,warnings[1])
print('PASS armed autorun, 75-degree pose, teleport recovery, reverse/rejoin without restart, pauses, end turnaround, stop and reinjection')
'''
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "lifecycle.luau"
        path.write_text(fixture + "\ndo\n" + source + "\nend\n" + checks + "\ndo\n" + source + "\nend\n" + after, encoding="utf8")
        subprocess.run([args.luau, str(path)], check=True, timeout=40)
    print("PASS generated file, compile and no remote/admin calls")


if __name__ == "__main__":
    main()
