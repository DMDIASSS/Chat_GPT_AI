-- Team membership comes from the game. Friendship comes from Roblox's live roster.
local Cooperation={};Cooperation.__index=Cooperation
function Cooperation.new() return setmetatable({enabled=true,roster={},status={}},Cooperation) end
function Cooperation:setRoster(rows) self.roster=rows or {} end
function Cooperation:update(frame)
 local s=frame.state;local teams={};local count=0
 for _,o in pairs(s.owners) do if (o.team or 0)>0 and not teams[o.team] then teams[o.team]=true;count+=1 end end
 local names=s.team_names or {};local declared=#names
 self.teamMode=declared>0 or count>0;self.ownTeam=frame.info.team or 0
 local ownerNames={};for _,o in pairs(s.owners) do if o.kind==2 and o.alive then ownerNames[o.name]=(ownerNames[o.name] or 0)+1 end end
 local players={}
 for _,p in ipairs(self.roster) do
  local name=p.display_name
  if name and p.user_id and p.user_id>0 then
   if players[name]~=nil then players[name]=false else players[name]=p end
  end
 end
 self.friends={};local rows={}
 for id,o in pairs(s.owners) do
  local player=players[o.name]
  if id~=frame.me and o.alive and o.kind==2 and ownerNames[o.name]==1 and player and player.is_friend==true then
   local opposing=self.teamMode and self.ownTeam>0 and (o.team or 0)~=self.ownTeam
   if self.enabled and not opposing then self.friends[id]=true end
   table.insert(rows,{nation=id,user_id=player.user_id,opposing_team=opposing,help_enabled=self.enabled and not opposing,
    binding='unique live display-name match; nation ownership is not account-ID authenticated'})
  end
 end
 table.sort(rows,function(a,b) return a.nation<b.nation end)
 s.bot_friend_guard=self.friends
 self.status={mode=self.teamMode and 'teams' or 'free_for_all',team_count=math.max(declared,count),
  count_source=declared>0 and 'snapshot team names' or 'observed team IDs; may be incomplete',own_team=self.ownTeam,
  friends_enabled=self.enabled,friends=rows}
end
function Cooperation:isFriend(id) return self.enabled and (self.friends or {})[id]==true end
function Cooperation:aid(frame,a,ready)
 if not ready or a.incoming>0 or (a.available or 0)<a.home*.1 then return nil end
 local best,urgency,amount
 for id,o in pairs(frame.state.owners) do
  local teammate=self.ownTeam>0 and o.team==self.ownTeam
  if id~=frame.me and o.alive and (teammate or self:isFriend(id)) and frame.state:are_allies(frame.me,id) then
   local incoming=0
   for _,attack in pairs(frame.state.attacks) do if attack.target==id and not attack.retreating then incoming+=attack.troops or 0 end end
   local cap=math.max(1,o.max_troops or 0);local need=math.max(0,incoming*1.2-(o.troops or 0))
   if (o.troops or 0)<cap*.3 and a.home>(frame.info.max_troops or math.huge)*.6 then need=math.max(need,cap*.4-(o.troops or 0)) end
   local send=math.floor(math.min(need,a.home*.08,a.available*.5,math.max(0,cap-(o.troops or 0))))
   local score=incoming/math.max(1,o.troops or 0)+(self:isFriend(id) and .5 or 0)
   if send>=100 and (not urgency or score>urgency) then best,urgency,amount=id,score,send end
  end
 end
 if best then return {intent={type='donate',target=best,troops=amount},reserve=a.reserve,objective='defend',channel='support',cooldown=45,
  label='Sending limited troop support to '..frame.state:owner_name(best),plan={amount=amount,cooperative_support=true,support_urgency=urgency}} end
end
return Cooperation
