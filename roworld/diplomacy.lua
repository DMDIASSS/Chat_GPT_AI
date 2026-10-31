-- Benefits and risks are estimates from visible state, not promises of loyalty.
local Diplomacy={}
local Weapons = require("./weapons")
local function pose(s,u)
 local p=u.path or {};if #p==0 then return u.patrol_tile end
 local i=math.clamp(math.floor(math.max(0,s.tick-(u.start_tick or s.tick))*100/math.max(1,u.ticks_per_tile_x100 or 100))+1,1,#p)
 return p[i]
end
function Diplomacy.evaluate(policy,frame,id,a,groups,mode)
 local s=frame.state;local o=s.owners[id];local reasons={}
 local function veto(reason) return {nation=id,mode=mode,score=-100,eligible=false,reasons={reason}} end
 if not o or not o.alive or id==frame.me then return veto('not a live foreign nation') end
 if (o.traitor_until or 0)>s.tick then return veto('currently marked traitor') end
 if policy.strategy and not policy.strategy:trustworthy(frame,id) then return veto('recent confirmed betrayal or unresolved distrust') end
 if (a.targets or {})[id] then return veto('our land campaign is still active') end
 if not Weapons.allianceSafe(s,frame.me,id) then return veto('our in-flight weapons endanger this alliance') end
 local near=groups[id]~=nil or (policy.adjacentAllies or {})[id]==true
 local home=math.max(1,a.home or frame.info.troops or 1)
 local ratio=(o.troops or 0)/home
 local memory=policy.opponents[id] or {};local heat=memory.heat or 0
 local kind=o.kind==nil and 2 or o.kind
 local score=kind==2 and 4 or kind==0 and .5 or -3
 local function add(value,reason) score+=value;table.insert(reasons,reason) end
 table.insert(reasons,kind==2 and 'human partnership preferred' or kind==0 and 'country partnership needs concrete benefits' or 'tribe has limited strategic value')
 if policy.cooperation and policy.cooperation:isFriend(id) then add(12,'Roblox friend matched in live roster; cooperation enabled') end
 if near then add(2,'shared frontier can be stabilized') end
 add(math.min(3,math.log(1+ratio)*2),'relative army strength')
 if s:are_allies(frame.me,id) then add(1,'existing relationship') end
 local profile=policy.profiles and policy.profiles:assessment(frame,id)
 if profile and profile.betrayal_penalty>0 then add(-profile.betrayal_penalty,'persistent observed betrayal history; display-name identity uncertain across matches') end
 if heat>.2 then add(-math.min(6,heat*3),'recent observed aggression') end
 local enemies={};local shared=false;local direct=false
 for _,attack in pairs(s.attacks) do
  if not attack.retreating then
   if attack.target==frame.me and attack.attacker~=id then enemies[attack.attacker]=true end
   if attack.attacker==frame.me and attack.target>0 then enemies[attack.target]=true end
   if attack.attacker==id and attack.target==frame.me then direct=true end
  end
 end
 for _,attack in pairs(s.attacks) do
  if attack.attacker==id and enemies[attack.target] and not attack.retreating then shared=true end
 end
 if shared then add(4,'actively opposing a shared threat') end
 for enemy in pairs(enemies) do if s:are_allies(id,enemy) then add(-3,'also allied with a current enemy');break end end
 if direct then
  add(-6,'currently attacking us')
  if ratio>1.5 and (a.incoming or 0)>home*.2 then add(4,'peace could relieve an overwhelming attack') end
  if (a.incoming or 0)>home*.8 then add(12,'last-resort peace under an overwhelming invasion') end
 end
 if kind==0 and near and ratio<.6 then add(-5,'weak neighbouring country is an expansion opportunity') end
 local early=s.playing_since and s.playing_since>=0 and s.tick-s.playing_since<1200
 if kind==0 and early and heat<.1 and not direct then add(-2,'early country grace may reduce immediate alliance value; retaliation remains possible') end
 if kind==0 and near and ratio>3 and not (direct and (a.incoming or 0)>home*.8) then
  return veto('dominant bordering country could later betray and absorb us')
 end
 if near and (memory.landTrend or 0)>math.max(5,(o.tiles or 0)*.003) and ratio>1.5 then add(-4,'rapid observed expansion raises future domination risk') end
 local fleet=0
 for _,u in pairs(s.units or {}) do
  if u.owner==id and u.kind==2 then
   local t=pose(s,u)
   if t and t>=0 and t<frame.map.N and policy.strategy and policy.strategy.core:isSite(frame.map,t) then fleet+=1 end
  end
 end
 if fleet>0 then
  add(2,'alliance could reduce immediate naval pressure')
  if ratio>1.5 or fleet>1 then add(-4,'concentrated warships near our core create coercion risk') end
 end
 local ports={};for _,b in pairs(s.structures) do if b.kind==1 and b.owner==frame.me then table.insert(ports,b) end end
 local trade=false
 for _,b in pairs(s.structures) do
  if b.kind==1 and b.owner==id then for _,ours in ipairs(ports) do
   if type(frame.map.coast_body_of)=='function' then
    local body=frame.map:coast_body_of(ours.tile)
    if body>0 and body==frame.map:coast_body_of(b.tile) then trade=true end
   end
  end end
 end
 if trade then add(2,'ports share a water body; potential trade relationship') end
 if not near and not shared and not trade then add(-1,'limited visible local relevance') end
 local threshold=mode=='offer' and 7 or mode=='renew' and 4.5 or 4
 return {nation=id,mode=mode,score=score,eligible=score>=threshold,reasons=reasons,
  threshold=threshold,army_ratio=ratio,nearby_warships=fleet,shared_enemy=shared,potential_trade=trade}
end
return Diplomacy
