-- One cancellable inference job. Only resume it once per Heartbeat.
local Worker={}
Worker.__index=Worker
function Worker.new(predict,clock)
    return setmetatable({predict=predict,clock=clock or os.clock,generation=0,
        peak_slice_ms=0,cancelled=0,completed=0},Worker)
end
function Worker:cancel()
    if self.job then self.cancelled+=1 end
    self.generation+=1;self.job=nil
end
function Worker:start(query,context,metadata)
    assert(not self.job,'Inference is already running')
    local job={context=context,metadata=metadata,at=self.clock(),cpu=0,slices=0,generation=self.generation}
    job.thread=coroutine.create(function()
        local function checkpoint()
            if self.clock()>=self.deadline then coroutine.yield()end
        end
        if type(query)=='function'then query,context=query(checkpoint);job.context=context end
        return self.predict(query,context,checkpoint)
    end)
    self.job=job
end
function Worker:step(budget)
    local job=self.job
    if not job then return nil end
    local began=self.clock()
    self.deadline=began+math.clamp(budget or .0015,.00025,.003)
    local ok,index,logits=coroutine.resume(job.thread)
    local spent=self.clock()-began
    job.cpu+=spent;job.slices+=1
    self.peak_slice_ms=math.max(self.peak_slice_ms,spent*1000)
    self.last_slice_ms=spent*1000
    if not ok then self.job=nil;error(index,0)end
    if self.job~=job or self.generation~=job.generation then return nil end
    if coroutine.status(job.thread)=='dead'then
        self.job=nil;self.completed+=1
        job.index=index;job.logits=logits;job.thread=nil
        job.wall=self.clock()-job.at
        self.wall=self.wall and self.wall*.75+job.wall*.25 or job.wall
        self.last=job
        return job
    end
end
function Worker:report()
    return {busy=self.job~=nil,completed=self.completed,cancelled=self.cancelled,backend=self.backend,
        peak_slice_ms=self.peak_slice_ms,last_slice_ms=self.last_slice_ms,
        last_cpu_ms=self.last and self.last.cpu*1000 or nil,
        last_wall_ms=self.last and self.last.wall*1000 or nil,
        last_slices=self.last and self.last.slices or nil}
end
return Worker
