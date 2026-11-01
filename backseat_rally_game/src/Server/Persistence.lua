-- Immutable replay pages + small manifests. No DataStore work on the simulation thread.
local DataStoreService=game:GetService('DataStoreService')
local HttpService=game:GetService('HttpService')
local P={};P.__index=P
local function fresh()return {version=1,xp=0,records={},bests={},applied={}}end
function P.new(config)
 local self=setmetatable({config=config,users={},cache={},order={},status={},warned=false},P)
 -- Opening a downloaded place is valid. Storage must never abort server startup.
 if game.GameId~=0 then
  local ok,profiles,replays=pcall(function()
   return DataStoreService:GetDataStore('BRExpeditionProfiles_v1'),DataStoreService:GetDataStore('BRExpeditionReplays_v1')
  end)
  if ok then self.profiles=profiles;self.replays=replays end
 end
 return self
end
function P:request(store,method,key,value)
 if not store then return false,'Session only'end
 local last
 for attempt=1,3 do
  local ok,result=pcall(function()
   if method=='GetAsync'then return store:GetAsync(key)end
   return store:UpdateAsync(key,function()return value end)
  end)
  if ok then return true,result end
  last=tostring(result)
  if not self.warned then self.warned=true;warn('Expedition storage unavailable; replays stay in this server until storage recovers.')end
  task.wait(math.min(2,attempt*.5))
 end
 return false,last
end
function P:load(userId)
 if self.users[userId]then return self.users[userId]end
 local profile=fresh();profile.loading=true;self.users[userId]=profile;self.status[userId]='Loading save…'
 if not self.profiles then
  profile.loading=false;self.status[userId]='Session only · ready to drive';return profile
 end
 task.spawn(function()
  local ok,data=self:request(self.profiles,'GetAsync','u:'..userId)
  if ok and type(data)=='table'and data.version==1 then
   profile.xp=tonumber(data.xp)or 0;profile.records=data.records or {};profile.bests=data.bests or {};profile.applied=data.applied or {}
  end
  profile.loading=false
  self.status[userId]=ok and 'Cloud save ready'or 'Session only · enable Studio API access for cloud saves'
 end)
 return profile
end
function P:remember(key,text)
 self.cache[key]=text;table.insert(self.order,key)
 while #self.order>80 do local old=table.remove(self.order,1);self.cache[old]=nil end
end
function P:newRecording(userId,metadata)
 metadata.id=HttpService:GenerateGUID(false);metadata.owner=userId;metadata.pages={};metadata.created=os.time()
 metadata.access={userId};metadata.markers={};metadata.saved=false;metadata.startTime=0
 return {meta=metadata,pending=0,failed=false,finished=false}
end
function P:page(record,text,frames)
 local meta=record.meta;local index=#meta.pages+1;local key='r:'..meta.id..':'..index
 local desc={index=index,from=frames[1][1]/1000,to=frames[#frames][1]/1000,count=#frames,key=key,saved=false}
 meta.pages[index]=desc;self:remember(key,text)
 if record.pending>=self.config.ReplayPending then
  record.failed=true;meta.partial=true;return
 end
 record.pending+=1
 task.spawn(function()
  local ok=self:request(self.replays,'UpdateAsync',key,text)
  desc.saved=ok;record.failed=record.failed or not ok;record.pending-=1
 end)
end
local function add(profile,meta,reward,config,durableOnly)
 local applied=profile.applied or {};profile.applied=applied
 if table.find(applied,meta.id)then return profile end
 table.insert(applied,meta.id);while #applied>32 do table.remove(applied,1)end
 profile.xp=math.max(0,tonumber(profile.xp)or 0)+reward
 if durableOnly and not meta.saved then return profile end
 local records=profile.records or {};profile.records=records
 table.insert(records,1,meta);while #records>config.LibrarySize do table.remove(records)end
 local bests=profile.bests or {};profile.bests=bests
 if meta.completed or meta.banked then
  local found
  for i,b in ipairs(bests)do if b.course==meta.course then found=i;break end end
  local previous=found and bests[found]
  local faster=not previous or meta.duration<previous.duration
  local farther=not previous or (meta.progress or 0)>(previous.progress or 0)
  if not previous or (meta.banked and farther)or (not meta.banked and faster)then
   if found then table.remove(bests,found)end
   table.insert(bests,1,meta)
  end
  while #bests>config.BestSize do table.remove(bests)end
 end
 return profile
end
function P:finish(record,reward,notify)
 record.finished=true
 task.spawn(function()
  local deadline=os.clock()+18
  while record.pending>0 and os.clock()<deadline do task.wait(.1)end
  local meta=record.meta;local complete=#meta.pages>0
  for _,page in ipairs(meta.pages)do if not page.saved then complete=false end end
  meta.saved=complete and not record.failed
  -- Session-only recordings stay accessible through the in-memory page cache.
  meta.storage=meta.saved and 'Saved to cloud'or 'Session only'
  local okManifest=self:request(self.replays,'UpdateAsync','m:'..meta.id,meta)
  if not okManifest then meta.saved=false;meta.storage='Session only'end
  for _,userId in ipairs(meta.access)do
   local profile=self:load(userId)
   add(profile,meta,reward,self.config)
   local savedProfile
   local ok=self.profiles and pcall(function()
    savedProfile=self.profiles:UpdateAsync('u:'..userId,function(old)
     old=type(old)=='table'and old.version==1 and old or fresh()
     return add(old,meta,reward,self.config,true)
    end)
   end)
   if ok and savedProfile then
    -- Preserve session-only clips in RAM without writing broken cloud references.
    local seen={};for _,r in ipairs(savedProfile.records)do seen[r.id]=true end
    for _,r in ipairs(profile.records)do if not r.saved and not seen[r.id]then table.insert(savedProfile.records,1,r);seen[r.id]=true end end
    while #savedProfile.records>self.config.LibrarySize do table.remove(savedProfile.records)end
    local courses={};for _,r in ipairs(savedProfile.bests)do courses[r.course]=true end
    for _,r in ipairs(profile.bests)do if not r.saved and not courses[r.course]then table.insert(savedProfile.bests,r);courses[r.course]=true end end
    while #savedProfile.bests>self.config.BestSize do table.remove(savedProfile.bests)end
    self.users[userId]=savedProfile
   elseif not self.profiles then meta.saved=false;meta.storage='Session only'
   elseif not ok then meta.saved=false;meta.storage='Session only · save index unconfirmed'end
   self.status[userId]=(meta.saved and ok)and 'Cloud save ready'or(not self.profiles and 'Session only · replay ready'or 'Session only · save was not confirmed')
   if notify then notify(userId,meta,self.status[userId])end
  end
  record.done=true
 end)
end
function P:find(userId,id)
 local profile=self:load(userId)
 for _,list in ipairs({profile.records,profile.bests})do for _,r in ipairs(list)do if r.id==id then return r end end end
end
function P:getPage(userId,id,index)
 local record=self:find(userId,id)
 if not record or type(index)~='number'or index%1~=0 then return nil,'Replay unavailable'end
 local page=record.pages[index];if not page then return nil,'Page unavailable'end
 local cached=self.cache[page.key];if cached then return cached end
 if not page.saved then return nil,'This session-only page is no longer in memory'end
 local ok,text=self:request(self.replays,'GetAsync',page.key)
 if ok and type(text)=='string'then self:remember(page.key,text);return text end
 return nil,'Could not load replay page; try again'
end
function P:library(userId)
 local profile=self:load(userId)
 return {xp=profile.xp,records=profile.records,bests=profile.bests,status=self.status[userId]or 'Loading save…'}
end
return P
