-- Replay-only camera rig. Driving cameras are owned by the driving controller.
-- No per-frame instances, raycasts or network traffic; director shots are local.
local Rig={};Rig.__index=Rig
local names={'COCKPIT','CHASE','ORBIT','DIRECTOR','FREECAM'}
local function clampDt(dt)return math.clamp(tonumber(dt)or 0,0,.1)end
local function flat(v)
 local f=Vector3.new(v.X,0,v.Z)
 return f.Magnitude>.001 and f.Unit or Vector3.new(0,0,-1)
end
function Rig.new(camera,uis,options)
 assert(camera and uis,'Replay camera requires camera and input service')
 local self=setmetatable({camera=camera,input=uis,options=options or {},mode=2,held={},connections={},angle=0,pitch=.3,distance=22,
  yaw=0,freePitch=0,freeSpeed=35,fov=70,alive=true,mouseHeld=false,frames=0},Rig)
 self.saved={cameraType=camera.CameraType,cframe=camera.CFrame,fov=camera.FieldOfView,
  mouseBehavior=uis.MouseBehavior,mouseIcon=uis.MouseIconEnabled}
 local function connect(signal,fn)self.connections[#self.connections+1]=signal:Connect(fn)end
 connect(uis.InputBegan,function(event,processed)
  if processed or uis:GetFocusedTextBox()then return end
  self:controlInput(event,Enum.UserInputState.Begin)
 end)
 connect(uis.InputEnded,function(event)
  self:controlInput(event,Enum.UserInputState.End)
 end)
 connect(uis.InputChanged,function(event)self:inputChanged(event)end)
 connect(uis.WindowFocusReleased,function()self.held={};self.mouseHeld=false;self:releaseMouse()end)
 return self
end
-- ContextActionService sinks the game's movement keys, marking raw UIS events
-- processed. The owning controller forwards those keys through this method.
function Rig:canInput()
 local allowed=self.alive and not self.input:GetFocusedTextBox()and (not self.options.canInput or self.options.canInput())
 if not allowed then self.held={};self.mouseHeld=false;self:releaseMouse()end
 return allowed
end
function Rig:controlInput(event,state)
 if not self:canInput()then return end
 local ended=state==Enum.UserInputState.End or state==Enum.UserInputState.Cancel
 if not ended and self.input:GetFocusedTextBox()then return end
 self.held[event.KeyCode.Name]=not ended or nil
 if event.UserInputType==Enum.UserInputType.MouseButton2 then
  self.mouseHeld=not ended;if ended then self:releaseMouse()end
 end
end
function Rig:name()return names[self.mode]end
function Rig:hint()
 if self.mode==5 then return 'RMB look · WASD move · Q/E down/up · Shift fast · wheel FOV'end
 if self.mode==3 then return 'RMB orbit · wheel distance'end
 if self.mode==4 then return 'Automatic roadside shots · C switch camera'end
 return 'C switch camera · P pause · , . seek'
end
function Rig:releaseMouse()
 if self.mouseCaptured then
  self.input.MouseBehavior=self.saved.mouseBehavior
  self.input.MouseIconEnabled=self.saved.mouseIcon
  self.mouseCaptured=false
 end
end
function Rig:setMode(mode)
 local n=type(mode)=='number'and mode or table.find(names,tostring(mode):upper())
 if not n or n~=math.floor(n)or n<1 or n>#names then return self:name()end
 self.mode=n;self.initialized=false;self.shot=nil;self.freeFrame=nil
 self:releaseMouse()
 return self:name()
end
function Rig:cycle()return self:setMode(self.mode%#names+1)end
function Rig:inputChanged(event)
 if not self:canInput()or event.UserInputType~=Enum.UserInputType.MouseWheel then return end
 local z=event.Position.Z
 if self.mode==5 then self.fov=math.clamp(self.fov-z*3,25,100)
 elseif self.mode==3 then self.distance=math.clamp(self.distance-z*2,6,85)end
end
function Rig:shift(delta)
 if self.freeFrame then self.freeFrame+=delta end
 if self.shot then self.shot.position+=delta end
 if self.lastPosition then self.lastPosition+=delta end
end
function Rig:_mouseDelta()
 if not self:canInput()then return 0,0 end
 if not self.mouseHeld and not self.input:IsMouseButtonPressed(Enum.UserInputType.MouseButton2)then self:releaseMouse();return 0,0 end
 if not self.mouseCaptured then self.mouseCaptured=true end
 self.input.MouseBehavior=Enum.MouseBehavior.LockCurrentPosition;self.input.MouseIconEnabled=false
 local d=self.input:GetMouseDelta();return d.X,d.Y
end
function Rig:update(cf,state,dt,time)
 if not self.alive then return self.camera.CFrame end
 dt=clampDt(dt);time=tonumber(time)or 0;state=state or {}
 local camera=self.camera;camera.CameraType=Enum.CameraType.Scriptable
 local speed=math.abs(state.v or 0);local forward=cf.LookVector;local up=Vector3.new(0,1,0)
 local discontinuity=self.lastTime and (math.abs(time-self.lastTime)>1 or (self.lastPosition and (cf.Position-self.lastPosition).Magnitude>180))
 if discontinuity then self.initialized=false;self.shot=nil end
 self.lastTime=time;self.lastPosition=cf.Position
 local mx,my=self:_mouseDelta();local target;local fov=70
 if self.mode==5 then
  if not self.freeFrame then
   self.freeFrame=camera.CFrame
   local look=self.freeFrame.LookVector
   self.yaw=math.atan2(-look.X,-look.Z);self.freePitch=math.asin(math.clamp(look.Y,-1,1))
  end
  self.yaw-=mx*.003;self.freePitch=math.clamp(self.freePitch-my*.003,-1.5,1.5)
  local rotation=CFrame.Angles(0,self.yaw,0)*CFrame.Angles(self.freePitch,0,0)
  local h=self.held
  local move=Vector3.new(((h.D or h.Right)and 1 or 0)-((h.A or h.Left)and 1 or 0),0,
   ((h.S or h.Down)and 1 or 0)-((h.W or h.Up)and 1 or 0))
  if move.Magnitude>1 then move=move.Unit end
  local vertical=((h.E or h.PageUp)and 1 or 0)-((h.Q or h.PageDown)and 1 or 0)
  local rate=self.freeSpeed*((h.LeftShift or h.RightShift)and 3 or 1)*((h.LeftAlt or h.RightAlt)and .2 or 1)
  local delta=(rotation.RightVector*move.X+rotation.LookVector*(-move.Z)+up*vertical)*dt*rate
  self.freeFrame=CFrame.new(self.freeFrame.Position+delta)*rotation;target=self.freeFrame;fov=self.fov
 elseif self.mode==1 then
  -- Car pose already includes suspension pitch and roll; replay preserves it.
  local offset=self.options.cockpitOffset or Vector3.new(-.7,2.05,.15)
  local pos=cf*offset;target=CFrame.lookAt(pos,pos+forward*45,cf.UpVector);fov=self.options.cockpitFov or 76
 elseif self.mode==3 then
  self.angle-=mx*.004;self.pitch=math.clamp(self.pitch-my*.003,-.05,1.2)
  local horizontal=math.cos(self.pitch)*self.distance
  local offset=Vector3.new(math.sin(self.angle)*horizontal,math.sin(self.pitch)*self.distance+2,math.cos(self.angle)*horizontal)
  target=CFrame.lookAt(cf.Position+offset,cf.Position+up);fov=65
 elseif self.mode==4 then
  local segment=math.floor(time/6)
  if not self.shot or self.shot.segment~=segment then
   local front=flat(forward);local right=flat(cf.RightVector);local choice=segment%4
   local ahead=math.clamp(speed*1.7,18,70)
   local position
   if choice==0 then position=cf.Position+front*ahead+right*18+up*4
   elseif choice==1 then position=cf.Position-front*15-right*27+up*9
   elseif choice==2 then position=cf.Position+front*26+right*35+up*20
   else position=cf.Position-front*22+right*14+up*3 end
   self.shot={segment=segment,position=position};self.initialized=false
  end
  target=CFrame.lookAt(self.shot.position,cf.Position+up*.8+forward*math.min(4,speed*.025));fov=48
 else
  local pos=cf.Position-forward*(15+speed*.035)+up*5.4
  target=CFrame.lookAt(pos,cf.Position+forward*7+up*1.3);fov=68+math.min(8,speed*.045)
 end
 local smooth=self.mode==1 and 18 or self.mode==3 and 14 or self.mode==4 and 12 or 8
 camera.CFrame=self.initialized and self.mode~=5 and camera.CFrame:Lerp(target,1-math.exp(-smooth*dt))or target
 camera.FieldOfView=fov;self.initialized=true;self.frames+=1
 return camera.CFrame
end
function Rig:destroy()
 if not self.alive then return end;self.alive=false
 for _,connection in ipairs(self.connections)do connection:Disconnect()end;self.connections={};self.held={}
 self:releaseMouse()
 self.camera.CameraType=self.saved.cameraType;self.camera.CFrame=self.saved.cframe;self.camera.FieldOfView=self.saved.fov
end
return Rig
