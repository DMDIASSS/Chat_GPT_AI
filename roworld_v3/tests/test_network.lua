local Wire=require("../shared/wire")
local Mirror=require("../shared/mirror")
local Network=require("../shared/network")
local Adapter=require("../shared/adapter")
local Policy=require("../agent")
local vectors=require("./wire_vectors")
local tests=0
local function test(name,fn) fn();tests+=1;print("PASS",name) end
local function bytes(hex)
    local b=buffer.create(#hex/2)
    for i=1,#hex,2 do buffer.writeu8(b,(i-1)/2,assert(tonumber(hex:sub(i,i+1),16))) end
    return b
end
local function hex(b)
    local result={};for i=0,buffer.len(b)-1 do table.insert(result,string.format("%02x",buffer.readu8(b,i))) end
    return table.concat(result)
end
local function decoded() return Wire.snapshot(bytes(vectors.snapshot)) end
local function map()
    local raw=buffer.create(768);buffer.fill(raw,0,128)
    for y=0,23 do buffer.writeu8(raw,y*32+20,0) end
    return Mirror.map({width=32,height=24,k_lin=2},raw,decoded()),raw
end

test("decodes actual game-encoded synthetic snapshot and delta",function()
    local s=decoded();assert(s.t==10 and s.map_w==32 and s.map_h==24)
    assert(buffer.len(s.owner)==3072 and s.owners[1][2]=="Fixture")
    local d=Wire.delta(bytes(vectors.delta))
    assert(d.t==15 and d.tiles[1]==393*1024+2 and d.stats[3]==45000)
    assert(d.ev[2][1]==14 and d.ev[2][7]==false)
end)
test("encodes orders byte-for-byte like the original game protocol",function()
    local intents={{type="spawn",tile=0},{type="attack",tile=393,ratio=.1},
        {type="build",kind="city",tile=389},{type="retreat",attack_id=9},{type="ally_reply",target=2,accept=true}}
    for i,intent in ipairs(intents) do assert(hex(Wire.intent(intent))==vectors["intent"..i]) end
end)
test("rejects truncated and corrupt envelopes before enabling the bot",function()
    assert(not pcall(Wire.snapshot,buffer.create(1)))
    assert(not pcall(Wire.snapshot,bytes("00020d01010000")))
    local b=bytes(vectors.snapshot)
    local short=buffer.create(buffer.len(b)-1);buffer.copy(short,0,b,0,buffer.len(short))
    assert(not pcall(Wire.snapshot,short))
end)
test("mirrors ownership, statistics, structures, attacks and requests",function()
    local s=Mirror.snapshot(decoded(),map(),1)
    assert(s.owners[1].tiles==63 and s.owners[1].gold==1000000 and next(s.border))
    Mirror.delta(s,Wire.delta(bytes(vectors.delta)))
    assert(s.tick==15 and s:tile_owner(393)==2 and s:has_fallout(393))
    assert(s.owners[1].troops==45000 and s.owners[1].max_troops==200000)
    assert(s.structures[2].kind==2 and s.structures[1].level==2)
    assert(s.attacks[9].target==2 and s:has_request(2,1))
    Mirror.delta(s,{t=16,ev={{17,1,2},{15,9}}})
    assert(s:are_allies(1,2) and not s:has_request(2,1) and not s.attacks[9])
    Mirror.delta(s,{t=17,ev={{18,1,2},{1,2,1}}})
    assert(not s:are_allies(1,2) and not s.owners[2].alive)
end)
test("scaled terrain uses the same cell centers as the game map resampler",function()
    local raw=buffer.create(32)
    buffer.fill(raw,0,128);buffer.writeu8(raw,1*8+3,159)
    local scaled=Mirror.map({width=8,height=4,k_lin=1},raw,{map_w=4,map_h=2})
    assert(scaled.k_lin==2 and not scaled:is_contestable(1) and scaled:is_contestable(0))
end)
test("fallback retains reserves and uses observed construction prices",function()
    local s=Mirror.snapshot(decoded(),map(),1)
    local session={state=s,connected=true}
    local ctx=Mirror.context(session)
    assert(ctx.rules:cost("city")==250000 and ctx.rules:cost("factory")==125000)
    assert(not ctx.rules:availability("atom").ok and not ctx.borders:can_reach_by_sea(0))
    local a=assert(Policy.new():decide({state=s,map=s.map,me=1,info=s.owners[1],ctx=ctx,now=10}))
    assert(a.intent.type=="attack" or a.intent.type=="build")
    if a.intent.type=="attack" then assert(a.intent.ratio<=.55) end
end)

test("naval observer tracks unit paths, health, removal and warship prices",function()
    local s=Mirror.snapshot(decoded(),map(),1)
    local ctx=Mirror.context({state=s,connected=true})
    local water=12*32+20;local port=water-1
    s.structures[40]={sid=40,owner=1,kind=1,tile=port,level=1,active_tick=0}
    assert(ctx.rules:availability("warship").ok and ctx.rules:cost("warship")==250000)
    assert(ctx.rules:placement("warship",water).ok)
    Mirror.delta(s,{t=11,ev={{9,90,2,1,{water},11,100,0,1000,1000,0,0,water},
        {9,91,0,1,{water},11,100,3000}}})
    assert(s.units[90].kind==2 and ctx.rules:cost("warship")==500000 and ctx.rules:transports()==1)
    Mirror.delta(s,{t=12,ev={{25,90,600,1000},{27,90,1,water},{28,90,{water,water+32},12,100},{22,2,400}}})
    assert(s.units[90].hp==600 and s.units[90].state==1 and #s.units[90].path==2)
    assert(s.owners[2].traitor_until==400)
    Mirror.delta(s,{t=13,ev={{11,90},{11,91}}})
    assert(not s.units[90] and ctx.rules:transports()==0 and ctx.rules:cost("warship")==250000)
end)
test("sea access distinguishes disconnected lakes and updates after losing a coast",function()
    local data=decoded();local raw=buffer.create(768);buffer.fill(raw,0,128)
    for y=0,23 do buffer.writeu8(raw,y*32+1,0);buffer.writeu8(raw,y*32+20,0) end
    local m=Mirror.map({width=32,height=24,k_lin=2},raw,data)
    local s=Mirror.snapshot(data,m,1);local ctx=Mirror.context({state=s,connected=true})
    assert(ctx.borders:can_reach_by_sea(12*32+2))
    assert(not ctx.borders:can_reach_by_sea(12*32+19))
    for t=0,m.N-1 do if s:tile_owner(t)==1 then buffer.writei32(s.owner,t*4,0) end end
    table.clear(s.border);s.tick+=1
    assert(not ctx.borders:can_reach_by_sea(12*32+2))
end)
test("multiplayer policy builds and redirects warships without interrupting repair",function()
    local m=map();local s=Mirror.snapshot(decoded(),m,1);local ctx=Mirror.context({state=s,connected=true})
    local water=12*32+20;local port=water-1
    s.structures[40]={sid=40,owner=1,kind=1,tile=port,level=1,active_tick=0}
    local f={state=s,map=m,me=1,info=s.owners[1],ctx=ctx,now=10};local p=Policy.new()
    local function fleet()
        p:prepare(f)
        for _,a in ipairs(p.candidates) do if a.kind=='warship' or a.kind=='move_warship' then return a end end
    end
    local a=assert(fleet());assert(a.intent.kind=="warship" and a.intent.tile==water)
    s.units[7]={uid=7,kind=2,owner=1,path={water},state=0,hp=1000,max_hp=1000,patrol_tile=water-32*10}
    s.units[8]={uid=8,kind=0,owner=2,path={water+32},start_tick=s.tick,ticks_per_tile_x100=100}
    s.owners[1].gold=0
    local b=assert(fleet());assert(b.intent.type=="move_warship" and b.intent.uid==7)
    s.units[7].state=1;assert(not fleet())
    s.units[7].state=0;s.alliances[1026]=true;assert(not fleet())
end)

local function harness()
    local n={clock=10,sent={},callbacks={},jobs={}}
    local _,raw=map()
    local event={}
    function event:Connect(fn)
        table.insert(n.callbacks,fn)
        local c={connected=true};function c:Disconnect() self.connected=false end
        n.connection=c;return c
    end
    local output={FireServer=function(_,...) table.insert(n.sent,table.pack(...)) end}
    local getMap={IsA=function(_,c) return c=="RemoteFunction" end,InvokeServer=function(_,id,index)
        assert(id=="world" and index==0)
        return {width=32,height=24,k_lin=2,zsize=768,chunks=1,chunk=raw}
    end}
    local root={FindFirstChild=function(_,name)
        return ({ToServer=output,ToClient={OnClientEvent=event},GetMap=getMap})[name]
    end}
    local services={ReplicatedStorage={FindFirstChild=function(_,name) return name=="AirfrontNet" and root end}}
    n.observer=Network.new(services,Wire,Mirror,function() return n.clock end,
        function(fn) table.insert(n.jobs,fn) end,function() end,function(b) return b end)
    function n:drain() while #self.jobs>0 do table.remove(self.jobs,1)() end end
    function n:receive(...) assert(self.connection.connected);self.callbacks[1](...) end
    return n
end
test("observer requests one normal resync and cannot send gameplay orders before a snapshot",function()
    local n=harness();assert(n.observer:poll()==nil)
    assert(#n.sent==1 and n.sent[1][1]==6)
    n.observer:poll();assert(#n.sent==1)
    n:receive(21,1,bytes(vectors.snapshot));assert(n.observer.main==nil)
    n:drain();local main=assert(n.observer:poll())
    assert(main.session.state.loaded and main.session.state.local_owner==1)
    main.session:send_intent({type="attack",tile=393,ratio=.1})
    assert(n.sent[2][1]==4 and hex(n.sent[2][2])==vectors.intent2)
end)
test("normal network deltas update the bot without any game module access",function()
    local n=harness();n.observer:poll();n:receive(21,1,bytes(vectors.snapshot));n:drain()
    n:receive(22,bytes(vectors.delta));n:drain()
    local adapter=Adapter.new({},function() error("Cannot require game module") end,function() return n.clock end)
    adapter.network=n.observer;adapter.networkActive=true
    local f=assert(adapter:frame());assert(f.info.troops==45000 and f.state.tick==15)
    assert(adapter:send({intent={type="attack",tile=361,ratio=.1},reserve=20000},f))
end)
test("bad packets and stopped updates invalidate the mirror and trigger bounded resync",function()
    local n=harness();n.observer:poll();n:receive(21,1,bytes(vectors.snapshot));n:drain()
    n:receive(22,bytes("0001ff"));n:drain()
    assert(not n.observer.session.state.loaded and n.observer.error)
    assert(not pcall(function() n.observer.session:send_intent({type="spawn",tile=0}) end))
    n.clock+=11;n.observer:poll();assert(n.sent[#n.sent][1]==6)
    n:receive(21,1,bytes(vectors.snapshot));n:drain()
    n.clock+=7;n.observer:poll();assert(not n.observer.session.state.loaded)
end)
test("switching nations and shutdown prevent stale orders",function()
    local n=harness();n.observer:poll();n:receive(21,1,bytes(vectors.snapshot));n:drain()
    local old=n.observer.session
    n:receive(31,2);assert(not old.state.loaded)
    n:receive(21,2,bytes(vectors.snapshot));n:drain()
    assert(n.observer.main.session.state.local_owner==2)
    n.observer:destroy();assert(not n.connection.connected)
    local count=#n.sent;n.observer:poll();assert(#n.sent==count)
    assert(not pcall(function() old:send_intent({type="spawn",tile=0}) end))
end)
test("match close and overflow keep gameplay disabled",function()
    local n=harness();n.observer:poll();n:receive(21,1,bytes(vectors.snapshot));n:drain()
    n:receive(24);assert(not n.observer.session.state.loaded)
    n.clock+=20;local count=#n.sent;n.observer:poll();assert(#n.sent==count)
    n:receive(21,1,bytes(vectors.snapshot))
    for _=1,257 do n:receive(22,bytes(vectors.delta)) end
    n:drain();assert(not n.observer.session.state.loaded)
end)
test("spectator snapshots and a match closing during terrain loading never enable gameplay",function()
    local n=harness();n.observer:poll();n:receive(21,0,bytes(vectors.snapshot));n:drain()
    assert(not n.observer.main and n.observer.status:find("Spectating"))
    local original=n.observer.fetchMap
    function n.observer:fetchMap(data)
        n:receive(24)
        return original(self,data)
    end
    n:receive(21,1,bytes(vectors.snapshot));n:drain()
    assert(not n.observer.main and n.observer.closed)
end)
test("unrelated packets do not disguise stale authoritative updates",function()
    local n=harness();n.observer:poll();n:receive(21,1,bytes(vectors.snapshot));n:drain()
    n.clock+=7;n:receive(23,"ordinary notice")
    n.observer:poll();assert(not n.observer.session.state.loaded)
end)
print("NETWORK TESTS",tests)
