-- Offline compatibility for the exported client, not the original game's backend.
-- Only fresh defaults from its own SaveStructure are used; no entitlements or remote data.
local Bridge={}
local function copy(value)
 if type(value)~='table'then return value end
 local result={};for key,item in pairs(value)do result[key]=copy(item)end;return result
end
function Bridge.start()
 local rs=game:GetService('ReplicatedStorage');local shared=rs:FindFirstChild('Shared')
 local structure=shared and shared:FindFirstChild('SaveStructure')
 if not structure then return nil end
 local defaults=require(structure).NotIncludingData
 assert(type(defaults)=='table'and type(defaults.Settings)=='table','Invalid exported SaveStructure')
 local players=game:GetService('Players')
 local folder=rs:FindFirstChild('RemoteEvents')
 if not folder then folder=Instance.new('Folder');folder.Name='RemoteEvents';folder.Parent=rs end
 local function remote(parent,name,class)
  local result=parent:FindFirstChild(name)
  if result then assert(result:IsA(class),'Conflicting legacy remote '..name);return result end
  result=Instance.new(class);result.Name=name;result.Parent=parent;return result
 end
 local names={'ReplicaRequestData','ReplicaSet','ReplicaSetValues','ReplicaTableInsert','ReplicaTableRemove',
  'ReplicaWrite','ReplicaSignal','ReplicaParent','ReplicaCreate','ReplicaBind','ReplicaDestroy'}
 local events={};for _,name in ipairs(names)do events[name]=remote(folder,name,'RemoteEvent')end
 remote(folder,'ReplicaSignalUnreliable','UnreliableRemoteEvent')
 local profiles,ids,sent,connections,requestAt={},{},{},{},{};local serial=0
 local function publish(player,key,value)
  if sent[player]then events.ReplicaSet:FireClient(player,ids[player],{'Settings',key},value)end
 end
 local function ensure(player)
  if profiles[player]then return profiles[player]end
  serial+=1;ids[player]=serial;local data=copy(defaults);profiles[player]=data;connections[player]={}
  local settings=player:FindFirstChild('Settings')
  if not settings then settings=Instance.new('Folder');settings.Name='Settings';settings.Parent=player end
  for key,value in pairs(data.Settings)do
   local class=type(value)=='boolean'and 'BoolValue'or(type(value)=='number'and 'NumberValue'or 'StringValue')
   local item=settings:FindFirstChild(key)
   if not item then item=Instance.new(class);item.Name=key;item.Value=value;item.Parent=settings
   elseif item:IsA(class)and type(item.Value)==type(value)then data.Settings[key]=item.Value end
   if item:IsA(class)then connections[player][#connections[player]+1]=item:GetPropertyChangedSignal('Value'):Connect(function()
    data.Settings[key]=item.Value;publish(player,key,item.Value)
   end)end
  end
  settings:SetAttribute('SessionOnlyCompatibility',true)
  return data
 end
 local request=events.ReplicaRequestData
 request.OnServerEvent:Connect(function(player)
  local now=os.clock();if now-(requestAt[player]or -math.huge)<.5 then return end;requestAt[player]=now
  local data=ensure(player)
  if not sent[player]then
   events.ReplicaCreate:FireClient(player,{[tostring(ids[player])]={'PlayerProfile',{Player=player,SessionOnly=true},data,0}})
   sent[player]=true
  end
  request:FireClient(player)
 end)
 local util=shared:FindFirstChild('RBXUtil');local net=util and util:FindFirstChild('Net')
 if net then
  local option=remote(net,'RE/SetOptionRE','RemoteEvent')
  option.OnServerEvent:Connect(function(player,key,value)
   local initial=type(key)=='string'and defaults.Settings[key]
   if initial==nil or type(value)~=type(initial)then return end
   if type(value)=='number'then
    if value~=value or math.abs(value)>1e6 then return end
    if key=='GraphicsQuality'then value=math.clamp(math.floor(value),1,4)
    elseif key:find('Volume',1,true)then value=math.clamp(value,0,1)
    else value=math.clamp(value,0,10)end
   end
   ensure(player);local item=player.Settings:FindFirstChild(key)
   if item then item.Value=value end
  end)
 end
 players.PlayerAdded:Connect(ensure)
 players.PlayerRemoving:Connect(function(player)
  for _,connection in ipairs(connections[player]or {})do connection:Disconnect()end
  profiles[player]=nil;ids[player]=nil;sent[player]=nil;connections[player]=nil;requestAt[player]=nil
 end)
 for _,player in ipairs(players:GetPlayers())do ensure(player)end
 return {get=function(player)return profiles[player]end,events=events}
end
return Bridge
