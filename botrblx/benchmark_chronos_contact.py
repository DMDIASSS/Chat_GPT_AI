"""Synthetic contact checks and Luau CPU timing; no live Roblox win-rate claim."""
import argparse
import json
import os
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--luau',default=os.environ.get('LUAU_BIN'))
    parser.add_argument('--output',type=Path,default=Path('work/chronos-contact.json'))
    args=parser.parse_args()
    if not args.luau:parser.error('Pass --luau or set LUAU_BIN')
    os.environ['LUAU_BIN']=args.luau
    app=Path(__file__).resolve().parent
    sys.path[:0]=[str(app),str(app/'tests')]
    from test_contact import ContactTests
    output=ContactTests().run_case('''
local curve={{0,.53356},{500,.3193},{1000,.18203},{1500,.1057},{1750,.08507},{3000,.03454}}
local function steeringAngle(speed)
 for i=2,#curve do
  if speed<=curve[i][1]then
   local a,b=curve[i-1],curve[i]
   return a[2]+(b[2]-a[2])*(speed-a[1])/(b[1]-a[1])
  end
 end
 return curve[#curve][2]
end
local function simulation(side,speed,x,assisted)
 local p=packet(side*x,-700,speed);p.ball.velocity={-side*150,0,0}
 local driver=Contact.new(profile,arena,physics);driver:reset()
 local controls=table.clone(action)
 local yaw=0
 local config=profile.car_presets.standard
 local wheelbase=config.front.offset[1]-config.back.offset[1]
 for tick=1,240 do
  local now=tick/120
  if tick%4==1 then
   driver:observe(p,controls,now)
   controls=assisted and driver:step(p,action,now)or nil
   controls=controls or action
  end
  local yawRate=controls[2]*speed*math.tan(steeringAngle(speed))/wheelbase
  yaw+=yawRate/120
  p.car.forward={-math.sin(yaw),math.cos(yaw),0};p.car.angular_velocity={0,0,yawRate}
  if controls[1]<0 then speed=math.max(0,speed-3500/120)end
  p.car.velocity={p.car.forward[1]*speed,p.car.forward[2]*speed,0}
  for i=1,2 do p.car.position[i]+=p.car.velocity[i]/120 end
  physics:step(p.ball,p.ball_radius,1/120)
  if driver:gap(p.car,p.ball.position,p.ball_radius,config.size,config.offset)<=0 then return true end
 end
 return false
end
local baseline,assisted,total=0,0,0
for _,side in ipairs({-1,1})do
 for _,speed in ipairs({1200,1800,2200})do
  for _,x in ipairs({180,240})do
   total+=1
   if simulation(side,speed,x,false)then baseline+=1 end
   if simulation(side,speed,x,true)then assisted+=1 end
  end
 end
end
local timings={}
for round=1,110 do
 for _,side in ipairs({-1,1})do
  for _,speed in ipairs({1200,1800,2200})do
   local p=packet(side*240,-600,speed);p.ball.velocity={-side*150,0,0}
   local driver=Contact.new(profile,arena,physics);driver:reset()
   local at=os.clock()
   driver:observe(p,action,round/30)
   driver:step(p,action,round/30)
   local ms=(os.clock()-at)*1000
   if round>10 then timings[#timings+1]=ms end
  end
 end
end
local sum=0;for _,ms in ipairs(timings)do sum+=ms end;table.sort(timings)
assert(assisted>baseline,'Contact corrections did not improve the synthetic scenario set')
print(('CONTACT_JSON {"synthetic_kinematic_contacts":{"cases":%d,"straight_control_hits":%d,"assisted_hits":%d},"cpu_ms":{"mean":%.6f,"p95":%.6f,"max":%.6f,"samples":%d}}')
 :format(total,baseline,assisted,sum/#timings,timings[math.ceil(#timings*.95)],timings[#timings],#timings))
''')
    line=next(line.removeprefix('CONTACT_JSON ')for line in output.splitlines()if line.startswith('CONTACT_JSON '))
    report=json.loads(line)
    report.update(adapter_version='6.11',mode='Cloud Luau CLI VM, synthetic ground contacts',
                  limitations='Simplified bicycle steering and braking; the comparison uses a straight-driving dummy, not a trained actor. No car collisions, aerials, network latency or live Roblox hit rate.',
                  reference='Steering-angle curve and wheelbase from the saved place numeric profile; saved ball/world solver',
                  live_roblox_measured=False,model_weights_changed=False)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
