import json,math,os,shutil,subprocess,tempfile,unittest,xml.etree.ElementTree as ET,zipfile,hashlib
from pathlib import Path
APP=Path(__file__).resolve().parents[1]
LUAU=os.environ.get('LUAU_BIN')or shutil.which('luau')or 'luau'
COMPILE=os.environ.get('LUAU_COMPILE_BIN')or shutil.which('luau-compile')or 'luau-compile'

def pure(extra=''):
    text=''
    for name in ['Config','Route','Dynamics','Replay']:
        text+='local '+('C'if name=='Config'else 'D'if name=='Dynamics'else name)+'=(function()\n'+(APP/'src/Shared'/f'{name}.lua').read_text()+'\nend)()\n'
    return text+extra

def roblox(extra='',client=False,server=True,before_client='',before_server=''):
    text=(APP/'tests/roblox_mock.luau').read_text()+'\nlocal nodes={}\n'
    roots={'Shared':"services.ReplicatedStorage",'Server':'services.ServerScriptService','Client':'sps'}
    text+="local replicated=Instance.new('Folder',services.ReplicatedStorage);replicated.Name='BackseatExpedition'\n"
    text+="local shared=Instance.new('Folder',replicated);shared.Name='Shared'\nlocal remotes=Instance.new('Folder',replicated);remotes.Name='Remotes'\n"
    for name,cls in [('Action','RemoteEvent'),('Request','RemoteFunction'),('State','UnreliableRemoteEvent'),('Input','UnreliableRemoteEvent')]:
        text+=f"local obj=Instance.new('{cls}',remotes);obj.Name='{name}'\n"
    for group,parent in [('Shared','shared'),('Server','services.ServerScriptService'),('Client','sps')]:
        text+=f"local folder=Instance.new('Folder',{parent});folder.Name='{group}'\n"if group!='Shared'else 'local folder=shared\n'
        for p in sorted((APP/'src'/group).glob('*.lua')):
            key=f'{group}/{p.name}';cls='Script'if '.server.'in p.name else 'LocalScript'if '.client.'in p.name else 'ModuleScript'
            text+=f"nodes[{json.dumps(key)}]=Instance.new('{cls}',folder);nodes[{json.dumps(key)}].Name={json.dumps(p.name.split('.')[0])}\n"
    for p in sorted((APP/'src').glob('*/*.lua')):
        key=str(p.relative_to(APP/'src'));text+='modules[nodes['+json.dumps(key)+']]=function(script)\n'+p.read_text()+'\nend\n'
    if server:text+=before_server+"\nmodules[nodes['Server/Main.server.lua']](nodes['Server/Main.server.lua'])\nadvance(.1)\n"
    if client:text+=before_client+"\nmodules[nodes['Client/Main.client.lua']](nodes['Client/Main.client.lua'])\nadvance(.2,true)\n"
    return text+extra

class GameTests(unittest.TestCase):
    def run_lua(self,text,timeout=35):
        with tempfile.TemporaryDirectory()as td:
            p=Path(td)/'test.luau';p.write_text(text)
            r=subprocess.run([LUAU,str(p)],capture_output=True,text=True,timeout=timeout)
        if r.returncode:Path('/tmp/backseat_failed_test.luau').write_text(text)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        return r.stdout

    def test_every_source_compiles(self):
        for p in (APP/'src').rglob('*.lua'):
            with self.subTest(p=p.name):
                r=subprocess.run([COMPILE,str(p)],capture_output=True,text=True)
                self.assertEqual(r.returncode,0,r.stderr)

    def test_thousand_seeds_have_continuous_safe_road_bounds(self):
        self.run_lua(pure('''
for seed=1,1000 do
 local route=Route.new(seed*7919,6144,C)
 for z=0,18000,53 do
  local p=route:point(z);local next=route:point(z+.01)
  assert(math.abs(p.dx)<1.1 and math.abs(p.dy)<.28,'Unreasonable road grade')
  assert(math.abs(p.curvature)<.014 and p.width==28,'Uncompletable bend')
  assert(math.abs(next.x-p.x)<.03 and math.abs(next.y-p.y)<.02,'Chunk discontinuity')
 end
 assert(route:point(0).x==0 and route:point(0).y==8)
end
'''))

    def test_route_is_reproducible_after_distant_seek_and_origin_rebase(self):
        self.run_lua(pure('''
local a,b=Route.new(86457,0,C),Route.new(86457,0,C)
for _,z in ipairs({0,255.99,256,4096,80000,1000000})do
 local x,y=a:point(z),b:point(z);assert(x.x==y.x and x.y==y.y and x.biome==y.biome)
 local origin=-math.floor(z/4096)*4096;assert(z+origin>=0 and z+origin<4096)
end
assert(a:point(1000).x~=Route.new(86458,0,C):point(1000).x,'Seeds do not change roads')
'''))

    def test_manual_driving_can_finish_many_different_roads(self):
        self.run_lua(pure('''
for seed=1,16 do
 local route=Route.new(seed*989,6144,C);local car=C.Cars[1];local s=D.new(route);local maxOffset=0
 for tick=1,36000 do
  local p=route:point(s.z);local look=32+math.abs(s.v)*.45;local target=route:point(s.z+look)
  local angle=(math.atan2(target.x-s.x,target.z-s.z)-s.yaw+math.pi)%(2*math.pi)-math.pi
  local curvature=2*math.sin(angle)/look
  local steer=math.clamp(-math.atan(curvature*car.wheelbase)/(math.rad(31)/(1+math.abs(s.v)/95)),-1,1)
  local bend=math.max(math.abs(route:point(s.z+40).curvature),math.abs(route:point(s.z+100).curvature),.0001)
  local targetSpeed=math.min(70,math.sqrt(20/bend))
  local input={steer=steer,throttle=s.v<targetSpeed and 1 or 0,brake=s.v>targetSpeed+2 and .5 or 0}
  D.step(s,input,route,car,C.Step)
  local _,offset=route:ground(s.x,s.z);maxOffset=math.max(maxOffset,math.abs(offset))
  if s.z>=6144 then break end
 end
 assert(s.z>=6144,'A valid road could not be completed with manual controls')
 assert(maxOffset<11,'A necessary racing line leaves the corridor')
end
'''))

    def test_braking_reverse_and_recovery_are_bounded(self):
        self.run_lua(pure('''
local route=Route.new(55,0,C);route.a=0;route.b=0;local s=D.new(route);local car=C.Cars[1]
for i=1,300 do D.step(s,{throttle=1},route,car,C.Step)end
assert(s.v>20 and s.v<=car.top)
for i=1,300 do D.step(s,{brake=1},route,car,C.Step)end
assert(math.abs(s.v)<.5,'Brakes accelerate backwards')
for i=1,300 do D.step(s,{throttle=-1},route,car,C.Step)end
assert(s.v< -5 and s.v>=-23)
D.reset(s,route,768);assert(s.z==768 and s.v==0)
'''))

    def test_positive_steer_turns_toward_the_cars_actual_right(self):
        self.run_lua(pure('''
local route=Route.new(55,0,C);route.a=0;route.b=0;local s=D.new(route);s.v=20
for i=1,60 do D.step(s,{throttle=.5,steer=.4},route,C.Cars[1],C.Step)end
assert(s.x<0 and s.yaw<0,'Right steering turned left when facing +Z')
'''))

    def test_replay_round_trip_seek_inputs_and_recovery_gap(self):
        self.run_lua(pure('''
local r=Route.new(5,0,C);local s=D.new(r);local frames={}
for i=0,10 do s.x=i*.1;s.z=i*2;s.yaw=i*.01;s.v=i;frames[#frames+1]=Replay.frame(i*.1,s,0,{throttle=.7,brake=.2})end
local text=Replay.encode(frames);local data=Replay.decode(text)
local state=Replay.sample(data,.55);assert(math.abs(state.z-11)<.06 and state.throttle==.7 and state.brake==.2)
local before=Replay.sample(data,0);assert(before.z==0)
local last=Replay.sample(data,30);assert(last.z==20)
local a=Replay.frame(1,s);s.z=768;local b=Replay.frame(6,s,1)
assert(Replay.sample({a,b},3).z~=768 and Replay.sample({a,b},6).z==768,'Recovery was interpolated as a flight')
assert(not pcall(Replay.decode,'1,2,3'))
assert(not pcall(Replay.decode,'1,2,3,4,5,6,7,0,5000,0,0'))
'''))

    def test_server_owns_endless_banking_and_saves_ghost_frames(self):
        self.run_lua(roblox('''
remotes.Action.OnServerEvent:Fire(localPlayer,'start',{mode='endless',car='hatch',seed=99})
advance(.2);remotes.Action.OnServerEvent:Fire(localPlayer,'ready',{});advance(3.3)
for i=1,80 do
 remotes.Input.OnServerEvent:Fire(localPlayer,{seq=i,throttle=1,steer=0,brake=0})
 advance(.05)
end
advance(.2);remotes.Action.OnServerEvent:Fire(localPlayer,'retire',{});advance(3)
local data=remotes.Request.OnServerInvoke(localPlayer,'library')
assert(#data.records==1 and data.records[1].banked and data.records[1].saved,'Banked replay was not saved')
local record=data.records[1];assert(#record.pages>=1)
advance(.2);local page=remotes.Request.OnServerInvoke(localPlayer,'page',{id=record.id,index=1})
assert(page.text and #page.text>30,'Ghost frames were not persisted')
local Codec=require(nodes['Shared/Replay.lua']);local frames=Codec.decode(page.text)
assert(#frames>10 and frames[#frames][1]>=record.duration*1000-1)
assert(data.xp>=0 and record.completed==false and #data.bests==1,'Banked endless ghost missing')
local C=require(nodes['Shared/Config.lua']);local P=require(nodes['Server/Persistence.lua'])
local fresh=P.new(C);fresh:load(localPlayer.UserId);advance(.3)
local durable=fresh:library(localPlayer.UserId)
assert(durable.records[1].id==record.id and durable.bests[1].id==record.id,'Replay/ghost did not survive a new storage session')
assert(fresh:getPage(localPlayer.UserId,record.id,1)==page.text,'Saved ghost page changed')
'''))

    def test_co_driver_shares_record_without_stealing_the_car(self):
        self.run_lua(roblox('''
local guest=newPlayer(202);players.PlayerAdded:Fire(guest);advance(.2)
remotes.Action.OnServerEvent:Fire(localPlayer,'start',{mode='sprint',seed=7});advance(.2)
remotes.Action.OnServerEvent:Fire(guest,'join',{owner=101});advance(.3)
remotes.Action.OnServerEvent:Fire(localPlayer,'ready',{});advance(3.4)
remotes.Input.OnServerEvent:Fire(guest,{seq=1,throttle=1,steer=1})
advance(.4);remotes.Action.OnServerEvent:Fire(localPlayer,'retire',{});advance(3)
local host=remotes.Request.OnServerInvoke(localPlayer,'library');local friend=remotes.Request.OnServerInvoke(guest,'library')
assert(#host.records==1 and #friend.records==1 and host.records[1].id==friend.records[1].id,'Co-op replay not shared')
local stranger=newPlayer(303);advance(.2)
local denied=remotes.Request.OnServerInvoke(stranger,'page',{id=host.records[1].id,index=1})
assert(denied.error,'Another player accessed a private replay')
'''))

    def test_storage_failure_is_session_only_and_does_not_claim_cloud_save(self):
        self.run_lua(roblox('''
datastore.fail=true
remotes.Action.OnServerEvent:Fire(localPlayer,'start',{mode='endless',seed=7});advance(.2)
remotes.Action.OnServerEvent:Fire(localPlayer,'ready',{});advance(3.3)
remotes.Action.OnServerEvent:Fire(localPlayer,'retire',{});advance(16)
local data=remotes.Request.OnServerInvoke(localPlayer,'library')
assert(data.records[1]and not data.records[1].saved,'A failed write was called saved')
assert(string.find(data.status,'Session only',1,true))
advance(.2);local page=remotes.Request.OnServerInvoke(localPlayer,'page',{id=data.records[1].id,index=1})
assert(page.text,'Session-only replay was discarded immediately')
'''))

    def test_client_builds_drivable_world_then_replays_saved_run(self):
        self.run_lua(roblox('''
local function click(text)
 for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==text then o.Activated:Fire();return end end
 error('Missing button '..text)
end
click('EXPEDITION');advance(.3,true);click('TAKE THE ROAD →');advance(6,true)
local roads=0;for _,o in ipairs(created)do if o.Name=='Road'and o.Parent then roads+=1 end end
assert(roads>16,'No streamed road was generated')
input.InputBegan:Fire({KeyCode=Enum.KeyCode.W},false);advance(3,true)
input.InputEnded:Fire({KeyCode=Enum.KeyCode.W});advance(.2,true)
click('RETIRE & SAVE');advance(4,true);click('WATCH REPLAY');advance(3,true)
local controls
for _,o in ipairs(created)do if o.Name=='ReplayControls'and o.Parent then controls=o end end
assert(controls and controls.Visible,'Saved replay viewer did not open')
local oldParts=0;for _,o in ipairs(created)do if o:IsA('BasePart')and o.Parent then oldParts+=1 end end
assert(oldParts<2400,'Stream did not bound the world')
click('EXIT REPLAY');advance(.7,true)
''',client=True),timeout=60)

    def test_finish_gate_saves_a_best_and_reuses_it_as_a_ghost(self):
        self.run_lua(roblox('''
local C=require(nodes['Shared/Config.lua']);local Route=require(nodes['Shared/Route.lua'])
local route=Route.new(989,6144,C);local car=C.Cars[1];local latest;local result
remotes.State.OnClientEvent:Connect(function(p)latest=p.runs[1]end)
remotes.Action.OnClientEvent:Connect(function(kind,data)if kind=='result'then result=data end end)
remotes.Action.OnServerEvent:Fire(localPlayer,'start',{mode='sprint',seed=989});advance(.2)
remotes.Action.OnServerEvent:Fire(localPlayer,'ready',{});advance(3.3)
for seq=1,10000 do
 if result then break end
 local s=latest.s;local look=36+math.abs(s.v)*.5;local target=route:point(s.z+look)
 local angle=(math.atan2(target.x-s.x,target.z-s.z)-s.yaw+math.pi)%(2*math.pi)-math.pi
 local curvature=2*math.sin(angle)/look
 local steer=math.clamp(-math.atan(curvature*car.wheelbase)/(math.rad(31)/(1+math.abs(s.v)/95)),-1,1)
 local bend=math.max(math.abs(route:point(s.z+40).curvature),math.abs(route:point(s.z+110).curvature),.0001)
 local targetSpeed=math.min(65,math.sqrt(18/bend))
 remotes.Input.OnServerEvent:Fire(localPlayer,{seq=seq,steer=steer,throttle=s.v<targetSpeed and 1 or 0,brake=s.v>targetSpeed+2 and .5 or 0})
 advance(.05)
end
assert(result and result.completed,'A finite run never finished')
advance(3)
local library=remotes.Request.OnServerInvoke(localPlayer,'library');assert(#library.bests==1 and library.records[1].saved)
assert(library.xp>=240 and library.records[1].progress>=6144,'Finish reward/gates missing')
local start
remotes.Action.OnClientEvent:Connect(function(kind,data)if kind=='start'then start=data end end)
remotes.Action.OnServerEvent:Fire(localPlayer,'start',{mode='sprint',seed=989});advance(.2)
assert(start and start.ghost==result.id,'Same road did not load its recorded ghost')
'''),timeout=60)

    def test_stream_is_bounded_across_seek_rebase_and_tunnel_clearance(self):
        self.run_lua(roblox('''
local C=require(nodes['Shared/Config.lua']);local Route=require(nodes['Shared/Route.lua'])
local Stream=require(nodes['Client/RoadStream.lua']);local route=Route.new(98,0,C)
local stream=Stream.new(workspace);stream:reset(route,1,0)
for i=0,40 do
 local z=i*256;stream:shift(-math.floor(z/4096)*4096);stream:update(z);stream:work(.003)
 local count=0;for _ in pairs(stream.chunks)do count+=1 end
 assert(count<=8 and #stream.pool<=400,'Chunk or part cache grew without bound')
 assert(stream:ready(z),'Generated road is missing beneath the car')
end
local z=14*256+100;stream:shift(0);stream:update(z);stream:work(.003)
local roofs=0
for _,entry in pairs(stream.chunks)do for _,part in ipairs(entry.model:GetChildren())do
 if part.Name=='Tunnel roof'then
  roofs+=1;local p=route:point(part.Position.Z)
  assert(part.Position.Y-part.Size.Y/2-p.y>10,'Tunnel clips the roof of the car')
 end
end end
assert(roofs>0,'Tunnel coverage missing')
stream:destroy();assert(#stream.pool==0 and next(stream.chunks)==nil)
'''))

    def test_four_visual_wheels_follow_the_road_surface(self):
        self.run_lua(roblox('''
local C=require(nodes['Shared/Config.lua']);local Route=require(nodes['Shared/Route.lua']);local D=require(nodes['Shared/Dynamics.lua']);local Assets=require(nodes['Shared/Assets.lua'])
local route=Route.new(555,0,C);local s=D.new(route);s.z=835;s.x=route:point(s.z).x+2;s.yaw=route:point(s.z).heading
local visual=Assets.car(workspace,C.Cars[1],false,false);local offset=Vector3.new(1800,0,0)
local frame=Assets.pose(visual,s,route,offset,.016)
assert(frame.LookVector:Dot(Vector3.new(math.sin(s.yaw),0,math.cos(s.yaw)))>.95,'Car faces backwards')
for _,wheel in ipairs(visual.wheels)do
 local p=wheel.tyre.Position-offset;local ground=route:ground(p.X,p.Z)
 assert(math.abs(p.Y-wheel.tyre.Size.Y/2-ground)<.001,'A tyre floats over or sinks into the road')
end
'''))

    def test_studio_installer_preserves_existing_bots_scripts_assets_and_settings(self):
        installer=(APP/'src/Installer.lua').read_text()
        script=roblox('''
service('SoundService')
function runService:IsRunning()return false end
local package=Instance.new('Model',workspace);package.Name='BackseatRallyExpansion'
local payload=Instance.new('Folder',package);payload.Name='Payload'
replicated.Parent=payload
local server=nodes['Server/Main.server.lua'].Parent;server.Name='BackseatExpeditionServer';server.Parent=payload
local client=nodes['Client/Main.client.lua'].Parent;client.Name='BackseatExpeditionClient';client.Parent=payload
local assets=Instance.new('Folder',services.ReplicatedStorage);assets.Name='Assets'
local cars=Instance.new('Folder',assets);cars.Name='Cars'
local hatch=Instance.new('Model',cars);hatch.Name='Hatch'
local body=Instance.new('Part',hatch);body.Name='Body'
local exterior=Instance.new('Model',hatch);exterior.Name='Exterior'
Instance.new('Part',exterior);Instance.new('Script',exterior);Instance.new('RemoteEvent',exterior)
local legacy=Instance.new('LocalScript',sps);legacy.Name='OldController'
local bot=Instance.new('Model',services.ServerStorage);bot.Name='MyBot'
local brain=Instance.new('Script',bot);brain.Name='Brain';brain.Disabled=false
local originalPart=Instance.new('Part',workspace);originalPart.Name='OriginalMap'
local playerModule=Instance.new('ModuleScript',services.StarterPlayer);playerModule.Name='PlayerModule'
services.Lighting.ClockTime=9;workspace.Gravity=75
local before={}
for _,serviceName in ipairs({'Workspace','ReplicatedStorage','StarterPlayer','ServerStorage','ServerScriptService'})do
 for _,obj in ipairs(services[serviceName]:GetDescendants())do before[obj]={parent=obj.Parent,disabled=obj.Disabled}end
end
local installerScript=Instance.new('ModuleScript',package)
local factory=function(script)
''',server=False)+installer+'''
end
local installer=factory(installerScript)
local result=installer.install()
assert(result.installed and result.cars==1,'Expansion did not install')
for obj,data in pairs(before)do assert(obj.Parent==data.parent and obj.Disabled==data.disabled,'Existing content was changed')end
assert(workspace.Gravity==75 and services.Lighting.ClockTime==9,'Original game settings changed')
assert(bot.Parent==services.ServerStorage and brain.Disabled==false and legacy.Disabled==false)
assert(package.Parent==workspace,'The imported package was deleted')
local shared=services.ReplicatedStorage.BackseatExpedition
assert(shared.ImportedCars.Hatch,'Existing exterior was not reused')
for _,item in ipairs(shared.ImportedCars:GetDescendants())do
 assert(not item:IsA('LuaSourceContainer')and not item:IsA('RemoteEvent'),'Imported executable content survived')
end
assert(services.ServerScriptService.BackseatExpeditionServer.Main.Disabled==false)
assert(sps.BackseatExpeditionClient.Main.Disabled==false)
local count=#services.ReplicatedStorage:GetChildren()
assert(not installer.install().installed and #services.ReplicatedStorage:GetChildren()==count,'Install is not idempotent')
'''
        self.run_lua(script)

    def test_rendered_road_surface_matches_four_contact_height_model(self):
        self.run_lua(roblox('''
local C=require(nodes['Shared/Config.lua']);local Route=require(nodes['Shared/Route.lua']);local Stream=require(nodes['Client/RoadStream.lua'])
local route=Route.new(98765,0,C);local stream=Stream.new(workspace);stream:reset(route,1,0);stream:update(1200);stream:work(.003)
local checked=0
for _,entry in pairs(stream.chunks)do for _,p in ipairs(entry.model:GetChildren())do if p.Name=='Road'then
 for _,x in ipairs({-10,0,10})do
  local surface=p.CFrame:PointToWorldSpace(Vector3.new(x,.35,0))-stream:offset()
  local expected=route:ground(surface.X,surface.Z)
  assert(math.abs(expected-surface.Y)<.2,'Banked road and tyre contact surface disagree')
 end
 checked+=1
end end end
assert(checked>50)
'''))

    def test_save_index_failure_is_not_reported_as_a_cloud_replay(self):
        self.run_lua(roblox('''
local profileStore=datastore.stores.BRExpeditionProfiles_v1
function profileStore:UpdateAsync()error('Index unavailable')end
remotes.Action.OnServerEvent:Fire(localPlayer,'start',{mode='endless',seed=77});advance(.2)
remotes.Action.OnServerEvent:Fire(localPlayer,'ready',{});advance(3.3)
remotes.Action.OnServerEvent:Fire(localPlayer,'retire',{});advance(4)
local data=remotes.Request.OnServerInvoke(localPlayer,'library')
assert(data.records[1]and not data.records[1].saved and string.find(data.status,'Session only',1,true),'An unindexed replay was called saved')
'''))

    def test_cloud_page_outage_does_not_stop_the_active_simulation(self):
        self.run_lua(roblox('''
local last
remotes.State.OnClientEvent:Connect(function(p)last=p.runs[1]end)
remotes.Action.OnServerEvent:Fire(localPlayer,'start',{mode='endless',seed=77});advance(.2)
remotes.Action.OnServerEvent:Fire(localPlayer,'ready',{});advance(3.3)
datastore.fail=true;advance(57)
assert(last and last.clock>56 and last.status=='running','A cloud retry stalled active gameplay')
assert(not last.recording,'Failed page was not reflected in recording status')
'''))

    def test_installer_refuses_to_modify_a_running_game(self):
        installer=(APP/'src/Installer.lua').read_text()
        self.run_lua(roblox('local factory=function(script)\n'+installer+'''
end
local original=services.ReplicatedStorage.BackseatExpedition
local ok=pcall(function()factory(Instance.new('ModuleScript')).install()end)
assert(not ok and services.ReplicatedStorage.BackseatExpedition==original)
assert(#services.ServerStorage:GetChildren()==0,'Live install modified the place')
''',server=False))

    def test_optional_launcher_restores_original_ui_camera_controls_and_lighting(self):
        self.run_lua(roblox('''
local original=Instance.new('ScreenGui',localPlayer.PlayerGui);original.Name='OriginalHUD';original.Enabled=true
local disabled=Instance.new('ScreenGui',localPlayer.PlayerGui);disabled.Name='OriginalDisabled';disabled.Enabled=false
local camera=workspace.CurrentCamera;camera.CameraType=Enum.CameraType.Custom;camera.FieldOfView=81
camera.CFrame=CFrame.new(11,21,31);services.Lighting.ClockTime=9
local function click(text)
 for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==text then o.Activated:Fire();return end end
 error('Missing button '..text)
end
advance(.5,true)
assert(camera.CFrame.Position.X==11 and camera.FieldOfView==81 and original.Enabled,'Expansion started without opt in')
click('EXPEDITION');advance(.3,true)
assert(not original.Enabled and not disabled.Enabled and camera.CameraType==Enum.CameraType.Scriptable)
original.Enabled=true;assert(not original.Enabled,'Legacy HUD overlaid the expansion')
local dynamic=Instance.new('ScreenGui',localPlayer.PlayerGui);dynamic.Name='LateHUD'
assert(not dynamic.Enabled,'A late legacy overlay was not temporarily hidden')
click('TAKE THE ROAD →');advance(6,true)
click('RETURN TO ORIGINAL');advance(4,true)
assert(original.Enabled and not disabled.Enabled and dynamic.Enabled,'Original UI state was not restored')
assert(camera.CameraType==Enum.CameraType.Custom and camera.FieldOfView==81 and camera.CFrame.Position.X==11)
assert(services.Lighting.ClockTime==9 and next(context.bound)==nil and next(runService.bound)==nil)
assert(not workspace:FindFirstChild('ExpeditionLocal')and not workspace:FindFirstChild('ExpeditionLocalPark'))
''',client=True,before_client="replicated:SetAttribute('AutoOpen',false)"))

    def test_start_ready_and_bank_restore_character_to_its_original_position(self):
        self.run_lua(roblox('''
localPlayer.Character:PivotTo(CFrame.new(123,27,-89))
remotes.Action.OnServerEvent:Fire(localPlayer,'start',{mode='endless',seed=77})
-- Readiness must not be lost when road generation completes within the action cooldown.
remotes.Action.OnServerEvent:Fire(localPlayer,'ready',{})
advance(4)
remotes.Action.OnServerEvent:Fire(localPlayer,'retire',{})
advance(.4)
local p=localPlayer.Character:GetPivot().Position
assert(math.abs(p.X-123)<.001 and math.abs(p.Y-27)<.001 and math.abs(p.Z+89)<.001,'Character did not return to its original position')
local library=remotes.Request.OnServerInvoke(localPlayer,'library')
assert(#library.records==1 and library.records[1].duration>.5,'Readiness or banking was dropped')
'''))

    def test_ready_place_and_installer_contain_exact_authored_sources(self):
        downloads=APP.parent/'downloads'
        if not downloads.is_dir():downloads=APP.parent
        place=downloads/'Backseat_Rally_Expedition.rbxlx';installer=downloads/'Backseat_Rally_Expansion.rbxmx'
        for path in [place,installer]:
            root=ET.parse(path).getroot();sources=[]
            for e in root.iter('Item'):
                source=e.find("Properties/ProtectedString[@name='Source']")
                if source is not None:sources.append(source.text)
            expected=[p.read_text()for p in (APP/'src').glob('*/*.lua')]
            if path==installer:expected.append((APP/'src/Installer.lua').read_text())
            self.assertCountEqual(sources,expected)
            self.assertFalse(any('loadstring('in s or 'getgenv('in s for s in sources))
        root=ET.parse(installer).getroot()
        for e in root.iter('Item'):
            if e.attrib['class']in ('Script','LocalScript'):self.assertEqual(e.find("Properties/bool[@name='Disabled']").text,'true')
