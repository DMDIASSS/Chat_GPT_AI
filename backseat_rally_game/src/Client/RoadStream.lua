-- Bounded chunk window; generation jobs yield frequently and recycle parts.
local Root=game:GetService('ReplicatedStorage'):WaitForChild('BackseatExpedition')
local C=require(Root.Shared.Config);local Route=require(Root.Shared.Route)
local Stream={};Stream.__index=Stream
local function rgb(a)return Color3.new(a[1],a[2],a[3])end
function Stream.new(parent)
 local folder=Instance.new('Folder');folder.Name='RallyWorld';folder.Parent=parent
 return setmetatable({folder=folder,chunks={},queue={},pool={},quality='medium',made=0,epoch=0},Stream)
end
function Stream:part(parent,name,size,cf,tint,material,shape)
 local p=table.remove(self.pool)or Instance.new('Part')
 p.Name=name;p.Size=size;p.CFrame=cf;p.Color=rgb(tint);p.Material=material or Enum.Material.SmoothPlastic
 p.Shape=shape or Enum.PartType.Block;p.Anchored=true;p.CanCollide=false;p.CanTouch=false;p.CanQuery=false
 p.CastShadow=false;p.Transparency=0;p.TopSurface=Enum.SurfaceType.Smooth;p.BottomSurface=Enum.SurfaceType.Smooth;p.Parent=parent
 self.made+=1;if self.made%8==0 then coroutine.yield()end
 return p
end
function Stream:release(chunk)
 for _,p in ipairs(chunk:GetChildren())do
  if p:IsA('BasePart')and #self.pool<400 then p.Parent=nil;self.pool[#self.pool+1]=p else p:Destroy()end
 end
 chunk:Destroy()
end
function Stream:reset(route,slot,originZ)
 self.epoch+=1;self.route=route;self.slot=slot or 1;self.originZ=originZ or 0
 for _,entry in pairs(self.chunks)do self:release(entry.model)end
 self.chunks={};self.queue={}
end
function Stream:shift(originZ)
 if originZ==self.originZ then return end
 local delta=Vector3.new(0,0,originZ-self.originZ)
 for _,entry in pairs(self.chunks)do
  -- Jobs resume with the new origin, so unfinished chunks are rebuilt.
  if entry.done then entry.model:PivotTo(entry.model:GetPivot()+delta)else entry.cancel=true end
 end
 self.originZ=originZ
end
function Stream:offset()return Vector3.new(C.WorldX+(self.slot or 1)*C.LaneSpacing,0,self.originZ or 0)end
function Stream:decor(model,index)
 local route=self.route;local cfg=C.Quality[self.quality];local offset=self:offset()
 local imported=Root:FindFirstChild('ImportedProps')
 local templates=imported and imported:GetChildren()or {}
 local z0=index*C.Chunk;local biome=C.Biomes[route:point(z0).biome]
 for i=1,cfg.props do
  local r=Route.random(route.seed,index*71+i*7);local z=z0+r*C.Chunk
  local p=route:point(z);local side=i%2==0 and 1 or -1;local x=p.x+side*(p.width/2+20+Route.random(route.seed,i+index*33)*65)
  local at=Vector3.new(x,p.y-2,z)+offset
  local height=8+Route.random(route.seed,i*71+index)*10
  local template=biome.trees and #templates>0 and self.quality~='low'and templates[(i-1)%#templates+1]
  if template then
   local prop=template:Clone();prop.Parent=model;prop:PivotTo(CFrame.new(at)*CFrame.Angles(0,r*6,0))
   coroutine.yield()
  elseif biome.trees and i%3~=0 then
   self:part(model,'Pine trunk',Vector3.new(1,height*.6,1),CFrame.new(at+Vector3.new(0,height*.3,0)),{.25,.20,.14},Enum.Material.Wood)
   local layers=self.quality=='low'and 1 or 2
   for level=1,layers do
    local size=(height*.65)*(1-(level-1)*.28)
    self:part(model,'Pine canopy',Vector3.new(size,height*.48,size),CFrame.new(at+Vector3.new(0,height*(.50+level*.16),0)),{.14,.27+level*.015,.19},Enum.Material.Grass,Enum.PartType.Ball)
   end
  elseif biome.desert and i%2==0 then
   self:part(model,'Cactus',Vector3.new(1.3,height*.65,1.3),CFrame.new(at+Vector3.new(0,height*.325,0)),{.28,.42,.27})
   self:part(model,'Cactus arm',Vector3.new(4,1,1),CFrame.new(at+Vector3.new(1,height*.4,0)),{.28,.42,.27})
  else
   self:part(model,'Boulder',Vector3.new(height*.7,height*.4,height*.55),CFrame.new(at+Vector3.new(0,height*.17,0))*CFrame.Angles(.12,r*4,.18),biome.snow and {.71,.74,.72}or{.39,.38,.33},Enum.Material.Slate,Enum.PartType.Ball)
  end
 end
 -- Distant low-poly landforms give each biome a readable skyline.
 local p=route:point(z0+C.Chunk/2)
 for _,side in ipairs({-1,1})do
  local h=biome.desert and 90 or 140
  self:part(model,'Distant ridge',Vector3.new(240,h,320),CFrame.new(p.x+side*420,p.y+h*.25-20,z0+128)*CFrame.new(offset),biome.ground,Enum.Material.Rock,Enum.PartType.Ball)
 end
end
function Stream:build(index,entry)
 local route=self.route;local model=entry.model;local offset=self:offset();local start=index*C.Chunk
 for z=start,start+C.Chunk-C.RoadStep,C.RoadStep do
  if entry.cancel or entry.epoch~=self.epoch then return end
  local a,b=route:point(z),route:point(z+C.RoadStep);local p=route:point(z+C.RoadStep/2)
  local pos=Vector3.new((a.x+b.x)/2,(a.y+b.y)/2,z+C.RoadStep/2)+offset
  local dir=Vector3.new(b.x-a.x,b.y-a.y,C.RoadStep)
  -- Match the analytic heightfield, including grade across a curved, banked road.
  local slope=math.tan(p.bank)/math.sqrt(1+p.dx*p.dx)
  local normal=Vector3.new(-slope,1,p.dx*slope-p.dy).Unit
  local frame=CFrame.lookAt(pos,pos+dir,normal)
  frame=frame-frame.UpVector*.35
  local length=dir.Magnitude+2.4;local biome=C.Biomes[p.biome]
  self:part(model,'Road',Vector3.new(p.width,.7,length),frame,biome.road,p.surface=='tarmac'and Enum.Material.Asphalt or Enum.Material.Ground)
  for _,side in ipairs({-1,1})do
   self:part(model,'Shoulder',Vector3.new(3,.5,length),frame*CFrame.new(side*(p.width/2+1.5),-.18,0),biome.ground,Enum.Material.Ground)
   if p.bridge or p.tunnel then
    self:part(model,'Safety rail',Vector3.new(.5,2.8,length),frame*CFrame.new(side*(p.width/2+.6),1.5,0),{.57,.59,.55},Enum.Material.Metal)
   end
  end
  if p.bridge and z==start then
   local water=self:part(model,'River',Vector3.new(320,.3,C.Chunk+8),CFrame.new(p.x,-12,start+C.Chunk/2)+offset,{.16,.36,.39},Enum.Material.Glass);water.Transparency=.2
  end
  if p.bridge and z%64==0 then
   for _,side in ipairs({-1,1})do self:part(model,'Bridge pier',Vector3.new(2,28,3),frame*CFrame.new(side*11,-14,0),{.36,.37,.34},Enum.Material.Concrete)end
  end
  if not p.bridge then self:part(model,'Land',Vector3.new(190,5,length+2),frame*CFrame.new(0,-4,0),biome.ground,Enum.Material.Grass)end
  if z%32==0 and p.surface=='tarmac'then self:part(model,'Centre dash',Vector3.new(.25,.04,8),frame*CFrame.new(0,.38,0),{.88,.85,.68})end
  if p.tunnel and z%32==0 then
   self:part(model,'Tunnel roof',Vector3.new(p.width+4,2,35),frame*CFrame.new(0,13,0),{.30,.32,.32},Enum.Material.Concrete)
   for _,side in ipairs({-1,1})do self:part(model,'Tunnel wall',Vector3.new(1,12,35),frame*CFrame.new(side*(p.width/2+1.5),6,0),{.31,.33,.32},Enum.Material.Concrete)end
   self:part(model,'Tunnel strip',Vector3.new(.3,.15,14),frame*CFrame.new(0,11.8,0),{.9,.77,.48},Enum.Material.Neon)
  end
  if z>=0 and (z%C.Checkpoint==0 or z==route.length and route.length>0)then
   for _,side in ipairs({-1,1})do self:part(model,'Timing post',Vector3.new(.4,7,.4),frame*CFrame.new(side*(p.width/2+2),3.5,0),{.95,.72,.29})end
   self:part(model,'Timing banner',Vector3.new(p.width+5,1.5,.3),frame*CFrame.new(0,7,0),{.14,.27,.23})
  end
 end
 self:decor(model,index);entry.done=true
end
function Stream:update(z)
 if not self.route then return end
 local cfg=C.Quality[self.quality];local centre=math.floor(math.max(0,z)/C.Chunk);local wanted={}
 for i=math.max(-1,centre-cfg.behind),centre+cfg.ahead do wanted[i]=true end
 for i,entry in pairs(self.chunks)do
  if not wanted[i]or entry.cancel then entry.cancel=true;self:release(entry.model);self.chunks[i]=nil end
 end
 -- Prioritize the piece beneath the car and its immediate approach.
 local order={centre,centre+1,centre-1}
 for i=centre+2,centre+cfg.ahead do order[#order+1]=i end
 for i=centre-2,math.max(-1,centre-cfg.behind),-1 do order[#order+1]=i end
 for _,i in ipairs(order)do if wanted[i]and not self.chunks[i]then
  local model=Instance.new('Model');model.Name='Road_'..i;model.Parent=self.folder
  local entry={model=model,epoch=self.epoch};self.chunks[i]=entry
  entry.job=coroutine.create(function()self:build(i,entry)end);self.queue[#self.queue+1]=entry
 end end
end
function Stream:work(budget)
 local began=os.clock()
 while #self.queue>0 and os.clock()-began<budget do
  local entry=self.queue[1]
  if entry.cancel or entry.epoch~=self.epoch or coroutine.status(entry.job)=='dead'then table.remove(self.queue,1)
  else local ok,err=coroutine.resume(entry.job);if not ok then entry.cancel=true;warn('Road generation failed: '..tostring(err));table.remove(self.queue,1)end end
 end
end
function Stream:ready(z)
 local index=math.floor(math.max(0,z)/C.Chunk)
 return self.chunks[index]and self.chunks[index].done and self.chunks[index+1]and self.chunks[index+1].done
end
function Stream:destroy()
 self.epoch+=1;for _,entry in pairs(self.chunks)do entry.cancel=true;self:release(entry.model)end
 for _,p in ipairs(self.pool)do p:Destroy()end;self.chunks={};self.pool={};self.folder:Destroy()
end
return Stream
