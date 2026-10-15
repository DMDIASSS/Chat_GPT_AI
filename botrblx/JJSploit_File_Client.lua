-- Update271 live bridge. Reads rendered state; Python sends normal OS input.
local TEAM=0 -- 0=blue, 1=orange. Freeplay spawns blue.
local HZ=15
local player=game:GetService("Players").LocalPlayer
local pg=assert(player:FindFirstChildOfClass("PlayerGui"),"Join first")
assert(not pg:FindFirstChild("Update271Bridge"),"Close the old Update271 panel first")
local gui=Instance.new("ScreenGui")
gui.Name="Update271Bridge";gui.ResetOnSpawn=false;gui.DisplayOrder=1000071
local panel=Instance.new("Frame",gui)
panel.Size=UDim2.fromOffset(420,160);panel.Position=UDim2.fromOffset(20,20)
panel.BackgroundColor3=Color3.fromRGB(18,22,30)
local label=Instance.new("TextLabel",panel)
label.Position=UDim2.fromOffset(10,8);label.Size=UDim2.new(1,-20,0,105)
label.BackgroundTransparency=1;label.TextColor3=Color3.new(1,1,1)
label.TextSize=14;label.Font=Enum.Font.Code;label.TextWrapped=true
label.Text="Update271: connecting to Python..."
local start=Instance.new("TextButton",panel)
start.Position=UDim2.fromOffset(10,120);start.Size=UDim2.fromOffset(150,30)
start.Text="Start bot / F6"
local teamButton=Instance.new("TextButton",panel)
teamButton.Position=UDim2.fromOffset(170,120);teamButton.Size=UDim2.fromOffset(120,30)
teamButton.Text="Team: BLUE"
local close=Instance.new("TextButton",panel)
close.Position=UDim2.fromOffset(300,120);close.Size=UDim2.fromOffset(110,30);close.Text="Close"
gui.Parent=pg
-- File transport: generated into the standalone client instead of HTTP.
label.Text="Update271 file client v3.2 (WRD): connecting to Python..."
local fileHttp=game:GetService("HttpService") -- JSON/UUID only; no network calls.
local fileSession=fileHttp:GenerateGUID(false)
local fileId=0
local function bridge_call(path,packet,token)
    assert(type(readfile)=="function"and type(writefile)=="function",
        "File mode needs both readfile and writefile; this executor does not expose them")
    fileId=fileId+1
    local id=fileId
    local replyPath="botrblx_exchange/replies/reply_"..fileSession.."_"..id..".json"
    local encoded=fileHttp:JSONEncode({session=fileSession,id=id,route=path,file_protocol=3,token=token or "",packet=packet})
    local wrote,writeError=pcall(writefile,"botrblx_exchange/request.json",encoded)
    assert(wrote,"Cannot write file telemetry. Select the executor workspace in START_FILE_BOT.bat: "..tostring(writeError))
    -- Some executor file calls yield for appreciable time. Handshakes carry no
    -- inputs and can wait longer; live telemetry still has the Python watchdog.
    -- Diagnostic: this WRD build takes 1.2–1.3s even on working paths.
    local deadline=os.clock()+4
    local detail="readfile was not called"
    while os.clock()<deadline do
        assert(id==fileId,"File request superseded")
        -- The executor's existence metadata need not reflect files published by
        -- Python. Always try the content read; missing files are retryable.
        local ok,body=pcall(readfile,replyPath)
        if not ok then
            detail="readfile failed: "..tostring(body):sub(1,160)
        elseif type(body)~="string"then
            detail="readfile returned "..type(body)..", expected string"
        else
            -- A BOM is not part of JSON but can be introduced by Windows tools.
            if body:sub(1,3)==string.char(239,187,191)then body=body:sub(4)end
            local decoded,response=pcall(function()return fileHttp:JSONDecode(body)end)
            if not decoded then
                detail="JSON decode failed ("..#body.." bytes) in request-specific reply"
            elseif type(response)~="table"then
                detail="decoded response is "..type(response)..", expected table"
            elseif response.session~=fileSession then
                detail="reply belongs to another client; close other bot panels/bridges"
            elseif tonumber(response.id)~=id then
                detail="reply id="..tostring(response.id)..", waiting for id="..id
            elseif response.file_protocol~=3 then
                detail="Python reply is not file transport v3"
            elseif type(response.data)~="table"or not tonumber(response.status)then
                detail="reply is missing data/status"
            else
                return fileHttp:JSONEncode(response.data),tonumber(response.status)
            end
        end
        task.wait(.01)
    end
    error("No matching file reply for request "..id..": "..detail..". Keep Python open (file transport v3).",0)
end

if player.Name~="Deadline_coolgun"or game.PlaceId~=101880234193261 then
    label.Text="This adapter is configured for Deadline_coolgun / place 101880234193261.";return
end
local http=game:GetService("HttpService")
local input=game:GetService("UserInputService")
local world=game:GetService("Workspace")
local alive,enabled,token,seq,armAt=true,false,nil,0,0
local sampler
local function call(path,packet)
    local began=os.clock()
    local body,status=bridge_call(path,packet,token)
    assert(not status or status==200,"Bridge "..tostring(status)..": "..body:sub(1,200))
    local data=http:JSONDecode(body)
    assert(type(data)=="table","Invalid JSON response")
    data.link_ms=math.floor((os.clock()-began)*1000+.5)
    return data
end
local function send(packet)
    seq=seq+1
    packet.seq=seq;packet.account=player.Name;packet.place=game.PlaceId
    return call("/frame",packet)
end
local function controls()
    start.Text=enabled and "Pause / F6"or "Start bot / F6"
    -- Injected boost clicks must not click this panel's buttons.
    start.Visible=not enabled;teamButton.Visible=not enabled;close.Visible=not enabled
end
local function toggle()
    enabled=not enabled;armAt=os.clock()+.5
    controls()
end
start.Activated:Connect(toggle)
teamButton.Activated:Connect(function()
    enabled=false;TEAM=1-TEAM
    teamButton.Text=TEAM==0 and "Team: BLUE"or "Team: ORANGE"
    controls()
end)
local hotkey=input.InputBegan:Connect(function(key,processed)
    if key.KeyCode==Enum.KeyCode.F8 then enabled=false;controls()end
    if not processed and key.KeyCode==Enum.KeyCode.F6 then toggle()end
end)
close.Activated:Connect(function()
    alive=false;enabled=false;hotkey:Disconnect();gui:Destroy()
    if sampler then sampler:Disconnect()end
    if token then task.spawn(function()pcall(send,{enabled=false,valid=false})end)end
end)
-- POSE_READER_BEGIN (also embedded by the standalone exporter)
local scene,car,ball,carRoot,ballRoot,lastCar,lastBall,lastTime
local function nearest(anchor,excluded)
    if not anchor then return nil end
    local best,distance=nil,3
    for _,model in ipairs(scene:GetDescendants())do
        if model:IsA("Model")and model~=excluded and model.PrimaryPart then
            local d=(model.PrimaryPart.Position-anchor.Position).Magnitude
            if d<distance then best,distance=model,d end
        end
    end
    return best
end
local boostLabel
local function boost()
    if boostLabel and boostLabel:IsDescendantOf(pg)then
        local value=tonumber(boostLabel.Text)
        if value and value>=0 and value<=100 then return value end
    end
    local hud=pg:FindFirstChild("CarSoccerHud")
    local holder=hud and hud:FindFirstChild("Boost",true)
    holder=holder and(holder:FindFirstChild("BoostS1",true)or holder)
    if holder then
        for _,item in ipairs(holder:GetDescendants())do
            if item:IsA("TextLabel")then
                local value=tonumber(item.Text)
                if value and value>=0 and value<=100 then boostLabel=item;return value end
            end
        end
    end
end
local function sim(v,k)return {v.X*k,v.Z*k,v.Y*k}end
local function pose(frame,previous,dt)
    local delta=frame.Position-previous.Position
    local axis,angle=previous:ToObjectSpace(frame):ToAxisAngle()
    local omega=previous:VectorToWorldSpace(axis)*(angle/dt)
    return {position=sim(frame.Position,10),velocity=sim(delta/dt,10),
        forward=sim(frame.LookVector,1),up=sim(frame.UpVector,1),
        angular_velocity=sim(omega,-1)},delta.Magnitude
end
local function read()
    local current=world:FindFirstChild("CarSoccer")
    if current~=scene then scene=current;car=nil;ball=nil end
    if not scene then return nil,"scene unavailable"end
    if not car or not ball or not carRoot:IsDescendantOf(scene)
        or not ballRoot:IsDescendantOf(scene)or car.PrimaryPart~=carRoot or ball.PrimaryPart~=ballRoot then
        local sounds=scene:FindFirstChild("Sounds")
        car=nearest(sounds and sounds:FindFirstChild("CarSound"))
        ball=car and nearest(sounds and sounds:FindFirstChild("BallSound"),car)
        if not car or not ball then return nil,"goal/reset: waiting for car and ball"end
        carRoot,ballRoot=car.PrimaryPart,ball.PrimaryPart
        lastCar,lastBall,lastTime=carRoot.CFrame,ballRoot.CFrame,os.clock()
        return nil,"warming up poses"
    end
    local now=os.clock();local dt=now-lastTime
    local cf,bf=carRoot.CFrame,ballRoot.CFrame
    if dt<=0 then return nil,"waiting for next frame"end
    local cp,cd=pose(cf,lastCar,dt);local bp,bd=pose(bf,lastBall,dt)
    lastCar,lastBall,lastTime=cf,bf,now
    if dt>.3 or cd/dt>350 or bd/dt>800 then return nil,"pose discontinuity/reset"end
    local b=boost()
    if b==nil then return nil,"numeric boost HUD missing"end
    local p,u=cp.position,cp.up
    -- Contact estimate for the standard soccer arena, NOT internal wheel state.
    local grounded=(p[3]<38 and u[3]>.65)
        or(p[3]>2006 and u[3]<-.65)
        or(math.abs(p[1])>4058 and u[1]*p[1]<-2500)
        or(math.abs(p[2])>5082 and math.abs(p[1])>1000 and u[2]*p[2]<-3200)
    return {car=cp,ball=bp,boost=b,team=TEAM,ground_estimate=grounded,valid=true}
end
-- POSE_READER_END
-- Sample poses independently of file round trips. A 1.3s RPC must not turn
-- every physics sample into a >0.3s discontinuity and invalidate the policy.
local latestPacket,latestReason,lastSample=nil,"warming up poses",-math.huge
sampler=game:GetService("RunService").Heartbeat:Connect(function()
    if not alive or os.clock()-lastSample<1/HZ then return end
    lastSample=os.clock()
    local ok,packet,reason=pcall(read)
    latestPacket=ok and packet or nil
    latestReason=ok and reason or "pose reader failed"
end)
task.spawn(function()
    while alive do
        local began=os.clock()
        local ok,err=pcall(function()
            if not token then
                local hello=call("/hello")
                assert(hello.protocol==1,"Wrong Python bridge version")
                token=hello.token;seq=0;enabled=false
            end
            if input:GetFocusedTextBox()then enabled=false end
            local packet={}
            if latestPacket and os.clock()-lastSample<=.3 then
                for key,value in pairs(latestPacket)do packet[key]=value end
            else
                packet={valid=false,reason=latestReason or "pose sampler stalled"}
            end
            if packet.valid and boost()==nil then packet={valid=false,reason="numeric boost HUD missing"}end
            packet.enabled=enabled and os.clock()>=armAt
            local reply=send(packet)
            if not alive then return end
            if reply.disarmed then enabled=false end
            controls()
            label.Text=("Update271 | %s\nKeys: %s | inference: %s ms\nLink: %s ms | F6 pause; F8 stop\nFreeplay; ground/flip estimated.")
                :format(reply.status or "connected",table.concat(reply.keys or {}," "),tostring(reply.ms or "-"),tostring(reply.link_ms or "-"))
        end)
        if not ok and alive then
            enabled=false;token=nil;controls()
            label.Text="Bridge stopped: "..tostring(err).."\nReconnecting..."
            task.wait(1)
        end
        task.wait(math.max(.005,1/HZ-(os.clock()-began)))
    end
end)
return {started=true,version=2}
