-- Frenet-space adapter: simulation x is lateral distance and z is course progress.
-- Visuals use the actual saved map coordinates, including hairpins and backtracking.
local Data=require(script.Parent.OriginalStageData)
local Course={};Course.__index=Course
local function interpolate(stage,distance)
 local rows=stage.points;local lo,hi=1,#rows
 while lo<hi do local mid=math.floor((lo+hi+1)/2);if rows[mid][1]<=distance then lo=mid else hi=mid-1 end end
 local a,b=rows[lo],rows[math.min(lo+1,#rows)]
 local span=b[1]-a[1];local t=span>0 and math.clamp((distance-a[1])/span,0,1)or 0
 local x,y,z,h,bank
 x=a[2]+(b[2]-a[2])*t;y=a[3]+(b[3]-a[3])*t;z=a[4]+(b[4]-a[4])*t
 h=a[5]+(b[5]-a[5])*t;bank=a[6]+(b[6]-a[6])*t
 return {position=Vector3.new(x,y,z),heading=h,bank=bank,dy=span>0 and (b[3]-a[3])/span or 0,
  curvature=span>0 and (b[5]-a[5])/span or 0,surface=(t<1 and a[7]or b[7])==1 and 'tarmac'or 'gravel'}
end
function Course.available()
 local result={};local world=workspace:FindFirstChild('World')
 if world then for id,stage in pairs(Data)do if world:FindFirstChild('Stage_'..id)then result[#result+1]={id=id,name=stage.name,incomplete=stage.incomplete}end end end
 table.sort(result,function(a,b)return a.id<b.id end);return result
end
function Course.new(id,config,seed)
 local stage=Data[id];if not stage then return nil end
 return setmetatable({original=true,slotIgnored=true,stageId=id,stage=stage,config=config,seed=seed or 0,
  length=stage.finish-stage.start,incomplete=stage.incomplete,name=stage.name},Course)
end
function Course.default(config,seed)
 local rs=game:GetService('ReplicatedStorage');local root=rs:FindFirstChild('BackseatExpedition')
 local id=root and root:GetAttribute('OriginalStage')
 if not id then local available=Course.available();id=available[1]and available[1].id end
 return id and Course.new(id,config,seed)or nil
end
function Course:worldPoint(progress)return interpolate(self.stage,math.clamp(progress+self.stage.start,0,self.stage.points[#self.stage.points][1])).position end
function Course:sample(progress)return interpolate(self.stage,math.clamp(progress+self.stage.start,0,self.stage.points[#self.stage.points][1]))end
function Course:point(progress)
 local p=self:sample(progress)
 return {x=0,y=p.position.Y,z=progress,dx=0,dy=p.dy,heading=0,curvature=p.curvature,bank=p.bank,width=self.stage.width,
  biome=self.stage.biome,bridge=false,tunnel=false,chunk=math.floor(math.max(0,progress)/self.config.Chunk),surface=p.surface}
end
function Course:ground(lateral,progress)
 local p=self:point(progress);local shoulder=math.max(0,math.abs(lateral)-p.width/2)
 return p.y+lateral*math.tan(p.bank)-math.min(shoulder*.13,3),lateral,p
end
function Course:frame(state,offset,height,pitch,roll)
 local p=self:sample(state.z);local left=Vector3.new(math.cos(p.heading),0,-math.sin(p.heading))
 local pos=p.position+left*state.x;pos=Vector3.new(pos.X,height or pos.Y,pos.Z)
 return CFrame.new(pos)*CFrame.Angles(0,math.pi+p.heading+state.yaw,0)*CFrame.Angles(pitch or 0,0,roll or 0)
end
function Course:conditions(progress)
 local cfg=self.config.Climate or {};local wet=(self.seed%3==0 and cfg.rainWetness or cfg.dryWetness)or .08
 return {temperature=self.stageId=='SakuraPass'and 18 or 12,wetness=wet,wind=math.sin(progress/1800)*(cfg.windSpeed or 3),friction=1-wet*(cfg.wetGripLoss or .24)}
end
function Course:note(progress)
 local p=self:point(progress+100);local curve=p.curvature
 if math.abs(curve)<.0015 then return 'STRAIGHT · opens'end
 local degree=math.abs(curve);local severity=degree>.03 and 'HAIRPIN'or(degree>.013 and '2'or(degree>.006 and '3'or '5'))
 return (curve>0 and 'LEFT 'or 'RIGHT ')..severity
end
function Course:call(progress,speed)
 local lead=math.max(30,math.abs(speed or 0)*2.5)
 return self:note(progress+lead-100)..string.format(' · %d m',math.floor(lead*self.config.StudMetres+.5))
end
function Course:key(mode,car)return table.concat({self.config.Generation,'original',self.stageId,mode,self.seed,self.length,car},':')end
return Course
