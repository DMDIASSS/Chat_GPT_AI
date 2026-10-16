-- Render cues verified against PadsView/PadLook: yellow rings mean active;
-- grey/dark rings mean cooldown. Position comes from each static PadHalo.
local Pads={}
Pads.__index=Pads
function Pads.new(profile)
    return setmetatable({profile=profile,entries={},lastIndex=-math.huge,lastRead=-math.huge,
        known=0,total=0},Pads)
end
local function horizontal(a,b)return (a.X-b.X)^2+(a.Z-b.Z)^2 end
function Pads:index(scene,now)
    local folder=scene:FindFirstChild("BoostPads")
    if folder==self.folder and now-self.lastIndex<2 then return end
    self.folder=folder;self.lastIndex=now;self.entries={};self.known=0
    if not folder then self.total=0;return end
    local rings={}
    for _,part in ipairs(folder:GetDescendants())do
        if part:IsA("BasePart")then
            if part.Name=="PadHalo"then self.entries[#self.entries+1]={halo=part,rings={}}
            elseif part.Name=="PadRing"then rings[#rings+1]=part end
        end
    end
    -- Assign each ring to its nearest halo, so similarly named decorations
    -- and nearby pad effects cannot be treated as extra boost pads.
    for _,ring in ipairs(rings)do
        local best,distance=nil,16^2
        for _,entry in ipairs(self.entries)do
            local d=horizontal(ring.Position,entry.halo.Position)
            if d<distance then best,distance=entry,d end
        end
        if best then best.rings[#best.rings+1]=ring end
    end
    self.total=#self.entries
    for _,entry in ipairs(self.entries)do
        local count=#entry.rings
        if count==16 then entry.big=true elseif count==10 then entry.big=false end
        local p=entry.halo.Position;local k=1/self.profile.roblox_studs_per_sim_unit
        if entry.big~=nil then
            entry.position={p.X*k,p.Z*k,entry.big and 73 or 70}
        end
    end
end
function Pads:read(scene,carPosition,now)
    self:index(scene,now)
    if now-self.lastRead>=.2 then
        self.lastRead=now;self.known=0
        for _,entry in ipairs(self.entries)do
            entry.active=nil
            if entry.big~=nil then
                local yellow,valid=0,true
                for _,ring in ipairs(entry.rings)do
                    if not ring:IsDescendantOf(self.folder)then valid=false;break end
                    local c=ring.Color
                    if type(ring.Transparency)~="number"or ring.Transparency>.25 or not c then valid=false;break end
                    if c.R>.8 and c.G>.6 and c.B<.65 then yellow=yellow+1
                    elseif c.B<c.R+.015 or c.B<c.G+.015 then
                        -- Other skins/tints are not a verified availability cue.
                        valid=false;break
                    end
                end
                if valid then entry.active=yellow==#entry.rings;self.known=self.known+1 end
            end
        end
    end
    local candidates={}
    for _,entry in ipairs(self.entries)do
        if entry.active~=nil and entry.position then
            local p=entry.position
            candidates[#candidates+1]={position=p,is_big=entry.big,active=entry.active,
                distance=(p[1]-carPosition[1])^2+(p[2]-carPosition[2])^2}
        end
    end
    table.sort(candidates,function(a,b)return a.distance<b.distance end)
    local selected,picked={},{}
    local limit=self.profile.policy_boost_limit
    -- Keep large-pad information even when several small pads are closer.
    local reserve=math.min(2,math.floor(limit/3))
    for _,candidate in ipairs(candidates)do
        if candidate.is_big and #selected<reserve then selected[#selected+1]=candidate;picked[candidate]=true end
    end
    for _,candidate in ipairs(candidates)do
        if #selected>=limit then break end
        if not picked[candidate]then selected[#selected+1]=candidate end
    end
    table.sort(selected,function(a,b)return a.distance<b.distance end)
    return selected
end
return Pads
