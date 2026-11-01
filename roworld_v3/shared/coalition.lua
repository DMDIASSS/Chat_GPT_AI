-- Tactical cooperation and opportunism from current public facts, not hidden intent.
-- Shared by proposals and the final sender, so relationship/risk changes cancel orders.
local Coalition={}
local Weapons=require('./weapons')
local function valid(m,t) return type(t)=='number' and t%1==0 and t>=0 and t<m.N end
local function sameTeam(s,a,b)
    local x,y=s.owners[a],s.owners[b]
    return x and y and (x.team or 0)>0 and x.team==y.team
end
local function protected(s,me,id)
    return id==me or s:are_allies(me,id) or (s.bot_friend_guard or {})[id]==true
end
local function growth(p,seconds)
    local h,c=math.max(0,p.troops or 0),math.max(1,p.max_troops or 1)
    return math.max(0,(h^.73/4+10)*(1-h/c)*10*seconds)
end
function Coalition.armies(s)
    local incoming,committed,between={},{},{}
    for _,a in pairs(s.attacks) do if not a.retreating then
        local n=math.max(0,a.troops or 0)
        incoming[a.target]=(incoming[a.target] or 0)+n
        committed[a.attacker]=(committed[a.attacker] or 0)+n
        local key=a.attacker*1024+a.target;between[key]=(between[key] or 0)+n
    end end
    return incoming,committed,between
end
function Coalition.frontier(frame,who,target)
    local s,m=frame.state,frame.map
    if who==frame.me then
        for t in pairs(frame.ctx.borders.border) do
            if s:tile_owner(t)==who then
                local x=t%m.W
                for _,n in ipairs({x>0 and t-1 or -1,x<m.W-1 and t+1 or -1,t-m.W,t+m.W}) do
                    if valid(m,n) and s:tile_owner(n)==target and m:is_contestable(n) and not s:has_fallout(n) then return n end
                end
            end
        end
        return nil
    end
    -- Other nations' border sets are not given by the client. Use bounded exact
    -- tile checks around their public centers; lack of evidence means no proposal.
    local anchors={};local p,q=s.owners[who],s.owners[target]
    for _,o in ipairs({p or {},q or {}}) do
        if valid(m,o.spawn_tile) then table.insert(anchors,o.spawn_tile) end
        if valid(m,o.label_tile) and o.label_tile~=o.spawn_tile then table.insert(anchors,o.label_tile) end
    end
    local r=math.min(6,math.max(1,math.ceil(18/(m.k_lin or 1))))
    for _,anchor in ipairs(anchors) do
        local x,y=anchor%m.W,anchor//m.W
        for yy=math.max(0,y-r),math.min(m.H-1,y+r) do for xx=math.max(0,x-r),math.min(m.W-1,x+r) do
            local t=yy*m.W+xx
            if s:tile_owner(t)==target and m:is_contestable(t) and not s:has_fallout(t) and s:borders_tile(who,t) then return t end
        end end
    end
end
function Coalition.support(frame,partner,target)
    local s,me=frame.state,frame.me;local p,q=s.owners[partner],s.owners[target]
    local function no(reason) return nil,reason end
    if partner==me or partner==target or not p or not q or not p.alive or not q.alive or not s:are_allies(me,partner) then return no('partner or target is no longer eligible') end
    if protected(s,me,target) or s:are_allies(partner,target) or sameTeam(s,partner,target)
        or s:has_request(me,target) or s:has_request(partner,target) or s:has_request(target,partner) then return no('target is protected or partnered with a participant') end
    if (p.traitor_until or 0)>s.tick or (frame.info.traitor_until or 0)>s.tick then return no('traitor vulnerability or unreliable recipient') end
    if type(s.alliance_info)=='function' and not sameTeam(s,me,partner) then
        local treaty=s:alliance_info(me,partner)
        if treaty and treaty.ticks_left<450 then return no('partnership expires too soon') end
    end
    local incoming,committed,between=Coalition.armies(s)
    local home=math.max(0,frame.info.troops or 0);local attack=between[partner*1024+target] or 0
    if (incoming[me] or 0)>home*.2 or (between[partner*1024+me] or 0)>0 then return no('our home defense is under too much pressure') end
    local counter=(between[target*1024+me] or 0)+(between[target*1024+partner] or 0)>math.max(1,q.troops or 0)*1.5
    if attack<=0 and not (counter and Coalition.frontier(frame,partner,target)) then return no('no observed attack or reachable counter opportunity') end
    local allyHome=math.max(0,p.troops or 0);local room=math.max(0,(p.max_troops or 0)-allyHome)
    local allySpare=math.max(0,allyHome-math.max((p.max_troops or 0)*.42,(incoming[partner] or 0)*1.5))
    local need=math.ceil(math.max(0,(q.troops or 0)*1.35+growth(q,3)+(incoming[partner] or 0)*.5-attack-allySpare))
    local reserve=math.max(home*.75,math.ceil((frame.info.max_troops or 0)*.42),(incoming[me] or 0)*2)
    local amount=math.min(need,math.floor(home*.08),math.floor(home-reserve),math.floor(room))
    if amount<100 or amount<need then return no('grant cannot close the estimated funding gap while retaining reserves') end
    if not sameTeam(s,me,partner) and not (s.bot_friend_guard or {})[partner] and allyHome+amount>(home-amount)*1.5 then return no('gift would create a dominant treaty neighbor') end
    -- A target backed by a much stronger third party is not a cheap finishing job.
    local backing=0
    for id,o in pairs(s.owners) do
        if id~=me and id~=partner and id~=target and o.alive and s:are_allies(target,id)
            and not s:are_allies(me,id) and not s:are_allies(partner,id) then backing+=o.troops or 0 end
    end
    if backing>home+allyHome then return no('target coalition outweighs the supporting pair') end
    return {partner=partner,target=target,amount=amount,reserve=reserve,need=need,
        commitment=attack,target_land=q.tiles or 0,mode=counter and 'counterattack' or 'finish_attack',
        score=(counter and 7 or 5.5)+math.min(1,attack/math.max(1,q.troops or 0)),
        uncertainty='Recipient controls its own army; a grant cannot force an attack or guarantee elimination'}
end
function Coalition.betrayal(frame,target,tile,followup)
    local s,m,me=frame.state,frame.map,frame.me;local p=s.owners[target]
    local function no(reason) return nil,reason end
    if not p or not p.alive or target==me or sameTeam(s,me,target) or (s.bot_friend_guard or {})[target] then return no('target is a teammate, protected friend or unavailable') end
    if followup then
        if s:are_allies(me,target) then return no('waiting for alliance break confirmation') end
    elseif not s:are_allies(me,target) or (frame.info.traitor_until or 0)>s.tick then return no('no treaty to end or already under the traitor penalty') end
    if not valid(m,tile) or s:tile_owner(tile)~=target or not s:borders_tile(me,tile)
        or not m:is_contestable(tile) or s:has_fallout(tile) or Weapons.hazard(s,tile,0,3) then return no('no current safe land frontier') end
    if s:has_request(me,target) then return no('our peace proposal is still pending') end
    local incoming,committed,between=Coalition.armies(s)
    local home=math.max(0,frame.info.troops or 0)
    if (incoming[me] or 0)>0 then return no('cannot opportunistically betray during an invasion') end
    for _,a in pairs(s.attacks) do
        if a.attacker==me and a.target>0 and not a.retreating and (not followup or a.target~=target) then return no('another war is active') end
    end
    for _,alert in ipairs(Weapons.alerts(s,me)) do if alert.hits_us then return no('home territory has a missile warning') end end
    for _,u in pairs(s.units or {}) do
        if u.owner==me and u.kind==0 then return no('an existing expedition could create another front') end
        if u.kind==2 and u.owner~=me and (u.owner==target or s:are_allies(target,u.owner)) and (u.hp or 1)>0 then
            local path=u.path or {};local index=math.clamp(math.floor(math.max(0,s.tick-(u.start_tick or s.tick))*100/math.max(1,u.ticks_per_tile_x100 or 100))+1,1,math.max(1,#path))
            local position=path[index] or u.patrol_tile
            if valid(m,position) then
                local near=valid(m,frame.info.label_tile) and m.dist2(position,frame.info.label_tile)*(m.k_lin or 1)^2<180^2
                for _,b in pairs(s.structures) do if b.owner==me and m.dist2(position,b.tile)*(m.k_lin or 1)^2<180^2 then near=true;break end end
                if near then return no('target or coalition warships can threaten our economic home') end
            end
        end
    end
    local victim=math.max(0,p.troops or 0)
    local need=math.ceil(victim*1.5+growth(p,3))
    local reserve=math.max(home*.8,math.ceil((frame.info.max_troops or 0)*.42))
    local existing=between[me*1024+target] or 0
    local amount=math.max(0,need-existing)
    if victim>home*.1 or need>home*.15 or home-amount<reserve then return no('capture would commit too much of our army') end
    if (p.tiles or 0)>math.max(200,(frame.info.tiles or 0)*.8) then return no('target is too large for a bounded raid') end
    local nearby={};local work=0
    for t in pairs(frame.ctx.borders.border) do
        work+=1;if work>8192 then return no('frontier coverage is insufficient for a low-risk assessment') end
        local x=t%m.W
        if s:tile_owner(t)==me then for _,n in ipairs({x>0 and t-1 or -1,x<m.W-1 and t+1 or -1,t-m.W,t+m.W}) do
            if valid(m,n) then nearby[s:tile_owner(n)]=true end
        end end
    end
    local exposure=victim
    for id,o in pairs(s.owners) do
        if id~=me and id~=target and o.alive then
            local center=o.label_tile or o.spawn_tile
            local close=nearby[id] or valid(m,center) and m.dist2(tile,center)*(m.k_lin or 1)^2<150^2
            if close and (not s:are_allies(me,id) or s:are_allies(target,id)) then exposure+=o.troops or 0 end
        end
    end
    -- Any treaty break marks us as a traitor: defense is halved for 300 ticks.
    if (home-amount)*.5<exposure*2 then return no('half-defense window is exposed to retaliation or a coalition') end
    local assetValue,trade=0,0
    for _,b in pairs(s.structures) do
        if b.owner==target then
            if b.kind==5 and (b.active_tick or 0)<=s.tick+300 and (p.gold or 0)>=750000 then return no('target can retaliate with missiles during our vulnerability window') end
            if b.kind==3 and (b.active_tick or 0)<=s.tick and m.dist2(tile,b.tile)*(m.k_lin or 1)^2<80^2 then return no('fortified frontier is outside the cheap-capture estimate') end
            if m.dist2(tile,b.tile)*(m.k_lin or 1)^2<=60^2 then
                assetValue+=(({[0]=125000,[1]=125000,[2]=125000,[3]=0,[4]=1500000,[5]=1000000})[b.kind] or 0)*(b.level or 1)
            end
            if b.kind==1 then trade=125000 end
        end
    end
    local treasury=math.max(0,p.gold or 0)*(p.kind==2 and .5 or 1)
    -- Treasury is counted only for a small target; it is not a guaranteed raid payout.
    local conquest=(p.tiles or 0)<=math.max(100,(frame.info.tiles or 0)*.25) and treasury or 0
    local reward=assetValue+conquest
    if reward<100000+trade*2 or reward<need*15 then return no('visible capture value does not compensate for army, treaty and trade costs') end
    return {target=target,tile=tile,amount=amount,reserve=reserve,need=need,exposure=exposure,
        estimated_assets=assetValue,estimated_conquest_gold=conquest,estimated_value=reward,
        defense_multiplier=.5,vulnerability_ticks=300,score=6+math.min(2,reward/1000000),
        uncertainty='Visible-state estimate; hidden intentions, future orders and credited conquests are unknown'}
end
return Coalition
