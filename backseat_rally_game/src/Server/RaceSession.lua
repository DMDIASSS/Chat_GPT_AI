-- Server-owned parallel rally races: one road/seed/ruleset, separate collision lanes.
-- The caller launches ordinary runs, then releases their countdown as one group.
local Race={};Race.__index=Race
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<1e12 end
local function label(player)return tostring(player.DisplayName or player.Name or player.UserId)end
local function deep(value)
 if type(value)~='table'then return value end
 local out={};for k,v in pairs(value)do out[k]=deep(v)end;return out
end
local function rules(source)
 source=type(source)=='table'and source or {}
 -- Never forward arbitrary client tables to the driving solver.
 local out={}
 for _,name in ipairs({'damage','damageEnabled','assists','keyboardAssist','tractionControl','abs','stabilityControl'})do
  if type(source[name])=='boolean'then out[name]=source[name]end
 end
 for _,name in ipairs({'tyrePressure','pressure','assistStrength'})do
  if finite(source[name])then out[name]=math.clamp(source[name],.55,1.4)end
 end
 return out
end
function Race.new(callbacks)
 assert(type(callbacks)=='table'and type(callbacks.notify)=='function'and type(callbacks.launch)=='function','Race callbacks required')
 return setmetatable({callbacks=callbacks,races={},membership={},serial=0,maxPlayers=8,maxRooms=16},Race)
end
function Race:_notice(player,message)self.callbacks.notify(player,'notice',message)end
function Race:_snapshot(race)
 local members={}
 for _,m in ipairs(race.members)do
  members[#members+1]={userId=m.userId,name=m.name,car=m.car,ready=m.ready,loaded=m.loaded,z=m.z,time=m.time,
   finished=m.finished,dnf=m.dnf or false,reason=m.reason}
 end
 table.sort(members,function(a,b)
  if a.dnf~=b.dnf then return not a.dnf end
  if a.finished~=b.finished then return a.finished end
  if a.finished and a.time~=b.time then return a.time<b.time end
  if a.z~=b.z then return a.z>b.z end
  return a.userId<b.userId
 end)
 for i,m in ipairs(members)do m.rank=i end
 return {id=race.id,host=race.host.UserId,name=label(race.host).."'s rally",status=race.status,seed=race.seed,mode='sprint',
  settings=deep(race.settings),members=members,maxPlayers=self.maxPlayers}
end
function Race:_send(race)
 local snapshot=self:_snapshot(race)
 for _,m in ipairs(race.members)do if m.player then self.callbacks.notify(m.player,'race',snapshot)end end
 return snapshot
end
function Race:_member(race,player)
 for _,m in ipairs(race.members)do if m.player==player then return m end end
end
function Race:lobby()
 local out={}
 for _,race in pairs(self.races)do if race.status=='lobby'and #race.members<self.maxPlayers then out[#out+1]=self:_snapshot(race)end end
 table.sort(out,function(a,b)return a.id<b.id end);return out
end
function Race:_free(player)
 return not self.callbacks.active or not self.callbacks.active(player)
end
function Race:action(player,kind,data)
 data=type(data)=='table'and data or {}
 local race=self.membership[player]
 if kind=='create'then
  if not self:_free(player)then self:_notice(player,'Finish or leave your current drive before hosting a race.');return false end
  if race then self:remove(player);race=nil end
  local count=0
  for id,entry in pairs(self.races)do
   if entry.status=='finished'then
    local live=false;for _,m in ipairs(entry.members)do if m.player and self.membership[m.player]==entry then live=true end end
    if not live then self.races[id]=nil else count+=1 end
   else count+=1 end
  end
  if count>=self.maxRooms then self:_notice(player,'Race rooms are full. Join an existing rally.');return false end
  self.serial+=1
  local seed=finite(data.seed)and math.floor(data.seed)%1000000000 or math.random(1,999999999)
  race={id=tostring(self.serial),host=player,seed=seed,status='lobby',settings=rules(data.settings),members={}}
  self.races[race.id]=race
  local member={player=player,userId=player.UserId,name=label(player),car=type(data.car)=='string'and string.sub(data.car,1,60)or 'hatch',ready=false,loaded=false,z=0,time=0,finished=false}
  race.members[1]=member;self.membership[player]=race;self:_send(race);return true
 elseif kind=='join'then
  if not self:_free(player)then self:_notice(player,'Finish or leave your current drive before joining a race.');return false end
  local target=self.races[tostring(data.id or '')]
  if not target or target.status~='lobby'or #target.members>=self.maxPlayers then self:_notice(player,'That rally lobby is unavailable or full.');return false end
  if race==target then self:_send(target);return true end
  if race then self:remove(player)end
  target.members[#target.members+1]={player=player,userId=player.UserId,name=label(player),car=type(data.car)=='string'and string.sub(data.car,1,60)or 'hatch',ready=false,loaded=false,z=0,time=0,finished=false}
  self.membership[player]=target;self:_send(target);return true
 elseif kind=='leave'then
  local member=race and self:_member(race,player)
  if race and race.status~='lobby'and race.status~='finished'and member and not member.finished and not member.dnf then self:_notice(player,'Retire from the race before leaving its room.');return false end
  self:remove(player);self.callbacks.notify(player,'race',{});return true
 elseif not race then self:_notice(player,'Join or host a rally first.');return false
 elseif kind=='ready'and race.status=='lobby'then
  local m=self:_member(race,player)
  m.ready=data.ready~=false
  if type(data.car)=='string'then m.car=string.sub(data.car,1,60)end
  self:_send(race);return true
 elseif kind=='start'and race.status=='lobby'then
  if race.host~=player then self:_notice(player,'Only the host can start this rally.');return false end
  if #race.members<2 then self:_notice(player,'Invite at least one other driver before starting.');return false end
  for _,m in ipairs(race.members)do
   if not m.ready then self:_notice(player,m.name..' is not ready.');return false end
   if not self:_free(m.player)then self:_notice(player,m.name..' is already driving.');return false end
   if self.callbacks.validate then
    local ok,reason=self.callbacks.validate(m.player,{mode='sprint',seed=race.seed,car=m.car,settings=deep(race.settings)},race.id)
    if not ok then self:_notice(player,reason or (m.name..' cannot start yet.'));return false end
   end
  end
  race.status='loading';local launched={}
  for _,m in ipairs(race.members)do
   m.loaded=false;m.finished=false;m.dnf=false;m.reason=nil;m.z=0;m.time=0
   local ok,result,reason=pcall(self.callbacks.launch,m.player,{mode='sprint',seed=race.seed,car=m.car,settings=deep(race.settings)},race.id)
   if not ok or not result then
    -- Launch can fail on car availability/slot allocation. Roll back every prior launch.
    for _,started in ipairs(launched)do if self.callbacks.cancel then self.callbacks.cancel(started.player,race.id)end end
    race.status='lobby'
    for _,entry in ipairs(race.members)do entry.ready=false;entry.loaded=false end
    self:_send(race)
    for _,entry in ipairs(race.members)do self:_notice(entry.player,reason or 'Unable to start every driver. Ready up and retry.')end
    return false
   end
   launched[#launched+1]=m
  end
  self:_send(race);return true
 end
 return false
end
function Race:_releaseIfLoaded(race)
 if race.status~='loading'then return false end
 local players={}
 for _,m in ipairs(race.members)do
  if m.player and not m.dnf and not m.finished then
   if not m.loaded then return false end
   players[#players+1]=m.player
  end
 end
 if #players==0 then race.status='finished';self:_send(race);return false end
 race.status='running';self:_send(race)
 if self.callbacks.countdown then self.callbacks.countdown(players,race.id)end
 return true
end
function Race:loaded(player)
 local race=self.membership[player];if not race or race.status~='loading'then return false end
 local member=self:_member(race,player);if not member or member.dnf then return false end
 member.loaded=true
 if self:_releaseIfLoaded(race)then return true end
 self:_send(race);return false
end
function Race:update(player,z,time,finished,reason)
 local race=self.membership[player];if not race or (race.status~='running'and race.status~='loading')then return end
 local m=self:_member(race,player);if not m or m.dnf or m.finished then return end
 if finite(z)then m.z=math.max(m.z,math.clamp(z,0,6144))end
 if finite(time)then m.time=math.max(m.time,math.max(0,time))end
 if finished==true then m.finished=true
 elseif reason then m.dnf=true;m.reason=string.sub(tostring(reason),1,64)end
 if reason and race.status=='loading'then self:_releaseIfLoaded(race)end
 local complete=true;for _,entry in ipairs(race.members)do if not entry.finished and not entry.dnf then complete=false end end
 if complete then race.status='finished'end
 local now=self.callbacks.clock and self.callbacks.clock()or os.clock()
 if finished==true or reason or not race.lastStandings or now-race.lastStandings>=.1 then
  race.lastStandings=now;return self:_send(race)
 end
end
function Race:remove(player)
 local race=self.membership[player];if not race then return end
 self.membership[player]=nil
 local m=self:_member(race,player)
 if race.status=='lobby'or race.status=='finished'then
  for i,entry in ipairs(race.members)do if entry==m then table.remove(race.members,i);break end end
 else
  m.player=nil;if not m.finished then m.dnf=true;m.reason='Left the race'end
 end
 local nextHost;for _,entry in ipairs(race.members)do if entry.player then nextHost=entry.player;break end end
 if not nextHost then self.races[race.id]=nil;return end
 if race.host==player then race.host=nextHost end
 if race.status=='loading'then self:_releaseIfLoaded(race)end
 local complete=true;for _,entry in ipairs(race.members)do if not entry.finished and not entry.dnf then complete=false end end
 if complete and race.status=='running'then race.status='finished'end
 self:_send(race)
end
function Race:forPlayer(player)
 local race=self.membership[player];return race and self:_snapshot(race)or nil
end
return Race
