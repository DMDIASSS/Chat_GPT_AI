-- Optional meshes never block driving or replace complete geometry before loading.
local ContentProvider=game:GetService('ContentProvider')
local Loader={};local entries=setmetatable({},{__mode='k'})
local timeout=8
local function inspect(template)
 local visible,external=0,false
 for _,item in ipairs(template:GetDescendants())do
  if item:IsA('BasePart')and item.Transparency<1 then
   visible+=1
   if item:IsA('MeshPart')then
    if item.MeshId==''then return false,false end
    external=true
   end
  elseif item:IsA('SpecialMesh')and item.MeshType==Enum.MeshType.FileMesh then
   if item.MeshId==''then return false,false end
   external=true
  elseif item:IsA('SurfaceAppearance')or item:IsA('Decal')or item:IsA('Texture')then external=true end
 end
 return visible>0,external
end
local function finish(entry,ok)
 if entry.status~='loading'then return end
 entry.status=ok and 'ready'or 'unavailable'
 local callbacks=entry.callbacks;entry.callbacks={}
 for _,callback in ipairs(callbacks)do task.defer(callback,ok)end
end
function Loader.check(template,callback)
 if not template then if callback then task.defer(callback,false)end;return 'unavailable'end
 local entry=entries[template]
 if not entry then
  entry={status='loading',callbacks={}};entries[template]=entry
  local valid,external=inspect(template)
  if not valid then entry.status='unavailable'
  elseif not external then entry.status='ready'
  else
   task.delay(timeout,function()finish(entry,false)end)
   task.spawn(function()
    local failed=false;local observed=false
    local ok=pcall(function()
     ContentProvider:PreloadAsync({template},function(_,status)
      observed=true
      if status~=Enum.AssetFetchStatus.Success then failed=true end
     end)
    end)
    finish(entry,ok and observed and not failed)
   end)
  end
 end
 if callback then
  if entry.status=='loading'then entry.callbacks[#entry.callbacks+1]=callback
  else task.defer(callback,entry.status=='ready')end
 end
 return entry.status
end
function Loader.ready(template)return Loader.check(template)=='ready'end
return Loader
