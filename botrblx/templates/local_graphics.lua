-- Bounded, reversible local rendering changes. Preserve gameplay/readout cues.
local Graphics={}
Graphics.__index=Graphics
function Graphics.new(world,lighting)
    return setmetatable({world=world,lighting=lighting,enabled=false,changes=setmetatable({},{__mode='k'}),
        queue={},head=1,tail=0,seen=setmetatable({},{__mode='k'}),changed=0,limit=8192},Graphics)
end
function Graphics:remember(object,key,value)
    local ok,old=pcall(function()return object[key]end)
    if not ok or old==nil or old==value then return end
    local fields=self.changes[object]
    if not fields then fields={};self.changes[object]=fields end
    if fields[key]then return end
    if pcall(function()object[key]=value end)then
        fields[key]={before=old,applied=value};self.changed+=1
    end
end
function Graphics:protected(object)
    local p=object
    for _=1,14 do
        if not p or p==self.world then break end
        if p.Name=='PadRing'or p.Name=='PadHalo'or p.Name=='Nametag'or p.Name=='CarSound'or p.Name=='BallSound'then return true end
        if p:IsA('BillboardGui')or p:IsA('GuiObject')then return true end
        if p:IsA('Model')and p.PrimaryPart then return true end
        p=p.Parent
    end
    return false
end
function Graphics:apply(object)
    if object:IsA('ParticleEmitter')or object:IsA('Trail')or object:IsA('Beam')or object:IsA('Smoke')
        or object:IsA('Fire')or object:IsA('Sparkles')or object:IsA('PostEffect')then
        self:remember(object,'Enabled',false)
        if object:IsA('ParticleEmitter')then self:remember(object,'Rate',0)end
    elseif object:IsA('Light')then self:remember(object,'Shadows',false)
    elseif object:IsA('Terrain')then
        self:remember(object,'WaterWaveSize',0);self:remember(object,'WaterWaveSpeed',0)
        self:remember(object,'WaterReflectance',0)
    elseif object:IsA('BasePart')then
        self:remember(object,'CastShadow',false)
        if not self:protected(object)then
            self:remember(object,'Reflectance',0)
            if Enum.Material then self:remember(object,'Material',Enum.Material.SmoothPlastic)end
            if object:IsA('MeshPart')then self:remember(object,'TextureID','')end
        end
    elseif not self:protected(object)then
        if object:IsA('Decal')or object:IsA('Texture')then self:remember(object,'Transparency',1)
        elseif object:IsA('SpecialMesh')then self:remember(object,'TextureId','')
        elseif object:IsA('SurfaceAppearance')then
            for _,key in ipairs({'ColorMap','NormalMap','RoughnessMap','MetalnessMap'})do self:remember(object,key,'')end
        end
    end
end
function Graphics:enqueue(object)
    if not self.enabled or self.seen[object]or self.tail-self.head>=self.limit then return end
    self.seen[object]=true;self.tail+=1;self.queue[self.tail]=object
end
function Graphics:setEnabled(enabled)
    if self.closed or self.enabled==enabled then return end
    self.enabled=enabled
    if self.added then self.added:Disconnect();self.added=nil end
    self.queue={};self.head=1;self.tail=0;self.children=nil;self.childAt=nil
    self.seen=setmetatable({},{__mode='k'})
    if enabled then
        -- Finish restoration before recording a new baseline on a quick re-toggle.
        self:restore()
        if self.lighting then self:remember(self.lighting,'GlobalShadows',false)end
        self:enqueue(self.world)
        if self.lighting then self:enqueue(self.lighting)end
        if self.world.DescendantAdded then
            self.added=self.world.DescendantAdded:Connect(function(object)self:enqueue(object)end)
        end
        if self.lighting and self.lighting.DescendantAdded then
            self.lightAdded=self.lighting.DescendantAdded:Connect(function(object)self:enqueue(object)end)
        end
    else
        if self.lightAdded then self.lightAdded:Disconnect();self.lightAdded=nil end
        self:restore()
    end
end
function Graphics:restore()
    for object,fields in pairs(self.changes)do
        for key,saved in pairs(fields)do
            pcall(function()
                -- Do not overwrite a later game/user change to this property.
                if object[key]==saved.applied then object[key]=saved.before end
            end)
        end
    end
    self.changes=setmetatable({},{__mode='k'});self.changed=0
end
function Graphics:step(budget)
    if not self.enabled or self.closed then return end
    local deadline=os.clock()+(budget or .00035)
    local count=0
    repeat
        if self.children then
            local object=self.children[self.childAt]
            if object then self:enqueue(object);self.childAt+=1
            else self.children=nil end
        elseif self.head<=self.tail then
            local object=self.queue[self.head];self.queue[self.head]=nil;self.head+=1
            if object and object.Parent then
                pcall(function()self:apply(object);self.children=object:GetChildren();self.childAt=1 end)
            elseif object==self.world then self.children=object:GetChildren();self.childAt=1 end
        else
            self.queue={};self.head=1;self.tail=0;break
        end
        count+=1
    until count>=48 or os.clock()>=deadline
end
function Graphics:close()
    self:setEnabled(false);self.closed=true
end
function Graphics:report()return {enabled=self.enabled,changed_properties=self.changed,pending=math.max(0,self.tail-self.head+1)}end
return Graphics
