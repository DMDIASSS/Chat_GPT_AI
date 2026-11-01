-- Incremental topology of a frozen public ownership snapshot. Never authorizes orders.
local Atlas={};Atlas.__index=Atlas
local VALUE={[0]=8,[1]=7,[2]=8,[3]=2,[4]=4,[5]=6}
local function adjacent(m,t,fn)
 local x=t%m.W
 if x>0 then fn(t-1) end;if x<m.W-1 then fn(t+1) end
 if t>=m.W then fn(t-m.W) end;if t<m.N-m.W then fn(t+m.W) end
end
function Atlas.new() return setmetatable({summary={ready=false,components={},relations={}}},Atlas) end
function Atlas:update(frame,budget)
 if self.lastTick==frame.state.tick then return end
 self.lastTick=frame.state.tick
 local m,s=frame.map,frame.state
 budget=math.clamp(budget or 16384,1,65536)
 local w=self.work
 if not w then
  if self.finishedAt and frame.now-self.finishedAt<5 then return end
  if typeof(s.owner)~='buffer' or buffer.len(s.owner)~=m.N*4 then return end
  local owner=buffer.create(m.N*4);buffer.copy(owner,0,s.owner)
  w={owner=owner,labels=buffer.create(m.N*4),queue=buffer.create(m.N*4),scan=0,head=0,tail=0,
   components={},relations={},tick=s.tick,at=frame.now,me=frame.me,structures={}}
  for _,b in pairs(s.structures) do table.insert(w.structures,{owner=b.owner,kind=b.kind,tile=b.tile,level=b.level or 1}) end
  self.work=w
 end
 local function id(t) return buffer.readi32(w.owner,t*4) end
 local function edge(a,b)
  if a<=0 or b<=0 or a==b then return end
  w.relations[a]=w.relations[a] or {};w.relations[b]=w.relations[b] or {}
  w.relations[a][b]=(w.relations[a][b] or 0)+1;w.relations[b][a]=(w.relations[b][a] or 0)+1
 end
 for _=1,budget do
  if w.head<w.tail then
   local t=buffer.readu32(w.queue,w.head*4);w.head+=1
   local c=w.components[#w.components];c.land+=1
   adjacent(m,t,function(n)
    local other=id(n)
    if other==w.me then
     if buffer.readu32(w.labels,n*4)==0 then
      buffer.writeu32(w.labels,n*4,#w.components);buffer.writeu32(w.queue,w.tail*4,n);w.tail+=1
     end
    elseif m:is_contestable(n) then
     c.border+=1;c.neighbours[tostring(other)]=(c.neighbours[tostring(other)] or 0)+1
     if other==0 and #c.neutral_frontier<12 then table.insert(c.neutral_frontier,n) end
    elseif type(m.is_water)=='function' and m:is_water(n) or m.water and m.water[n] then c.coast+=1 end
   end)
  elseif w.scan<m.N then
   local t=w.scan;w.scan+=1;local other=id(t)
   if other>0 then
    if t%m.W<m.W-1 then edge(other,id(t+1)) end
    if t<m.N-m.W then edge(other,id(t+m.W)) end
   end
   if other==w.me and buffer.readu32(w.labels,t*4)==0 then
    table.insert(w.components,{id=#w.components+1,tile=t,land=0,asset_value=0,buildings=0,coast=0,border=0,neighbours={},neutral_frontier={}})
    buffer.writeu32(w.labels,t*4,#w.components);w.head=0;w.tail=1;buffer.writeu32(w.queue,0,t)
   end
  else
   local ownLand=0;for _,c in ipairs(w.components) do ownLand+=c.land end
   for _,b in ipairs(w.structures) do
    if b.owner==w.me and b.tile>=0 and b.tile<m.N then
     local c=w.components[buffer.readu32(w.labels,b.tile*4)]
     if c then c.buildings+=1;c.asset_value+=(VALUE[b.kind] or 1)*b.level end
    end
   end
   local main
   for _,c in ipairs(w.components) do
    c.share=c.land/math.max(1,ownLand)
    if not main or c.asset_value+c.land*.01>main.asset_value+main.land*.01 then main=c end
   end
   self.labels=w.labels;self.components=w.components;self.finishedAt=frame.now
   local rows=table.clone(w.components);table.sort(rows,function(a,b) return a.land>b.land end)
   while #rows>32 do table.remove(rows) end
   local relations={}
   for a,neighbors in pairs(w.relations) do
    local row={nation=a,neighbours={}}
    for b,length in pairs(neighbors) do table.insert(row.neighbours,{nation=b,edges=length}) end
    table.sort(row.neighbours,function(x,y) return x.edges>y.edges end)
    table.insert(relations,row)
   end
   table.sort(relations,function(a,b) return a.nation<b.nation end)
   self.summary={ready=true,snapshot_tick=w.tick,snapshot_at=w.at,completed_at=frame.now,own_land=ownLand,
    component_count=#w.components,components=rows,main_component=main and main.id,relations=relations,
    scope='Frozen public ownership; topology may be stale. Neutral frontier is sampled; component connectivity is exact for this snapshot.'}
   self.work=nil;return
  end
 end
end
function Atlas:component(frame,tile)
 if not self.labels or not tile or tile<0 or tile>=frame.map.N or frame.now-(self.summary.snapshot_at or 0)>30
  or frame.state:tile_owner(tile)~=frame.me then return nil end
 return self.components[buffer.readu32(self.labels,tile*4)]
end
function Atlas:siteRisk(frame,tile)
 local c=self:component(frame,tile);local exposure=0;local m=frame.map
 -- Short exact probes complement component boundaries; not an unseen attack forecast.
 local x,y=tile%m.W,tile//m.W;local radius=math.max(1,math.ceil(24/(m.k_lin or 1)))
 for _,d in ipairs({{1,0},{-1,0},{0,1},{0,-1},{1,1},{-1,-1},{1,-1},{-1,1}}) do
  for step=1,radius do
   local xx,yy=x+d[1]*step,y+d[2]*step
   if xx<0 or yy<0 or xx>=m.W or yy>=m.H then break end
   local id=frame.state:tile_owner(yy*m.W+xx)
   if id>0 and id~=frame.me and not frame.state:are_allies(frame.me,id) then exposure+=1-step/(radius+1);break end
  end
 end
 return math.clamp(exposure/4+(c and c.id~=self.summary.main_component and c.share<.15 and .25 or 0),0,1)
end
function Atlas:report(now)
 local row=table.clone(self.summary);row.age_seconds=row.snapshot_at and math.max(0,now-row.snapshot_at) or nil
 row.scanning=self.work~=nil;return row
end
return Atlas
