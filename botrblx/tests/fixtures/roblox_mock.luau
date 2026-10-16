-- Synthetic Roblox API fixtures. No extracted game scripts or recordings.

local warn=print
local now=0
local os={clock=function()return now end}
local Vector3={}
function Vector3.new(x,y,z)
 local v={X=x,Y=y,Z=z}
 return setmetatable(v,{
  __div=function(a,b)return Vector3.new(a.X/b,a.Y/b,a.Z/b)end,
  __mul=function(a,b)return Vector3.new(a.X*b,a.Y*b,a.Z*b)end,
  __sub=function(a,b)return Vector3.new(a.X-b.X,a.Y-b.Y,a.Z-b.Z)end,
  __index=function(t,k)if k=='Magnitude'then return math.sqrt(t.X*t.X+t.Y*t.Y+t.Z*t.Z)end end
 })
end
local function frame(x)
 local v={Position=Vector3.new(x,2,0),LookVector=Vector3.new(1,0,0),UpVector=Vector3.new(0,1,0)}
 function v:ToObjectSpace(_)return {ToAxisAngle=function()return Vector3.new(0,-1,0),.15 end}end
 function v:VectorToWorldSpace(axis)return axis end
 return v
end
local function event()
 local e={listeners={}}
 function e:Connect(callback)
  local c={enabled=true};function c:Disconnect()self.enabled=false end
  table.insert(self.listeners,{connection=c,callback=callback});return c
 end
 function e:Fire()for _,v in ipairs(self.listeners)do if v.connection.enabled then v.callback()end end end
 return e
end
local created={}
local function object(class,name)
 local o={ClassName=class,Name=name or class,children={},Activated=event()}
 function o:GetDescendants()local a={} local function add(parent)for _,child in pairs(parent.children)do a[#a+1]=child;add(child)end end add(self);return a end
 function o:GetChildren()local a={} for _,child in pairs(self.children)do a[#a+1]=child end return a end
 function o:IsA(c)return self.ClassName==c or c=='BasePart'and self.ClassName=='Part'end
 function o:FindFirstChild(n,recursive)if self.children[n]then return self.children[n]end if recursive then for _,child in pairs(self.children)do local found=child:FindFirstChild(n,true)if found then return found end end end end
 function o:FindFirstChildOfClass(c)for _,v in pairs(self.children)do if v:IsA(c)then return v end end end
 function o:WaitForChild(n)return self.children[n]end
 function o:GetFullName()return self.Parent and self.Parent:GetFullName()..'.'..self.Name or self.Name end
 function o:IsDescendantOf(parent)local p=self.Parent while p do if p==parent then return true end p=p.Parent end return false end
 function o:Destroy()self.destroyed=true end
 return setmetatable(o,{__newindex=function(t,k,v)rawset(t,k,v);if k=='Parent'and v then v.children[t.Name]=t end end})
end
local playerGui=object('PlayerGui','PlayerGui')
local player=object('Player','Deadline_coolgun');playerGui.Parent=player
local workspace=object('Workspace','Workspace')
local car=object('Model','Car');car.Parent=workspace
local carRoot=object('Part','Root');carRoot.Parent=car
carRoot.CFrame=frame(0);carRoot.Anchored=true;carRoot.AssemblyLinearVelocity=Vector3.new(0,0,0)
local ball=object('Model','Ball');ball.Parent=workspace
local ballRoot=object('Part','Root');ballRoot.Parent=ball
ballRoot.CFrame=frame(5);ballRoot.Anchored=true;ballRoot.AssemblyLinearVelocity=Vector3.new(0,0,0)
function workspace:GetDescendants()return {car,carRoot,ball,ballRoot}end
local beat=event()
local services={Players={LocalPlayer=player},Workspace=workspace,RunService={Heartbeat=beat}}
local game={PlaceId=101880234193261}
function game:GetService(name)assert(services[name],'Unexpected service '..name);return services[name]end
local Instance={new=function(class)local o=object(class);created[#created+1]=o;return o end}
local UDim2={new=function()return {}end,fromOffset=function()return {}end,fromScale=function()return {}end}
local Color3={new=function()return {}end,fromRGB=function()return {}end}
local Enum={Font={Code=1},TextXAlignment={Left=1},TextYAlignment={Top=1}}
local require=function()error('Probe must not load any game modules')end

local scene=object('Folder','CarSoccer');scene.Parent=workspace
car.Name='RandomCar';ball.Name='RandomBall'
car.Parent=scene;ball.Parent=scene;scene.children.Car=car;scene.children.Ball=ball
car.PrimaryPart=carRoot;ball.PrimaryPart=ballRoot
carRoot.Size=Vector3.new(.2,.2,.2);ballRoot.Size=Vector3.new(.2,.2,.2)
carRoot.Position=carRoot.CFrame.Position;ballRoot.Position=ballRoot.CFrame.Position
local sounds=object('Folder','Sounds');sounds.Parent=scene
local carAnchor=object('Part','CarSound');carAnchor.Parent=sounds;carAnchor.Position=carRoot.Position
local ballAnchor=object('Part','BallSound');ballAnchor.Parent=sounds;ballAnchor.Position=ballRoot.Position
local hud=object('ScreenGui','CarSoccerHud');hud.Parent=playerGui
local speed=object('Frame','BallSpeed');speed.Parent=hud
local label=object('TextLabel','TextLabel');label.Parent=speed;label.Text='0 km/h'
local captured
services.HttpService={JSONEncode=function(self,data)captured=data;return 'MOCK_POSE_JSON'end}
local task={wait=function(dt)
 now=now+dt
 carRoot.CFrame=frame(now*2);carRoot.Position=carRoot.CFrame.Position
 ballRoot.CFrame=frame(5+now*2);ballRoot.Position=ballRoot.CFrame.Position
 label.Text='0.72 km/h'
end}

Enum.KeyCode={W='W',S='S',A='A',D='D',Q='Q',E='E',LeftShift='LeftShift'}
Enum.UserInputType={MouseButton1='MouseButton1',MouseButton2='MouseButton2'}
services.UserInputService={GetFocusedTextBox=function()return nil end,
 IsKeyDown=function(self,key)return key=='LeftShift'and now>=10 and now<20 end,
 IsMouseButtonPressed=function(self,key)return key=='MouseButton1'and now<50 end}
local boost=object('Frame','Boost');boost.Parent=hud
local boostCaption=object('TextLabel','TextLabel');boostCaption.Parent=boost;boostCaption.Text='BOOST'
local boostStyle=object('Frame','BoostS1');boostStyle.Parent=boost
local boostLabel=object('TextLabel','TextLabel');boostLabel.Parent=boostStyle;boostLabel.Text='100'
local didRebind=false
local function move(dt)
 now=now+dt
 carRoot.CFrame=frame(now*2);carRoot.Position=carRoot.CFrame.Position
 ballRoot.CFrame=frame(5+now*2+(now>=25 and 1000 or 0));ballRoot.Position=ballRoot.CFrame.Position
 carAnchor.Position=carRoot.Position;ballAnchor.Position=ballRoot.Position
 boostLabel.Text=tostring(math.max(0,math.floor(100-now*2)))
 label.Text='0.72 km/h'
 beat:Fire()
end

Enum.KeyCode.F6='F6';Enum.KeyCode.F8='F8'
services.UserInputService.InputBegan=event()
local packets={}
local encoded={hello={protocol=1,token='local-test-token'}}
local counter=0
services.HttpService.JSONEncode=function(self,data)
 counter=counter+1;local key=tostring(counter);encoded[key]=data;return key
end
services.HttpService.JSONDecode=function(self,data)return assert(encoded[data],data)end
local request=function(options)
 if string.find(options.Url,'/hello',1,true)then return {StatusCode=200,Body='hello'}end
 assert(options.Method=='POST'and options.Headers['X-Bridge-Token']=='local-test-token')
 local p=assert(encoded[options.Body]);packets[#packets+1]=p
 assert(p.place==101880234193261 and p.account=='Deadline_coolgun')
 if p.enabled then
  for _,item in ipairs(created)do
   -- The independent launcher/error panel is not a bot control button.
   if item.ClassName=='TextButton'and item.Text~='Close launcher'then assert(item.Visible==false,'Boost could click a bot UI button')end
  end
 end
 local status=p.enabled and(p.valid and'RUNNING'or'WAITING')or'PAUSED'
 local reply={status=status,disarmed=false,keys={},ms=1}
 counter=counter+1;local key=tostring(counter);encoded[key]=reply
 return {StatusCode=200,Body=key}
end
local function click(text)
 for _,v in ipairs(created)do
  if v.ClassName=='TextButton'and v.Text==text then v.Activated:Fire();return end
 end
 error('Button missing: '..text)
end
local startedBot=false
task.spawn=function(callback)callback()end
