"""Original saved stages and original car objects remain the default when present."""
import unittest
import test_game as h

MAP='''
local world=Instance.new('Folder',workspace);world.Name='World'
local stage=Instance.new('Folder',world);stage.Name='Stage_SakuraPass'
local collision=Instance.new('Folder',stage);collision.Name='Collision'
local road=Instance.new('Part',collision);road.Name='Road';road.Size=Vector3.new(16,2,180);road.CFrame=CFrame.new(0,79,-70);road.Transparency=1
road.Color=Color3.new(.6,.6,.6);road.Material=Enum.Material.Plastic
local shoulder=Instance.new('Part',collision);shoulder.Name='Shoulder';shoulder.Transparency=1;shoulder.Color=Color3.new(.6,.6,.6);shoulder.Material=Enum.Material.Plastic
local tree=Instance.new('Part',stage);tree.Name='OriginalTree';tree.Transparency=0;tree.Color=Color3.new(.2,.5,.1)
'''
class OriginalCourseTests(unittest.TestCase):
    run_lua=h.GameTests.run_lua
    def test_original_stage_geometry_hairpins_and_coordinate_frame(self):
        self.run_lua(h.roblox('''
local O=require(nodes['Shared/OriginalCourse.lua']);local C=require(nodes['Shared/Config.lua'])
local r=O.new('SakuraPass',C,5);assert(r.original and r.length==5260)
assert((r:worldPoint(0)-Vector3.new(0,80,-40)).Magnitude<.01)
local turns,backtracking=0,false
for z=0,r.length,4 do
 local p=r:point(z);local a,b=r:worldPoint(z),r:worldPoint(z+1)
 assert(p.y==p.y and math.abs(p.dy)<1 and math.abs(p.curvature)<.06)
 if math.abs(p.curvature)>.03 then turns+=1 end
 if b.Z>a.Z then backtracking=true end
 local cf=r:frame({x=0,z=z,yaw=0},Vector3.zero,p.y+2.2,0,0)
 assert((cf.Position-Vector3.new(a.X,p.y+2.2,a.Z)).Magnitude<.01)
 if z<r.length-5 then assert(cf.LookVector:Dot(Vector3.new(b.X-a.X,0,b.Z-a.Z).Unit)>.96,'Car faces away from the actual road')end
end
assert(turns>20 and backtracking,'Original hairpins were replaced by a monotone procedural road')
local pine=O.new('PineForest',C,5);assert(pine.incomplete and pine.length==1780 and pine.stage.originalFinish==5440)
''',server=False))

    def test_digital_controls_can_complete_original_saved_sakura(self):
        self.run_lua(h.roblox('''
local O=require(nodes['Shared/OriginalCourse.lua']);local C=require(nodes['Shared/Config.lua']);local D=require(nodes['Shared/Dynamics.lua'])
local r=O.new('SakuraPass',C,5);local car=C.Cars[1];local s=D.new(r);local maxLateral=0
for i=1,100000 do
 local curvature=r:point(s.z+4).curvature;local maximum=0
 for ahead=0,130,10 do maximum=math.max(maximum,math.abs(r:point(s.z+ahead).curvature))end
 local target=math.min(42,math.sqrt(11/math.max(.001,maximum)))
 local world=r:frame(s,Vector3.zero,r:point(s.z).y,0,0).Position
 local targetPoint=r:worldPoint(s.z+10+math.abs(s.v)*.4)
 local desired=math.atan2(targetPoint.X-world.X,targetPoint.Z-world.Z)
 local delta=(desired-r:sample(s.z).heading-s.yaw+math.pi)%(2*math.pi)-math.pi
 local length=math.max(5,math.sqrt((targetPoint.X-world.X)^2+(targetPoint.Z-world.Z)^2))
 local angle=-math.atan(2*math.sin(delta)/length*car.wheelbase)
 local steer=math.clamp(angle/(math.rad(car.steering.MaxAngle)/(1+math.abs(s.v)/95)),-1,1)
 D.step(s,{throttle=s.v<target and 1 or 0,brake=s.v>target+1 and .6 or 0,steer=steer},r,car,C.Step)
 maxLateral=math.max(maxLateral,math.abs(s.x));assert(s.x==s.x and s.z==s.z)
 if s.z>=r.length then break end
end
assert(s.z>=r.length,'Original course cannot be completed with supported steering')
assert(maxLateral<7.5,'Driving the original route requires leaving its road')
''',server=False),timeout=60)

    def test_native_road_appearance_is_reused_then_restored(self):
        self.run_lua(h.roblox(MAP+'''
local C=require(nodes['Shared/Config.lua']);local O=require(nodes['Shared/OriginalCourse.lua']);local S=require(nodes['Client/RoadStream.lua'])
local oldColor,oldMaterial=road.Color,road.Material;local count=#created
local stream=S.new(workspace);stream:reset(O.new('SakuraPass',C),8,4096);stream:update(0);stream:work(.003)
assert(stream:offset()==Vector3.zero and stream:ready(0))
assert(road.Transparency==0 and shoulder.Transparency==0 and tree.Transparency==0)
assert(road.Parent==collision and tree.Parent==stage and #created==count+1,'Original map was replaced or duplicated')
stream:shift(-4096);assert(road.Position.Z==-70,'Baked original map was rebased')
stream:destroy();assert(road.Transparency==1 and shoulder.Transparency==1 and road.Color==oldColor and road.Material==oldMaterial)
assert(tree.Parent==stage,'Closing the rally deleted original scenery')
''',server=False))

    def test_server_spawns_on_original_map_and_restores_replication_focus(self):
        self.run_lua(h.roblox('''
local start;remotes.Action.OnClientEvent:Connect(function(k,d)if k=='start'then start=d end end)
local oldFocus=Instance.new('Part',workspace);localPlayer.ReplicationFocus=oldFocus
remotes.Action.OnServerEvent:Fire(localPlayer,'start',{mode='sprint',seed=5})
advance(.2);assert(start.stage=='SakuraPass'and start.length==5260 and start.originZ==0)
local model=workspace.Rally_101;assert(math.abs(model.Root.Position.Z+40)<.01 and model.Root.Position.X==0)
assert(localPlayer.ReplicationFocus==model.Root,'Streaming focus stayed at the old garage')
remotes.Action.OnServerEvent:Fire(localPlayer,'ready',{});advance(3.4)
remotes.Action.OnServerEvent:Fire(localPlayer,'retire',{});advance(.3)
assert(localPlayer.ReplicationFocus==oldFocus)
''',before_server=MAP))

    def test_client_uses_original_map_and_keeps_camera_near_it(self):
        self.run_lua(h.roblox('''
local function click(text)for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==text then o.Activated:Fire();return end end;error(text)end
click('TAKE THE ROAD →');advance(6,true)
assert(math.abs(workspace.CurrentCamera.CFrame.Position.X)<10 and workspace.CurrentCamera.CFrame.Position.Z<0,'Client still drives in generated distant lanes')
assert(road.Transparency==0 and workspace.ExpeditionLocal.RallyWorld)
assert(#workspace.ExpeditionLocal.RallyWorld:GetChildren()==0,'Procedural chunks replaced original scenery')
click('RETURN TO ORIGINAL');advance(4,true);assert(road.Transparency==1 and tree.Parent==stage)
''',before_server=MAP,client=True),timeout=60)
    def test_saved_map_obstacle_cast_stops_the_car_and_records_an_impact(self):
        self.run_lua(h.roblox('''
local latest;remotes.State.OnClientEvent:Connect(function(p)latest=p.runs[1]end)
remotes.Action.OnServerEvent:Fire(localPlayer,'start',{mode='sprint',seed=5})
advance(.2);remotes.Action.OnServerEvent:Fire(localPlayer,'ready',{});advance(3.4)
for i=1,80 do remotes.Input.OnServerEvent:Fire(localPlayer,{seq=i,throttle=1});advance(.05)end
local progress=latest.s.z;local crashes=latest.s.crashes;assert(latest.s.v>10)
blocked=true
for i=81,90 do remotes.Input.OnServerEvent:Fire(localPlayer,{seq=i,throttle=1});advance(.05)end
assert(latest.s.z<progress+3 and latest.s.crashes>crashes,'Original world obstacle was ignored')
assert(latest.s.impactId and latest.s.impactId>0 and casts>0)
''',before_server=MAP+'''
RaycastParams={new=function()return {}end};blocked=false;casts=0
function workspace:Blockcast(frame,size,direction,params)
 casts+=1;assert(params.RespectCanCollide and #params.FilterDescendantsInstances>=2)
 if blocked then return {Normal=-direction.Unit,Instance=tree,Distance=0}end
end
'''))

if __name__=='__main__':unittest.main()
