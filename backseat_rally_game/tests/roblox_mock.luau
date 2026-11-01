-- Headless test doubles; no claim to emulate the Roblox renderer or rigid-body engine.
local nativeOS=os;local now=0;local os={clock=function()return now end,time=function()return 1793577600+math.floor(now)end}
local warnings={};local function warn(text)warnings[#warnings+1]=text end
local function event()
 local e={listeners={}}
 function e:Connect(fn)local c={active=true};function c:Disconnect()self.active=false end;self.listeners[#self.listeners+1]={fn=fn,c=c};return c end
 function e:Fire(...)for _,l in ipairs(table.clone(self.listeners))do if l.c.active then l.fn(...)end end end
 return e
end
local V={};local vm={}
function V.new(x,y,z)return setmetatable({X=x or 0,Y=y or 0,Z=z or 0,__kind='Vector3'},vm)end
V.zero=V.new();local Vector3=V;local Vector2={new=function(x,y)return V.new(x,y,0)end}
function vm.__add(a,b)return V.new(a.X+b.X,a.Y+b.Y,a.Z+b.Z)end
function vm.__sub(a,b)return V.new(a.X-b.X,a.Y-b.Y,a.Z-b.Z)end
function vm.__unm(a)return V.new(-a.X,-a.Y,-a.Z)end
function vm.__mul(a,b)if type(a)=='number'then return V.new(a*b.X,a*b.Y,a*b.Z)end;return V.new(a.X*b,a.Y*b,a.Z*b)end
function vm.__div(a,b)return a*(1/b)end
function vm:Dot(b)return self.X*b.X+self.Y*b.Y+self.Z*b.Z end
function vm:Cross(b)return V.new(self.Y*b.Z-self.Z*b.Y,self.Z*b.X-self.X*b.Z,self.X*b.Y-self.Y*b.X)end
function vm:Lerp(b,t)return self+(b-self)*t end
vm.__index=function(a,k)if k=='Magnitude'then return math.sqrt(a:Dot(a))elseif k=='Unit'then return a/math.max(a.Magnitude,1e-12)end;return vm[k]end
local cfMT={};local CFrame={}
local function cf(p,r)return setmetatable({Position=p,r=r or {1,0,0,0,1,0,0,0,1},__kind='CFrame'},cfMT)end
function CFrame.new(x,y,z)if type(x)=='table'then return cf(x)end;return cf(V.new(x,y,z))end
CFrame.identity=CFrame.new()
local function rotate(r,v)return V.new(r[1]*v.X+r[2]*v.Y+r[3]*v.Z,r[4]*v.X+r[5]*v.Y+r[6]*v.Z,r[7]*v.X+r[8]*v.Y+r[9]*v.Z)end
function cfMT.__mul(a,b)
 if b.__kind=='Vector3' then return a.Position+rotate(a.r,b)end
 local r={};for i=0,2 do for j=0,2 do local n=0;for k=0,2 do n+=a.r[i*3+k+1]*b.r[k*3+j+1]end;r[i*3+j+1]=n end end
 return cf(a.Position+rotate(a.r,b.Position),r)
end
function cfMT.__add(a,b)return cf(a.Position+b,a.r)end
function cfMT.__sub(a,b)return cf(a.Position-b,a.r)end
function cfMT:Inverse()
 local r=self.r;local t={r[1],r[4],r[7],r[2],r[5],r[8],r[3],r[6],r[9]};return cf(rotate(t,-self.Position),t)
end
function cfMT:PointToWorldSpace(p)return self*p end
function cfMT:Lerp(b,t)
 local r={};for i=1,9 do r[i]=self.r[i]+(b.r[i]-self.r[i])*t end
 return cf(self.Position:Lerp(b.Position,t),r)
end
cfMT.__index=function(a,k)
 if k=='LookVector'then return V.new(-a.r[3],-a.r[6],-a.r[9])elseif k=='RightVector'then return V.new(a.r[1],a.r[4],a.r[7])elseif k=='UpVector'then return V.new(a.r[2],a.r[5],a.r[8])elseif k=='Rotation'then return cf(V.zero,a.r)end
 return cfMT[k]
end
function CFrame.Angles(x,y,z)
 local sx,cx,sy,cy,sz,cz=math.sin(x),math.cos(x),math.sin(y),math.cos(y),math.sin(z),math.cos(z)
 return cf(V.zero,{1,0,0,0,cx,-sx,0,sx,cx})*cf(V.zero,{cy,0,sy,0,1,0,-sy,0,cy})*cf(V.zero,{cz,-sz,0,sz,cz,0,0,0,1})
end
function CFrame.lookAt(p,target,upVector)
 local back=(p-target).Unit;local right=(upVector or V.new(0,1,0)):Cross(back).Unit;local up=back:Cross(right)
 return cf(p,{right.X,up.X,back.X,right.Y,up.Y,back.Y,right.Z,up.Z,back.Z})
end
local function enumGroup()return setmetatable({},{__index=function(t,k)local n={Name=k,Value=k};rawset(t,k,n);return n end})end
local Enum=setmetatable({},{__index=function(t,k)local group=enumGroup();rawset(t,k,group);return group end})
Enum.RenderPriority.Last={Value=2000}
local Color3={new=function(r,g,b)return {R=r,G=g,B=b,__kind='Color3'}end}
function Color3.fromRGB(r,g,b)return Color3.new(r/255,g/255,b/255)end
local ColorSequence={new=function(...)return {...}end}
local UDim={new=function(s,o)return {Scale=s,Offset=o}end}
local UDim2={new=function(xs,xo,ys,yo)return {X=UDim.new(xs,xo),Y=UDim.new(ys,yo)}end}
function UDim2.fromOffset(x,y)return UDim2.new(0,x,0,y)end
function UDim2.fromScale(x,y)return UDim2.new(x,0,y,0)end
local function typeof(v)return type(v)=='table'and v.__kind or type(v)end
local queue={}
local task={}
local function schedule(co,at)queue[#queue+1]={co=co,at=at}end
function task.spawn(fn,...)local args={...};schedule(coroutine.create(function()fn(table.unpack(args))end),now)end
function task.defer(fn,...)task.spawn(fn,...)end
function task.delay(dt,fn)schedule(coroutine.create(fn),now+dt)end
function task.wait(dt)return coroutine.yield(dt or 1/60)end
local function pump()
 local again=true;local guard=0
 while again do
  again=false;guard+=1;assert(guard<1000,'Task loop did not yield')
  for i=#queue,1,-1 do local job=queue[i];if job.at<=now then
   table.remove(queue,i);local ok,delay=coroutine.resume(job.co,1/60);assert(ok,delay)
   if coroutine.status(job.co)~='dead'then schedule(job.co,now+math.max(.001,tonumber(delay)or 1/60))end;again=true
  end end
 end
end
local methods={};local created={};local Instance={};local objects={}
local function subclass(cls,base)
 if cls==base then return true end
 if base=='BasePart'then return table.find({'Part','Seat','SpawnLocation','MeshPart','WedgePart'},cls)~=nil end
 if base=='BaseScript'then return cls=='Script'or cls=='LocalScript'end
 if base=='LuaSourceContainer'then return cls=='ModuleScript'or subclass(cls,'BaseScript')end
 if base=='PostEffect'then return table.find({'BloomEffect','BlurEffect','ColorCorrectionEffect','DepthOfFieldEffect','SunRaysEffect'},cls)~=nil end
 return false
end
function Instance.new(cls,parent)
 local props={ClassName=cls,Name=cls,children={},attrs={},signals={},Enabled=true,CFrame=CFrame.identity,Size=V.new(1,1,1),Transparency=0,LocalTransparencyModifier=0,Visible=true,Text='',Disabled=false}
 local obj
 obj=setmetatable({p=props},{__index=function(_,k)
  if methods[k]then return methods[k]end
  if k=='Position'and subclass(cls,'BasePart')then return props.CFrame.Position end
  if k=='AbsolutePosition'then return V.zero end
  if k=='AbsoluteSize'then return Vector2.new(1140,680)end
  if props[k]~=nil then return props[k]end
  for _,child in ipairs(props.children)do if child.Parent==obj and child.Name==k then return child end end
  if table.find({'ChildAdded','CharacterAdded','OnServerEvent','OnClientEvent','Activated','InputBegan','InputEnded','InputChanged','WindowFocusReleased','WindowFocused','PlayerAdded','PlayerRemoving','RenderStepped','Heartbeat'},k)then props[k]=event();return props[k]end
  return nil
 end,__newindex=function(_,k,v)
  if k=='Parent'and props.Parent~=v then
   if props.Parent then local list=props.Parent.p.children;local i=table.find(list,obj);if i then table.remove(list,i)end end
   if v then v.p.children[#v.p.children+1]=obj end
  end
  props[k]=v
  if k=='Parent'and v and v.p.ChildAdded then v.p.ChildAdded:Fire(obj)end
  if props.signals[k]then props.signals[k]:Fire()end
 end})
 created[#created+1]=obj;if parent then obj.Parent=parent end;return obj
end
function methods:IsA(cls)return subclass(self.ClassName,cls)end
function methods:GetChildren()return table.clone(self.p.children)end
function methods:GetDescendants()local all={};local function add(n)for _,c in ipairs(n:GetChildren())do all[#all+1]=c;add(c)end end;add(self);return all end
function methods:FindFirstChild(name)for _,c in ipairs(self:GetChildren())do if c.Name==name then return c end end end
function methods:WaitForChild(name)local result=assert(self:FindFirstChild(name),'Missing '..self.Name..'.'..name);return result end
function methods:FindFirstChildOfClass(cls)for _,c in ipairs(self:GetChildren())do if c:IsA(cls)then return c end end end
function methods:Destroy()for _,c in ipairs(self:GetChildren())do c:Destroy()end;self.Parent=nil;self.p.destroyed=true end
function methods:ClearAllChildren()for _,c in ipairs(self:GetChildren())do c:Destroy()end end
function methods:GetPivot()return self.PrimaryPart and self.PrimaryPart.CFrame or self.WorldPivot or CFrame.identity end
function methods:PivotTo(target)
 local delta=target*self:GetPivot():Inverse()
 for _,p in ipairs(self:GetDescendants())do if p:IsA('BasePart')then p.CFrame=delta*p.CFrame end end
 if self.PrimaryPart then self.PrimaryPart.CFrame=target end
 self.WorldPivot=target
end
function methods:GetBoundingBox()return self:GetPivot(),V.new(6,6,10)end
function methods:SetAttribute(k,v)self.p.attrs[k]=v end
function methods:GetAttribute(k)return self.p.attrs[k]end
function methods:GetPropertyChangedSignal(k)self.p.signals[k]=self.p.signals[k]or event();return self.p.signals[k]end
function methods:GetFullName()return self.Parent and self.Parent:GetFullName()..'.'..self.Name or self.Name end
function methods:Clone()
 local mapping={}
 local function clone(n)local out=Instance.new(n.ClassName);mapping[n]=out
  for k,v in pairs(n.p)do if not table.find({'Parent','children','attrs','signals','PrimaryPart'},k)then out[k]=v end end
  for k,v in pairs(n.p.attrs)do out:SetAttribute(k,v)end
  for _,c in ipairs(n:GetChildren())do local q=clone(c);q.Parent=out end
  return out
 end
 local out=clone(self);for old,new in pairs(mapping)do if old.PrimaryPart then new.PrimaryPart=mapping[old.PrimaryPart]end end;return out
end
function methods:Sit(h)self.Occupant=h;h.SeatPart=self;h.Sit=true end
function methods:Play()self.Playing=true end
local services={};local game={GameId=123,PlaceId=456}
function game:GetService(name)local result=assert(services[name],'Missing service '..name);return result end
function game:BindToClose(fn)self.onClose=fn end
local function service(name)local s=Instance.new(name);s.Name=name;services[name]=s;return s end
local workspace=service('Workspace');workspace.CurrentCamera=Instance.new('Camera');workspace.CurrentCamera.ViewportSize=Vector2.new(1280,720)
function workspace:GetServerTimeNow()return now end
service('ReplicatedStorage');service('ReplicatedFirst');service('ServerScriptService');service('ServerStorage');service('StarterGui');service('Lighting')
local content=service('ContentProvider');content.calls={}
function content:PreloadAsync(items,callback)
 self.calls[#self.calls+1]=items
 local status=self.status or Enum.AssetFetchStatus.Success
 if self.delay and self.delay>0 then task.wait(self.delay)end
 if self.fail then error('Asset unavailable')end
 for _,item in ipairs(items)do callback(item.Name,status)end
end
local sp=service('StarterPlayer');local sps=Instance.new('StarterPlayerScripts',sp);sps.Name='StarterPlayerScripts';local scs=Instance.new('StarterCharacterScripts',sp);scs.Name='StarterCharacterScripts'
local players=service('Players');players.list={}
function players:GetPlayers()return table.clone(self.list)end
function players:GetPlayerByUserId(id)for _,p in ipairs(self.list)do if p.UserId==id then return p end end end
local function newPlayer(id)
 local p=Instance.new('Player',players);p.Name='Player'..id;p.DisplayName=p.Name;p.UserId=id
 local pg=Instance.new('PlayerGui',p);pg.Name='PlayerGui';local char=Instance.new('Model',workspace);char.Name='Character'
 local h=Instance.new('Humanoid',char);local base=Instance.new('Part',char);char.PrimaryPart=base;p.Character=char
 players.list[#players.list+1]=p;return p
end
local localPlayer=newPlayer(101);players.LocalPlayer=localPlayer
function methods:FireClient(player,...)self.p.sent=self.p.sent or {};self.p.sent[#self.p.sent+1]={player,...};if player==localPlayer then self.OnClientEvent:Fire(...)end end
function methods:FireAllClients(...)self.OnClientEvent:Fire(...)end
function methods:FireServer(...)self.OnServerEvent:Fire(localPlayer,...)end
function methods:InvokeServer(...)return self.OnServerInvoke(localPlayer,...)end
local runService=service('RunService');function runService:IsStudio()return true end;function runService:IsRunning()return true end
runService.bound={}
function runService:BindToRenderStep(name,priority,fn)self.bound[name]=fn end
function runService:UnbindFromRenderStep(name)self.bound[name]=nil end
local context=service('ContextActionService');context.bound={}
function context:BindActionAtPriority(name,fn)self.bound[name]=fn end
function context:UnbindAction(name)self.bound[name]=nil end
local input=service('UserInputService');input.TouchEnabled=false
function input:GetFocusedTextBox()return nil end
function input:IsMouseButtonPressed()return false end
function input:GetMouseDelta()return Vector2.new(0,0)end
local function deep(t)if type(t)~='table'then return t end;local out={};for k,v in pairs(t)do out[k]=deep(v)end;return out end
local datastore=service('DataStoreService');datastore.stores={};datastore.fail=false
function datastore:GetDataStore(name)
 if self.stores[name]then return self.stores[name]end
 local store={values={},writes=0}
 function store:GetAsync(k)assert(not datastore.fail,'API disabled');return deep(self.values[k])end
 function store:UpdateAsync(k,fn)assert(not datastore.fail,'API disabled');self.writes+=1;local v=fn(deep(self.values[k]));self.values[k]=deep(v);return deep(v)end
 self.stores[name]=store;return store
end
local http=service('HttpService');http.counter=0
function http:GenerateGUID()self.counter+=1;return 'test-run-'..self.counter end
local function advance(seconds,render)
 local steps=math.ceil(seconds*60)
 for _=1,steps do now+=1/60;pump();runService.Heartbeat:Fire(1/60);if render then runService.RenderStepped:Fire(1/60);for _,fn in pairs(runService.bound)do fn(1/60)end end;pump()end
end
local modules,cache={},{};local require
require=function(node)if cache[node]then return cache[node]end;local result=assert(modules[node],'Unknown module '..tostring(node and node.Name))(node);cache[node]=result;return result end
