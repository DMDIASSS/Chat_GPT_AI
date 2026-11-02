local UI={};UI.__index=UI
local Players=game:GetService('Players');local UIS=game:GetService('UserInputService')
local C=require(game:GetService('ReplicatedStorage').BackseatExpedition.Shared.Config)
local OriginalCourse=require(game:GetService('ReplicatedStorage').BackseatExpedition.Shared.OriginalCourse)
local D=require(game:GetService('ReplicatedStorage').BackseatExpedition.Shared.Dynamics)
local Assets=require(game:GetService('ReplicatedStorage').BackseatExpedition.Shared.Assets)
local palette={ink=Color3.fromRGB(14,19,24),panel=Color3.fromRGB(22,29,36),card=Color3.fromRGB(35,44,52),
 light=Color3.fromRGB(241,244,246),muted=Color3.fromRGB(180,194,203),gold=Color3.fromRGB(255,194,79),red=Color3.fromRGB(239,126,99)}
local function frame(parent,name,x,y,w,h,bg)
 local f=Instance.new('Frame');f.Name=name;f.Position=UDim2.fromOffset(x,y);f.Size=UDim2.fromOffset(w,h);f.BackgroundColor3=bg or palette.panel;f.BorderSizePixel=0;f.Parent=parent;return f
end
local function label(parent,text,x,y,w,h,size,tint)
 local t=Instance.new('TextLabel');t.Position=UDim2.fromOffset(x,y);t.Size=UDim2.fromOffset(w,h);t.BackgroundTransparency=1
 t.Text=text;t.TextColor3=tint or palette.light;t.Font=Enum.Font.Gotham;t.TextSize=size or 16;t.TextXAlignment=Enum.TextXAlignment.Left;t.TextWrapped=true;t.Parent=parent;return t
end
local function button(parent,text,x,y,w,h,callback,accent)
 local b=Instance.new('TextButton');b.Position=UDim2.fromOffset(x,y);b.Size=UDim2.fromOffset(w,h);b.BackgroundColor3=accent and palette.gold or palette.card
 b.TextColor3=accent and palette.ink or palette.light;b.Text=text;b.Font=Enum.Font.GothamBold;b.TextSize=15;b.BorderSizePixel=0;b.AutoButtonColor=true;b.Parent=parent
 local corner=Instance.new('UICorner');corner.CornerRadius=UDim.new(0,6);corner.Parent=b
 if callback then b.Activated:Connect(callback)end;return b
end
function UI.time(seconds)
 seconds=math.max(0,seconds or 0);return string.format('%02d:%05.2f',math.floor(seconds/60),seconds%60)
end
function UI.new(callbacks)
 local gui=Instance.new('ScreenGui');gui.Name='ExpeditionUI';gui.ResetOnSpawn=false;gui.IgnoreGuiInset=true;gui.DisplayOrder=10000;gui.Parent=Players.LocalPlayer:WaitForChild('PlayerGui')
 local self=setmetatable({gui=gui,callbacks=callbacks,mode=C.Modes[1],car=C.Cars[1],quality='medium',xp=0,speedIndex=3},UI)
 self.originalCourse=C.UseOriginalStages and OriginalCourse.default(C);self.useOriginal=self.originalCourse~=nil
 self.launcher=button(gui,'EXPEDITION',0,0,160,40,function()callbacks.open()end,true)
 self.launcher.Position=UDim2.new(1,-180,0,72)
 self.closeButton=button(gui,'RETURN TO ORIGINAL',0,0,180,36,function()callbacks.close()end)
 self.closeButton.Position=UDim2.new(1,-200,0,24);self.closeButton.Visible=false
 local canvas=frame(gui,'ResponsiveCanvas',0,0,1180,680,palette.ink);canvas.AnchorPoint=Vector2.new(.5,.5);canvas.Position=UDim2.fromScale(.5,.5);canvas.BackgroundTransparency=1
 local scale=Instance.new('UIScale');scale.Parent=canvas
 self.scale=scale;self.canvas=canvas
 local menu=frame(canvas,'GarageMenu',0,0,1180,680,palette.ink);self.menu=menu
 local grad=Instance.new('UIGradient');grad.Color=ColorSequence.new(palette.ink,palette.panel);grad.Rotation=28;grad.Parent=menu
 button(menu,'SETTINGS · F4',950,25,195,36,function()callbacks.settings()end)
 label(menu,'BACKSEAT / EXPEDITION',34,25,760,30,19,palette.gold).Font=Enum.Font.GothamBold
 label(menu,'Find the long\nway home.',32,79,660,125,53).Font=Enum.Font.GothamBold
 local preview=Instance.new('ViewportFrame');preview.Name='CarPreview';preview.Position=UDim2.fromOffset(420,78)
 preview.Size=UDim2.fromOffset(260,130);preview.BackgroundTransparency=1
 preview.Ambient=Color3.fromRGB(185,185,185);preview.LightColor=Color3.fromRGB(255,244,218)
 preview.LightDirection=Vector3.new(-1,-1,-1);preview.Parent=menu
 local previewCamera=Instance.new('Camera');previewCamera.FieldOfView=34
 previewCamera.CFrame=CFrame.lookAt(Vector3.new(15,9,-19),Vector3.new(0,.5,0));previewCamera.Parent=preview
 preview.CurrentCamera=previewCamera
 self.previewWorld=Instance.new('WorldModel');self.previewWorld.Parent=preview
 label(menu,'A fresh road. A proper finish. Your best run, waiting as a ghost.',36,211,640,40,17,palette.muted)
 self.modeButtons={}
 for i,mode in ipairs(C.Modes)do
  local x,y=36+((i-1)%2)*318,274+math.floor((i-1)/2)*88
  local b=button(menu,mode.name,x,y,300,76,function()self.mode=mode;self:selection()end)
  b.Text='';label(b,mode.name,14,7,270,24,18).Font=Enum.Font.GothamBold
  label(b,mode.tag,14,35,268,32,12,palette.muted);self.modeButtons[i]=b
 end
 label(menu,'YOUR GARAGE',36,463,600,22,12,palette.gold)
 local garage=Instance.new('ScrollingFrame');garage.Name='AllCars';garage.Position=UDim2.fromOffset(36,494);garage.Size=UDim2.fromOffset(625,55)
 garage.BackgroundTransparency=1;garage.BorderSizePixel=0;garage.ScrollingDirection=Enum.ScrollingDirection.X;garage.ScrollBarThickness=6;garage.CanvasSize=UDim2.fromOffset(#C.Cars*210,0);garage.Parent=menu
 self.carButtons={}
 for i,car in ipairs(C.Cars)do
  local b=button(garage,car.name,(i-1)*210,0,196,48,function()self.car=car;self:selection()end);self.carButtons[i]=b
 end
 self.courseButton=button(menu,'MAP: ORIGINAL',36,574,618,22,function()
  if self.originalCourse then self.useOriginal=not self.useOriginal;self:selection()end
 end)
 self.carDescription=label(menu,'',36,549,625,28,13,palette.muted)
 local seed=Instance.new('TextBox');seed.Name='CourseSeed';seed.Position=UDim2.fromOffset(36,600);seed.Size=UDim2.fromOffset(155,42)
 seed.Text='';seed.PlaceholderText='Seed · random';seed.ClearTextOnFocus=false;seed.TextColor3=palette.light;seed.PlaceholderColor3=palette.muted;seed.BackgroundColor3=palette.card;seed.TextSize=14;seed.Font=Enum.Font.Gotham;seed.Parent=menu;self.seed=seed
 self.startButton=button(menu,'TAKE THE ROAD →',205,600,269,42,function()callbacks.start(self.mode.id,self.car.id,tonumber(seed.Text),self.useOriginal and 'original'or 'generated')end,true)
 self.menuMessage=label(menu,'',36,650,640,24,14,palette.gold)
 button(menu,'REPLAY LIBRARY',489,600,165,42,function()callbacks.library()end)
 local side=frame(menu,'Roadbook',708,75,438,566,palette.card)
 label(side,'ROADBOOK / NEXT DEPARTURE',24,21,390,25,12,palette.gold)
 self.modeTitle=label(side,'',24,56,390,42,29);self.modeTitle.Font=Enum.Font.GothamBold
 self.modeDetail=label(side,'',24,103,385,50,15,palette.muted)
 label(side,'DRIVE / CO-DRIVE / RACE',24,184,390,23,12,palette.gold)
 self.drivers=frame(side,'Drivers',24,218,390,145,palette.card)
 button(side,'REFRESH OPEN SEATS',24,374,390,34,function()callbacks.lobby()end)
 self.saveStatus=label(side,'Loading your garage…',24,425,390,48,13,palette.muted)
 button(side,'RACE FRIENDS',24,480,390,34,function()self:openRaces()end)
 button(side,'QUALITY: MEDIUM',24,523,390,30,function()
  local order={'low','medium','high'};self.quality=order[(table.find(order,self.quality)or 2)%3+1]
  self.qualityButton.Text='QUALITY: '..self.quality:upper();callbacks.quality(self.quality)
 end)
 self.qualityButton=side:GetChildren()[#side:GetChildren()]
 -- Keep a direct reference, independent of child enumeration order.
 for _,child in ipairs(side:GetChildren())do if child:IsA('TextButton')and child.Text=='QUALITY: MEDIUM'then self.qualityButton=child end end
 self.hud=frame(canvas,'DrivingHUD',0,0,1180,680,palette.ink);self.hud.BackgroundTransparency=1;self.hud.Visible=false
 -- Keep the driving instruments below Roblox's core controls, leaving the centre clear.
 local top=frame(self.hud,'Run strip',20,64,1140,58,palette.ink);top.BackgroundTransparency=1
 local noteCard=frame(top,'Pacenote card',326,0,506,51,palette.ink);noteCard.BackgroundTransparency=.18
 local corner=Instance.new('UICorner');corner.CornerRadius=UDim.new(0,8);corner.Parent=noteCard
 self.runSummary=label(top,'',4,1,302,48,15,palette.light);self.runSummary.TextStrokeTransparency=.5
 self.note=label(noteCard,'STRAIGHT · opens',15,0,476,51,23,palette.gold);self.note.Font=Enum.Font.GothamBold;self.note.TextXAlignment=Enum.TextXAlignment.Center
 self.timer=label(top,'00:00.00',884,0,246,48,28);self.timer.TextXAlignment=Enum.TextXAlignment.Right;self.timer.TextStrokeTransparency=.55
 self.message=label(self.hud,'',190,145,800,68,26,palette.light);self.message.TextXAlignment=Enum.TextXAlignment.Center;self.message.Font=Enum.Font.GothamBold;self.message.TextStrokeTransparency=.4
 self.speed=label(self.hud,'0',960,520,194,73,62);self.speed.Font=Enum.Font.GothamBold;self.speed.TextXAlignment=Enum.TextXAlignment.Right;self.speed.TextStrokeTransparency=.55
 label(self.hud,'KM/H',1060,595,94,20,13,palette.light).TextXAlignment=Enum.TextXAlignment.Right
 local telemetryCard=frame(self.hud,'Telemetry card',24,532,589,66,palette.ink);telemetryCard.BackgroundTransparency=.23
 local telemetryCorner=Instance.new('UICorner');telemetryCorner.CornerRadius=UDim.new(0,7);telemetryCorner.Parent=telemetryCard
 self.telemetry=label(telemetryCard,'',13,3,565,60,15,palette.light)
 self.assetStatus=label(self.hud,'',28,600,770,22,13,palette.gold)
 self.ghost=label(self.hud,'',28,498,660,28,15,palette.gold);self.ghost.TextStrokeTransparency=.5
 self.endButton=button(self.hud,'RETIRE & SAVE',977,133,180,31,function()callbacks.stop()end);self.endButton.TextSize=12;self.endButton.BackgroundTransparency=.16
 local tools=frame(self.hud,'Driving tools',0,0,945,680,palette.ink);tools.BackgroundTransparency=1;self.drivingTools=tools
 local function drivingButton(text,x,w,fn)
  local b=button(tools,text,x,632,w,30,fn);b.TextSize=12;b.BackgroundTransparency=.16;return b
 end
 drivingButton('R · CHECKPOINT',24,175,function()callbacks.recover()end)
 drivingButton('B · MARK MOMENT',211,190,function()callbacks.bookmark()end)
 drivingButton('C · CENTER LOOK',413,150,function()callbacks.camera()end)
 drivingButton('SETTINGS · F4',576,168,function()callbacks.settings()end)
 self.serviceButton=drivingButton('T · SERVICE',756,175,function()callbacks.service()end)
 self.toolToggle=button(self.hud,'HIDE CONTROLS',970,632,188,30,function()
  self.toolsExpanded=not self.drivingTools.Visible;self.drivingTools.Visible=self.toolsExpanded
  self.toolToggle.Text=self.toolsExpanded and 'HIDE CONTROLS'or 'CONTROLS'
 end);self.toolToggle.TextSize=12;self.toolToggle.BackgroundTransparency=.16
 self.standings=label(self.hud,'',946,215,212,230,15,palette.gold);self.standings.TextStrokeTransparency=.4
 self.coRoadbook=label(self.hud,'',24,225,355,174,18,palette.light);self.coRoadbook.Visible=false;self.coRoadbook.TextStrokeTransparency=.5
 self.leave=button(self.hud,'LEAVE CO-DRIVER SEAT',947,174,210,31,function()callbacks.leave()end);self.leave.Visible=false
 self.calls={}
 for i,n in ipairs({'left','right','caution'})do
  local b=button(self.hud,n:upper(),24+(i-1)*132,434,122,37,function()callbacks.call(n)end);b.Visible=false;self.calls[i]=b
 end
 local library=frame(canvas,'ReplayLibrary',0,0,1180,680,palette.ink);library.Visible=false;self.libraryPanel=library
 label(library,'THE ROAD, REMEMBERED.',36,34,850,48,34).Font=Enum.Font.GothamBold
 label(library,'Saved runs and fastest ghosts · each run keeps its exact road seed',38,93,1020,32,16,palette.muted)
 button(library,'← GARAGE',953,35,190,42,function()self:show('menu');callbacks.lobby()end)
 local scroll=Instance.new('ScrollingFrame');scroll.Name='SavedRuns';scroll.Position=UDim2.fromOffset(36,147);scroll.Size=UDim2.fromOffset(1110,482)
 scroll.BackgroundTransparency=1;scroll.BorderSizePixel=0;scroll.ScrollBarThickness=4;scroll.CanvasSize=UDim2.fromOffset(0,0);scroll.Parent=library;self.records=scroll
 self.libraryStatus=label(library,'',36,640,1080,27,13,palette.muted)
 self.result=frame(canvas,'RunResult',190,115,800,450,palette.ink);self.result.Visible=false
 label(self.result,'ROADBOOK / RUN COMPLETE',32,28,730,25,13,palette.gold)
 self.resultTitle=label(self.result,'Made it home.',30,82,730,60,43);self.resultTitle.Font=Enum.Font.GothamBold
 self.resultInfo=label(self.result,'',32,164,730,104,21)
 self.resultSaved=label(self.result,'Saving replay and ghost…',32,291,730,48,14,palette.muted)
 self.watchButton=button(self.result,'WATCH REPLAY',32,365,230,44,function()if self.resultMeta and self.resultReady then callbacks.watch(self.resultMeta)end end)
 button(self.result,'SAME ROAD AGAIN',278,365,230,44,function()
  if self.resultMeta and self.resultReady then callbacks.start(self.resultMeta.mode,self.resultMeta.car,self.resultMeta.seed,self.resultMeta.stage and 'original'or 'generated')end
 end,true)
 button(self.result,'GARAGE',524,365,245,44,function()self:show('menu');callbacks.lobby()end)
 local replay=frame(canvas,'ReplayControls',0,563,1180,117,palette.ink);self.replayControls=replay;replay.Visible=false
 self.replayLabel=label(replay,'',20,8,1140,23,13,palette.muted)
 local timeline=button(replay,'',20,42,1140,16,nil);timeline.BackgroundColor3=palette.card;self.timeline=timeline
 self.playhead=frame(timeline,'Playhead',0,0,0,16,palette.gold)
 local drag=false
 local function scrub(x)callbacks.seek(math.clamp((x-timeline.AbsolutePosition.X)/math.max(1,timeline.AbsoluteSize.X),0,1))end
 timeline.InputBegan:Connect(function(event)if event.UserInputType==Enum.UserInputType.MouseButton1 or event.UserInputType==Enum.UserInputType.Touch then drag=true;scrub(event.Position.X)end end)
 UIS.InputChanged:Connect(function(event)if drag and (event.UserInputType==Enum.UserInputType.MouseMovement or event.UserInputType==Enum.UserInputType.Touch)then scrub(event.Position.X)end end)
 UIS.InputEnded:Connect(function(event)if event.UserInputType==Enum.UserInputType.MouseButton1 or event.UserInputType==Enum.UserInputType.Touch then drag=false end end)
 self.pauseButton=button(replay,'PAUSE',20,72,130,34,function()callbacks.pause()end)
 button(replay,'−5 s',163,72,100,34,function()callbacks.skip(-5)end)
 button(replay,'+5 s',276,72,100,34,function()callbacks.skip(5)end)
 self.rateButton=button(replay,'1×',390,72,110,34,function()
  self.speedIndex=self.speedIndex%5+1;local speed=({.25,.5,1,2,4})[self.speedIndex];self.rateButton.Text=speed..'×';callbacks.rate(speed)
 end)
 button(replay,'C · CAMERA',514,72,178,34,function()callbacks.camera()end)
 button(replay,'EXIT REPLAY',950,72,210,34,function()callbacks.exitReplay()end)
 local race=frame(canvas,'FriendRaces',210,92,760,495,palette.panel);race.Visible=false;self.racePanel=race
 label(race,'RALLY / FRIEND RACES',24,20,610,34,25,palette.gold).Font=Enum.Font.GothamBold
 button(race,'CLOSE',635,20,101,34,function()race.Visible=false end)
 label(race,'Same road, simultaneous start. Separate collision lanes. Fastest finish wins.',24,60,705,41,15,palette.muted)
 self.raceRows=frame(race,'Rooms',24,113,712,271,palette.panel)
 button(race,'HOST RALLY',24,401,163,38,function()callbacks.race('Create')end,true)
 button(race,'READY',201,401,153,38,function()callbacks.race('Ready',{ready=true})end)
 button(race,'START RACE',368,401,167,38,function()callbacks.race('Start')end,true)
 button(race,'LEAVE ROOM',549,401,187,38,function()callbacks.race('Leave')end)
 label(race,'Host selects seed, damage and assists in setup. Choose your car before readying. Refresh from garage for new rooms.',24,450,712,35,12,palette.muted)
 -- Native-size touch controls remain usable independently of menu scaling.
 self.touch=Instance.new('Frame');self.touch.Name='TouchControls';self.touch.Size=UDim2.fromScale(1,1);self.touch.BackgroundTransparency=1;self.touch.Visible=false;self.touch.Parent=gui
 for _,spec in ipairs({{'◀','left',18,-155},{'▶','right',104,-155},{'BRAKE','brake',-190,-155},{'GO','throttle',-104,-155}})do
  local b=button(self.touch,spec[1],0,0,78,72,nil,spec[2]=='throttle')
  b.Position=UDim2.new(spec[3]<0 and 1 or 0,spec[3],1,spec[4]);b.TextSize=18
  b.InputBegan:Connect(function(e)if e.UserInputType==Enum.UserInputType.Touch or e.UserInputType==Enum.UserInputType.MouseButton1 then callbacks.touch(spec[2],true)end end)
  b.InputEnded:Connect(function(e)if e.UserInputType==Enum.UserInputType.Touch or e.UserInputType==Enum.UserInputType.MouseButton1 then callbacks.touch(spec[2],false)end end)
 end
 self:selection();self:resize();canvas.Visible=false;return self
end
function UI:resize()
 local camera=workspace.CurrentCamera;local v=camera and camera.ViewportSize or Vector2.new(1280,720)
 self.scale.Scale=math.min(v.X/1220,v.Y/720)
end
function UI:selection()
 if self.previewWorld and self.previewCarId~=self.car.id then
  if self.previewCar then self.previewCar.model:Destroy()end
  -- Show a complete car immediately, independently of external mesh permissions.
  self.previewCar=Assets.car(self.previewWorld,self.car,false,C.ImportedVisuals)
  self.previewCarId=self.car.id
 end
 for i,b in ipairs(self.modeButtons)do b.BackgroundColor3=C.Modes[i]==self.mode and Color3.fromRGB(61,85,63)or palette.card end
 for i,b in ipairs(self.carButtons)do
  local car=C.Cars[i];b.BackgroundColor3=car==self.car and Color3.fromRGB(61,85,63)or palette.card
  b.Text=car.name..(self.xp<car.unlock and ' · '..car.unlock..' XP'or '')
 end
 self.carDescription.Text=string.format('%d kg · %d hp · %d Nm · %d:%d balance · %.1f studs wheelbase',self.car.mass,self.car.power,self.car.torque,math.floor((1-self.car.rearShare)*100+.5),math.floor(self.car.rearShare*100+.5),self.car.wheelbase)
 self.courseButton.Text=self.useOriginal and ('MAP: '..self.originalCourse.name:upper()..' · ORIGINAL OBJECTS')or 'MAP: GENERATED · PORTABLE ALTERNATIVE'
 self.modeTitle.Text=self.mode.name
 self.modeDetail.Text=self.mode.length==0 and 'An endless road. Bank at any point.\nEvery completed run keeps its replay.'or string.format('%.1f km · finishable seeded stage\nCheckpoint recovery adds 5 seconds.',self.mode.length*C.StudMetres/1000)
 if self.useOriginal then
  local stage=self.originalCourse;self.modeTitle.Text=stage.name
  self.modeDetail.Text=string.format('%.2f km · uploaded original map\n%s',stage.length*C.StudMetres/1000,stage.incomplete and 'Saved section only: later road is absent.'or 'Original roads, scenery and service park.')
 end
end
function UI:show(which)
 if self.racePanel and which~='menu'then self.racePanel.Visible=false end
 self.menu.Visible=which=='menu';self.hud.Visible=which=='drive'or which=='replay';self.libraryPanel.Visible=which=='library';self.result.Visible=which=='result'
 self.replayControls.Visible=which=='replay'
 self.drivingTools.Visible=which=='drive';self.toolToggle.Visible=which=='drive'
 self.assetStatus.Visible=which=='drive'
 self.telemetry.Parent.Visible=which=='drive'
 self.touch.Visible=which=='drive'and UIS.TouchEnabled
 self.mode= self.mode or C.Modes[1]
end
function UI:lobby(data)
 self.races=data.races or {};self.raceData=data.race
 if self.racePanel.Visible then self:renderRaces()end
 if data.library then self.xp=data.library.xp or 0;self.saveStatus.Text=(data.library.status or '')..'\n'..self.xp..' XP';self:selection()end
 for _,c in ipairs(self.drivers:GetChildren())do c:Destroy()end
 if #(data.drivers or {})==0 then label(self.drivers,'No open seats yet. Start a road and a friend can join you.',0,0,385,100,16,palette.muted)end
 for i,d in ipairs(data.drivers or {})do if i<=3 then button(self.drivers,d.name..' · JOIN',0,(i-1)*47,390,39,function()self.callbacks.join(d.owner)end)end end
end
function UI:openRaces()
 self.racePanel.Visible=true;self:renderRaces();self.callbacks.lobby()
end
function UI:renderRaces()
 for _,o in ipairs(self.raceRows:GetChildren())do o:Destroy()end
 local race=self.raceData
 if race then
  label(self.raceRows,'ROOM '..race.id..'  /  SEED '..race.seed..'  /  '..race.status:upper(),0,0,710,30,16,palette.gold)
  for i,m in ipairs(race.members or {})do
   label(self.raceRows,(m.ready and '✓ 'or '○ ')..m.name..'   /   '..m.car..(m.userId==race.host and '   HOST'or ''),4,37+(i-1)*29,700,28,15)
  end
 else
  if #(self.races or {})==0 then label(self.raceRows,'Host a rally, then ask friends in this server to join from RACE FRIENDS.',3,45,700,120,22,palette.muted)end
  for i,room in ipairs(self.races or {})do if i<=5 then
   button(self.raceRows,room.name..' · '..#room.members..'/8 · JOIN',0,(i-1)*50,710,43,function()self.callbacks.race('Join',{id=room.id})end)
  end end
 end
end
function UI:raceState(data)
 self.raceData=data
 if data and data.status=='lobby'then self.racePanel.Visible=true;self:renderRaces()
 elseif data and data.status~='lobby'then self.racePanel.Visible=false
 elseif self.racePanel.Visible then self:renderRaces()end
 local lines={}
 if data and data.status~='lobby'then
  lines[1]='RALLY / '..data.status:upper()
  for i,m in ipairs(data.members or {})do
   local result=m.dnf and 'RETIRED'or(m.finished and UI.time(m.time)or string.format('%.0f m',m.z*C.StudMetres))
   lines[#lines+1]=i..'. '..m.name..'\n   '..result
  end
 end
 self.standings.Text=table.concat(lines,'\n')
end
function UI:library(data)
 self:show('library');self.libraryStatus.Text=data.status or '';self.xp=data.xp or self.xp
 for _,child in ipairs(self.records:GetChildren())do child:Destroy()end
 local list,seen={},{}
 for _,collection in ipairs({data.records or {},data.bests or {}})do for _,r in ipairs(collection)do if not seen[r.id]then seen[r.id]=true;list[#list+1]=r end end end
 table.sort(list,function(a,b)return a.created>b.created end)
 for i,r in ipairs(list)do
  local row=frame(self.records,'Run',0,(i-1)*91,1090,79,palette.card)
  label(row,(r.mode or 'rally'):upper()..' / '..(r.car or 'hatch'):upper(),16,8,510,24,17).Font=Enum.Font.GothamBold
  label(row,'Seed '..r.seed..' · '..UI.time(r.duration)..' · '..(r.storage or 'Session only'),16,39,680,25,13,palette.muted)
  button(row,'WATCH',801,19,120,40,function()self.callbacks.watch(r)end)
  button(row,'RACE ROAD',935,19,140,40,function()self.callbacks.start(r.mode,r.car,r.seed,r.stage and 'original'or 'generated')end,true)
 end
 if #list==0 then label(self.records,'Your first road is waiting. Finish or bank a run to save its replay.',15,60,1020,100,23,palette.muted)end
 self.records.CanvasSize=UDim2.fromOffset(0,#list*91)
end
function UI:resultScreen(meta)
 self:show('result');self.resultMeta=meta;self.resultReady=false
 self.resultTitle.Text=meta.completed and 'Made it home.'or(meta.banked and 'A good place to stop.'or 'Every road teaches you.')
 self.resultInfo.Text=string.format('%s     +%d XP\n%.2f km · %d contacts · %.0f s penalties',UI.time(meta.duration),meta.reward or 0,(meta.progress or 0)*C.StudMetres/1000,meta.crashes or 0,meta.penalty or 0)
 self.resultSaved.Text='Saving replay and ghost…';self.watchButton.Text='SAVING…'
end
function UI:saved(data)
 if self.resultMeta and self.resultMeta.id==data.id then self.resultReady=true;self.resultSaved.Text=data.status;self.watchButton.Text='WATCH REPLAY'end
end
function UI:visualStatus(visual)
 local original=visual and (visual.interiorReady or visual.interior)
 self.assetStatus.Text=original and (visual.skinStatus=='partial'and 'ORIGINAL PARTS · SOME EXTERNAL MESHES UNAVAILABLE'or '')or (visual and visual.skinStatus=='loading'and 'LOADING ORIGINAL INTERIOR…'or 'PORTABLE COCKPIT · ORIGINAL INTERIOR NOT LOADED')
 self.assetStatus.TextColor3=palette.gold
end
function UI:runInfo(run,s,route,clock)
 local climate=route:conditions(s.z)
 self.runSummary.Text=(run.stageName or (route.original and route.name)or run.mode or 'replay'):upper()..(run.stage and ''or (' / SEED '..run.seed))..'\n'..(route.original and 'Uploaded original stage'or C.Biomes[route:point(s.z).biome].name)..string.format(' · %d°C · wet %d%%',climate.temperature,climate.wetness*100)
 self.note.Text=run.missed and 'MISSED CHECKPOINT · press R'or route:call(s.z,s.v)
 self.timer.Text=UI.time(clock);self.speed.Text=tostring(math.floor(math.abs(s.v)*C.StudMetres*3.6+.5))
 local progress=run.length and run.length>0 and string.format('%.2f / %.2f km',math.max(0,s.z)*C.StudMetres/1000,run.length*C.StudMetres/1000)or string.format('%.2f km',math.max(0,s.z)*C.StudMetres/1000)
 local tyre=D.telemetry(s)
 self.telemetry.Text=string.format('GEAR %s   ·   %d RPM   ·   %s   ·   BODY %d%%\nTYRES %.0f%%   ·   %.0f°C   ·   %d PUNCTURES   ·   %s',
  s.v<-.5 and 'R'or tostring(s.gear or 1),math.floor(s.rpm or 850),s.tcsActive and 'TCS'or(s.absActive and 'ABS'or 'RALLY'),100-math.floor(s.damage or 0),
  tyre.pressure*100,tyre.temperature,tyre.punctures,progress)
 self.endButton.Text=run.mode=='endless'and 'BANK RUN & SAVE'or 'RETIRE & SAVE'
 local passenger=run.passenger==Players.LocalPlayer.UserId;self.leave.Visible=passenger
 self.coRoadbook.Visible=passenger
 self.serviceButton.Visible=not passenger and not self.replayControls.Visible
 local expanded=self.toolsExpanded
 if expanded==nil then expanded=math.abs(s.v)<2 or passenger end
 self.drivingTools.Visible=expanded and not self.replayControls.Visible
 self.toolToggle.Text=self.drivingTools.Visible and 'HIDE CONTROLS'or 'CONTROLS'
 self.ghost.Visible=not self.replayControls.Visible and self.ghost.Text~=''and not string.find(self.ghost.Text,'Every finished run',1,true)
 if passenger then
  local lines={'CO-DRIVER ROADBOOK'}
  for i,lead in ipairs({2.5,5,8})do local ahead=math.max(55,math.abs(s.v)*lead);lines[#lines+1]=string.format('%d m · %s',math.floor(ahead*C.StudMetres),route:note(s.z+ahead-100))end
  lines[#lines+1]='J / K call turn · L caution'
  self.coRoadbook.Text=table.concat(lines,'\n')
 end
 for _,b in ipairs(self.calls)do b.Visible=passenger end
 self.endButton.Visible=not passenger and self.replayControls.Visible==false
end
return UI
