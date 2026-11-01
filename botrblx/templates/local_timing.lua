-- Deadline scheduling and bounded active-run measurements. No game APIs.
local Timing={}
Timing.__index=Timing
function Timing.due(now,deadline,period)
    if deadline and now+1e-6<deadline then return false,deadline,0 end
    local late=deadline and math.max(0,now-deadline)or 0
    local nextAt=deadline and deadline+(math.floor(late/period)+1)*period or now+period
    return true,nextAt,late
end
function Timing.new(target)
    return setmetatable({target=target,samples={},rate=0},Timing)
end
function Timing:record(sample)
    if not self.last or sample.time-self.last.time>.5 then self.windowAt=sample.time;self.count=0;self.rate=0 end
    self.count=self.count+1
    if sample.time-self.windowAt>=1 then
        self.rate=(self.count-1)/(sample.time-self.windowAt)
        self.count=1;self.windowAt=sample.time
    end
    self.last=sample
    self.samples[#self.samples+1]=sample
    if #self.samples>120 then table.remove(self.samples,1)end
end
function Timing:report()
    local out={target_hz=self.target,decision_hz=self.rate,samples=#self.samples,last=self.last,
        model_calls=0,fields={}}
    for _,key in ipairs({'pose_ms','observe_ms','model_ms','planning_ms','safety_ms','decision_ms','input_ms','schedule_late_ms','entities'})do
        local sum,peak=0,0
        for _,sample in ipairs(self.samples)do local n=sample[key]or 0;sum=sum+n;peak=math.max(peak,n)end
        out.fields[key]={mean=sum/math.max(1,#self.samples),max=peak}
    end
    for _,sample in ipairs(self.samples)do out.model_calls=out.model_calls+(sample.model_ran and 1 or 0)end
    return out
end
return Timing
