local Players=game:GetService('Players')
local ReplicatedStorage=game:GetService('ReplicatedStorage')
local RunService=game:GetService('RunService')
local Workspace=game:GetService('Workspace')
local root=ReplicatedStorage:WaitForChild('BackseatExpedition')
local C=require(root.Shared.Config);local Route=require(root.Shared.Route)
local D=require(root.Shared.Dynamics);local Replay=require(root.Shared.Replay)
local Persistence=require(script.Parent.Persistence);local storage=Persistence.new(C)
local Assets=require(root.Shared.Assets)
local remotes=root.Remotes;local action=remotes.Action;local request=remotes.Request;local stateEvent=remotes.State;local inputEvent=remotes.Input
local runs,viewing,slots={}, {}, {};local ending=0;local returnPoints={}
local function getCar(id)for _,car in ipairs(C.Cars)do if car.id==id then return car end end;return C.Cars[1]end
local function getMode(id)for _,mode in ipairs(C.Modes)do if mode.id==id then return mode end end;return C.Modes[1]end
local function tell(player,kind,data)if player and player.Parent then action:FireClient(player,kind,data)end end
local function participants(run)
 local out={run.player};if run.passenger and run.passenger.Parent then table.insert(out,run.passenger)end;return out
end
local function broadcastRun(run,kind,data)for _,p in ipairs(participants(run))do tell(p,kind,data)end end
local function origin(run)return Vector3.new(C.WorldX+run.slot*C.LaneSpacing,0,-math.floor(run.s.z/4096)*4096)end
local function worldFrame(run)
 local y,pitch,roll=D.pose(run.s,run.route)
 return CFrame.new(Vector3.new(run.s.x,y,run.s.z)+origin(run))*CFrame.Angles(0,math.pi+run.s.yaw,0)*CFrame.Angles(pitch,0,roll)
end
local function seatPlayer(player,seat)
 local character=player.Character;local humanoid=character and character:FindFirstChildOfClass('Humanoid')
 if humanoid then character:PivotTo(seat.CFrame*CFrame.new(0,3,0));seat:Sit(humanoid)end
end
local function rememberReturn(player)
 if not returnPoints[player]and player.Character then returnPoints[player]=player.Character:GetPivot()end
end
local function returnLobby(player)
 viewing[player]=nil
 local character=player.Character;local h=character and character:FindFirstChildOfClass('Humanoid')
 if h then h.Sit=false;h.Jump=true end
 local target=returnPoints[player];returnPoints[player]=nil
 task.delay(.15,function()if target and character and character.Parent and not runs[player]and not viewing[player]then character:PivotTo(target)end end)
end
local function packet(run)
 return {id=run.record.meta.id,owner=run.player.UserId,name=run.player.DisplayName,mode=run.mode.id,seed=run.route.seed,length=run.route.length,
  car=run.car.id,slot=run.slot,s=D.copy(run.s),clock=run.clock,penalty=run.penalty,nextGate=run.nextGate,
  missed=run.missed or false,status=run.status,originZ=origin(run).Z,course=run.record.meta.course,
  passenger=run.passenger and run.passenger.UserId or 0,ghost=run.ghost and run.ghost.id or nil,recording=not run.record.failed}
end
local function recordFrame(run,flag)
 local f=Replay.frame(run.clock+run.penalty,run.s,flag,run.input);local frames=run.frames
 frames[#frames+1]=f
 if #frames>=C.ReplayPage then storage:page(run.record,Replay.encode(frames),frames);run.frames={}end
end
local function finish(run,reason)
 if runs[run.player]~=run then return end
 recordFrame(run)
 runs[run.player]=nil;slots[run.slot]=nil;ending+=1
 if #run.frames>0 then storage:page(run.record,Replay.encode(run.frames),run.frames);run.frames={}end
 local meta=run.record.meta;meta.duration=run.clock+run.penalty;meta.penalty=run.penalty
 meta.completed=reason=='finish';meta.banked=reason=='bank';meta.reason=reason
 meta.distance=run.s.distance;meta.progress=run.missed and run.lastGate or run.validZ;meta.crashes=run.s.crashes
 local reward=meta.completed and run.mode.xp or (meta.banked and math.floor(run.validZ/128)or 0)
 if meta.completed and run.s.crashes==0 then reward+=50;meta.cleanBonus=50 end
 meta.reward=reward
 local members=participants(run)
 for _,p in ipairs(members)do
  returnLobby(p);tell(p,'result',meta)
 end
 run.model:Destroy()
 storage:finish(run.record,reward,function(userId,record,status)
  local p=Players:GetPlayerByUserId(userId);tell(p,'saved',{id=record.id,status=status,saved=record.saved})
 end)
 task.spawn(function()local deadline=os.clock()+22;while not run.record.done and os.clock()<deadline do task.wait(.1)end;ending-=1 end)
end
local function start(player,data)
 if runs[player]or viewing[player]then return end
 local car=getCar(data.car);local profile=storage:load(player.UserId)
 if profile.xp<car.unlock then tell(player,'notice','This car unlocks at '..car.unlock..' XP.');return end
 if profile.loading then tell(player,'notice','Loading your garage save; try again in a moment.');return end
 local numeric=tonumber(data.seed);if not numeric or numeric~=numeric or math.abs(numeric)>1e12 then numeric=math.random(1,999999999)end
 local mode=getMode(data.mode);local seed=math.floor(numeric)%1000000000
 if mode.id=='daily'then seed=math.floor(os.time()/86400)end
 local slot
 for i=1,C.MaxPlayers do if not slots[i]then slot=i;break end end
 if not slot then tell(player,'notice','All rally slots are in use. Join a co-driver seat or try again shortly.');return end
 local route=Route.new(seed,mode.length,C)
 local run={player=player,route=route,car=car,mode=mode,slot=slot,s=D.new(route),clock=0,penalty=0,nextGate=C.Checkpoint,
  lastGate=0,validZ=0,status='loading',frames={},sample=0,input={throttle=0,steer=0,brake=1},lastInput=0,seq=-1,created=os.clock(),recoverAt=-100}
 if mode.length>0 then run.nextGate=math.min(run.nextGate,mode.length)end
 run.record=storage:newRecording(player.UserId,{seed=seed,length=mode.length,mode=mode.id,car=car.id,course=route:key(mode.id,car.id),generation=C.Generation,weather=mode.weather})
 for _,best in ipairs(profile.bests)do if best.course==run.record.meta.course then run.ghost=best;break end end
 local model=Instance.new('Model');model.Name='Rally_'..player.UserId
 local body=Instance.new('Part');body.Name='Root';body.Size=Vector3.new(6,2,10);body.Transparency=1;body.Anchored=true;body.CanCollide=false;body.Parent=model;model.PrimaryPart=body
 for i,name in ipairs({'Driver','CoDriver'})do
  local seat=Instance.new('Seat');seat.Name=name;seat.Size=Vector3.new(2,1,2);seat.Transparency=1;seat.Anchored=true;seat.CanCollide=false
  seat.CFrame=CFrame.new(i==1 and -1.3 or 1.3,.25,0);seat.Parent=model
 end
 model.Parent=Workspace;run.model=model;model:PivotTo(worldFrame(run));runs[player]=run;slots[slot]=run
 rememberReturn(player);seatPlayer(player,model.Driver);tell(player,'start',packet(run));recordFrame(run)
end
local lastAction={}
action.OnServerEvent:Connect(function(player,kind,data)
 if type(kind)~='string'then return end
 local now=os.clock();if kind~='ready'and kind~='retire'and kind~='leave'and now-(lastAction[player]or -math.huge)<.12 then return end;lastAction[player]=now
 data=type(data)=='table'and data or {};local run=runs[player]
 if kind=='start'then start(player,data)
 elseif kind=='ready'and run and run.status=='loading'then run.status='countdown';run.countUntil=now+3;broadcastRun(run,'countdown',3)
 elseif kind=='retire'and run then finish(run,run.mode.id=='endless'and 'bank'or 'retired')
 elseif kind=='recover'and run and now-run.recoverAt>3 and run.status=='running'then
  run.recoverAt=now;run.penalty+=5;D.reset(run.s,run.route,run.lastGate);run.missed=false;recordFrame(run,1);broadcastRun(run,'notice','Recovered to checkpoint · +5 seconds')
 elseif kind=='bookmark'and run then
  local markers=run.record.meta.markers;if #markers<32 then markers[#markers+1]=run.clock+run.penalty end;tell(player,'notice','Replay moment marked')
 elseif kind=='join'then
  if run or viewing[player]then return end
  local host=Players:GetPlayerByUserId(tonumber(data.owner)or 0);local target=host and runs[host]
  if target and not target.passenger then
   rememberReturn(player);target.passenger=player;viewing[player]=target
   if not table.find(target.record.meta.access,player.UserId)then table.insert(target.record.meta.access,player.UserId)end
   seatPlayer(player,target.model.CoDriver);tell(player,'start',packet(target));tell(host,'notice',player.DisplayName..' joined as co-driver')
  end
 elseif kind=='leave'and viewing[player]then
  local target=viewing[player];target.passenger=nil;returnLobby(player);tell(player,'lobby',{})
 elseif kind=='call'and viewing[player]then
  local allowed={left='LEFT · co-driver call',right='RIGHT · co-driver call',caution='CAUTION · co-driver call'}
  if allowed[data.note]then tell(viewing[player].player,'notice',allowed[data.note])end
 end
end)
inputEvent.OnServerEvent:Connect(function(player,data)
 local run=runs[player];if not run or type(data)~='table'then return end
 if type(data.seq)~='number'or data.seq%1~=0 or data.seq<=run.seq then return end
 local function unit(n)if type(n)~='number'or n~=n then return 0 end;return math.clamp(n,-1,1)end
 run.seq=data.seq;run.lastInput=os.clock()
 run.input={throttle=unit(data.throttle),steer=unit(data.steer),brake=math.max(0,unit(data.brake)),handbrake=data.handbrake==true}
end)
local requestAt={}
request.OnServerInvoke=function(player,kind,data)
 local now=os.clock();if now-(requestAt[player]or -math.huge)<.12 then return {error='Please wait a moment'}end;requestAt[player]=now
 if kind=='library'then return storage:library(player.UserId)
 elseif kind=='replay'then
  local id=type(data)=='table'and data.id;local r=storage:find(player.UserId,id)
  if not r then return {error='Replay unavailable'}end
  return {record=r}
 elseif kind=='page'then
  if type(data)~='table'then return {error='Invalid request'}end
  local text,reason=storage:getPage(player.UserId,data.id,data.index);return text and {text=text}or {error=reason}
 elseif kind=='lobby'then
  local open={};for _,r in pairs(runs)do if not r.passenger then table.insert(open,{owner=r.player.UserId,name=r.player.DisplayName,mode=r.mode.name})end end
  return {drivers=open,library=storage:library(player.UserId)}
 end
 return {error='Unknown request'}
end
local accumulated,network=0,0
RunService.Heartbeat:Connect(function(dt)
 accumulated=math.min(accumulated+dt,.15);local steps=0
 while accumulated>=C.Step and steps<5 do
  accumulated-=C.Step;steps+=1
  for _,run in pairs(runs)do
   if run.status=='loading'and os.clock()-run.created>45 then finish(run,'loading cancelled')
   elseif run.status=='countdown'then
    if os.clock()>=run.countUntil then run.status='running';broadcastRun(run,'go',{})end
   elseif run.status=='running'then
    local input=os.clock()-run.lastInput<.6 and run.input or {throttle=0,steer=0,brake=.5}
    D.step(run.s,input,run.route,run.car,C.Step);run.clock+=C.Step
    local p=run.route:point(run.s.z);local lateral=math.abs((run.s.x-p.x)/math.sqrt(1+p.dx*p.dx))
    if not run.missed and run.s.z>=run.nextGate and run.s.z<run.nextGate+30 and lateral<p.width/2+2 then
     run.lastGate=run.nextGate;run.validZ=run.lastGate;run.s.damage=math.max(0,run.s.damage-12)
     if run.route.length>0 and run.lastGate>=run.route.length then finish(run,'finish')
     else
      run.nextGate=run.lastGate+C.Checkpoint
      if run.route.length>0 then run.nextGate=math.min(run.nextGate,run.route.length)end
      broadcastRun(run,'checkpoint',{z=run.lastGate,time=run.clock+run.penalty})
     end
    elseif run.s.z>run.nextGate+30 then run.missed=true end
    if not run.missed and lateral<p.width/2+3 then run.validZ=math.max(run.validZ,run.s.z)end
    if runs[run.player]==run then
    run.sample+=C.Step
    if run.sample>=1/C.ReplayRate then run.sample-=1/C.ReplayRate;recordFrame(run)end
    end
   end
  end
 end
 network+=dt
 if network>=1/C.StateRate then
  network=0;local list={}
  for _,run in pairs(runs)do
   run.model:PivotTo(worldFrame(run));list[#list+1]=packet(run)
   if not run.model.Driver.Occupant and os.clock()-run.created>2 then seatPlayer(run.player,run.model.Driver)end
  end
  if #list>0 then stateEvent:FireAllClients({time=Workspace:GetServerTimeNow(),runs=list})end
 end
end)
Players.PlayerAdded:Connect(function(player)storage:load(player.UserId)end)
Players.PlayerRemoving:Connect(function(player)
 if runs[player]then finish(runs[player],runs[player].mode.id=='endless'and 'bank'or 'disconnected')end
 if viewing[player]then viewing[player].passenger=nil;viewing[player]=nil end
 lastAction[player]=nil;requestAt[player]=nil
end)
for _,p in ipairs(Players:GetPlayers())do storage:load(p.UserId)end
game:BindToClose(function()
 local list={};for _,run in pairs(runs)do list[#list+1]=run end
 for _,run in ipairs(list)do finish(run,run.mode.id=='endless'and 'bank'or 'server closed')end
 local untilTime=os.clock()+25;while ending>0 and os.clock()<untilTime do task.wait(.1)end
end)
-- Reuse visual templates in the expansion namespace without changing the source assets.
task.spawn(function()
 local ok,reason=pcall(function()require(root.Shared.ImportAssets).harvest(root)end)
 if not ok then warn('Optional original visual templates unavailable: '..tostring(reason))end
end)
