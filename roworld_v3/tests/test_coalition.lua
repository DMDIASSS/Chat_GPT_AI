local C=require('../shared/coalition')
local Agent=require('../agent')
local Adapter=require('../shared/adapter')
local fixture=require('./fixture')
local n=0;local function test(name,fn) fn();n+=1;print('PASS',name) end
local function support()
    local f=fixture();f.info.kind=2;f.info.troops=100000;f.info.max_troops=200000
    local p=f.state.owners[2];p.kind=2;p.troops=10000;p.max_troops=30000;p.tiles=50;p.label_tile=p.spawn_tile
    f.state.owners[3]={alive=true,kind=0,name='Victim',troops=5000,max_troops=50000,tiles=40,gold=150000,spawn_tile=405,label_tile=405}
    f.state.allied[1026]=true;f.state.attacks[8]={aid=8,attacker=2,target=3,troops=5000}
    return f
end
local function betrayal()
    local f=fixture();f.info.kind=2;f.info.troops=500000;f.info.max_troops=800000;f.info.tiles=300
    local p=f.state.owners[2];p.kind=0;p.troops=5000;p.max_troops=50000;p.tiles=30;p.gold=200000
    f.set(393,2);f.state.allied[1026]=true;f.refresh()
    return f
end
local function adapter(f)
    local a=Adapter.new({},function() error('reuse the live session') end,function() return f.now end);a.main=f.main;return a
end
local function action(p,f,kind,field)
    p:prepare(f)
    for _,a in ipairs(p.candidates) do if a.kind==kind and (not field or (a.plan or {})[field]) then return a end end
end
test('ordinary treaty ally gets only the calculated useful funding gap',function()
    local f=support();local q=assert(C.support(f,2,3))
    assert(q.amount==q.need and q.amount<=8000 and f.info.troops-q.amount>=84000 and q.mode=='finish_attack')
end)
test('already funded ally and a hopelessly expensive campaign get no grant',function()
    local f=support();f.state.attacks[8].troops=100000;assert(not C.support(f,2,3))
    f.state.attacks[8].troops=1;f.state.owners[3].troops=100000;assert(not C.support(f,2,3))
end)
test('a target allied with either participant or protected friend is excluded',function()
    for _,mode in ipairs({'ours','theirs','friend','pending','team'}) do
        local f=support()
        if mode=='ours' then f.state.allied[1027]=true elseif mode=='theirs' then f.state.allied[2051]=true
        elseif mode=='friend' then f.state.bot_friend_guard={[3]=true}
        elseif mode=='pending' then f.state.requests[2051]=1 else f.state.owners[2].team=2;f.state.owners[3].team=2 end
        assert(not C.support(f,2,3),mode)
    end
end)
test('moderate invasion can fund a reachable counter without surrendering donor reserves',function()
    local f=support();f.state.attacks[8]=nil;f.state.attacks[9]={attacker=3,target=1,troops=9000}
    f.state.owners[2].troops=16000;f.set(405,3);f.set(404,2)
    local q=assert(C.support(f,2,3));assert(q.mode=='counterattack' and f.info.troops-q.amount>=84000)
    f.set(404,0);assert(not C.support(f,2,3))
end)
test('heavy invasion, recipient capacity and treaty expiry stop tactical gifts',function()
    local f=support();f.state.attacks[9]={attacker=3,target=1,troops=25000};assert(not C.support(f,2,3))
    f.state.attacks[9]=nil;f.state.owners[2].max_troops=10000;assert(not C.support(f,2,3))
    f.state.owners[2].max_troops=30000
    function f.state:alliance_info() return {ticks_left=100} end
    assert(not C.support(f,2,3))
end)
test('donor vulnerability, recipient treachery and a dominating target coalition stop support',function()
    local f=support();f.info.traitor_until=100;assert(not C.support(f,2,3))
    f.info.traitor_until=0;f.state.owners[2].traitor_until=100;assert(not C.support(f,2,3))
    f.state.owners[2].traitor_until=0
    f.state.owners[4]={alive=true,troops=200000};f.state.allied[3076]=true
    assert(not C.support(f,2,3))
end)
test('policy proposes offensive help without a Roblox friendship requirement',function()
    local f=support();local p=Agent.new();local a=assert(action(p,f,'donate','strategic_support'))
    assert(a.intent.target==2 and a.plan.support_target==3 and not p.cooperation:isFriend(2))
    p.betrayalPlan={target=2,reserve=80000,deadline=f.now+35}
    assert(not action(p,f,'donate','strategic_support'))
end)
test('a gift without new campaign progress cannot be repeated',function()
    local f=support();local p=Agent.new();local a=assert(action(p,f,'donate','strategic_support'));p:sent(a,f.now)
    f.now+=60;f.state.tick+=600
    assert(not action(p,f,'donate','strategic_support'))
    f.state.owners[3].tiles=25
    assert(action(p,f,'donate','strategic_support'))
end)
test('sender cancels gifts if the ally partners with the victim before dispatch',function()
    local f=support();local p=Agent.new();local a=assert(action(p,f,'donate','strategic_support'));local sender=adapter(f)
    f.state.allied[2051]=true;assert(not sender:send(a,assert(sender:frame())))
end)
test('sender permits a bounded strategic counter gift during a small invasion',function()
    local f=support();f.state.attacks[8]=nil;f.state.attacks[9]={attacker=3,target=1,troops=9000}
    f.state.owners[2].troops=16000;f.set(405,3);f.set(404,2)
    local p=Agent.new();local a=assert(action(p,f,'donate','strategic_support'));local sender=adapter(f)
    local sent,intent=sender:send(a,assert(sender:frame()));assert(sent and intent.troops<=8000)
    f.now+=1;f.state.attacks[9].troops=50000;assert(not sender:send(a,assert(sender:frame())))
end)
test('a weak wealthy neighboring ally can justify a carefully budgeted treaty break',function()
    local f=betrayal();local q=assert(C.betrayal(f,2,393,false))
    assert(q.estimated_value==200000 and q.defense_multiplier==.5 and q.vulnerability_ticks==300)
    assert(f.info.troops-q.amount>=q.reserve)
end)
test('poor targets and valuable trade partnerships are not free betrayal opportunities',function()
    local f=betrayal();f.state.owners[2].gold=0;assert(not C.betrayal(f,2,393,false))
    f.state.owners[2].gold=200000;f.state.structures[5]={owner=2,kind=1,tile=393,level=1,active_tick=0}
    assert(not C.betrayal(f,2,393,false))
end)
test('teammates and protected friends cannot be betrayed',function()
    local f=betrayal();f.info.team=3;f.state.owners[2].team=3;assert(not C.betrayal(f,2,393,false))
    f.info.team=0;f.state.bot_friend_guard={[2]=true};assert(not C.betrayal(f,2,393,false))
end)
test('nearby powerful nations and the target coalition outweigh nominal capture value',function()
    local f=betrayal();f.state.owners[4]={alive=true,troops=300000,label_tile=394}
    assert(not C.betrayal(f,2,393,false))
    f.state.allied[1028]=true;assert(C.betrayal(f,2,393,false))
    f.state.allied[2052]=true;assert(not C.betrayal(f,2,393,false))
end)
test('invasions, an existing war and existing traitor vulnerability prevent a new betrayal',function()
    local f=betrayal();f.state.attacks[5]={attacker=2,target=1,troops=1};assert(not C.betrayal(f,2,393,false))
    f.state.attacks[5]={attacker=1,target=3,troops=1};assert(not C.betrayal(f,2,393,false))
    f.state.attacks={};f.info.traitor_until=100;assert(not C.betrayal(f,2,393,false))
    f.info.traitor_until=0;f.state.units={[4]={kind=0,owner=1,path={400}}};assert(not C.betrayal(f,2,393,false))
end)
test('enemy missiles and front defenses invalidate a cheap capture estimate',function()
    local f=betrayal();f.state.owners[2].gold=1000000
    f.state.structures[5]={owner=2,kind=5,tile=400,level=1,active_tick=100}
    assert(not C.betrayal(f,2,393,false))
    f.state.structures[5]={owner=2,kind=3,tile=393,level=1,active_tick=0}
    assert(not C.betrayal(f,2,393,false))
    f.state.structures={};f.state.owners[2].gold=200000
    f.state.units={[9]={kind=2,owner=2,path={393},hp=1000}}
    assert(not C.betrayal(f,2,393,false))
end)
test('proposal and sender re-evaluate a non-traitor alliance before breaking it',function()
    local f=betrayal();local p=Agent.new();local a=assert(action(p,f,'ally_break','opportunistic_betrayal'))
    local sender=adapter(f);assert(sender:send(a,assert(sender:frame())))
    f.now+=1;f.state.owners[4]={alive=true,troops=300000,label_tile=394}
    assert(not sender:send(a,assert(sender:frame())))
end)
test('capture waits for actual alliance termination and retains the penalty reserve',function()
    local f=betrayal();local p=Agent.new();local a=assert(action(p,f,'ally_break','opportunistic_betrayal'));p:sent(a,f.now)
    f.state.tick+=10;f.now+=1;assert(not action(p,f,'attack','after_betrayal'))
    for _,candidate in ipairs(p.candidates) do assert(candidate.kind~='expand' and candidate.kind~='boat' and candidate.kind~='donate') end
    f.state.allied[1026]=nil;f.info.traitor_until=f.state.tick+300;f.state.tick+=10;f.now+=1
    local capture=assert(action(p,f,'attack','after_betrayal'));assert(capture.reserve>=400000 and p.observation.reserve>=400000)
    assert(not action(p,f,'ally_request'))
    local sender=adapter(f);assert(sender:send(capture,assert(sender:frame())))
end)
test('a newly unsafe post-break position cancels capture rather than bypassing the planner',function()
    local f=betrayal();local p=Agent.new();local a=assert(action(p,f,'ally_break','opportunistic_betrayal'));p:sent(a,f.now)
    f.state.allied[1026]=nil;f.info.traitor_until=f.state.tick+300
    f.state.owners[4]={alive=true,troops=300000,label_tile=394}
    p:prepare(f);for _,candidate in ipairs(p.candidates) do assert(candidate.kind~='attack') end
end)
test('late changes cancel a capture and completed plans are released without another break',function()
    local f=betrayal();local p=Agent.new();local a=assert(action(p,f,'ally_break','opportunistic_betrayal'));p:sent(a,f.now)
    f.state.allied[1026]=nil;f.info.traitor_until=301
    local capture=assert(action(p,f,'attack','after_betrayal'));local sender=adapter(f)
    f.state.allied[1026]=true;assert(not sender:send(capture,assert(sender:frame())))
    f.state.allied[1026]=nil;f.state.owners[2].alive=false;p:prepare(f)
    assert(not p.betrayalPlan and p.betrayalHistory[1].status=='target ended' and p.cooldowns.betrayal>f.now)
end)
print('COALITION SCENARIOS',n)
