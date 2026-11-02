-- Mesh geometry and optional decoration have separate availability. Never discard
-- usable native car parts just because a private texture or sound cannot load.
local ContentProvider=game:GetService('ContentProvider')
local Loader={};local entries=setmetatable({},{__mode='k'})
local function inspect(template)
 local visible,native,ids,seen=0,0,{},{}
 for _,item in ipairs(template:GetDescendants())do
  if item:IsA('BasePart')and item.Transparency<1 then
   visible+=1
   local mesh=item:IsA('MeshPart')and item or item:FindFirstChildOfClass('SpecialMesh')
   local external=mesh and (mesh:IsA('MeshPart')or mesh.MeshType==Enum.MeshType.FileMesh)
   if external then
    local id=mesh.MeshId
    if id and id~=''and not seen[id]then seen[id]=true;ids[#ids+1]=id end
    if not id or id==''then ids[#ids+1]=''end
   else native+=1 end
  end
 end
 return visible,native,ids
end
function Loader.nativeParts(template)local _,native=inspect(template);return native end
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
  local visible,native,ids=inspect(template);entry.native=native
  if visible==0 or table.find(ids,'')then entry.status='unavailable'
  elseif #ids==0 then entry.status='ready'
  else
   task.delay(8,function()finish(entry,false)end)
   task.spawn(function()
    local failed,observed=false,false
    local ok=pcall(function()
     -- Only required geometry IDs: an optional decal/SurfaceAppearance failure
     -- must not suppress an otherwise working exterior or original interior.
     ContentProvider:PreloadAsync(ids,function(_,status)
      observed=true;if status~=Enum.AssetFetchStatus.Success then failed=true end
     end)
    end)
    finish(entry,ok and observed and not failed)
   end)
  end
 end
 if callback then
  if entry.status=='loading'then entry.callbacks[#entry.callbacks+1]=callback else task.defer(callback,entry.status=='ready')end
 end
 return entry.status
end
function Loader.ready(template)return Loader.check(template)=='ready'end
return Loader
