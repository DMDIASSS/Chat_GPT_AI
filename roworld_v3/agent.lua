-- New v3 decision core. Does not call v2 Policy, Strategy or Planner.
local Agent={};Agent.__index=Agent
local Schema=require('./schema')
local Observe=require('./observe')
local Actions=require('./actions')
local Neural=require('./neural')
local Cooperation=require('./shared/cooperation')
local Profiles=require('./shared/profiles')
local Recorder=require('./shared/recorder')
function Agent.new(profiles,weights)
    local valid,reason
    if weights then valid,reason=Neural.validate(weights) end
    return setmetatable({profiles=profiles or Profiles.new(),cooperation=Cooperation.new(),weights=valid,
        modelStatus=valid and 'loaded residual policy' or reason or 'built-in policy; no trained model loaded',
        seed=739391,cooldowns={},campaigns={},distrust={},postPurchases={},outcome={},history={},metrics={orders=0}},Agent)
end
function Agent:random(n) self.seed=self.seed*48271%2147483647;return self.seed%math.max(1,n) end
function Agent:reset(frame)
    self.state,self.me=frame.state,frame.me;self.anchor=nil;self.frontCursor=0;self.lastTick=nil;self.observation=nil
    self.cooldowns={};self.campaigns={};self.distrust={};self.postPurchases={};self.outcome={};self.history={};self.lastObservation=nil
    self.lastSentAt,self.lastSentKind,self.pending,self.lastRejected,self.lastWaiting=nil,nil,nil,nil,nil
    self.blocked=false
    self.supportProjects={};self.tacticalAssessments={};self.betrayalPlan=nil;self.betrayalHistory={}
    self.metrics={orders=0,peakLand=frame.info.tiles or 0};self.profiles:start(frame);self.recorder=Recorder.new(frame)
    self.allianceSeq=frame.state.alliance_seq or 0;self.missileHistory={};self.missilesSeen={}
end
function Agent:prepare(frame)
    if self.state~=frame.state or self.me~=frame.me or self.lastTick and frame.state.tick<self.lastTick then self:reset(frame) end
    self.cooperation:update(frame);self.profiles:observe(frame);self.recorder:observe(frame)
    self.lastTick=frame.state.tick
    self.phase,self.ownAlive=frame.state.phase,frame.info.alive
    for _,event in ipairs(frame.state.alliance_events or {}) do
        if (event.seq or 0)>self.allianceSeq and event.breaker and event.breaker>0 and event.breaker~=frame.me
            and (event.a==frame.me or event.b==frame.me) then
            self.profiles:betrayed(frame,event.breaker);self.distrust[event.breaker]=frame.now+180
        end
    end
    self.allianceSeq=frame.state.alliance_seq or 0
    if self.betrayalPlan then
        local p=self.betrayalPlan;local target=frame.state.owners[p.target]
        if not target or not target.alive or frame.now>=p.deadline or self.cooperation:isFriend(p.target) then
            table.insert(self.betrayalHistory,{target=p.target,tick=frame.state.tick,status=(not target or not target.alive) and 'target ended' or 'plan ended or protection changed'})
            if #self.betrayalHistory>16 then table.remove(self.betrayalHistory,1) end
            self.betrayalPlan=nil
        end
    end
    for i=#self.postPurchases,1,-1 do if frame.now-self.postPurchases[i]>=60 then table.remove(self.postPurchases,i) end end
    for id,c in pairs(self.campaigns) do
        local p=frame.state.owners[id]
        if not p or not p.alive then self.campaigns[id]=nil
        else
            if (p.tiles or 0)<c.last_land then c.progress_at=frame.now;c.last_land=p.tiles or 0 end
            if frame.now>=c.deadline then
                if frame.now>=c.deadline+15 then self.campaigns[id]=nil else c.pause_until=c.deadline+15 end
            end
        end
    end
    local o=Observe.read(frame,self)
    local prev=self.lastObservation
    local dt=prev and math.max(1,o.tick-prev.tick) or 1
    self.outcome={prev and Schema.clamp(((frame.info.tiles or 0)-prev.land)/math.max(1,prev.land)) or 0,
        prev and Schema.clamp((o.home-prev.home)/math.max(1,prev.home)) or 0,
        prev and Schema.clamp(((frame.info.gold or 0)-prev.gold)/math.max(1000,prev.gold)) or 0,
        self.lastSentKind and self.lastSentKind/#Schema.types or 0,self.blocked and 1 or 0,
        Schema.clamp(dt/100),self.lastSentAt and Schema.clamp((frame.now-self.lastSentAt)/30) or 0,
        self.pending and 1 or 0}
    for i=1,8 do o.context[Schema.context-8+i]=self.outcome[i] end
    self.lastObservation={tick=o.tick,home=o.home,gold=frame.info.gold or 0,land=frame.info.tiles or 0}
    self.missileAlerts=o.alerts
    for _,a in ipairs(o.alerts) do if not self.missilesSeen[a.uid] then
        self.missilesSeen[a.uid]=true;table.insert(self.missileHistory,a)
        if #self.missileHistory>32 then table.remove(self.missileHistory,1) end
    end end
    self.metrics.peakLand=math.max(self.metrics.peakLand,frame.info.tiles or 0)
    self.observation=o
    local candidates,filtered=Actions.generate(frame,o,self)
    local logits,value=Neural.score(self.weights,o.context,candidates)
    self.candidates=candidates;self.logits=logits;self.value=value;self.filtered=filtered
    self.board={mode=o.incoming>o.home*.6 and 'defend' or 'observe-and-compare',incoming=o.incoming,
        reserve=o.reserve,available=o.available,candidate_count=#candidates,model=self.modelStatus,
        planner={objective='compare legal candidates'}}
    return o,candidates,logits,value
end
function Agent:decide(frame)
    self.evaluated=false
    if self.state==frame.state and self.lastTick==frame.state.tick then return nil,self.lastWaiting or 'Waiting for the next authoritative tick' end
    if self.state==frame.state and self.me==frame.me and self.lastTick and frame.state.tick>=self.lastTick
        and frame.state.tick-self.lastTick<Schema.decision_ticks and self.phase==frame.state.phase and self.ownAlive==frame.info.alive then
        return nil,self.lastWaiting or 'Watching between one-second decisions'
    end
    self.evaluated=true
    local _,candidates,logits=self:prepare(frame)
    local chosen,probs=Neural.pick(logits,self.stochastic and (self:random(1000000)+.5)/1000000 or nil)
    self.selected=chosen;self.probabilities=probs
    local a=candidates[chosen];self.board.planner.objective=a.kind;self.lastWaiting=a.label
    if a.kind=='wait' then self.pending=nil;return nil,a.label end
    self.pending=a;return a,a.label
end
function Agent:sent(action,now)
    self.cooldowns[action.channel]=now+action.cooldown
    self.lastSentAt=now;self.lastSentKind=Schema.ids[action.kind];self.blocked=false;self.pending=nil
    self.metrics.orders+=1
    local intent=action.intent
    if intent.type=='donate' and (action.plan or {}).strategic_support then
        local q=action.plan.assessment;local key=intent.target..':'..action.plan.support_target
        self.supportProjects[key]={partner=intent.target,target=action.plan.support_target,at=now,
            commitment=q.commitment,target_land=q.target_land,amount=intent.troops}
        local count,oldest=0,nil
        for k,row in pairs(self.supportProjects) do count+=1;if not oldest or row.at<self.supportProjects[oldest].at then oldest=k end end
        if count>64 then self.supportProjects[oldest]=nil end
    elseif intent.type=='ally_break' and (action.plan or {}).opportunistic_betrayal then
        self.betrayalPlan={target=intent.target,created=now,deadline=now+35,reserve=action.reserve,status='awaiting confirmation',assessment=action.plan.assessment}
    elseif (action.plan or {}).after_betrayal and self.betrayalPlan then self.betrayalPlan.status='capture issued' end
    self.metrics[intent.type]=(self.metrics[intent.type] or 0)+1
    if intent.type=='build' and intent.kind=='defense' then table.insert(self.postPurchases,now) end
    local target=intent.target or intent.tile and self.state:tile_owner(intent.tile)
    if intent.type=='attack' and target and target>0 then
        local amount=(self.state.owners[self.me].troops or 0)*(intent.ratio or 0)
        local c=self.campaigns[target]
        if not c then
            c={started=now,deadline=now+75,budget=math.max(amount,(self.state.owners[self.me].troops or 0)*.55),
                spent=0,progress_at=now,pause_until=0,last_land=(self.state.owners[target] or {}).tiles or 0}
            self.campaigns[target]=c
        end
        c.spent+=amount
    end
    table.insert(self.history,{tick=self.state.tick,kind=action.kind,target=target,tile=intent.tile,
        ratio=intent.ratio,troops=intent.troops,cost=action.cost,label=action.label,plan=action.plan})
    if #self.history>64 then table.remove(self.history,1) end
end
function Agent:rejected(reason)
    self.blocked=true;self.lastRejected=tostring(reason);self.pending=nil
end
function Agent:report()
    if not self.observation then return {version='3.1.0',schema=Schema.version,status='no observed match'} end
    local ranked={};for i,a in ipairs(self.candidates or {}) do table.insert(ranked,{kind=a.kind,score=self.logits[i],
        probability=self.probabilities and self.probabilities[i],intent=a.intent,label=a.label,plan=a.plan}) end
    table.sort(ranked,function(a,b) return a.score>b.score end)
    local o=self.observation;local diplomatic={};for id,r in pairs(o.diplomacy) do
        table.insert(diplomatic,{nation=id,allied=r.allied,same_team=r.same_team,friend=r.friend,
            outgoing_request=r.outgoing_request,incoming_request=r.incoming_request,expiry=r.expiry})
    end
    return {version='3.1.0',schema=Schema.version,policy=self.modelStatus,competitive_strength_verified=false,
        tick=self.state.tick,observation_tick=o.tick,observation_age_ticks=math.max(0,self.state.tick-o.tick),
        decision_interval_ticks=Schema.decision_ticks,me=self.me,own=self.state.owners[self.me],metrics=self.metrics,runtime=self.runtime,
        board=self.board,actions=self.history,candidates=ranked,filtered_by_risk=self.filtered,
        cooperation=self.cooperation.status,public_players=o.players,exact_diplomacy=diplomatic,public_alliance_pairs=o.relationships,
        tactical_support=self.tacticalAssessments,support_projects=self.supportProjects,proposed_betrayal=self.betrayalPlan,ended_betrayal_plans=self.betrayalHistory,
        construction_assessments=self.constructionAssessments,own_structures=o.ownStructures,
        exact_attacks=o.attacks,exact_units=o.units,exact_missiles=o.missiles,context=o.context,
        missile_alerts=self.missileAlerts,missile_alert_history=self.missileHistory,nuclear_threat=o.nuclearThreat,
        public_observations=self.recorder:report(),opponent_profiles=self.profiles:report({state=self.state,me=self.me}),
        observation_scope='Current public client observations; no hidden intent, private country timers or invented action labels',
        last_rejected=self.lastRejected}
end
return Agent
