local Players=game:GetService("Players")
local World=game:GetService("Workspace")
local Replicated=game:GetService("ReplicatedStorage")
local Run=game:GetService("RunService")
local UIS=game:GetService("UserInputService")
local Http=game:GetService("HttpService")
local player=Players.LocalPlayer
local pg=assert(player:FindFirstChildOfClass("PlayerGui"),"Join the game before loading Rally Assist")
local old=pg:FindFirstChild("BackseatRallyAssist")
if old then
    local shutdown=old:FindFirstChild("Shutdown")
    if shutdown and shutdown:IsA("BindableEvent")then shutdown:Fire()else old:Destroy()end
end
local app={alive=true,enabled=false,version="1.0.0",connections={},status="Sit in the driver seat. F6 enables assists.",
    cfg={speed=1.4,turn=1.2,grip=1.2,maxKmh=180,pace=1,auto=false,line="Showcase",learn=false},
    trace={},routeCache={},driver=Driver.new(),ghost=Ghost.new(),input=Input.new(UIS)}
app.adapter=Adapter.new(player,World,Replicated,app.input)
local env=type(getgenv)=="function"and getgenv()or nil
if env then env.__BackseatRallyAssist=app end
local activeWindow=isrbxactive or isgameactive
if type(activeWindow)~="function"then activeWindow=nil end
local focused=true
local function connect(signal,callback)
    local c=signal:Connect(callback);app.connections[#app.connections+1]=c;return c
end
local function blocked()
    return not focused or UIS:GetFocusedTextBox()~=nil or(activeWindow and not activeWindow())
        or player:GetAttribute("InMenu")==true or player:GetAttribute("InGarage")==true
        or player:GetAttribute("InReplay")==true or player:GetAttribute("KnockedOut")==true
        or player:GetAttribute("InFrame")==true
end
local function release()
    app.input:release();app.adapter:restore();app.adapter:automatic(false)
    app.driver=Driver.new();app.autoReady=false;app.command=nil;app.epoch=(app.epoch or 0)+1
end
function app.stop(reason)
    app.enabled=false;release();app.status=reason or "Stopped. Normal controls restored."
end
function app.start()
    release();app.enabled=true;app.lastError=nil;app.status="Assists enabled; waiting for your car"
end
function app.toggleAuto()
    if not app.enabled and app.cfg.auto then app.start();return end
    app.cfg.auto=not app.cfg.auto;release()
    if app.cfg.auto then app.enabled=true;app.status="Autodrive armed; waiting for driver seat"
    else app.status="Manual driving with assistance"end
end
local ghostLease,ghostBase
local function learnGhost(on)
    app.cfg.learn=on
    if on and not ghostLease then
        ghostBase=player:GetAttribute("Ghost");ghostLease=true;player:SetAttribute("Ghost",true)
    elseif not on and ghostLease then
        if player:GetAttribute("Ghost")==true then player:SetAttribute("Ghost",ghostBase)end
        ghostLease=false
    end
end
local gui=Instance.new("ScreenGui")
gui.Name="BackseatRallyAssist";gui.ResetOnSpawn=false;gui.DisplayOrder=1000081;gui.ZIndexBehavior=Enum.ZIndexBehavior.Sibling
local shutdown=Instance.new("BindableEvent");shutdown.Name="Shutdown";shutdown.Parent=gui
local palette={bg=Color3.fromRGB(15,20,28),card=Color3.fromRGB(25,33,44),edge=Color3.fromRGB(49,65,80),
    text=Color3.fromRGB(237,244,251),dim=Color3.fromRGB(149,171,190),accent=Color3.fromRGB(62,209,182),danger=Color3.fromRGB(236,102,111)}
local function make(class,properties,parent)
    local o=Instance.new(class);for k,v in pairs(properties)do o[k]=v end;o.Parent=parent;return o
end
local function corner(o,r)make("UICorner",{CornerRadius=UDim.new(0,r)},o)end
local panel=make("Frame",{Name="Window",Size=UDim2.fromOffset(444,676),Position=UDim2.fromOffset(22,24),
    BackgroundColor3=palette.bg,BorderSizePixel=0,Active=true},gui)
corner(panel,12);make("UIStroke",{Color=palette.edge,Thickness=1},panel)
local scale=make("UIScale",{Scale=1},panel)
local header=make("TextButton",{Name="Titlebar",Size=UDim2.new(1,-88,0,46),BackgroundTransparency=1,Text="  BACKSEAT / RALLY ASSIST",
    TextColor3=palette.text,TextXAlignment=Enum.TextXAlignment.Left,TextSize=15,Font=Enum.Font.GothamBold,AutoButtonColor=false},panel)
local function button(name,text,x,y,w,h,parent,callback)
    local b=make("TextButton",{Name=name,Text=text,Position=UDim2.fromOffset(x,y),Size=UDim2.fromOffset(w,h),
        BackgroundColor3=palette.card,BorderSizePixel=0,TextColor3=palette.text,TextSize=13,Font=Enum.Font.GothamBold,AutoButtonColor=true},parent)
    corner(b,7);connect(b.Activated,callback);return b
end
local body=make("Frame",{Name="Body",BackgroundTransparency=1,Position=UDim2.fromOffset(14,48),Size=UDim2.new(1,-28,1,-58)},panel)
local minimized=false
local minimize=button("Minimize","–",354,9,32,28,panel,function()
    minimized=not minimized;body.Visible=not minimized
    panel.Size=UDim2.fromOffset(444,minimized and 46 or 676)
end)
button("Close","×",394,9,32,28,panel,function()app.destroy()end)
local status=make("TextLabel",{Name="Status",Size=UDim2.new(1,0,0,54),BackgroundColor3=palette.card,BorderSizePixel=0,
    TextColor3=palette.dim,TextSize=12,Font=Enum.Font.Code,TextWrapped=true,Text="Ready",TextXAlignment=Enum.TextXAlignment.Left},body)
corner(status,7)
local master=button("Master","Enable assists [F6]",0,64,204,34,body,function()if app.enabled then app.stop()else app.start()end end)
local auto=button("AutoDrive","Autodrive OFF [F7]",212,64,204,34,body,app.toggleAuto)
local sliders={};local draggingSlider,draggingPanel
local function slider(key,label,lo,hi,step,suffix,y)
    local row=make("Frame",{Name=key,BackgroundTransparency=1,Position=UDim2.fromOffset(0,y),Size=UDim2.new(1,0,0,53)},body)
    make("TextLabel",{Size=UDim2.new(1,-95,0,24),BackgroundTransparency=1,Text=label,TextSize=13,
        Font=Enum.Font.Gotham,TextColor3=palette.dim,TextXAlignment=Enum.TextXAlignment.Left},row)
    local value=make("TextBox",{Name="Value",Position=UDim2.new(1,-91,0,0),Size=UDim2.fromOffset(91,25),
        BackgroundColor3=palette.card,BorderSizePixel=0,TextColor3=palette.text,TextSize=13,
        Font=Enum.Font.GothamBold,ClearTextOnFocus=false},row);corner(value,5)
    local track=make("TextButton",{Name="Track",Position=UDim2.fromOffset(1,37),Size=UDim2.new(1,-2,0,6),Text="",
        BackgroundColor3=palette.card,BorderSizePixel=0,AutoButtonColor=false},row);corner(track,4)
    local fill=make("Frame",{Size=UDim2.fromScale(0,1),BackgroundColor3=palette.accent,BorderSizePixel=0},track);corner(fill,4)
    local knob=make("Frame",{Size=UDim2.fromOffset(12,12),AnchorPoint=Vector2.new(.5,.5),Position=UDim2.fromScale(0,.5),
        BackgroundColor3=palette.text,BorderSizePixel=0},track);corner(knob,6)
    local function set(v)
        if type(v)~="number"or v~=v or math.abs(v)==math.huge then return end
        app.cfg[key]=math.clamp(math.floor(v/step+.5)*step,lo,hi)
        local fraction=(app.cfg[key]-lo)/(hi-lo)
        fill.Size=UDim2.fromScale(fraction,1);knob.Position=UDim2.fromScale(fraction,.5)
        value.Text=(step>=1 and string.format("%.0f",app.cfg[key])or string.format("%.2f",app.cfg[key]))..suffix
    end
    local function drag(x)set(lo+math.clamp((x-track.AbsolutePosition.X)/math.max(track.AbsoluteSize.X,1),0,1)*(hi-lo))end
    connect(track.InputBegan,function(input)
        if input.UserInputType==Enum.UserInputType.MouseButton1 or input.UserInputType==Enum.UserInputType.Touch then
            draggingSlider={input=input,drag=drag};drag(input.Position.X)
        end
    end)
    connect(value.FocusLost,function()local v=tonumber((value.Text:gsub("[^%d%.%-]","")));set(v or app.cfg[key])end)
    sliders[key]=set;set(app.cfg[key])
end
slider("speed","Speed / power boost",1,3,.05,"×",110)
slider("turn","Turn response boost",1,2.5,.05,"×",166)
slider("grip","Grip boost",1,3,.05,"×",222)
slider("maxKmh","Autodrive speed cap",50,260,5," km/h",278)
slider("pace","Reference pace",.6,1.25,.05,"×",334)
local sources={"Showcase","Road","Personal ghost"}
local lineButton=button("Line","Line: Showcase",0,395,416,32,body,function()
    local index=table.find(sources,app.cfg.line)or 1;app.cfg.line=sources[index%#sources+1];app.driver=Driver.new()
end)
local learnButton=button("LearnGhost","Learn loaded ghost: OFF",0,435,416,32,body,function()learnGhost(not app.cfg.learn)end)
local function saveGhosts()
    assert(type(writefile)=="function","writefile is unavailable")
    writefile("BackseatRally_Ghosts.json",Http:JSONEncode({version=1,tracks=app.ghost.tracks}))
    app.status="Saved BackseatRally_Ghosts.json"
end
local function loadGhosts()
    assert(type(readfile)=="function","readfile is unavailable")
    local raw=readfile("BackseatRally_Ghosts.json");assert(#raw<5000000,"Ghost file is too large")
    local data=Http:JSONDecode(raw);assert(type(data)=="table"and data.version==1 and type(data.tracks)=="table","Unsupported ghost file")
    local accepted=0
    for key,track in pairs(data.tracks)do
        local stage=type(key)=="string"and key:match("^([A-Za-z]+)/")
        if stage and PROFILES[stage]and type(track)=="table"and type(track.samples)=="table"and #track.samples>=2 and #track.samples<=12000 then
            local valid=true
            for _,r in ipairs(track.samples)do
                if type(r)~="table"or #r<6 then valid=false;break end
                for i=1,6 do if type(r[i])~="number"or r[i]~=r[i]or math.abs(r[i])>1e7 then valid=false;break end end
                if not valid then break end
            end
            if valid then
                app.ghost.tracks[key]={samples=track.samples,duration=track.samples[#track.samples][1],source="saved personal ghost"};accepted=accepted+1
            end
        end
    end
    app.driver=Driver.new();app.routeCache={};app.status="Loaded "..accepted.." ghost line(s)"
end
local function guarded(fn)
    return function()local ok,err=pcall(fn);if not ok then app.status=tostring(err)end end
end
button("SaveGhost","Save ghost lines",0,475,204,31,body,guarded(saveGhosts))
button("LoadGhost","Load ghost lines",212,475,204,31,body,guarded(loadGhosts))
button("Report","Save diagnostics",0,514,416,31,body,guarded(function()
    assert(type(writefile)=="function","writefile is unavailable")
    writefile("BackseatRally_Report.json",Http:JSONEncode({version=app.version,settings=app.cfg,status=app.status,
        last_error=app.lastError,stage=app.stage,input=app.input.name,native_tune=app.adapter.applied~=nil,
        ghost_status=app.ghost.reason,trace=app.trace}))
    app.status="Saved BackseatRally_Report.json"
end))
make("TextLabel",{Position=UDim2.fromOffset(0,554),Size=UDim2.new(1,0,0,44),BackgroundTransparency=1,
    Text="Showcase = recorded game driving line.\nPersonal ghost = best run loaded by the game. F8 stops.",TextWrapped=true,
    TextColor3=palette.dim,TextSize=11,Font=Enum.Font.Gotham},body)
local function resize()
    local camera=World.CurrentCamera
    if camera then scale.Scale=math.clamp(math.min((camera.ViewportSize.Y-36)/676,(camera.ViewportSize.X-28)/444),.55,1)end
end
resize()
connect(header.InputBegan,function(input)
    if input.UserInputType==Enum.UserInputType.MouseButton1 or input.UserInputType==Enum.UserInputType.Touch then
        draggingPanel={input=input,at=input.Position,position=panel.Position}
    end
end)
connect(UIS.InputChanged,function(input)
    if draggingSlider and(input==draggingSlider.input or input.UserInputType==Enum.UserInputType.MouseMovement)then
        draggingSlider.drag(input.Position.X)
    elseif draggingPanel and(input==draggingPanel.input or input.UserInputType==Enum.UserInputType.MouseMovement)then
        local delta=input.Position-draggingPanel.at;local p=draggingPanel.position
        local camera=World.CurrentCamera;local viewport=camera and camera.ViewportSize or Vector2.new(1920,1080)
        panel.Position=UDim2.fromOffset(math.clamp(p.X.Offset+delta.X,0,math.max(0,viewport.X-444*scale.Scale)),
            math.clamp(p.Y.Offset+delta.Y,0,math.max(0,viewport.Y-46*scale.Scale)))
    end
end)
connect(UIS.InputEnded,function(input)
    if draggingSlider and(input==draggingSlider.input or input.UserInputType==Enum.UserInputType.MouseButton1)then draggingSlider=nil end
    if draggingPanel and(input==draggingPanel.input or input.UserInputType==Enum.UserInputType.MouseButton1)then draggingPanel=nil end
end)
connect(UIS.InputBegan,function(input,processed)
    if input.KeyCode==Enum.KeyCode.F8 then app.stop("Stopped by F8")
    elseif not processed and not UIS:GetFocusedTextBox()then
        if input.KeyCode==Enum.KeyCode.F6 then if app.enabled then app.stop()else app.start()end
        elseif input.KeyCode==Enum.KeyCode.F7 then app.toggleAuto()end
    end
end)
connect(UIS.WindowFocusReleased,function()focused=false;app.stop("Paused: Roblox lost focus")end)
connect(UIS.WindowFocused,function()focused=true end)
function app.destroy()
    if not app.alive then return end
    app.alive=false;app.stop();learnGhost(false);app.input:destroy();app.adapter:destroy()
    for _,c in ipairs(app.connections)do c:Disconnect()end
    gui:Destroy()
    if env and env.__BackseatRallyAssist==app then env.__BackseatRallyAssist=nil end
end
connect(shutdown.Event,app.destroy)
gui.Parent=pg
local function lineFor(stage,carId,halfWidth)
    local key=stage.."/"..carId
    local profile=PROFILES[stage]
    app.routeCache[stage]=app.routeCache[stage]or {base=Route.fromStage(profile)}
    local cache=app.routeCache[stage]
    if app.cfg.line=="Personal ghost"and app.ghost.tracks[key]then
        local data=app.ghost.tracks[key]
        if cache.ghostData~=data or cache.ghostWidth~=halfWidth then
            cache.ghostData=data;cache.ghost=Route.fromShowcase(data.samples,{source="personal ghost",stage=stage})
            cache.ghost=Route.constrain(cache.ghost,cache.base,profile.Width,halfWidth,profile.features);cache.ghostWidth=halfWidth
            local first=cache.base:nearest(cache.ghost.points[1])
            local last=cache.base:nearest(cache.ghost.points[#cache.ghost.points])
            if first.s>profile.StartAt+60 or last.s<profile.FinishAt-60 then
                cache.ghost=nil;app.ghost.reason="Personal ghost does not cover the full stage"
            end
        end
        if cache.ghost then return cache.ghost,cache.base end
    end
    if app.cfg.line~="Road"and SHOWCASES[stage]then
        if not cache.showcase or cache.showcaseWidth~=halfWidth then
            cache.showcase=Route.fromShowcase(SHOWCASES[stage].samples,{source="showcase",stage=stage})
            cache.showcase=Route.constrain(cache.showcase,cache.base,profile.Width,halfWidth,profile.features);cache.showcaseWidth=halfWidth
        end
        return cache.showcase,cache.base
    end
    return cache.base,cache.base
end
local ghostNet=Replicated:FindFirstChild("Shared")
ghostNet=ghostNet and ghostNet:FindFirstChild("RBXUtil")
ghostNet=ghostNet and ghostNet:FindFirstChild("Net")
ghostNet=ghostNet and ghostNet:FindFirstChild("RE/Ghost")
if ghostNet and ghostNet:IsA("RemoteEvent")then
    connect(ghostNet.OnClientEvent,function(kind,car,payload)
        if kind=="Load"and car==app.adapter.car and type(payload)=="table"and type(payload.Data)=="string"then
            local stage=car:GetAttribute("StageId")or "PineForest"
            local carId=car:GetAttribute("CarId")or "Hatch"
            if PROFILES[stage]then app.ghost:receive(stage,carId,payload)end
        end
    end)
end
local lastUi,lastTrace,lastObstacle=-math.huge,-math.huge,-math.huge
local obstacle,previousCar,previousStage,previousLine
local probing=false
connect(Run.Heartbeat,function(dt)
    if not app.alive then return end
    local now=os.clock()
    local ok,err=pcall(function()
        app.adapter:connectNative(now)
        local car,reason=app.adapter:find()
        local suspended=blocked()or dt>.2
        if not car then
            if previousCar then release();previousCar=nil end
            app.status=reason
        elseif suspended then
            release();app.status="Paused for menu, chat or frame stall"
        else
            if car~=previousCar then release();previousCar=car;app.ghost.capture=nil end
            app.adapter:tune(app.cfg,app.enabled)
            local state=app.adapter:measure();app.stage=state.stage
            if not PROFILES[state.stage]then release();app.status="No route profile for this stage";return end
            if state.stage~=previousStage then app.driver=Driver.new();previousStage=state.stage end
            if app.cfg.learn then
                local folder=World:FindFirstChild("RallyGhostLocal")
                local ghost=folder and folder:FindFirstChild("Ghost_"..state.carId)
                local updated=ghost and ghost:GetAttribute("GhostStep")
                if ghost and ghost:IsA("Model")and ghost.PrimaryPart and type(updated)=="number"and now-updated<.5 then
                    local p=ghost.PrimaryPart.Position
                    local speed=ghost.PrimaryPart.AssemblyLinearVelocity.Magnitude
                    local elapsed=World:GetServerTimeNow()-(car:GetAttribute("RunStartedAt")or World:GetServerTimeNow())
                    app.ghost:sample(state.stage,state.carId,state.runState,{x=p.X,y=p.Y,z=p.Z,speed=speed,elapsed=elapsed},now)
                elseif state.runState~="Running"then
                    app.ghost:sample(state.stage,state.carId,state.runState,{},now)
                end
            end
            if app.enabled then
                if app.cfg.auto then
                    app.adapter:automatic(true)
                    if not app.autoReady and not probing then
                        probing=true;local epoch=app.epoch
                        task.spawn(function()
                            local function cancelled()return not app.alive or not app.enabled or not app.cfg.auto or app.epoch~=epoch or blocked()end
                            local success,passed,message=pcall(function()
                                return app.input:probe(cancelled,function(text)app.status=text end)
                            end)
                            probing=false
                            if cancelled()then app.input:release();return end
                            if not success or not passed then
                                app.cfg.auto=false;app.input:release();app.adapter:automatic(false)
                                app.status=tostring(success and message or passed);return
                            end
                            app.autoReady=true
                        end)
                    end
                    if app.autoReady then
                        local line,base=lineFor(state.stage,state.carId,state.halfWidth)
                        if line~=previousLine then app.driver=Driver.new();previousLine=line end
                        if now-lastObstacle>.1 then obstacle=app.adapter:obstacle(state);lastObstacle=now end
                        state.obstacle=obstacle
                        if not app.adapter.applied then state.grip=state.grip*app.cfg.grip end
                        local command=Driver.step(app.driver,line,base,PROFILES[state.stage],state,app.cfg,dt,now)
                        local written,why=app.input:write(command)
                        if not app.alive or not app.enabled or not app.cfg.auto then app.input:release();return end
                        assert(written,why)
                        app.adapter:boost(state,app.cfg,command,dt)
                        app.command=command;app.status=command.mode
                        if app.cfg.line=="Personal ghost"and line.meta.source~="personal ghost"then
                            app.status=app.status.." (personal ghost not loaded)"
                        end
                    end
                else
                    app.input:release();app.adapter:automatic(false)
                    app.adapter:boost(state,app.cfg,app.input:manualState(),dt)
                    app.status="Manual assist"
                end
            end
            app.state=state
            if now-lastTrace>.25 then
                lastTrace=now;app.trace[#app.trace+1]={time=now,state=state,enabled=app.enabled,auto=app.cfg.auto,
                    input=app.input.name,command=app.command}
                if #app.trace>120 then table.remove(app.trace,1)end
            end
        end
        if now-lastUi>.15 then
            lastUi=now;resize()
            master.Text=app.enabled and "Disable assists [F6]"or "Enable assists [F6]"
            master.BackgroundColor3=app.enabled and palette.accent or palette.card
            master.TextColor3=app.enabled and palette.bg or palette.text
            auto.Text=app.cfg.auto and(app.enabled and "Autodrive ON [F7]"or "Resume autodrive [F7]")or "Autodrive OFF [F7]"
            lineButton.Text="Line: "..app.cfg.line
            local capture=app.ghost.capture
            local learning=not app.cfg.learn and "OFF"or(capture and(capture.invalid and "start a fresh run"or(#capture.rows.." points"))or "waiting for ghost")
            learnButton.Text="Learn loaded ghost: "..learning
            local speed=app.state and math.sqrt(app.state.vx^2+app.state.vz^2)*1.008 or 0
            status.Text=string.format("  %s\n  %s | %.0f km/h | input: %s",app.status,app.stage or "No car",speed,app.input.name)
        end
    end)
    if not ok then app.lastError=tostring(err);app.stop("Stopped: "..tostring(err));status.Text=app.status end
end)
return app
