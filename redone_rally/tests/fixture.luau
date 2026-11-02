-- Extend the shared headless fixture. This is not a Roblox rigid-body/renderer emulator.
Vector3.xAxis,Vector3.yAxis,Vector3.zAxis=V.new(1,0,0),V.new(0,1,0),V.new(0,0,1)
function cfMT:ToObjectSpace(other)return self:Inverse()*other end
function cfMT:VectorToWorldSpace(vector)return rotate(self.r,vector)end
function cfMT:VectorToObjectSpace(vector)return self:Inverse():VectorToWorldSpace(vector)end
function cfMT:PointToObjectSpace(point)return self:Inverse()*point end
function CFrame.fromMatrix(p,x,y,z)z=z or x:Cross(y);return cf(p,{x.X,y.X,z.X,x.Y,y.Y,z.Y,x.Z,y.Z,z.Z})end
local oldSubclass=subclass
subclass=function(cls,base)return cls=='VehicleSeat'and base=='BasePart'or oldSubclass(cls,base)end
local oldNew=Instance.new
Instance.new=function(cls,parent)
 local n=oldNew(cls,parent)
 n.Touched=event();n.MouseButton1Click=event();n.MouseButton1Down=event();n.MouseButton1Up=event();n.Ended=event()
 if n:IsA('BasePart')then n.AssemblyLinearVelocity=V.zero;n.AssemblyAngularVelocity=V.zero;n.AssemblyMass=1200 end
 if cls=='VehicleSeat'then n.ThrottleFloat=0;n.SteerFloat=0 end
 return n
end
function methods:ScaleTo(scale)
 local origin=self:GetPivot()
 for _,p in ipairs(self:GetDescendants())do if p:IsA('BasePart')then
  local localCF=origin:ToObjectSpace(p.CFrame);p.CFrame=origin*CFrame.new(localCF.Position*scale)*localCF.Rotation;p.Size=p.Size*scale
 end end
end
function methods:FindFirstAncestorWhichIsA(cls)local p=self.Parent;while p do if p:IsA(cls)then return p end;p=p.Parent end end
function methods:SetNetworkOwner(player)self.p.networkOwner=player end
function methods:Stop()self.Playing=false end
function methods:Emit(count)self.p.emitted=(self.p.emitted or 0)+count end
function methods:LoadAsync()return Enum.AssetFetchStatus.Failure end
local originalPlay=methods.Play
function methods:Play()self.p.plays=(self.p.plays or 0)+1;originalPlay(self)end
local RaycastParams={new=function()return {}end}
local NumberSequence={new=function(...)return {...}end}
local NumberSequenceKeypoint={new=function(...)return {...}end}
local ColorSequenceKeypoint={new=function(...)return {...}end}
local NumberRange={new=function(...)return {...}end}
local PhysicalProperties={new=function(...)return {...}end}
local Random={}
function Random.new(seed)
 local state=seed%2147483647
 local r={}
 function r:NextNumber(a,b)state=(state*16807)%2147483647;local v=state/2147483647;if a then return a+(b-a)*v end;return v end
 function r:NextInteger(a,b)return math.min(b,a+math.floor(self:NextNumber()*(b-a+1)))end
 return r
end
service('SoundService');service('TweenService');service('PhysicsService');service('CollectionService')
function services.PhysicsService:RegisterCollisionGroup()end
function services.PhysicsService:CollisionGroupSetCollidable()end
function services.CollectionService:AddTag()end
function runService:IsServer()return true end
function runService:IsClient()return true end
input.keys={}
function input:IsKeyDown(key)return self.keys[key]==true end
function input:GetFocusedTextBox()return self.focusedText end
function players:GetPlayerFromCharacter(char)for _,p in ipairs(self.list)do if p.Character==char then return p end end end
workspace.Gravity=196.2
function workspace:Raycast(origin,direction,params)
 if self.noGround then return nil end
 if direction.Y>=0 then return nil end
 local t=-origin.Y/direction.Y
 if t<0 or t>1 then return nil end
 return {Instance=self.ground,Distance=(direction*t).Magnitude,Position=origin+direction*t,Normal=Vector3.yAxis,Material=Enum.Material.Asphalt}
end
workspace.ground=Instance.new('Part',workspace);workspace.ground:SetAttribute('SurfaceType','Tarmac')
local function folder(parent,name)local f=Instance.new('Folder',parent);f.Name=name;return f end
local function part(parent,name,size,position,rotation,cls)
 local p=Instance.new(cls or 'Part',parent);p.Name=name;p.Size=size;p.CFrame=CFrame.new(position)*(rotation or CFrame.identity);return p
end
local assetFolder=folder(services.ReplicatedStorage,'BackseatAssets')
local carAssets=folder(assetFolder,'Cars')
for _,name in ipairs({'GroupB','Sedan','Saloon','Hybrid','Coupe'})do
 local car=Instance.new('Model',carAssets);car.Name=name
 car.PrimaryPart=part(car,'Root',V.new(6,3,14),V.zero)
 part(car,'Shell',V.new(6.6,4.4,15),V.new(0,0.9,0),nil,'MeshPart')
 part(car,'Exhaust',V.new(.4,.4,1),V.new(1,-1,7))
end
local wheelAsset=Instance.new('Model',assetFolder);wheelAsset.Name='Wheel'
wheelAsset.PrimaryPart=part(wheelAsset,'Root',V.new(.5,.5,.5),V.zero)
local badRotation=CFrame.Angles(0,math.pi,math.pi/2)
for _,spec in ipairs({{'Tyre',.9,2.296,2.296,-.002},{'Rim',.1386,1.588,1.5793,-.3707},{'Nuts',.057,.4594,.4594,-.4435},{'Barrel',.794,1.4,1.4,-.017}})do
 part(wheelAsset,spec[1],V.new(spec[2],spec[3],spec[4]),V.new(spec[5],0,0),badRotation,'MeshPart')
end
part(wheelAsset,'BrakeDisc',V.new(.08,1.2,1.2),V.new(-.1,0,0))
local propAssets=folder(assetFolder,'Props')
for _,name in ipairs({'Spruce1','Spruce2','Birch1','Rock1','Rock2','MarkerPole','ChevronSign','TimeControlBoard','StartArch','FinishArch','HayBale','ServiceTent','Flag'})do
 local m=Instance.new('Model',propAssets);m.Name=name;m.PrimaryPart=part(m,name..'_native',V.new(3,5,3),V.new(0,2.5,0))
end
local function node(path)
 local n=services[path[1]]
 for i=2,#path do local child=n:FindFirstChild(path[i]);if not child then child=folder(n,path[i])end;n=child end
 return n
end
local function near(a,b,eps)assert(math.abs(a-b)<(eps or 1e-5),tostring(a)..' ~= '..tostring(b))end
local function key(keyCode,down,processed)
 input.keys[keyCode]=down
 if down then input.InputBegan:Fire({KeyCode=keyCode},processed or false)else input.InputEnded:Fire({KeyCode=keyCode},false)end
end
