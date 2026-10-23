-- Update271 live bridge. Reads rendered state; Python sends normal OS input.
-- TEAM_READER_BEGIN
local Teams=(function()
-- Team identity from rendered match UI. No game modules or private tables loaded.
local Teams={}
Teams.__index=Teams
local function plain(value)
    return (tostring(value or ""):gsub("<[^>]*>",""):gsub("&amp;","&"):gsub("&lt;","<"):gsub("&gt;",">"):match("^%s*(.-)%s*$")):lower()
end
local function colorTeam(color,palette,dimmed)
    if not color then return nil end
    for team,base in ipairs(palette)do
        local scale=1
        if dimmed then
            scale=(color.R*base[1]+color.G*base[2]+color.B*base[3])/(base[1]^2+base[2]^2+base[3]^2)
        end
        if scale>=(dimmed and .95^8-.01 or .99)and scale<=1.01 then
            if math.max(math.abs(color.R-base[1]*scale),math.abs(color.G-base[2]*scale),math.abs(color.B-base[3]*scale))<.012 then return team-1 end
        end
    end
end
local function rgb(r,g,b)return {r/255,g/255,b/255}end
function Teams.plate(color)
    return colorTeam(color,{rgb(46,120,226),rgb(232,116,38)},true)
end
function Teams.relation(tag)
    -- MatchView.setNames: teammate Plate height=.74 plus Boost; opponent=1.
    local plate=tag and tag:FindFirstChild("Plate")
    local height=plate and plate.Size and plate.Size.Y and plate.Size.Y.Scale
    local holder=tag and tag:FindFirstChild("Boost")
    local fill=holder and holder:FindFirstChild("Fill")
    if type(height)~="number"then return nil end
    if math.abs(height-.74)<.001 and fill then return true end
    if math.abs(height-1)<.001 and not holder then return false end
end
local function edgeTeam(row)
    local face=row:FindFirstChild("Face")
    local edge=face and face:FindFirstChild("TeamEdge")
    if not edge then return nil end
    if edge.BackgroundTransparency==1 then
        for _,child in ipairs(edge:GetChildren())do
            if child:IsA("Frame")then edge=child;break end
        end
    end
    -- ScoreSheet's standard and cel layouts use these exact team-edge colors.
    local c=edge.BackgroundColor3
    return colorTeam(c,{rgb(30,155,240),rgb(252,122,2)},false)
        or colorTeam(c,{rgb(92,208,255),rgb(252,122,2)},false)
end
function Teams.new(player)
    return setmetatable({player=player,names={},source="waiting for match team",at=-math.huge},Teams)
end
function Teams:roster(pg)
    local names,counts={}, {[0]=0,[1]=0}
    local sheet=pg:FindFirstChild("CarSoccerMatchSheet")
    if sheet then
        for _,row in ipairs(sheet:GetDescendants())do
            if row:IsA("Frame")and row.Name:match("^Row%d+$")then
                local team=edgeTeam(row)
                if team~=nil then
                    counts[team]=counts[team]+1
                    for _,item in ipairs(row:GetDescendants())do
                        if item:IsA("TextLabel")then
                            local name=plain(item.Text)
                            if name~="" and not tonumber(name)then
                                if names[name]and names[name].row~=row then names[name]={ambiguous=true}
                                else names[name]={team=team,row=row}end
                            end
                        end
                    end
                end
            end
        end
    end
    self.names,self.counts=names,counts
    local own=names[plain(self.player.Name)]
    if not own and self.player.DisplayName then own=names[plain(self.player.DisplayName)]end
    if own and not own.ambiguous then return own.team end
end
function Teams:named(tag)
    local plate=tag and tag:FindFirstChild("Plate")
    local label=plate and plate:FindFirstChild("Name")
    local row=label and self.names[plain(label.Text)]
    if row and not row.ambiguous then return row.team end
end
function Teams:detect(pg,scene,ownRoot,now,manual)
    if now-self.at<.2 and manual==self.manual and scene==self.scene then return self.team,self.source end
    self.at,self.manual,self.scene=now,manual,scene
    local roster=self:roster(pg)
    local vote,conflict
    for _,tag in ipairs(scene:GetDescendants())do
        if tag.Name=="Nametag"and tag:IsA("BillboardGui")and tag.Enabled~=false and tag.Parent~=ownRoot then
            local root=tag.Parent
            local model=root and root.Parent
            if root and root:IsA("BasePart")and model and model:IsA("Model")and model.PrimaryPart==root then
                local relation=Teams.relation(tag)
                local plate=tag:FindFirstChild("Plate")
                local team=self:named(tag)or(plate and Teams.plate(plate.BackgroundColor3))
                if team~=nil and relation~=nil then
                    local inferred=relation and team or 1-team
                    if vote~=nil and vote~=inferred then conflict=true end
                    vote=inferred
                end
            end
        end
    end
    if manual~=nil then self.team,self.source=manual,"manual override"
    elseif conflict or(roster~=nil and vote~=nil and roster~=vote)then self.team,self.source=nil,"team UI updating; waiting"
    elseif roster~=nil then self.team,self.source=roster,"scoreboard: "..self.player.Name
    elseif vote~=nil then self.team,self.source=vote,"nameplate relationship"
    else
        local hud=pg:FindFirstChild("CarSoccerMatchHud")
        if hud and hud.Enabled then self.team,self.source=nil,"open scoreboard once to identify your team"
        else self.team,self.source=0,"freeplay blue (no active match HUD)"end
    end
    return self.team,self.source
end
return Teams

end)()
-- TEAM_READER_END
local TEAM,manualTeam=nil,nil
local HZ=15
local player=game:GetService("Players").LocalPlayer
local pg=assert(player:FindFirstChildOfClass("PlayerGui"),"Join first")
local teamReader=Teams.new(player)
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
teamButton.Text="Team: AUTO"
local close=Instance.new("TextButton",panel)
close.Position=UDim2.fromOffset(300,120);close.Size=UDim2.fromOffset(110,30);close.Text="Close"
gui.Parent=pg
-- BRIDGE_TRANSPORT_BEGIN
local URL="http://127.0.0.1:28771"
-- HTTP_COMPAT_BEGIN: inline copy shared by the launcher and standalone client.
local http_preferred
local function http_response_detail(value)
    if type(value)~="table"then return "returned "..type(value)end
    local fields={}
    for key,item in pairs(value)do
        fields[#fields+1]=tostring(key)..":"..type(item)..(type(item)=="string"and "("..#item..")"or "")
        if #fields>=10 then break end
    end
    table.sort(fields)
    local code=value.StatusCode or value.Status or value.status_code or value.status
    local message=value.StatusMessage or value.status_message or value.Error or value.error or value.Message
    return "fields={"..table.concat(fields,",").."}; status="..tostring(code)
        ..(type(message)=="string"and "; message="..message:sub(1,160)or "")
end
local function http_response_parts(first,second)
    if first==false then return nil,nil,"returned false: "..tostring(second):sub(1,160)end
    local value=first
    if (value==nil or value==true)and second~=nil then value=second;second=nil end
    local body,code
    if type(value)=="string"then body=value
    elseif type(value)=="table"then
        code=value.StatusCode or value.Status or value.status_code or value.status
        for _,key in ipairs({"Body","body","ResponseBody","responseBody"})do
            if type(value[key])=="string"and #value[key]>0 then body=value[key];break end
        end
    end
    if (not body or #body==0)and type(second)=="string"and #second>0 then body=second end
    if type(body)~="string"or #body==0 then
        return nil,nil,"no response body; "..http_response_detail(value)
    end
    local status=code~=nil and tonumber(code)or nil
    if code~=nil and not status then return nil,nil,"Unrecognized HTTP status: "..tostring(code)end
    return body,status
end
local function http_request_checked(options)
    local candidates={}
    local function add(name,fn)
        if type(fn)~="function"then return end
        for _,entry in ipairs(candidates)do if entry.fn==fn then return end end
        candidates[#candidates+1]={name=name,fn=fn}
    end
    if http_preferred then add(http_preferred.name,http_preferred.fn)end
    add("request",request);add("http_request",http_request)
    assert(#candidates>0,"HTTP request function unavailable")
    local errors={}
    for _,entry in ipairs(candidates)do
        local ok,first,second=pcall(entry.fn,options)
        if ok then
            local body,status,detail=http_response_parts(first,second)
            if body then http_preferred=entry;return body,status end
            errors[#errors+1]=entry.name..": "..detail
        else
            errors[#errors+1]=entry.name..": "..tostring(first):sub(1,240)
        end
    end
    error("No usable HTTP response. "..table.concat(errors," | "),0)
end
-- HTTP_COMPAT_END
local function bridge_call(path,packet,token)
    return http_request_checked({Url=URL..path,Method=packet and "POST"or "GET",
        Headers={ ["Content-Type"]="application/json",["X-Bridge-Token"]=token or ""},
        Body=packet and game:GetService("HttpService"):JSONEncode(packet)or nil,Timeout=2})
end
-- BRIDGE_TRANSPORT_END

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
    enabled=false;manualTeam=manualTeam==nil and 0 or(manualTeam==0 and 1 or nil)
    teamReader.at=-math.huge
    teamButton.Text=manualTeam==nil and "Team: AUTO"or(manualTeam==0 and "Manual: BLUE"or "Manual: ORANGE")
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
local arenaAdapter,padReader,carReader -- Standalone mode supplies geometry/pads/other cars.
local function teamChanged()enabled=false;controls()end
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
        if arenaAdapter then arenaAdapter:measureCar(car,carRoot)end
        lastCar,lastBall,lastTime=carRoot.CFrame,ballRoot.CFrame,os.clock()
        return nil,"warming up poses"
    end
    local now=os.clock()
    local detected,teamSource=teamReader:detect(pg,scene,carRoot,now,manualTeam)
    teamButton.Text=manualTeam==nil and("AUTO: "..(detected==nil and "?"or(detected==0 and "BLUE"or "ORANGE")))
        or(manualTeam==0 and "Manual: BLUE"or "Manual: ORANGE")
    if detected==nil then return nil,teamSource end
    if detected~=TEAM then
        local previousTeam=TEAM;TEAM=detected
        if previousTeam~=nil then teamChanged()end
        lastCar,lastBall,lastTime=carRoot.CFrame,ballRoot.CFrame,now
        return nil,"team identified; warming up poses"
    end
    local dt=now-lastTime
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
    local contacts,ballContacts,ballRadius,ballSizeVerified
    if arenaAdapter then
        if scene:FindFirstChild("ArenaFree")then return nil,"alternate arena needs its own physics profile"end
        if now-(arenaAdapter.lastMeasure or -math.huge)>2 then arenaAdapter:measureCar(car,carRoot)end
        ballRadius,ballSizeVerified=arenaAdapter:ballRadius(ballRoot)
        grounded,contacts,ballContacts=arenaAdapter:ground(cp,bp,ballRadius)
    end
    local packet={car=cp,ball=bp,boost=b,team=TEAM,ground_estimate=grounded,valid=true}
    packet.team_source=teamSource
    if arenaAdapter then
        packet.ball_radius,packet.ball_size_verified=ballRadius,ballSizeVerified
        packet.car_preset=arenaAdapter.preset;packet.car_size_verified=arenaAdapter.hitboxVerified
        packet.wheel_contacts=contacts
        packet.ball_wheel_contacts=ballContacts
    end
    if padReader then
        packet.boost_pads=padReader:read(scene,cp.position,now)
        packet.boost_known=padReader.known;packet.boost_total=padReader.total
    end
    if carReader then
        packet.other_cars=carReader:read(scene,carRoot,ballRoot,now,pose,bp,ballRadius,TEAM)
        packet.opponents=carReader.opponents;packet.teammates=carReader.teammates
        packet.unknown_cars=carReader.unknown
    end
    return packet
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
