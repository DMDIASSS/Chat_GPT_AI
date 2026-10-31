"""Optional: run the uploaded game's tyre/contact code on our fitted road-plane poses."""
import argparse
from pathlib import Path
import subprocess
import tempfile

from check_place import make_harness

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scripts-dir", type=Path, required=True)
    parser.add_argument("--luau", default="luau")
    args = parser.parse_args()
    source = make_harness(args.scripts_dir).split("do\nlocal UserInputService, LocalPlayer", 1)[0]
    source += "\nlocal Surface=(function()\n" + (ROOT / "surface.lua").read_text() + "\nend)()\n"
    source += r'''
local cases=0
for _,grade in ipairs({-.5,0,.5}) do
for _,bank in ipairs({-.4,0,.6}) do
for _,angle in ipairs({-180,-120,-90,-75,-60,0,35,60,75,90,120,180}) do
for _,kmh in ipairs({85,500,10000}) do
 local length=math.sqrt(1+grade*grade+bank*bank)
 local up=Vector3.new(-grade,1,-bank)/length
 local floor=12
 World.raycastOverride=function(origin,direction,_params)
  local denominator=direction.Y-grade*direction.X-bank*direction.Z
  if math.abs(denominator)<1e-8 then return nil end
  local t=(grade*origin.X+bank*origin.Z+floor-origin.Y)/denominator
  if t<0 or t>1 then return nil end
  return {Position=origin+direction*t,Normal=up,Distance=direction.Magnitude*t,Material=Enum.Material.Asphalt,Instance=floorPart}
 end
 local car,root=spawnCar()
 local geometry={}
 for _,name in ipairs({'FL','FR','RL','RR'}) do
  local p=root:FindFirstChild(name).Position
  table.insert(geometry,{name=name,x=p.X,y=p.Y,z=p.Z,reach=1.94})
 end
 local function query(x,y,z,d)
  local hit=World:Raycast(Vector3.new(x,y,z),Vector3.new(0,-d,0),{})
  if hit then return {x=hit.Position.X,y=hit.Position.Y,z=hit.Position.Z,up={x=up.X,y=up.Y,z=up.Z}} end
 end
 local fit,why=Surface.solve({x=0,z=0},.5,math.rad(angle),geometry,{x=0,y=floor,z=0,up={x=up.X,y=up.Y,z=up.Z}},query)
 assert(fit,why)
 local p,r,u,f=fit.position,fit.right,fit.up,fit.forward
 local target=CFrame.fromMatrix(Vector3.new(p.x,p.y,p.z),Vector3.new(r.x,r.y,r.z),Vector3.new(u.x,u.y,u.z),Vector3.new(-f.x,-f.y,-f.z))
 car:PivotTo(target)
 local v=fit.travel
 root.AssemblyLinearVelocity=Vector3.new(v.x,v.y,v.z)*kmh/1.2
 local engine=CarPhysics.new(car,cfg)
 engine:step(1/120,{throttle=.6,brake=0,steer=0,handbrake=false,analogSteer=true})
 assert(engine.groundedCount==4,'Original CarPhysics did not find all four wheels')
 assert(math.abs(engine.speed*1.2-kmh)<1e-5)
 local expected=if math.abs(angle)>90 then math.sign(angle)*(180-math.abs(angle)) else angle
 assert(math.abs(math.deg(engine.beta)-expected)<1e-5,'Native drift angle differs')
 cases+=1;car:Destroy()
end
end
end
end
print('PASS original CarPhysics: '..cases..' four-wheel contacts, bank/grade, forward/reverse angles and 85/500/10000 km/h poses')
print('Scope: mocked road planes and rigid-body calls, not live Roblox collision/network validation')
'''
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "contact_check.luau"
        path.write_text(source, encoding="utf8")
        subprocess.run([args.luau, str(path)], check=True, timeout=45)


if __name__ == "__main__":
    main()
