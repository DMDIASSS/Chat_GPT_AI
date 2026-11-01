local UI={};UI.__index=UI
local Players=game:GetService('Players');local UIS=game:GetService('UserInputService')
local C=require(game:GetService('ReplicatedStorage').BackseatExpedition.Shared.Config)
local palette={ink=Color3.fromRGB(20,35,32),panel=Color3.fromRGB(29,48,42),card=Color3.fromRGB(41,62,52),
 light=Color3.fromRGB(242,232,207),muted=Color3.fromRGB(169,184,163),gold=Color3.fromRGB(233,180,84),red=Color3.fromRGB(224,119,91)}
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
 self.launcher=button(gui,'EXPEDITION',0,0,160,40,function()callbacks.open()end,true)
 self.launcher.Position=UDim2.new(1,-180,0,72)
 self.closeButton=button(gui,'RETURN TO ORIGINAL',0,0,180,36,function()callbacks.close()end)
 self.closeButton.Position=UDim2.new(1,-200,0,24);self.closeButton.Visible=false
 local canvas=frame(gui,'ResponsiveCanvas',0,0,1180,680,palette.ink);canvas.AnchorPoint=Vector2.new(.5,.5);canvas.Position=UDim2.fromScale(.5,.5);canvas.BackgroundTransparency=1
 local scale=Instance.new('UIScale');scale.Parent=canvas
 self.scale=scale;self.canvas=canvas
 local menu=frame(canvas,'GarageMenu',0,0,1180,680,palette.ink);self.menu=menu
 local grad=Instance.new('UIGradient');grad.Color=ColorSequence.new(palette.ink,palette.panel);grad.Rotation=28;grad.Parent=menu
 label(menu,'BACKSEAT / EXPEDITION',34,25,760,30,19,palette.gold).Font=Enum.Font.GothamBold
 label(menu,'Find the long\nway home.',32,79,660,125,53).Font=Enum.Font.GothamBold
 label(menu,'A fresh road. A proper finish. Your best run, waiting as a ghost.',36,211,640,40,17,palette.muted)
 self.modeButtons={}
 for i,mode in ipairs(C.Modes)do
  local x,y=36+((i-1)%2)*318,274+math.floor((i-1)/2)*88
  local b=button(menu,mode.name,x,y,300,76,function()self.mode=mode;self:selection()end)
  b.Text='';label(b,mode.name,14,7,270,24,18).Font=Enum.Font.GothamBold
  label(b,mode.tag,14,35,268,32,12,palette.muted);self.modeButtons[i]=b
 end
 label(menu,'YOUR GARAGE',36,463,600,22,12,palette.gold)
 self.carButtons={}
 for i,car in ipairs(C.Cars)do
  local b=button(menu,car.name,36+(i-1)*210,494,196,48,function()self.car=car;self:selection()end);self.carButtons[i]=b
 end
 self.carDescription=label(menu,'',36,549,625,28,13,palette.muted)
 local seed=Instance.new('TextBox');seed.Name='CourseSeed';seed.Position=UDim2.fromOffset(36,600);seed.Size=UDim2.fromOffset(155,42)
 seed.Text='';seed.PlaceholderText='Seed · random';seed.ClearTextOnFocus=false;seed.TextColor3=palette.light;seed.PlaceholderColor3=palette.muted;seed.BackgroundColor3=palette.card;seed.TextSize=14;seed.Font=Enum.Font.Gotham;seed.Parent=menu;self.seed=seed
 button(menu,'TAKE THE ROAD →',205,600,269,42,function()callbacks.start(self.mode.id,self.car.id,tonumber(seed.Text))end,true)
 button(menu,'REPLAY LIBRARY',489,600,165,42,function()callbacks.library()end)
 local side=frame(menu,'Roadbook',708,75,438,566,palette.card)
 label(side,'ROADBOOK / NEXT DEPARTURE',24,21,390,25,12,palette.gold)
 self.modeTitle=label(side,'',24,56,390,42,29);self.modeTitle.Font=Enum.Font.GothamBold
 self.modeDetail=label(side,'',24,103,385,50,15,palette.muted)
 label(side,'SOLO + CO-DRIVER SEAT',24,184,390,23,12,palette.gold)
 self.drivers=frame(side,'Drivers',24,218,390,145,palette.card)
 button(side,'REFRESH OPEN SEATS',24,374,390,34,function()callbacks.lobby()end)
 self.saveStatus=label(side,'Loading your garage…',24,425,390,48,13,palette.muted)
 button(side,'QUALITY: MEDIUM',24,493,390,34,function()
  local order={'low','medium','high'};self.quality=order[(table.find(order,self.quality)or 2)%3+1]
  self.qualityButton.Text='QUALITY: '..self.quality:upper();callbacks.quality(self.quality)
 end)
 self.qualityButton=side:GetChildren()[#side:GetChildren()]
 -- Keep a direct reference, independent of child enumeration order.
 for _,child in ipairs(side:GetChildren())do if child:IsA('TextButton')and child.Text=='QUALITY: MEDIUM'then self.qualityButton=child end end
 self.hud=frame(canvas,'DrivingHUD',0,0,1180,680,palette.ink);self.hud.BackgroundTransparency=1;self.hud.Visible=false
 local top=frame(self.hud,'Run strip',0,0,1180,66,palette.ink);top.BackgroundTransparency=.08
 self.runSummary=label(top,'',22,9,390,48,14,palette.muted)
 self.note=label(top,'STRAIGHT · opens',400,9,500,48,21,palette.gold);self.note.Font=Enum.Font.GothamBold
 self.timer=label(top,'00:00.00',930,9,230,48,27);self.timer.TextXAlignment=Enum.TextXAlignment.Right
 self.message=label(self.hud,'',170,114,840,80,27,palette.light);self.message.TextXAlignment=Enum.TextXAlignment.Center;self.message.Font=Enum.Font.GothamBold
 self.speed=label(self.hud,'0',935,486,224,100,78);self.speed.Font=Enum.Font.GothamBold;self.speed.TextXAlignment=Enum.TextXAlignment.Right
 label(self.hud,'KM/H',1065,584,95,22,13,palette.gold).TextXAlignment=Enum.TextXAlignment.Right
 self.telemetry=label(self.hud,'',24,535,600,76,14,palette.muted)
 self.ghost=label(self.hud,'',24,490,660,28,15,palette.gold)
 self.endButton=button(self.hud,'RETIRE & SAVE',947,92,210,37,function()callbacks.stop()end)
 button(self.hud,'R · CHECKPOINT',24,623,175,36,function()callbacks.recover()end)
 button(self.hud,'B · MARK MOMENT',211,623,190,36,function()callbacks.bookmark()end)
 button(self.hud,'C · CAMERA',413,623,150,36,function()callbacks.camera()end)
 self.leave=button(self.hud,'LEAVE CO-DRIVER SEAT',947,137,210,36,function()callbacks.leave()end);self.leave.Visible=false
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
  if self.resultMeta and self.resultReady then callbacks.start(self.resultMeta.mode,self.resultMeta.car,self.resultMeta.seed)end
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
 for i,b in ipairs(self.modeButtons)do b.BackgroundColor3=C.Modes[i]==self.mode and Color3.fromRGB(61,85,63)or palette.card end
 for i,b in ipairs(self.carButtons)do
  local car=C.Cars[i];b.BackgroundColor3=car==self.car and Color3.fromRGB(61,85,63)or palette.card
  b.Text=car.name..(self.xp<car.unlock and ' · '..car.unlock..' XP'or '')
 end
 self.carDescription.Text=self.car.description
 self.modeTitle.Text=self.mode.name
 self.modeDetail.Text=self.mode.length==0 and 'An endless road. Bank at any point.\nEvery completed run keeps its replay.'or string.format('%.1f km · finishable seeded stage\nCheckpoint recovery adds 5 seconds.',self.mode.length*C.StudMetres/1000)
end
function UI:show(which)
 self.menu.Visible=which=='menu';self.hud.Visible=which=='drive'or which=='replay';self.libraryPanel.Visible=which=='library';self.result.Visible=which=='result'
 self.replayControls.Visible=which=='replay';self.touch.Visible=which=='drive'and UIS.TouchEnabled
 self.mode= self.mode or C.Modes[1]
end
function UI:lobby(data)
 if data.library then self.xp=data.library.xp or 0;self.saveStatus.Text=(data.library.status or '')..'\n'..self.xp..' XP';self:selection()end
 for _,c in ipairs(self.drivers:GetChildren())do c:Destroy()end
 if #(data.drivers or {})==0 then label(self.drivers,'No open seats yet. Start a road and a friend can join you.',0,0,385,100,16,palette.muted)end
 for i,d in ipairs(data.drivers or {})do if i<=3 then button(self.drivers,d.name..' · JOIN',0,(i-1)*47,390,39,function()self.callbacks.join(d.owner)end)end end
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
  button(row,'RACE ROAD',935,19,140,40,function()self.callbacks.start(r.mode,r.car,r.seed)end,true)
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
function UI:runInfo(run,s,route,clock)
 self.runSummary.Text=(run.mode or 'replay'):upper()..' / SEED '..run.seed..'\n'..C.Biomes[route:point(s.z).biome].name
 self.note.Text=run.missed and 'MISSED CHECKPOINT · press R'or route:note(s.z+math.abs(s.v))
 self.timer.Text=UI.time(clock);self.speed.Text=tostring(math.floor(math.abs(s.v)*C.StudMetres*3.6+.5))
 local progress=run.length and run.length>0 and string.format('%.2f / %.2f km',math.max(0,s.z)*C.StudMetres/1000,run.length*C.StudMetres/1000)or string.format('%.2f km',math.max(0,s.z)*C.StudMetres/1000)
 self.telemetry.Text=string.format('THROTTLE %3d%%   BRAKE %3d%%   STEER %+3d%%\n%s   ·   BODY %d%%   ·   R recover / B mark / C camera',
  (s.throttle or 0)*100,(s.brake or 0)*100,(s.steer or 0)*100,progress,100-math.floor(s.damage or 0))
 self.endButton.Text=run.mode=='endless'and 'BANK RUN & SAVE'or 'RETIRE & SAVE'
 local passenger=run.passenger==Players.LocalPlayer.UserId;self.leave.Visible=passenger
 for _,b in ipairs(self.calls)do b.Visible=passenger end
 self.endButton.Visible=not passenger and self.replayControls.Visible==false
end
return UI
