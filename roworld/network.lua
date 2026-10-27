-- Independent observer of the player's existing multiplayer connection.
local Network={};Network.__index=Network
function Network.new(services,wire,mirror,now,spawn,cooperate,decompress)
    return setmetatable({services=services,wire=wire,mirror=mirror,now=now,spawn=spawn,cooperate=cooperate,
        decompress=decompress,queue={},generation=0,packets=0,lastRequest=-math.huge,lastPacket=0,
        status="Join multiplayer; waiting for a server snapshot",destroyed=false,maps={}},Network)
end
function Network:invalidate(reason)
    self.status=reason;self.error=reason
    if self.session and self.session.state then self.session.state.loaded=false end
    self.needsSnapshot=true
end
function Network:fetchMap(data)
    local id=assert(data.map_id,"Snapshot has no map ID")
    local base=id:match("^(.-)@%d+$") or id
    local cache=self.maps[base]
    if cache then return self.mirror.map(cache.meta,cache.raw,data,self.cooperate) end
    local remote=self.root:FindFirstChild("GetMap")
    assert(remote and remote:IsA("RemoteFunction"),"RoWorld map service unavailable")
    local meta=remote:InvokeServer(base,0)
    assert(type(meta)=="table" and typeof(meta.chunk)=="buffer","RoWorld map request returned no terrain")
    assert(type(meta.zsize)=="number" and meta.zsize>0 and meta.zsize<=32*1024*1024,"Invalid map download size")
    assert(type(meta.chunks)=="number" and meta.chunks>=1 and meta.chunks<=50,"Invalid map chunk count")
    local zipped=buffer.create(meta.zsize);local offset=buffer.len(meta.chunk)
    assert(offset<=meta.zsize);buffer.copy(zipped,0,meta.chunk)
    for index=1,meta.chunks-1 do
        assert(not self.destroyed,"Observer stopped")
        local part=remote:InvokeServer(base,index)
        assert(type(part)=="table" and typeof(part.chunk)=="buffer","Interrupted RoWorld map download")
        local size=buffer.len(part.chunk);assert(offset+size<=meta.zsize,"Oversized map chunk")
        buffer.copy(zipped,offset,part.chunk);offset+=size
    end
    assert(offset==meta.zsize,"Incomplete map download")
    local raw=self.decompress(zipped)
    self.maps[base]={meta=meta,raw=raw}
    return self.mirror.map(meta,raw,data,self.cooperate)
end
function Network:process(row)
    if row.op==21 then
        self.status="Reading multiplayer snapshot and terrain..."
        local data=self.wire.snapshot(row.body,self.decompress)
        local map=self:fetchMap(data)
        local state=self.mirror.snapshot(data,map,row.me,self.cooperate)
        if self.destroyed or row.generation~=self.generation then return end
        local observer=self
        local session={mode=2,_sim=nil,state=state,connected=true}
        function session:multiplayer_available() return self.connected and not observer.destroyed end
        function session:send_intent(intent)
            assert(self.state.loaded and self.connected and not observer.destroyed,"Observer is not synchronized")
            observer.toServer:FireServer(4,observer.wire.intent(intent))
        end
        function session:note_activity()
            if observer.now()-(observer.lastActivity or -math.huge)>=30 then
                observer.lastActivity=observer.now();observer.toServer:FireServer(7)
            end
        end
        self.session=session;self.main={session=session,ui={ctx=self.mirror.context(session)}}
        self.needsSnapshot=false;self.closed=false;self.error=nil;self.status="Multiplayer snapshot synchronized"
        self.lastUpdate=self.now()
    elseif row.op==22 and self.session and self.session.state.loaded then
        local delta=self.wire.delta(row.body,row.tail,self.decompress)
        self.mirror.delta(self.session.state,delta)
        self.lastUpdate=self.now()
    end
end
function Network:receive(op,...)
    if self.destroyed then return end
    self.packets+=1;self.lastPacket=self.now()
    if op==24 then
        self.generation+=1;table.clear(self.queue)
        self.closed=true;self:invalidate("Match closed; join a multiplayer match");return
    end
    if op==31 then
        self.generation+=1;table.clear(self.queue)
        self:invalidate("Your nation changed; waiting for a fresh snapshot");return
    end
    local row
    if op==21 then
        local me,packet=...
        if type(me)~="number" or typeof(packet)~="buffer" then return end
        self.generation+=1;table.clear(self.queue)
        if self.session then self.session.state.loaded=false end
        if me==0 then
            self.needsSnapshot=false;self.status="Spectating; select your nation before starting autoplay";return
        end
        row={op=op,me=me,body=packet,generation=self.generation}
    elseif op==22 then
        local packet,tail=...
        if typeof(packet)~="buffer" or (tail~=nil and typeof(tail)~="buffer") then return end
        row={op=op,body=packet,tail=tail,generation=self.generation}
    else return end
    if #self.queue>=256 then
        self.generation+=1;table.clear(self.queue);self:invalidate("Observer update queue overflow; resynchronizing");return
    end
    table.insert(self.queue,row)
    if self.working then return end
    self.working=true
    self.spawn(function()
        while not self.destroyed and #self.queue>0 do
            local item=table.remove(self.queue,1)
            if item.generation==self.generation then
                local ok,err=pcall(function() self:process(item) end)
                if not ok and item.generation==self.generation then
                    self.generation+=1;table.clear(self.queue);self:invalidate("Network observer: "..tostring(err))
                end
            end
        end
        self.working=false
    end)
end
function Network:poll()
    if self.destroyed then return nil end
    if not self.connection then
        local replicated=self.services.ReplicatedStorage
        local root=replicated and replicated:FindFirstChild("AirfrontNet")
        local input=root and root:FindFirstChild("ToClient")
        local output=root and root:FindFirstChild("ToServer")
        if not input or not output then self.status="Waiting for RoWorld multiplayer remotes";return nil end
        self.root,self.toServer=root,output
        self.connection=input.OnClientEvent:Connect(function(...) self:receive(...) end)
        self.needsSnapshot=true
    end
    if self.session and self.session.state.loaded and (self.now()-self.lastPacket>6 or
        self.session.state.phase==1 and self.now()-(self.lastUpdate or self.lastPacket)>6) then
        self:invalidate("Multiplayer updates stopped; resynchronizing")
    end
    if not self.closed and self.needsSnapshot and not self.working and self.now()-self.lastRequest>=10 then
        self.lastRequest=self.now()
        -- The game's normal resync operation for this client's existing match.
        -- Never HELLO/JOIN/LEAVE, never switch queues or impersonate an owner.
        local ok,err=pcall(function() self.toServer:FireServer(6) end)
        if not ok then self:invalidate("Multiplayer resync request failed: "..tostring(err)) end
    end
    return self.main
end
function Network:diagnostics()
    return "network_packets="..self.packets.."\nnetwork_status="..self.status.."\nnetwork_error="..tostring(self.error or "none")
end
function Network:destroy()
    self.destroyed=true;self.generation+=1;table.clear(self.queue)
    if self.connection then self.connection:Disconnect() end
    if self.session then self.session.connected=false;self.session.state.loaded=false end
end
return Network
