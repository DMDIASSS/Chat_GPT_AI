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
