-- Clone visual templates only; source instances stay untouched.
local ImportAssets={}
local function safeClone(model,maxParts)
 local clone=model:Clone();local count=0
 for _,item in ipairs(clone:GetDescendants())do
  if item:IsA('LuaSourceContainer')or item:IsA('RemoteEvent')or item:IsA('RemoteFunction')or item:IsA('ProximityPrompt')or item:IsA('PackageLink')or item:IsA('Constraint')or item:IsA('JointInstance')then item:Destroy()
  elseif item:IsA('BasePart')then count+=1;item.Anchored=true;item.CanCollide=false;item.CanTouch=false;item.CanQuery=false;item.CastShadow=false
  elseif item:IsA('Sound')or item:IsA('ParticleEmitter')or item:IsA('Light')or item:IsA('Trail')or item:IsA('Beam')then item:Destroy()end
 end
 if count>maxParts then clone:Destroy();return nil end
 return clone
end
function ImportAssets.harvest(root)
 if not root:FindFirstChild('ImportedAudio')then
  local audio=Instance.new('Folder');audio.Name='ImportedAudio';audio.Parent=root
  -- Idle, mid-load and high-load loops referenced by the supplied car audio bank.
  for i,id in ipairs({'rbxassetid://79745038579097','rbxassetid://112975795144083','rbxassetid://99444077339790'})do
   local sound=Instance.new('Sound');sound.Name=({'Idle','Run','High'})[i]
   sound.SoundId=id;sound.Looped=true;sound.Volume=0;sound.Parent=audio
  end
 end
 if root:FindFirstChild("ImportedCars") then return #root.ImportedCars:GetChildren(),#root.ImportedProps:GetChildren() end
 local rs=game:GetService('ReplicatedStorage');local assets=rs:FindFirstChild('Assets')
 if not assets then return 0,0 end
 local cars,props=0,0
 local carFolder=Instance.new('Folder');carFolder.Name='ImportedCars';carFolder.Parent=root
 local propFolder=Instance.new('Folder');propFolder.Name='ImportedProps';propFolder.Parent=root
 local originals=assets:FindFirstChild('Cars')
 for _,name in ipairs({'Hatch','OrsoSafari','Coupe'})do
  local source=originals and originals:FindFirstChild(name)
  local exterior=source and source:FindFirstChild('Exterior');local body=source and source:FindFirstChild('Body')
  if exterior and body and body:IsA('BasePart')then
   local clone=safeClone(exterior,180)
   if clone then
    clone.Name=name;local reference=body:Clone();reference.Name='SkinRoot';reference.Transparency=1;reference.Anchored=true;reference.CanCollide=false
    reference:ClearAllChildren();reference.Parent=clone;clone.PrimaryPart=reference;clone:PivotTo(CFrame.identity);clone.Parent=carFolder;cars+=1
   end
  end
 end
 local stage=assets:FindFirstChild('Stage');local forest=stage and stage:FindFirstChild('Forest')
 for _,name in ipairs({'SpruceYoung1','SpruceSlim1','Birch1','Rock1','Bush1'})do
  local source=forest and forest:FindFirstChild(name)
  if source and source:IsA('Model')then
   local clone=safeClone(source,24)
   if clone then
    local cf,size=clone:GetBoundingBox();clone.WorldPivot=CFrame.new(cf.Position.X,cf.Position.Y-size.Y/2,cf.Position.Z)
    clone:PivotTo(CFrame.identity);clone.Parent=propFolder;props+=1
   end
  end
 end
 return cars,props
end
return ImportAssets
