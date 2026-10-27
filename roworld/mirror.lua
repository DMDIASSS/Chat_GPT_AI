-- Read-only multiplayer observations. This does not run or modify game physics.
local Mirror={}
local Weapons = require("./weapons")
local State={};State.__index=State
local KINDS={city=0,port=1,factory=2,defense=3,sam=4,silo=5}
local function adjacent(map,t,fn)
    local x=t%map.W
    if x>0 then fn(t-1) end;if x<map.W-1 then fn(t+1) end
    if t>=map.W then fn(t-map.W) end;if t<map.N-map.W then fn(t+map.W) end
end
local function key(a,b) return math.min(a,b)*1024+math.max(a,b) end
function State:tile_owner(t) assert(t>=0 and t<self.map.N);return buffer.readi32(self.owner,t*4) end
function State:has_fallout(t) return bit32.band(buffer.readu8(self.flags,t),1)~=0 end
function State:owner_name(id) return self.owners[id] and self.owners[id].name or "Unknown" end
function State:are_allies(a,b)
    if a==0 or b==0 or a==b then return false end
    local x,y=self.owners[a],self.owners[b]
    return self.alliances[key(a,b)]==true or (x and y and x.team>0 and x.team==y.team) or false
end
function State:has_request(a,b) return self.requests[a*1024+b]~=nil end
function State:has_alliance(a,b) return self.alliances[key(a,b)]==true end
function State:alliance_info(a,b)
    if not self:has_alliance(a,b) then return nil end
    local k=key(a,b);local expires=self.alliance_expires[k] or -1;local flags=self.alliance_ext[k] or 0
    local mine=a<b and 1 or 2;local window=expires>=self.tick and expires<=self.tick+300
    local meAsked=bit32.band(flags,mine)~=0
    return {expires_at=expires,ticks_left=math.max(0,expires-self.tick),in_window=window,
        me_asked=meAsked,other_asked=bit32.band(flags,3-mine)~=0,
        can_extend=window and not meAsked and self.owners[a] and self.owners[a].alive and self.owners[b] and self.owners[b].alive or false}
end
function State:borders_tile(id,t)
    local found=false;adjacent(self.map,t,function(n) if self:tile_owner(n)==id then found=true end end);return found
end
function State:recheck(t)
    if self:tile_owner(t)~=self.local_owner then self.border[t]=nil;return end
    local border=false;adjacent(self.map,t,function(n) if self:tile_owner(n)~=self.local_owner then border=true end end)
    self.border[t]=border or nil
end
local function owner(row)
    return {id=row[1],name=tostring(row[2]),kind=row[4] or 0,team=row[5] or 0,alive=row[6]==true,
        troops=row[8] or 0,gold=row[9] or 0,max_troops=row[10] or 0,income=row[11] or 0,
        traitor_until=row[12] or 0,spawn_tile=row[13] or -1,spawned=(row[13] or -1)>=0,label_tile=row[13] or -1,tiles=0}
end
local function unit(s,row,offset)
    offset=offset or 0
    local u={uid=row[offset+1],kind=row[offset+2],owner=row[offset+3],path=row[offset+4] or {},
        start_tick=row[offset+5] or 0,ticks_per_tile_x100=row[offset+6] or 100,troops=row[offset+7] or 0,
        hp=row[offset+8] or 0,max_hp=row[offset+9] or 0,veterancy=row[offset+10] or 0,
        state=row[offset+11] or 0,patrol_tile=row[offset+12] or -1}
    s.units[u.uid]=u;return u
end
local function structure(s,row,offset)
    offset=offset or 0
    local b={sid=row[offset+1],kind=row[offset+2],owner=row[offset+3],tile=row[offset+4],
        level=row[offset+5] or 1,active_tick=row[offset+6] or 0,shots=row[offset+7] or {}}
    s.structures[b.sid]=b;return b
end
local function nuke(s,row,offset)
    offset=offset or 0
    local n={uid=row[offset+1],kind=row[offset+2],owner=row[offset+3],from_tile=row[offset+4],
        to_tile=row[offset+5],launch_tick=row[offset+6],flight_ticks=row[offset+7]}
    s.nukes[n.uid]=n;return n
end
local function attack(s,row,offset)
    offset=offset or 0
    s.attacks[row[offset+1]]={aid=row[offset+1],attacker=row[offset+2],target=row[offset+3],
        troops=row[offset+4],anchor_tile=row[offset+5],retreating=row[offset+6]==true}
end
function Mirror.map(meta,raw,snapshot,yield)
    yield=yield or function() end
    local w,h=snapshot.map_w or meta.width,snapshot.map_h or meta.height
    assert(type(w)=="number" and type(h)=="number" and w>0 and h>0 and w*h<=16777216,"Invalid snapshot dimensions")
    assert(buffer.len(raw)==meta.width*meta.height,"Invalid terrain length")
    local map={W=w,H=h,N=w*h,k_lin=(meta.k_lin or 1)*(meta.width/w)}
    map.bytes=buffer.create(map.N)
    local land,coast=buffer.create(map.N*4),buffer.create(map.N*4)
    local lands,coasts=0,0
    function map.dist2(a,b) return (a%w-b%w)^2+(a//w-b//w)^2 end
    function map:is_contestable(t) return t>=0 and t<self.N and buffer.readu8(self.bytes,t)>=128 and buffer.readu8(self.bytes,t)~=159 end
    function map:is_water(t) return t>=0 and t<self.N and buffer.readu8(self.bytes,t)<128 end
    function map:is_coastal(t)
        if not self:is_contestable(t) then return false end
        local water=false;adjacent(self,t,function(n) if self:is_water(n) then water=true end end);return water
    end
    for t=0,map.N-1 do
        local x,y=t%w,t//w
        local source=math.min(meta.height-1,math.floor((y+.5)*meta.height/h))*meta.width+math.min(meta.width-1,math.floor((x+.5)*meta.width/w))
        buffer.writeu8(map.bytes,t,buffer.readu8(raw,source))
        if t%32768==0 then yield() end
    end
    for t=0,map.N-1 do
        if map:is_contestable(t) then
            buffer.writei32(land,lands*4,t);lands+=1
            if map:is_coastal(t) then buffer.writei32(coast,coasts*4,t);coasts+=1 end
        end
        if t%32768==0 then yield() end
    end
    map.land_list,map.coast_list=buffer.create(lands*4),buffer.create(coasts*4)
    buffer.copy(map.land_list,0,land,0,lands*4);buffer.copy(map.coast_list,0,coast,0,coasts*4)
    -- Four-neighbour water components, computed once per terrain download.
    -- Match the game's left/right/up/down coastal-body convention.
    map.water_body=buffer.create(map.N*4)
    local queue=buffer.create(map.N*4);local body,work=0,0
    for t=0,map.N-1 do
        if map:is_water(t) and buffer.readu32(map.water_body,t*4)==0 then
            body+=1;local head,tail=0,1
            buffer.writeu32(queue,0,t);buffer.writeu32(map.water_body,t*4,body)
            while head<tail do
                local p=buffer.readu32(queue,head*4);head+=1
                adjacent(map,p,function(n)
                    if map:is_water(n) and buffer.readu32(map.water_body,n*4)==0 then
                        buffer.writeu32(map.water_body,n*4,body);buffer.writeu32(queue,tail*4,n);tail+=1
                    end
                end)
                work+=1;if work%32768==0 then yield() end
            end
        end
        if t%32768==0 then yield() end
    end
    function map:water_body_of(t)
        return t>=0 and t<self.N and buffer.readu32(self.water_body,t*4) or 0
    end
    function map:coast_body_of(t)
        local found=0
        adjacent(self,t,function(n) if found==0 then found=self:water_body_of(n) end end)
        return found
    end
    return map
end
function Mirror.snapshot(data,map,me,yield)
    assert(typeof(data.owner)=="buffer" and buffer.len(data.owner)==map.N*4,"Incomplete ownership snapshot")
    assert(typeof(data.flags)=="buffer" and buffer.len(data.flags)==map.N,"Incomplete fallout snapshot")
    local s=setmetatable({map=map,owner=data.owner,flags=data.flags,owners={},structures={},attacks={},nukes={},units={},
        alliances={},alliance_expires={},alliance_ext={},playing_since=data.playing_since or -1,
        requests={},built={},border={},alliance_events={},alliance_seq=0,fallout_count=0,mirvs_launched=data.mirvs_launched or 0,
        local_owner=me,tick=data.t or 0,phase=data.phase or 0,loaded=false,
        rules={STRUCT_MIN_DIST=15/map.k_lin,MAX_BOATS_PLAYER=10}},State)
    for _,row in ipairs(data.owners or {}) do s.owners[row[1]]=owner(row) end
    for _,row in ipairs(data.structs or {}) do structure(s,row) end
    for _,row in ipairs(data.attacks or {}) do attack(s,row) end
    for _,row in ipairs(data.units or {}) do unit(s,row) end
    for _,row in ipairs(data.nukes or {}) do nuke(s,row) end
    for _,row in ipairs(data.allies or {}) do
        local k=key(row[1],row[2]);s.alliances[k]=true;s.alliance_expires[k]=row[3];s.alliance_ext[k]=row[4] or 0
    end
    for _,row in ipairs(data.requests or {}) do s.requests[row[1]*1024+row[2]]=row[3] or s.tick end
    for _,row in ipairs(data.built or {}) do
        s.built[row[1]]={};for i=0,15 do s.built[row[1]][i]=row[i+2] or 0 end
    end
    for t=0,map.N-1 do
        if s:has_fallout(t) then s.fallout_count+=1 end
        local id=s:tile_owner(t);local info=s.owners[id]
        if info then info.tiles+=1;if info.label_tile<0 then info.label_tile=t end end
        if id==me then s:recheck(t) end
        if yield and t%32768==0 then yield() end
    end
    assert(s.owners[me]~=nil,"Snapshot has no local nation")
    s.loaded=true;return s
end
local function built(s,id,kind)
    s.built[id]=s.built[id] or {};s.built[id][kind]=(s.built[id][kind] or 0)+1
end
function Mirror.delta(s,d)
    if d.t and d.t<=s.tick then return end
    assert(type(d.t)=="number","Delta has no authoritative tick")
    -- Reliable ordered RemoteEvents may coalesce multiple simulation ticks.
    -- A larger tick increment is not evidence of missing ownership updates.
    s.tick=d.t
    for _,entry in ipairs(d.tiles or {}) do
        local tile,id=entry//1024,entry%1024;assert(tile>=0 and tile<s.map.N,"Invalid ownership update")
        local old=s:tile_owner(tile)
        if old~=id then
            if s.owners[old] then s.owners[old].tiles-=1 end
            if s.owners[id] then s.owners[id].tiles+=1 end
            buffer.writei32(s.owner,tile*4,id);s:recheck(tile);adjacent(s.map,tile,function(n) s:recheck(n) end)
        end
    end
    for _,entry in ipairs(d.flags or {}) do
        local tile=entry//256;assert(tile>=0 and tile<s.map.N)
        local before=s:has_fallout(tile);buffer.writeu8(s.flags,tile,entry%256)
        if before~=s:has_fallout(tile) then s.fallout_count+=before and -1 or 1 end
    end
    for i=1,#(d.stats or {}),6 do
        local row=d.stats;local info=s.owners[row[i]]
        if info then info.troops=row[i+2];info.gold=row[i+3];info.max_troops=row[i+4];info.income=row[i+5] end
    end
    for _,e in ipairs(d.ev or {}) do
        local kind,id=e[1],e[2]
        if kind==0 then s.owners[id]={id=id,name=tostring(e[3]),kind=e[5],team=e[6] or 0,alive=true,spawned=false,spawn_tile=-1,label_tile=-1,tiles=0,troops=0,gold=0,max_troops=0}
        elseif kind==1 and s.owners[id] then s.owners[id].alive=false
        elseif kind==2 then s.phase=id;if id==1 and s.playing_since<0 then s.playing_since=s.tick end
        elseif kind==3 and s.owners[id] then local info=s.owners[id];info.spawned=true;info.spawn_tile=e[3];info.label_tile=e[3]
        elseif kind==4 then local b=structure(s,e,1);built(s,b.owner,b.kind)
        elseif kind==5 and s.structures[id] then s.structures[id].owner=e[3]
        elseif kind==6 then s.structures[id]=nil
        elseif kind==9 then local u=unit(s,e,1);if u.kind==2 then built(s,u.owner,15) end
        elseif kind==10 and s.units[id] then s.units[id].path={e[3]};s.units[id].start_tick=s.tick
        elseif kind==11 then s.units[id]=nil
        elseif kind==12 then local n=nuke(s,e,1);if n.kind==2 then s.mirvs_launched+=1 end
        elseif kind==13 then s.nukes[id]=nil
        elseif kind==14 then attack(s,e,1)
        elseif kind==15 then s.attacks[id]=nil
        elseif kind==16 then s.requests[id*1024+e[3]]=e[4] or s.tick
        elseif kind==17 then
            local k=key(id,e[3]);s.alliances[k]=true;s.alliance_expires[k]=e[4] or s.tick+3000;s.alliance_ext[k]=0
            s.requests[id*1024+e[3]]=nil;s.requests[e[3]*1024+id]=nil
        elseif kind==18 then
            s.alliances[key(id,e[3])]=nil;s.alliance_seq+=1
            s.alliance_expires[key(id,e[3])]=nil;s.alliance_ext[key(id,e[3])]=nil
            table.insert(s.alliance_events,{seq=s.alliance_seq,a=id,b=e[3],breaker=e[4] or 0,expired=e[5]==true,tick=s.tick})
            if #s.alliance_events>64 then table.remove(s.alliance_events,1) end
        elseif kind==20 then s.phase=2
        elseif kind==21 then s.requests[id*1024+e[3]]=nil
        elseif kind==22 and s.owners[id] then s.owners[id].traitor_until=e[3]
        elseif kind==23 and s.structures[id] then
            local b=s.structures[id];local added=e[3]-b.level
            for _=1,math.max(0,added) do built(s,b.owner,b.kind) end
            b.level,b.active_tick=e[3],e[4]
        elseif kind==25 and s.units[id] then s.units[id].hp=e[3];s.units[id].max_hp=e[4]
        elseif kind==26 and s.units[id] then s.units[id].veterancy=e[3]
        elseif kind==27 and s.units[id] then s.units[id].state=e[3];s.units[id].patrol_tile=e[4]
        elseif kind==28 and s.units[id] then
            local u=s.units[id];u.path=e[3];u.start_tick=e[4];u.ticks_per_tile_x100=e[5]
        elseif kind==29 and s.nukes[e[3]] then s.nukes[e[3]].sam_sid=id
        elseif kind==30 and s:has_alliance(id,e[3]) then
            local k=key(id,e[3]);s.alliance_expires[k]=e[4];s.alliance_ext[k]=e[5] or 0
        elseif kind==32 and s.structures[id] then s.structures[id].shots=e[3]
        end
    end
end
function Mirror.context(session)
    local ctx={session=session,state=session.state}
    function ctx:in_match() return self.session.connected and self.state.loaded end
    local borders={border=session.state.border}
    function borders:has_coast()
        for tile in pairs(self.border) do if ctx.state.map:is_coastal(tile) then return true end end
        return false
    end
    function borders:can_reach_by_sea(tile)
        local map=ctx.state.map
        if not map:is_coastal(tile) then return false end
        local body=map:coast_body_of(tile)
        if self.bodyTick~=ctx.state.tick then
            self.bodyTick=ctx.state.tick;self.bodies={}
            for t in pairs(self.border) do
                if map:is_coastal(t) then self.bodies[map:coast_body_of(t)]=true end
            end
        end
        return body>0 and self.bodies[body]==true
    end
    ctx.borders=borders
    local rules={}
    function rules:transports()
        local count=0;for _,u in pairs(ctx.state.units) do if u.owner==ctx.state.local_owner and u.kind==0 then count+=1 end end
        return count
    end
    function rules:cost(kind)
        local s,id=ctx.state,ctx.state.local_owner;local k=KINDS[kind]
        if Weapons.kinds[kind]~=nil then return Weapons.cost(s,kind) end
        if kind=="warship" then
            local count=0;for _,u in pairs(s.units) do if u.owner==id and u.kind==2 then count+=1 end end
            return math.min(1000000,(math.min(count,(s.built[id] or {})[15] or 0)+1)*250000)
        end
        if k==nil then return math.huge end
        local kinds=(kind=="port" or kind=="factory") and {1,2} or {k};local n=0
        for _,wanted in ipairs(kinds) do
            local levels=0;for _,b in pairs(s.structures) do if b.owner==id and b.kind==wanted then levels+=b.level end end
            n+=math.min(levels,(s.built[id] or {})[wanted] or 0)
        end
        if k<=2 then return math.min(1000000,125000*2^math.min(n,4)) end
        if k==3 then return math.min(250000,(n+1)*50000) end
        if k==4 then return math.min(3000000,(n+1)*1500000) end
        return 1000000
    end
    function rules:availability(kind)
        local supported=KINDS[kind]~=nil or kind=="warship" or Weapons.kinds[kind]~=nil
        local info=ctx.state.owners[ctx.state.local_owner]
        local launcher=Weapons.kinds[kind]==nil or #Weapons.launchers(ctx.state,ctx.state.local_owner,0)>0
        local port=kind~="warship"
        if not port then for _,b in pairs(ctx.state.structures) do
            if b.owner==ctx.state.local_owner and b.kind==1 and b.active_tick<=ctx.state.tick then port=true;break end
        end end
        return {ok=supported and info.alive and info.spawned and ctx.state.phase==1 and info.gold>=self:cost(kind)
            and launcher and port and (kind~="port" or borders:has_coast()),cost=self:cost(kind)}
    end
    function rules:placement(kind,tile)
        local s,id,map=ctx.state,ctx.state.local_owner,ctx.state.map
        local result={ok=false,tile=tile}
        if Weapons.kinds[kind]~=nil then
            if not self:availability(kind).ok or tile<0 or tile>=map.N then return result end
            local target=s:tile_owner(tile)
            result.ok=target>0 and target~=id and not s:are_allies(id,target)
            return result
        end
        if kind=="warship" then
            if not self:availability(kind).ok or not map:is_water(tile) then return result end
            for _,b in pairs(s.structures) do
                if b.owner==id and b.kind==1 and b.active_tick<=s.tick
                    and map:coast_body_of(b.tile)==map:water_body_of(tile) then result.ok=true;return result end
            end
            return result
        end
        if not self:availability(kind).ok or s:tile_owner(tile)~=id or not map:is_contestable(tile) then return result end
        if kind=="port" and not map:is_coastal(tile) then return result end
        for _,b in pairs(s.structures) do
            if map.dist2(tile,b.tile)<s.rules.STRUCT_MIN_DIST^2 then
                if b.owner==id and b.kind==KINDS[kind] and b.kind~=3 and b.active_tick<=s.tick then
                    return {ok=true,tile=b.tile,upgrade=true}
                end
                return result
            end
        end
        result.ok=true;return result
    end
    ctx.rules=rules;return ctx
end
return Mirror
