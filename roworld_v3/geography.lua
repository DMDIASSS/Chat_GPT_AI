-- Bounded, current-state geometry. Every proposed destination is checked again at send time.
local Geography = {}
local Weapons = require('./shared/weapons')
function Geography.valid(m,t) return type(t)=='number' and t%1==0 and t>=0 and t<m.N end
function Geography.neighbors(m,t,fn)
    local x=t%m.W
    if x>0 then fn(t-1) end;if x<m.W-1 then fn(t+1) end
    if t>=m.W then fn(t-m.W) end;if t<m.N-m.W then fn(t+m.W) end
end
function Geography.magnitude(m,t)
    local bytes=m.bytes or m.tile_bytes or m.terr
    return bytes and bit32.band(buffer.readu8(bytes,t),31) or 0
end
function Geography.sample(m,list,index)
    local b=m[list]
    if typeof(b)~='buffer' or buffer.len(b)<4 then return nil end
    return buffer.readi32(b,(index%(buffer.len(b)//4))*4)
end
function Geography.anchor(frame,old)
    local s,m,me=frame.state,frame.map,frame.me
    -- Retain the original economic home while it remains ours. Recenter only after loss.
    if Geography.valid(m,old) and s:tile_owner(old)==me then return old end
    local best,weight=nil,-1
    for _,b in pairs(s.structures) do
        if b.owner==me then
            local value=({[0]=4,[1]=3,[2]=5,[3]=0,[4]=2,[5]=1})[b.kind] or 0
            value*=b.level or 1
            if value>weight or value==weight and (not best or b.tile<best) then best,weight=b.tile,value end
        end
    end
    if best then return best end
    for _,t in ipairs({frame.info.spawn_tile or -1,frame.info.label_tile or -1}) do
        if Geography.valid(m,t) and s:tile_owner(t)==me then return t end
    end
    local candidate
    for t in pairs(frame.ctx.borders.border) do if s:tile_owner(t)==me and (not candidate or t<candidate) then candidate=t end end
    return candidate or 0
end
function Geography.fronts(frame,cursor)
    local s,m,me=frame.state,frame.map,frame.me
    local border=frame.ctx.borders.border
    local keys={};for t in pairs(border) do table.insert(keys,t) end;table.sort(keys)
    local count=#keys;local groups={};local near={};local sites={};local seen={}
    local budget=math.min(count,4096);local offset=count>0 and (cursor or 0)%count or 0
    for i=1,budget do
        local t=keys[(offset+i-1)%count+1]
        if s:tile_owner(t)==me then
            if #sites<64 then table.insert(sites,t) end
            Geography.neighbors(m,t,function(n)
                local id=s:tile_owner(n)
                if id>0 and id~=me then near[id]=true end
                if id~=me and m:is_contestable(n) and not s:has_fallout(n) and not seen[n] then
                    seen[n]=true
                    local g=groups[id];if not g then g={id=id,tile=n,front=0,tiles={}};groups[id]=g end
                    g.front+=1
                    if #g.tiles<8 then table.insert(g.tiles,n) end
                    if n<g.tile then g.tile=n end
                end
            end)
        end
    end
    return groups,near,sites,offset+budget,count>0 and budget/count or 1
end
function Geography.safe(frame,t,kind)
    local s,m=frame.state,frame.map
    local margin=(kind=='defense' or kind=='sam') and 8 or 18
    if not Geography.valid(m,t) or s:tile_owner(t)~=frame.me or s:has_fallout(t)
        or Weapons.hazard(s,t,margin) then return false,margin end
    local r=math.ceil(margin/(m.k_lin or 1));local x,y=t%m.W,t//m.W
    for yy=math.max(0,y-r),math.min(m.H-1,y+r) do
        for xx=math.max(0,x-r),math.min(m.W-1,x+r) do
            if (xx-x)^2+(yy-y)^2<=r*r then
                local p=yy*m.W+xx
                if s:has_fallout(p) or s:tile_owner(p)~=frame.me and (m:is_contestable(p) or kind~='port') then
                    return false,margin
                end
            end
        end
    end
    return true,margin
end
function Geography.sites(frame,anchor,frontSites)
    local m=frame.map;local seen={};local sites={}
    local function add(t)
        if Geography.valid(m,t) and not seen[t] and frame.state:tile_owner(t)==frame.me then
            seen[t]=true;table.insert(sites,t)
        end
    end
    add(anchor)
    local spacing=math.max(1,math.ceil(12/(m.k_lin or 1)))
    local x,y=anchor%m.W,anchor//m.W
    for dy=-3,3 do for dx=-3,3 do
        local xx,yy=x+dx*spacing,y+dy*spacing
        if xx>=0 and yy>=0 and xx<m.W and yy<m.H then add(yy*m.W+xx) end
    end end
    for _,b in pairs(frame.state.structures) do if b.owner==frame.me then add(b.tile) end end
    for _,t in ipairs(frontSites or {}) do if m:is_coastal(t) then add(t) end end
    -- The original spawn can remain owned while its neighborhood becomes unsafe.
    -- Search other holdings too, rather than silently saving forever at that point.
    for i=1,64 do add(Geography.sample(m,'land_list',(frame.state.tick or 0)*31337+i*104729)) end
    return sites
end
function Geography.landing(frame,t,anchor,escape)
    local s,m=frame.state,frame.map
    if s:borders_tile(frame.me,t) then return nil end
    local x,y=anchor%m.W,anchor//m.W;local dx,dy=t%m.W-x,t//m.W-y
    local water=false;local samples=math.min(64,math.max(math.abs(dx),math.abs(dy)))
    for i=1,samples do
        local p=math.floor(y+dy*i/samples)*m.W+math.floor(x+dx*i/samples)
        local wet=type(m.is_water)=='function' and m:is_water(p) or m.water and m.water[p]
        if wet then water=true;break end
    end
    if not water and not escape then return nil end
    local room=0;local tx,ty=t%m.W,t//m.W
    local r=math.max(1,math.ceil(20/(m.k_lin or 1)))
    for _,d in ipairs({{1,0},{-1,0},{0,1},{0,-1},{1,1},{1,-1},{-1,1},{-1,-1}}) do
        local xx,yy=tx+d[1]*r,ty+d[2]*r
        if xx>=0 and yy>=0 and xx<m.W and yy<m.H then
            local p=yy*m.W+xx
            if m:is_contestable(p) and s:tile_owner(p)==0 and not s:has_fallout(p) then room+=1 end
        end
    end
    local danger=0
    for id,p in pairs(s.owners) do
        local center=p.label_tile or p.spawn_tile
        if id~=frame.me and p.alive and p.kind==2 and not s:are_allies(frame.me,id) and Geography.valid(m,center) then
            local distance=math.sqrt(m.dist2(t,center))*(m.k_lin or 1)
            if distance<120 then danger+=math.max(0,1-distance/120)*(p.troops or 0)/math.max(1,frame.info.troops or 0) end
        end
    end
    if danger>.75 then return nil end
    return room*.15-danger*4+(water and .4 or 0)
end
function Geography.spawnScore(frame,t)
    local s,m=frame.state,frame.map
    if not Geography.valid(m,t) or not m:is_contestable(t) or s:has_fallout(t) then return nil end
    local owner=s:tile_owner(t)
    if owner~=0 and not (s.phase==0 and owner==frame.me and t==frame.info.spawn_tile) then return nil end
    local score,open,water,players=0,0,0,0
    local r=math.max(2,math.ceil(40/(m.k_lin or 1)));local x,y=t%m.W,t//m.W
    for dy=-2,2 do for dx=-2,2 do
        local xx,yy=x+dx*r/2,y+dy*r/2
        if xx>=0 and yy>=0 and xx<m.W and yy<m.H then
            local p=math.floor(yy)*m.W+math.floor(xx)
            if m:is_contestable(p) then
                if s:tile_owner(p)==0 then open+=1;score+=1-Geography.magnitude(m,p)/40 end
            else water+=1 end
        end
    end end
    local nearest=math.huge
    for id,o in pairs(s.owners) do
        local p=o.spawn_tile
        if id~=frame.me and o.alive and Geography.valid(m,p) then
            local d=math.sqrt(m.dist2(t,p))*(m.k_lin or 1)
            if o.kind==2 then
                nearest=math.min(nearest,d)
                if d<140 then players+=1;score-=(140-d)*.14 end
            elseif o.kind==1 and d<100 then score+=1 end
        end
    end
    score+=math.min(3,water*.3)+math.min(200,nearest)*.03
    if open<8 then score-=20 end
    return score,{neutral_samples=open,water_samples=water,nearby_humans=players,nearest_human=nearest<math.huge and nearest or -1}
end
return Geography
