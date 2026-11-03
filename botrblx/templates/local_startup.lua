-- Startup gets a larger work slice than live inference, with bounded waits.
local Startup={}
Startup.__index=Startup
function Startup.new(options)
    options=options or {}
    local clock=options.clock or os.clock
    local now=clock()
    return setmetatable({clock=clock,wait=options.wait or task.wait,spawn=options.spawn or task.spawn,
        fetch=options.fetch or function(url)return game:HttpGet(url)end,
        alive=options.alive or function()return true end,render=options.render or function()end,
        budget=options.budget or .008,timeout=options.timeout or 120,downloadTimeout=options.downloadTimeout or 60,
        began=now,sliceAt=now,uiAt=-math.huge,stage='Preparing model'},Startup)
end
function Startup:show(force)
    local now=self.clock()
    if force or now-self.uiAt>=.1 then
        self.uiAt=now
        self.render(self.stage,self.done,self.total,now-self.began)
    end
end
function Startup:progress(stage,done,total)
    local changed=stage~=self.stage
    self.stage=stage;self.done=done;self.total=total
    self:show(changed)
end
function Startup:checkpoint(force)
    assert(self.alive(),'Model loading cancelled')
    assert(self.clock()-self.began<self.timeout,'Model preparation timed out after 120s. Close the panel and retry.')
    self:show(false)
    if force or self.clock()-self.sliceAt>=self.budget then
        self.wait()
        self.sliceAt=self.clock()
        assert(self.alive(),'Model loading cancelled')
    end
end
function Startup:download(url,expectedBytes)
    self:progress(('Downloading FP32 model (%.1f MB)'):format(expectedBytes/1000000))
    local request={active=true,done=false}
    self.spawn(function()
        local ok,data=pcall(self.fetch,url)
        if request.active and self.alive()then request.ok=ok;request.data=data;request.done=true end
    end)
    local began=self.clock()
    while not request.done and self.alive()and self.clock()-began<self.downloadTimeout do
        self:show(false);self.wait(.1)
    end
    request.active=false -- a timed-out/cancelled HTTP reply can never start the model
    assert(self.alive(),'Model loading cancelled')
    assert(request.done,('Model download timed out after %ds. Close the panel and retry.'):format(self.downloadTimeout))
    assert(request.ok,'Model download failed: '..tostring(request.data))
    assert(type(request.data)=='string'and #request.data==expectedBytes,
        'Incomplete model download. Close the panel and retry.')
    return request.data
end
return Startup
