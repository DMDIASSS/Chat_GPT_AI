local Players=game:GetService('Players');local RS=game:GetService('ReplicatedStorage')
local RunService=game:GetService('RunService');local UIS=game:GetService('UserInputService');local Lighting=game:GetService('Lighting')
local player=Players.LocalPlayer;local root=RS:WaitForChild('BackseatExpedition');local remotes=root.Remotes
local C=require(root.Shared.Config);local Route=require(root.Shared.Route);local D=require(root.Shared.Dynamics);local Assets=require(root.Shared.Assets)
local Presence=require(script.Parent.Presence);local UI=require(script.Parent.UI);local RoadStream=require(script.Parent.RoadStream);local ReplayPlayer=require(script.Parent.ReplayPlayer)
local mode='closed';local scene,stream,visual,route,run,predicted,ghostPlayer,ghostVisual,replayPlayer
local replayTime,replayRate,replayPaused=0,1,false
local held={};local gamepad={steer=0,throttle=0,brake=0};local seq=0;local sent=0;local accumulator=0;local roadAt=0
local cameraMode=1;local cameraNames={'CHASE','HOOD','ORBIT','FREE'};local orbitAngle,orbitPitch,orbitDistance=0,.35,20
local freeFrame;local readySent=false;local noticeUntil=0;local lastFrame;local clockAt,clockValue=0,0
local correction;local countdownUntil;local ui;local presence;local menuPark;local closing=false
local openExpansion,closeExpansion
local function notice(text,seconds)if ui then ui.message.Text=tostring(text);noticeUntil=os.clock()+(seconds or 3)end end
local function invoke(kind,data)
 local ok,response=pcall(function()return remotes.Request:InvokeServer(kind,data)end)
 if not ok then return {error='Connection interrupted; try again'}end
 return response or {error='No response'}
end
local function controls()
 local focus=UIS:GetFocusedTextBox();if focus then return {throttle=0,brake=.5,steer=0}end
 local reversing=held.brake and predicted and predicted.v<.8
 return {throttle=held.throttle and 1 or ((held.reverse or reversing)and -1 or gamepad.throttle),
  brake=held.brake and not reversing and 1 or gamepad.brake,steer=held.left and -1 or (held.right and 1 or gamepad.steer),handbrake=held.handbrake==true}
end
local function clearScene()
 if ghostPlayer then ghostPlayer:destroy();ghostPlayer=nil end
 if replayPlayer then replayPlayer:destroy();replayPlayer=nil end
 if stream then stream:destroy();stream=nil end
 if scene then scene:Destroy();scene=nil end
 visual=nil;ghostVisual=nil;predicted=nil;correction=nil;lastFrame=nil;freeFrame=nil;held={}
end
local function menuCamera()
 if not menuPark then
  menuPark=Instance.new('Model');menuPark.Name='ExpeditionLocalPark';menuPark.Parent=workspace
  Assets.park(menuPark);menuPark:PivotTo(CFrame.new(C.WorldX,0,0))
 end
 local camera=workspace.CurrentCamera;camera.CameraType=Enum.CameraType.Scriptable
 camera.CFrame=CFrame.lookAt(Vector3.new(C.WorldX+52,22,53),Vector3.new(C.WorldX,3,-12));camera.FieldOfView=56
 presence:view(camera.CFrame,56)
end
local function getCar(id)for _,car in ipairs(C.Cars)do if car.id==id then return car end end;return C.Cars[1]end
local function refreshLobby()
 task.spawn(function()local data=invoke('lobby');if data.error then notice(data.error)else ui:lobby(data)end end)
end
local function exitToMenu()
 clearScene();mode='menu';run=nil;ui:show('menu');menuCamera();refreshLobby()
end
local function setQuality(quality)if stream then stream.quality=quality end end
local function setup(metadata,initial)
 if menuPark then menuPark:Destroy();menuPark=nil end
 clearScene();run=metadata;route=Route.new(metadata.seed,metadata.length,C)
 scene=Instance.new('Folder');scene.Name='ExpeditionLocal';scene.Parent=workspace
 stream=RoadStream.new(scene);stream.quality=ui.quality;stream:reset(route,metadata.slot or 1,metadata.originZ or 0)
 visual=Assets.car(scene,getCar(metadata.car),false,ui.quality~='low',true)
 predicted=initial or D.new(route);readySent=false;accumulator=0;cameraMode=1;roadAt=0
 workspace.CurrentCamera.CameraType=Enum.CameraType.Scriptable;workspace.CurrentCamera.FieldOfView=72
 Lighting.ClockTime=metadata.mode=='daily'and 18.15 or 15.8
end
local function loadGhost(id)
 if not id then return end
 local active=run and run.id
 task.spawn(function()
  local data=invoke('replay',{id=id})
  if not run or run.id~=active or mode~='drive'or data.error or not data.record or data.record.generation~=C.Generation then return end
  ghostPlayer=ReplayPlayer.new(remotes.Request,data.record);ghostVisual=Assets.car(scene,getCar(data.record.car),true,false);ghostPlayer:page(1)
 end)
end
local function watch(record)
 if record.generation~=C.Generation then notice('This replay uses a different road generation version.');return end
 mode='replay';setup({seed=record.seed,length=record.length,slot=1,originZ=0,mode=record.mode,car=record.car,passenger=0},nil)
 replayPlayer=ReplayPlayer.new(remotes.Request,record);replayPlayer:page(1)
 replayTime=record.startTime or 0;replayRate=1;replayPaused=false;ui:show('replay');notice('Loading saved replay…',2)
 for _,child in ipairs(ui.timeline:GetChildren())do if child.Name=='Moment'then child:Destroy()end end
 for _,t in ipairs(record.markers or {})do
  local marker=Instance.new('Frame');marker.Name='Moment';marker.Size=UDim2.fromOffset(3,16)
  marker.Position=UDim2.new(t/math.max(record.duration,1),-1,0,0);marker.BorderSizePixel=0;marker.BackgroundColor3=Color3.fromRGB(237,126,84);marker.Parent=ui.timeline
 end
end
ui=UI.new({
 open=function()openExpansion()end,close=function()
  if mode=='drive'then closing=true;remotes.Action:FireServer(run and run.owner~=player.UserId and 'leave'or 'retire');notice('Saving the run…')else closeExpansion()end
 end,
 start=function(modeId,carId,seed)
  if mode=='drive'then return end
  if mode=='replay'then clearScene();mode='menu'end
  remotes.Action:FireServer('start',{mode=modeId,car=carId,seed=seed});notice('Preparing your road…',2)
 end,
 library=function()task.spawn(function()local data=invoke('library');if data.error then notice(data.error)else ui:library(data)end end)end,
 lobby=refreshLobby,quality=setQuality,
 stop=function()if mode=='drive'then remotes.Action:FireServer('retire')end end,
 recover=function()if mode=='drive'then remotes.Action:FireServer('recover')end end,
 bookmark=function()if mode=='drive'then remotes.Action:FireServer('bookmark')end end,
 camera=function()cameraMode=cameraMode%(mode=='replay'and 4 or 3)+1;freeFrame=workspace.CurrentCamera.CFrame;notice(cameraNames[cameraMode]..' CAMERA',1.5)end,
 join=function(owner)remotes.Action:FireServer('join',{owner=owner})end,
 leave=function()remotes.Action:FireServer('leave')end,
 call=function(note)remotes.Action:FireServer('call',{note=note})end,
 touch=function(key,down)held[key]=down end,
 watch=watch,
 seek=function(fraction)if replayPlayer then replayTime=math.clamp(fraction*replayPlayer.meta.duration,replayPlayer.meta.startTime or 0,replayPlayer.meta.duration)end end,
 skip=function(delta)if replayPlayer then replayTime=math.clamp(replayTime+delta,replayPlayer.meta.startTime or 0,replayPlayer.meta.duration)end end,
 pause=function()replayPaused=not replayPaused;ui.pauseButton.Text=replayPaused and 'PLAY'or 'PAUSE'end,
 rate=function(rate)replayRate=rate end,
 exitReplay=function()exitToMenu();task.delay(.2,function()ui.callbacks.library()end)end,
})
presence=Presence.new(ui.gui)
openExpansion=function()
 if presence.active then return end
 presence:open();mode='menu';closing=false;ui.canvas.Visible=true;ui.launcher.Visible=false;ui.closeButton.Visible=true
 ui:show('menu');menuCamera();refreshLobby()
end
closeExpansion=function()
 clearScene();if menuPark then menuPark:Destroy();menuPark=nil end
 mode='closed';run=nil;closing=false;countdownUntil=nil;held={};gamepad={steer=0,throttle=0,brake=0}
 ui.canvas.Visible=false;ui.touch.Visible=false;ui.closeButton.Visible=false;ui.launcher.Visible=true
 presence:close()
end
local keyMap={W='throttle',S='brake',A='left',D='right',Space='handbrake',Down='reverse',Up='throttle',Left='left',Right='right'}
UIS.InputBegan:Connect(function(input,processed)
 if mode=='closed'or processed or UIS:GetFocusedTextBox()then return end
 local name=input.KeyCode.Name
 if keyMap[name]then held[keyMap[name]]=true end
 if name=='R'then ui.callbacks.recover()
 elseif name=='B'then ui.callbacks.bookmark()
 elseif name=='C'then ui.callbacks.camera()
 elseif name=='J'then ui.callbacks.call('left')
 elseif name=='K'then ui.callbacks.call('right')
 elseif name=='L'then ui.callbacks.call('caution')
 elseif mode=='replay'and name=='P'then ui.callbacks.pause()
 elseif mode=='replay'and name=='Comma'then ui.callbacks.skip(-5)
 elseif mode=='replay'and name=='Period'then ui.callbacks.skip(5)end
end)
UIS.InputEnded:Connect(function(input)
 local name=input.KeyCode.Name;if keyMap[name]then held[keyMap[name]]=false end
end)
UIS.InputChanged:Connect(function(input)
 if mode=='closed'then return end
 if input.KeyCode==Enum.KeyCode.Thumbstick1 then gamepad.steer=input.Position.X
 elseif input.KeyCode==Enum.KeyCode.ButtonR2 then gamepad.throttle=input.Position.Z
 elseif input.KeyCode==Enum.KeyCode.ButtonL2 then gamepad.brake=input.Position.Z
 elseif input.UserInputType==Enum.UserInputType.MouseWheel then orbitDistance=math.clamp(orbitDistance-input.Position.Z*2,8,55)end
end)
UIS.WindowFocusReleased:Connect(function()held={};gamepad={steer=0,throttle=0,brake=0}end)
remotes.Action.OnClientEvent:Connect(function(kind,data)
 if kind=='start'then
  if not presence.active then openExpansion()end
  mode='drive';setup(data,D.copy(data.s));clockAt=os.clock();clockValue=data.clock;ui:show('drive');notice('Building the road ahead…',10);loadGhost(data.ghost)
 elseif kind=='countdown'then countdownUntil=os.clock()+3;notice('3 · get ready',3)
 elseif kind=='go'then countdownUntil=nil;if run then run.status='running'end;notice('GO · make it a good one',1.5)
 elseif kind=='notice'then notice(data)
 elseif kind=='checkpoint'then notice('CHECKPOINT / '..UI.time(data.time),1.6)
 elseif kind=='result'then
  if closing then closeExpansion()else clearScene();mode='result';run=nil;menuCamera();ui:resultScreen(data)end
 elseif kind=='saved'then ui:saved(data)
 elseif kind=='lobby'then if closing then closeExpansion()else exitToMenu()end end
end)
remotes.State.OnClientEvent:Connect(function(packet)
 if mode~='drive'or not run then return end
 for _,data in ipairs(packet.runs or {})do if data.owner==run.owner then
  local oldOrigin=run.originZ or 0;local oldPenalty=run.penalty;run=data
  if data.originZ~=oldOrigin then
   local delta=Vector3.new(0,0,data.originZ-oldOrigin);stream:shift(data.originZ)
   workspace.CurrentCamera.CFrame=workspace.CurrentCamera.CFrame+delta
   if freeFrame then freeFrame+=delta end
  end
  local target=D.copy(data.s)
  local lag=math.clamp(workspace:GetServerTimeNow()-packet.time,0,.25)
  if data.status=='running'and data.owner==player.UserId then
   local input=controls();local left=lag
   while left>0 do local dt=math.min(C.Step,left);D.step(target,input,route,getCar(data.car),dt);left-=dt end
  end
  local error=predicted and math.sqrt((predicted.x-target.x)^2+(predicted.z-target.z)^2)or 100
  if not predicted or error>18 or oldPenalty~=data.penalty then predicted=target;correction=nil else correction=target end
  clockValue=data.clock;clockAt=os.clock()
  break
 end end
end)
local function updateCamera(cf,dt)
 local camera=workspace.CurrentCamera
 if cameraMode==4 then
  freeFrame=freeFrame or camera.CFrame
  local direction=Vector3.new((held.right and 1 or 0)-(held.left and 1 or 0),0,(held.brake and 1 or 0)-(held.throttle and 1 or 0))
  if UIS:IsMouseButtonPressed(Enum.UserInputType.MouseButton2)then
   local delta=UIS:GetMouseDelta();freeFrame=CFrame.new(freeFrame.Position)*CFrame.Angles(0,-delta.X*.004,0)*freeFrame.Rotation*CFrame.Angles(-delta.Y*.004,0,0)
  end
  freeFrame=freeFrame*CFrame.new(direction*dt*55);camera.CFrame=freeFrame;presence:view(camera.CFrame);return
 end
 if UIS:IsMouseButtonPressed(Enum.UserInputType.MouseButton2)then
  local delta=UIS:GetMouseDelta();orbitAngle-=delta.X*.006;orbitPitch=math.clamp(orbitPitch+delta.Y*.004,-.05,1.1)
 end
 local target
 if cameraMode==2 then
  local pos=cf.Position+cf.LookVector*3.8+Vector3.new(0,2.1,0);target=CFrame.lookAt(pos,pos+cf.LookVector*40)
 elseif cameraMode==3 then
  local offset=Vector3.new(math.sin(orbitAngle)*orbitDistance,math.sin(orbitPitch)*orbitDistance+3,math.cos(orbitAngle)*orbitDistance)
  target=CFrame.lookAt(cf.Position+offset,cf.Position+Vector3.new(0,.7,0))
 else
  local pos=cf.Position-cf.LookVector*(15+math.abs(predicted.v)*.025)+Vector3.new(0,6.3,0)
  target=CFrame.lookAt(pos,cf.Position+cf.LookVector*9+Vector3.new(0,1.6,0))
 end
 camera.CFrame=lastFrame and camera.CFrame:Lerp(target,1-math.exp(-9*dt))or target
 presence:view(camera.CFrame)
 lastFrame=cf
end
local uiAt=0;local slowTime=0
RunService.RenderStepped:Connect(function(dt)
 if mode=='closed'then return end
 ui:resize()
 if countdownUntil and os.clock()<countdownUntil then ui.message.Text=tostring(math.ceil(countdownUntil-os.clock()))..' · GET READY'end
 if noticeUntil>0 and os.clock()>noticeUntil then ui.message.Text='';noticeUntil=0 end
 if mode~='drive'and mode~='replay'then return end
 if not stream or not predicted then return end
 local input=controls();local speed=getCar(run.car)
 if mode=='drive'then
  sent+=dt
  if sent>=1/C.InputRate then sent=0;seq+=1;input.seq=seq;remotes.Input:FireServer(input)end
  accumulator=math.min(accumulator+dt,.1)
  while accumulator>=C.Step do
   accumulator-=C.Step
   if run.status=='running'then
    local driving=run.owner==player.UserId and input or {throttle=predicted.throttle or 0,brake=predicted.brake or 0,steer=predicted.steer or 0,handbrake=predicted.handbrake}
    D.step(predicted,driving,route,speed,C.Step)end
   if correction then
    -- Advance the correction too, so interpolation does not pull toward an old pose.
    if run.status=='running'then
     local driving=run.owner==player.UserId and input or {throttle=correction.throttle or 0,brake=correction.brake or 0,steer=correction.steer or 0,handbrake=correction.handbrake}
     D.step(correction,driving,route,speed,C.Step)end
    local blend=1-math.exp(-7*C.Step)
    for _,k in ipairs({'x','z','v','lateralV'})do predicted[k]+=(correction[k]-predicted[k])*blend end
    local delta=(correction.yaw-predicted.yaw+math.pi)%(math.pi*2)-math.pi;predicted.yaw+=delta*blend
    predicted.damage=correction.damage;predicted.crashes=correction.crashes
   end
  end
 else
  local state,error=replayPlayer:sample(replayTime)
  if state then
   predicted=state
   if not replayPaused and stream:ready(predicted.z)then replayTime=math.min(replayPlayer.meta.duration,replayTime+dt*replayRate)end
   if replayTime>=replayPlayer.meta.duration then replayPaused=true;ui.pauseButton.Text='PLAY'end
  else notice(error,.5)end
  local newOrigin=-math.floor(predicted.z/4096)*4096
  if newOrigin~=(run.originZ or 0)then
   local delta=Vector3.new(0,0,newOrigin-(run.originZ or 0));stream:shift(newOrigin);run.originZ=newOrigin;workspace.CurrentCamera.CFrame+=delta
  end
 end
 roadAt+=dt
 if roadAt>.10 then roadAt=0;stream:update(predicted.z)end
 stream:work(.0025)
 if mode=='drive'and not readySent and run.owner==player.UserId and stream:ready(predicted.z)then readySent=true;remotes.Action:FireServer('ready')end
 local cf=Assets.pose(visual,predicted,route,stream:offset(),dt*(mode=='replay'and (replayPaused and 0 or replayRate)or 1))
 updateCamera(cf,dt)
 local clock=mode=='replay'and replayTime or(clockValue+(run.status=='running'and math.min(.3,os.clock()-clockAt)or 0)+(run.penalty or 0))
 if ghostPlayer and ghostVisual then
  local ghost=ghostPlayer:sample(clock)
  if ghost then
   Assets.pose(ghostVisual,ghost,route,stream:offset(),dt)
   ui.ghost.Text=string.format('SAVED GHOST · %+0.1f m along the road',(predicted.z-ghost.z)*C.StudMetres)
  else ui.ghost.Text='Loading saved ghost…'end
 else ui.ghost.Text=mode=='replay'and 'SAVED REPLAY · P pause / , . seek / RMB orbit'or 'Every finished run saves a replay. Beat your time to update its ghost.'end
 uiAt+=dt
 if uiAt>.1 then
  uiAt=0;ui:runInfo(run,predicted,route,clock)
  if mode=='replay'then
   ui.playhead.Size=UDim2.fromScale(math.clamp(replayTime/math.max(1,replayPlayer.meta.duration),0,1),1)
   ui.replayLabel.Text=UI.time(replayTime)..' / '..UI.time(replayPlayer.meta.duration)..'   '..cameraNames[cameraMode]..' CAMERA   ·   '..(replayPlayer.meta.storage or '')
  end
 end
 slowTime=dt>.027 and slowTime+dt or math.max(0,slowTime-dt*.35)
 if slowTime>6 and ui.quality~='low'then
  ui.quality=ui.quality=='high'and 'medium'or 'low';stream.quality=ui.quality;ui.qualityButton.Text='QUALITY: '..ui.quality:upper()..' · AUTO';slowTime=0
 end
end)
-- Opt in with the launcher; the original game keeps its camera and interface.
