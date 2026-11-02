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
function ImportAssets.harvest(root,requested)
 if require(script.Parent.Config).ExternalAudio and not root:FindFirstChild('ImportedAudio')then
  local audio=Instance.new('Folder');audio.Name='ImportedAudio';audio.Parent=root
  -- Idle, mid-load and high-load loops referenced by the supplied car audio bank.
  for i,id in ipairs({'rbxassetid://79745038579097','rbxassetid://112975795144083','rbxassetid://99444077339790'})do
   local sound=Instance.new('Sound');sound.Name=({'Idle','Run','High'})[i]
   sound.SoundId=id;sound.Looped=true;sound.Volume=0;sound.Parent=audio
  end
 end
 local rs=game:GetService('ReplicatedStorage');local assets=rs:FindFirstChild('Assets')
 if not assets then return 0,0 end
 local cars,props=0,0
 local carFolder=root:FindFirstChild('ImportedCars')
 if not carFolder then carFolder=Instance.new('Folder');carFolder.Name='ImportedCars';carFolder.Parent=root end
 local propFolder=root:FindFirstChild('ImportedProps')
 if not propFolder then propFolder=Instance.new('Folder');propFolder.Name='ImportedProps';propFolder.Parent=root end
 local originals=assets:FindFirstChild('Cars')
 local names={};for _,car in ipairs(require(script.Parent.Config).Cars)do names[#names+1]=car.template end
 -- Keep Hatch as a compatible source for older installed payloads.
 if not table.find(names,'Hatch')then names[#names+1]='Hatch'end
 for _,name in ipairs(names)do
  local source=originals and originals:FindFirstChild(name)
  local exterior=source and source:FindFirstChild('Exterior');local body=source and source:FindFirstChild('Body')
  if (not requested or requested==name)and not carFolder:FindFirstChild(name)and exterior and body and body:IsA('BasePart')then
   local clone=safeClone(exterior,600)
   if clone then
    local interior=source:FindFirstChild('Interior');if interior then local cabin=safeClone(interior,600);if cabin then cabin.Parent=clone end end
    clone.Name=name;local reference=body:Clone();reference.Name='SkinRoot';reference.Transparency=1;reference.Anchored=true;reference.CanCollide=false
    reference:ClearAllChildren()
    local wheels=source:FindFirstChild('Wheels');local centre=Vector3.zero;local count=0
    if wheels then for _,wheel in ipairs(wheels:GetChildren())do if wheel:IsA('Model')or wheel:IsA('BasePart')then centre+=wheel:GetPivot().Position;count+=1 end end end
    if count==4 then reference.CFrame=CFrame.new(centre/4)*body.CFrame.Rotation end
    for _,eyeName in ipairs({'DriverEye','CoDriverEye'})do
     local eye=body:FindFirstChild(eyeName)
     if eye and eye:IsA('Attachment')then local copy=eye:Clone();copy.CFrame=reference.CFrame:Inverse()*body.CFrame*eye.CFrame;copy.Parent=reference end
    end
    if wheels then local group=Instance.new('Folder');group.Name='OriginalWheels';group.Parent=clone
     for _,wheel in ipairs(wheels:GetChildren())do if wheel:IsA('Model')then local copy=safeClone(wheel,64);if copy then copy.Parent=group end end end
    end
    reference.Parent=clone;clone.PrimaryPart=reference;clone:PivotTo(CFrame.identity);clone.Parent=carFolder;cars+=1
   end
  end
 end
 local stage=assets:FindFirstChild('Stage');local forest=stage and stage:FindFirstChild('Forest')
 for _,name in ipairs({'SpruceYoung1','SpruceSlim1','Birch1','Rock1','Bush1'})do
  local source=forest and forest:FindFirstChild(name)
  if not propFolder:FindFirstChild(name)and source and source:IsA('Model')then
   local clone=safeClone(source,24)
   if clone then
    local cf,size=clone:GetBoundingBox();clone.WorldPivot=CFrame.new(cf.Position.X,cf.Position.Y-size.Y/2,cf.Position.Z)
    clone:PivotTo(CFrame.identity);clone.Parent=propFolder;props+=1
   end
  end
 end
 return #carFolder:GetChildren(),#propFolder:GetChildren()
end
function ImportAssets.getCar(root,name)
 local library=root:FindFirstChild('ImportedCars');local found=library and library:FindFirstChild(name)
 if not found then ImportAssets.harvest(root,name);library=root:FindFirstChild('ImportedCars');found=library and library:FindFirstChild(name)end
 return found
end
return ImportAssets
