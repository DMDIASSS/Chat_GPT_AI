-- Studio-only inspection of the project currently open. No remote calls or module execution.
local Collector={}
local Run=game:GetService('RunService')
local Http=game:GetService('HttpService')
local Store=game:GetService('ServerStorage')
local recording
local function studio()assert(Run:IsStudio(),'Use this collector in Roblox Studio, in a project you can edit.')end
local function read(object,key)
 local ok,value=pcall(function()return object[key]end)
 if ok then return value end
end
local function encode(value,depth)
 depth=depth or 0;if depth>5 then return '<depth limit>'end
 local kind=typeof(value)
 if kind=='number'then return value==value and math.abs(value)<math.huge and value or tostring(value)end
 if kind=='string'or kind=='boolean'then return value end
 if kind=='Vector3'then return {value.X,value.Y,value.Z}end
 if kind=='Color3'then return {value.R,value.G,value.B}end
 if kind=='CFrame'then return {value:GetComponents()}end
 if kind=='PhysicalProperties'then return {density=value.Density,friction=value.Friction,elasticity=value.Elasticity,frictionWeight=value.FrictionWeight,elasticityWeight=value.ElasticityWeight}end
 if kind=='Instance'then return value:GetFullName()end
 if kind=='table'then local out={};for k,v in pairs(value)do out[tostring(k)]=encode(v,depth+1)end;return out end
 return value~=nil and tostring(value)or nil
end
local fields={
 BasePart={'Size','CFrame','Anchored','CanCollide','CollisionGroup','Massless','CustomPhysicalProperties','CurrentPhysicalProperties','AssemblyMass','AssemblyCenterOfMass','AssemblyLinearVelocity','AssemblyAngularVelocity','Color','Material','Transparency'},
 MeshPart={'MeshId','TextureID','RenderFidelity','CollisionFidelity'},
 SpecialMesh={'MeshId','TextureId','MeshType','Scale','Offset'},
 Attachment={'CFrame','Axis','SecondaryAxis'},
 SpringConstraint={'FreeLength','Stiffness','Damping','LimitsEnabled','MinLength','MaxLength','CurrentLength','Attachment0','Attachment1'},
 HingeConstraint={'ActuatorType','AngularVelocity','MotorMaxTorque','ServoMaxTorque','TargetAngle','CurrentAngle','Attachment0','Attachment1'},
 CylindricalConstraint={'AngularActuatorType','AngularVelocity','MotorMaxAngularAcceleration','MotorMaxTorque','Velocity','TargetPosition','Attachment0','Attachment1'},
 VehicleSeat={'ThrottleFloat','SteerFloat','Torque','MaxSpeed','TurnSpeed'},
 ValueBase={'Value'},Sound={'SoundId','Volume','PlaybackSpeed'},Animation={'AnimationId'},
}
local function inspect(object)
 local item={path=object:GetFullName(),class=object.ClassName,name=object.Name,attributes=encode(object:GetAttributes()),properties={}}
 for class,keys in pairs(fields)do if object:IsA(class)then for _,key in ipairs(keys)do item.properties[key]=encode(read(object,key))end end end
 if object:IsA('BasePart')then local ok,mass=pcall(function()return object:GetMass()end);if ok then item.properties.partMass=mass end end
 if object:IsA('LuaSourceContainer')then
  local source=read(object,'Source');item.sourceReadable=type(source)=='string';item.sourceBytes=source and #source or 0
  item.sourceStatus=not source and 'not readable'or(#source<80 and 'short: inspect for placeholder'or 'present; functionality not established')
 end
 return item
end
local function reportFolder(label)
 local folder=Instance.new('Folder');folder.Name='DM_Collection_'..label..'_'..tostring(os.time());folder.Parent=Store;return folder
end
local function writeJSON(parent,name,data)
 local text=Http:JSONEncode(data);local folder=Instance.new('Folder');folder.Name=name;folder.Parent=parent
 -- Base64 is unnecessary: StringValue preserves JSON bytes in RBXM/XML.
 for index=1,math.max(1,math.ceil(#text/48000))do
  local value=Instance.new('StringValue');value.Name=string.format('%05d',index);value.Value=text:sub((index-1)*48000+1,index*48000);value.Parent=folder
 end
 folder:SetAttribute('Encoding','UTF-8 JSON; concatenate StringValues by Name');return #text
end
local function disableCloneScripts(clone)
 local list=clone:GetDescendants();table.insert(list,1,clone)
 for _,object in ipairs(list)do if object:IsA('BaseScript')then
  object:SetAttribute('DM_OriginalDisabled',object.Disabled);object.Disabled=true
 end end
end
function Collector.capture(options)
 studio();options=options or {}
 local output=reportFolder('Project');local copies=Instance.new('Folder');copies.Name='CopiedObjects';copies.Parent=output
 output:SetAttribute('ClonedScriptsDisabled',true)
 local manifest={schema=1,placeId=game.PlaceId,gameId=game.GameId,running=Run:IsRunning(),
  limitation='Only instances/properties available in this Studio session; no missing server code or private permissions recovered.',
  items={},copies={},skipped={},counts={},scriptSummary={readable=0,unreadable=0,short=0},streamingEnabled=workspace.StreamingEnabled}
 local selected=options.roots
 if not selected then
  selected={}
  for _,name in ipairs({'Workspace','ReplicatedStorage','ReplicatedFirst','ServerScriptService','ServerStorage','StarterPlayer','StarterGui','Lighting','SoundService','MaterialService'})do
   local ok,service=pcall(function()return game:GetService(name)end);if ok then selected[#selected+1]=service end
  end
 end
 local scanned={}
 for _,root in ipairs(selected)do
  local group=Instance.new('Folder');group.Name=root.Name;group.Parent=copies
  local all=root:GetDescendants();table.insert(all,1,root)
  for i,object in ipairs(all)do
   if object~=output and not object:IsDescendantOf(output)and not scanned[object]then
    scanned[object]=true;local item=inspect(object);manifest.items[#manifest.items+1]=item
    manifest.counts[object.ClassName]=(manifest.counts[object.ClassName]or 0)+1
    if item.sourceReadable~=nil then local key=item.sourceReadable and 'readable'or 'unreadable';manifest.scriptSummary[key]+=1
     if item.sourceReadable and item.sourceBytes<80 then manifest.scriptSummary.short+=1 end
    end
   end
   if i%350==0 then task.wait()end
  end
  if options.copyObjects~=false then for _,object in ipairs(root:GetChildren())do
   if object~=output and not object:IsDescendantOf(output)and not object.Name:match('^DM_Collection_')then
    -- Never modify Archivable or any other property on a source instance.
    local ok,clone=pcall(function()return object:Clone()end)
    if ok and clone then disableCloneScripts(clone);clone.Parent=group;manifest.copies[#manifest.copies+1]=object:GetFullName()
    else manifest.skipped[#manifest.skipped+1]={path=object:GetFullName(),reason='Clone unavailable (for example Archivable=false); source unchanged'}end
   end
   task.wait()
  end end
 end
 writeJSON(output,'Manifest',manifest)
 local instructions=Instance.new('StringValue');instructions.Name='READ_ME';instructions.Value='Right-click this folder in Explorer > Save to File > .rbxm. Export before stopping Play. Copies retain accessible references; scripts disabled only in copies. Terrain voxels and source place settings require File > Save to File (.rbxl) separately. Missing server code/private assets are not restored.';instructions.Parent=output
 print('DM COLLECTION READY: '..output:GetFullName()..' | '..#manifest.items..' inspected instances | short scripts '..manifest.scriptSummary.short..' | unreadable scripts '..manifest.scriptSummary.unreadable)
 return output,manifest
end
function Collector.start(car,options)
 studio();assert(not recording,'A recording is already running; call stop first.')
 assert(car and (car:IsA('Model')or car:IsA('BasePart')),'Select the spawned car Model first.')
 options=options or {};local maxSamples=math.clamp(tonumber(options.maxSamples)or 1800,1,3600)
 local body=car:IsA('BasePart')and car or car.PrimaryPart or car:FindFirstChild('Body',true)or car:FindFirstChildWhichIsA('BasePart',true)
 assert(body and body:IsA('BasePart'),'Selected model has no physical body.')
 local values={};for _,o in ipairs(car:GetDescendants())do if o:IsA('ValueBase')or o:IsA('SpringConstraint')or o:IsA('HingeConstraint')or o:IsA('VehicleSeat')then
  if #values<128 then values[#values+1]=o end
 end end
 local data={schema=1,car=car:GetFullName(),initial=inspect(body),samples={},note='Observed Studio runtime, not recovered server implementation.'}
 local job={data=data,elapsed=0,nextSample=0,maxSamples=maxSamples};recording=job
 job.connection=Run.Heartbeat:Connect(function(dt)
  if not body.Parent or #data.samples>=maxSamples then Collector.stop();return end
  job.elapsed+=dt;if job.elapsed<job.nextSample then return end;job.nextSample=job.elapsed+.1
  local sample={time=job.elapsed,body=inspect(body),values={}}
  for _,object in ipairs(values)do if object.Parent then sample.values[#sample.values+1]=inspect(object)end end
  data.samples[#data.samples+1]=sample
 end)
 print('DM RECORDING: '..data.car..' — drive, then call require(workspace.DM_Collector).stop() before stopping Play.')
 return job
end
function Collector.stop()
 studio();if not recording then return nil end
 local job=recording;recording=nil;job.connection:Disconnect()
 local output=reportFolder('Runtime');writeJSON(output,'RuntimeSamples',job.data)
 print('DM RUNTIME READY: '..output:GetFullName()..' | '..#job.data.samples..' samples. Save this folder as .rbxm before stopping Play.')
 return output,job.data
end
return Collector
