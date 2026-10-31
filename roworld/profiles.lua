-- Bounded evidence, not mind-reading. Cross-match names are weak identities.
local Profiles={};Profiles.__index=Profiles
local function number(v,limit) return type(v)=='number' and v==v and math.clamp(v,0,limit) or 0 end
local function key(o)
 if not o or o.kind~=2 or type(o.name)~='string' or #o.name==0 or #o.name>80 then return nil end
 return o.name
end
function Profiles.new(saved)
 local self=setmetatable({records={},session={},seen={},history={},clock=0},Profiles)
 if type(saved)=='table' and saved.version==1 and type(saved.records)=='table' then
  for i,r in ipairs(saved.records) do
   if i>128 then break end
   if type(r)=='table' and type(r.name)=='string' and #r.name>0 and #r.name<=80 then
    self.clock=math.max(self.clock,number(r.touch,1000000000))
    self.records[r.name]={name=r.name,betrayals=number(r.betrayals,100),attacks=number(r.attacks,100000),
     touch=number(r.touch,1000000000),attack_fraction=number(r.attack_fraction,1),naval=number(r.naval,100000),observations=number(r.observations,100000)}
   end
  end
 end
 return self
end
function Profiles:start(frame)
 if self.matchState==frame.state and self.me==frame.me then return end
 self.session={};self.seen={};self.units={};self.matchState=frame.state;self.me=frame.me;self.history={};self.lastTick=nil
end
function Profiles:record(o)
 local name=key(o);if not name then return nil end
 local r=self.records[name]
 if not r then
  local count=0;for _ in pairs(self.records) do count+=1 end
  if count>=128 then
   local oldest
   for name,row in pairs(self.records) do if not oldest or (row.touch or 0)<(self.records[oldest].touch or 0) then oldest=name end end
   if oldest then self.records[oldest]=nil end
  end
  r={name=name,betrayals=0,attacks=0,attack_fraction=0,naval=0,observations=0};self.records[name]=r
 end
 self.clock+=1;r.touch=self.clock
 return r
end
function Profiles:betrayed(frame,id)
 local r=self:record(frame.state.owners[id]);if r then r.betrayals+=1 end
 self.session[id]=self.session[id] or {};self.session[id].name=key(frame.state.owners[id]);self.session[id].betrayals=(self.session[id].betrayals or 0)+1
end
function Profiles:observe(frame)
 if self.matchState~=frame.state or self.me~=frame.me then self:start(frame) end
 local live={}
 for aid,a in pairs(frame.state.attacks) do
  live[aid]=true
  if a.attacker~=frame.me and not self.seen[aid] and not a.retreating then
   local o=frame.state.owners[a.attacker];local r=self:record(o)
   if r then
    local fraction=math.clamp((a.troops or 0)/math.max(1,(a.troops or 0)+(o.troops or 0)),0,1)
    r.attack_fraction=r.attacks==0 and fraction or r.attack_fraction*.8+fraction*.2;r.attacks+=1
    local m=self.session[a.attacker] or {attacks=0};m.attacks=(m.attacks or 0)+1
    m.name=key(o);m.against_us=(m.against_us or 0)+(a.target==frame.me and 1 or 0);self.session[a.attacker]=m
   end
  end
 end
 self.seen=live
 if not self.lastTick or frame.state.tick-self.lastTick>=100 then
  self.lastTick=frame.state.tick
  for id,o in pairs(frame.state.owners) do
   local r=id~=frame.me and o.alive and self:record(o)
   if r then r.observations+=1 end
  end
  local units={}
  for uid,u in pairs(frame.state.units or {}) do
   units[uid]=true
   if u.owner~=frame.me and u.kind==2 and not self.units[uid] then local r=self:record(frame.state.owners[u.owner]);if r then r.naval+=1 end end
  end
  self.units=units
 end
end
function Profiles:assessment(frame,id)
 local name=key(frame.state.owners[id]);local r=self.records[name];local m=self.session[id] or {}
 if m.name~=name then m={} end
 return {nation=id,identity='display name; cross-match identity uncertain',observed_attacks=r and r.attacks or 0,
  attack_fraction=r and r.attack_fraction or 0,naval_observations=r and r.naval or 0,
  betrayal_penalty=math.min(8,(m.betrayals or 0)*5+math.min(2,r and r.betrayals or 0)),
  confidence=r and math.min(1,r.attacks/10) or 0,against_us=m.against_us or 0}
end
function Profiles:export()
 local rows={};for _,r in pairs(self.records) do table.insert(rows,table.clone(r)) end
 table.sort(rows,function(a,b) return a.name<b.name end)
 return {version=1,scope='Local bounded observations, keyed by ambiguous display name; no automatic upload',records=rows}
end
function Profiles:report(frame)
 local rows={};for id,o in pairs(frame.state.owners) do if id~=frame.me and o.kind==2 then table.insert(rows,self:assessment(frame,id)) end end
 table.sort(rows,function(a,b) return a.nation<b.nation end);return rows
end
return Profiles
