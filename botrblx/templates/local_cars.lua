-- Read remote cars from the game's team nameplates, never chassis paint.
local Cars={}
Cars.__index=Cars
local colors={{46/255,120/255,226/255},{232/255,116/255,38/255}}
function Cars.team(color)
    if not color then return nil end
    local c={color.R,color.G,color.B}
    if not c[1]or not c[2]or not c[3]then return nil end
    for i,base in ipairs(colors)do
        local scale=(c[1]*base[1]+c[2]*base[2]+c[3]*base[3])/(base[1]^2+base[2]^2+base[3]^2)
        if scale>=.95^8-.01 and scale<=1.01 then
            local error=0
            for j=1,3 do error=math.max(error,math.abs(c[j]-base[j]*scale))end
            if error<.025 then return i-1 end
        end
    end
end
function Cars.new(profile,arenaClass)
    return setmetatable({profile=profile,arenaClass=arenaClass,tracked={},scanAt=-math.huge},Cars)
end
function Cars:read(scene,ownRoot,ballRoot,now,pose,ball,ballRadius,ownTeam)
    if scene~=self.scene then self.scene=scene;self.tracked={};self.scanAt=-math.huge end
    if now-self.scanAt>=.5 then
        self.scanAt=now
        local found={}
        for _,tag in ipairs(scene:GetDescendants())do
            if tag.Name=="Nametag"and tag:IsA("BillboardGui")then
                local root=tag.Parent
                local model=root and root.Parent
                if root and root:IsA("BasePart")and model and model:IsA("Model")
                    and model.PrimaryPart==root and root~=ownRoot and root~=ballRoot then
                    local entry=self.tracked[root]or{arena=self.arenaClass.new(self.profile)}
                    entry.tag,entry.model,entry.root=tag,model,root
                    found[root]=entry
                end
            end
        end
        self.tracked=found
    end
    local rows={}
    self.opponents,self.teammates,self.unknown,self.boostUnknown=0,0,0,0
    for root,entry in pairs(self.tracked)do
        local plate=entry.tag:FindFirstChild("Plate")
        local team=plate and Cars.team(plate.BackgroundColor3)
        local visible=root~=ownRoot and root~=ballRoot and root:IsDescendantOf(scene)
            and entry.model.PrimaryPart==root and entry.tag:IsDescendantOf(root)and entry.tag.Enabled~=false
        if visible and team~=nil then
            local frame=root.CFrame
            local dt=entry.at and now-entry.at or 0
            if entry.frame and dt>0 and dt<=.3 then
                local body,distance=pose(frame,entry.frame,dt)
                if distance/dt<=350 then
                    if now-(entry.arena.lastMeasure or -math.huge)>2 then entry.arena:measureCar(entry.model,root)end
                    if not entry.groundAt or now-entry.groundAt>=.1 then
                        entry.ground=entry.arena:ground(body,ball,ballRadius);entry.groundAt=now
                    end
                    if entry.ground then entry.lastGround=now end
                    body.team=team
                    body.ground_estimate=entry.ground==true
                    body.flip_estimate=body.ground_estimate or(entry.lastGround~=nil and now-entry.lastGround<1.25)
                    local holder=entry.tag:FindFirstChild("Boost")
                    local fill=holder and holder:FindFirstChild("Fill")
                    -- Only teammates have a source-backed boost bar. Opponent
                    -- boost/flip are explicitly estimates, not hidden state.
                    body.boost_verified=team==ownTeam and fill~=nil
                    body.boost_estimate=body.boost_verified and math.clamp(fill.Size.X.Scale*100,0,100)or 50
                    rows[#rows+1]=body
                else entry.lastGround=nil;entry.groundAt=nil end
            else entry.lastGround=nil;entry.groundAt=nil end
            entry.frame,entry.at=frame,now
        else
            if visible then self.unknown=self.unknown+1 end
            entry.frame,entry.at,entry.lastGround=nil,nil,nil
        end
    end
    local p=ownRoot.Position
    local function distance(body)
        local v=body.position
        return (v[1]-p.X*10)^2+(v[2]-p.Z*10)^2+(v[3]-p.Y*10)^2
    end
    table.sort(rows,function(a,b)return distance(a)<distance(b)end)
    while #rows>5 do table.remove(rows)end
    for _,body in ipairs(rows)do
        if body.team==ownTeam then self.teammates=self.teammates+1 else self.opponents=self.opponents+1 end
        if not body.boost_verified then self.boostUnknown=self.boostUnknown+1 end
    end
    return rows
end
return Cars
