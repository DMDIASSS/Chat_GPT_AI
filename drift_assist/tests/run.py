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
    for name in ("test_controller.lua", "test_roads.lua", "test_input_lease.lua", "test_driving.lua"):
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
assert(first.alive and not first.enabled and first.version=='1.0.0')
local start=assert(findCreated('Start'))
start.Activated:Fire();step();assert(first.enabled and not first.lastError)
assert(first.status=='Spawn / enter your own car')
local car,root,seat=spawnCar()
input.held.W=true;input.held.A=true
for _=1,35 do step() end
assert(first.physicsWrites>0 and first.lastCommand.targetAngle>0 and player:GetAttribute('DebugInput')==nil)
assert(root.AssemblyAngularVelocity.Y>0)
local writes=first.physicsWrites
input.focus=object('TextBox');step();assert(first.physicsWrites==writes)
input.focus=nil
services.GuiService.MenuIsOpen=true;step();assert(first.physicsWrites==writes)
services.GuiService.MenuIsOpen=false
input.WindowFocusReleased:Fire();step();assert(first.physicsWrites==writes)
input.WindowFocused:Fire()
car:SetAttribute('NetOwner',999);step();assert(first.physicsWrites==writes)
car:SetAttribute('NetOwner',player.UserId)
root.Anchored=true;step();assert(first.physicsWrites==writes)
root.Anchored=false
humanoid.SeatPart=nil;step();assert(first.physicsWrites==writes)
humanoid.SeatPart=seat
player:SetAttribute('InGarage',true);step();assert(first.physicsWrites==writes)
player:SetAttribute('InGarage',nil)
services.Workspace.clockOffset=1793290000
player:SetAttribute('RaceGoAt',services.Workspace:GetServerTimeNow()+10)
step();assert(first.physicsWrites==writes)
player:SetAttribute('RaceGoAt',nil)
root.CFrame.UpVector=Vector3.new(0,-1,0);step();assert(first.physicsWrites==writes)
root.CFrame.UpVector=Vector3.new(0,1,0)
root.Position=Vector3.new(0,30,0);step();assert(first.physicsWrites==writes)
root.Position=Vector3.new(0,2,0)
local maps=object('Folder',services.ReplicatedStorage,'Minimap')
local road=object('StringValue',maps,'TestRoad');road.Value='line|36|0,100;0,-300'
input.held.A=nil
first.setMode('road')
for _=1,10 do step() end
assert(not first.lastError,first.lastError)
assert(first.path and first.lastCommand.override and player:GetAttribute('DebugInput'))
assert(first.inputWrites>0 and not first.lastCommand.reason:find('Obstacle'))
input.held.S=true;step();assert(player:GetAttribute('DebugInput')==nil and not first.lastCommand.override)
input.held.S=nil;step();assert(player:GetAttribute('DebugInput'))
input.focus=object('TextBox');step();assert(player:GetAttribute('DebugInput')==nil)
input.focus=nil;step();assert(player:GetAttribute('DebugInput'))
start.Activated:Fire();assert(not first.enabled and player:GetAttribute('DebugInput')==nil)
local stopped=first.physicsWrites
for _=1,10 do step() end
assert(first.physicsWrites==stopped)
findCreated('Diagnostics').Activated:Fire()
assert(savedFiles['HowToDrift_Diagnostics.json'] and services.HttpService.lastEncoded.trace)
local oldConnections=first.connections
'''
    after = r'''
local second=assert(env.__HowToDriftAssist)
assert(second~=first and not first.alive and not first.enabled and second.alive and not second.enabled)
for _,c in ipairs(oldConnections) do assert(not c.active) end
assert(player:GetAttribute('DebugInput')==nil and #warnings==0)
second.setMode('road');second.start()
for _=1,5 do step() end
assert(player:GetAttribute('DebugInput'))
player:SetAttribute('DebugInput','external');step()
assert(not second.enabled and player:GetAttribute('DebugInput')=='external')
second.destroy();assert(env.__HowToDriftAssist==nil and player:GetAttribute('DebugInput')=='external')
for _,c in ipairs(second.connections) do assert(not c.active) end
print('PASS standalone start, manual drive, auto road, native brake override, pause, ownership, stop, diagnostics and reinjection')
'''
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "lifecycle.luau"
        path.write_text(fixture + "\ndo\n" + source + "\nend\n" + checks + "\ndo\n" + source + "\nend\n" + after, encoding="utf8")
        subprocess.run([args.luau, str(path)], check=True, timeout=40)
    print("PASS generated file, compile and no remote/admin calls")


if __name__ == "__main__":
    main()
