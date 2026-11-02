-- Resolve the exported PlayerModule's native input graph without unbounded waits.
-- Originals are retained; the fallback is a copied input graph, not fabricated actions.
local RS=game:GetService('ReplicatedStorage')
local Players=game:GetService('Players')
local RunService=game:GetService('RunService')
local Input={};local cache=setmetatable({},{__mode='k'})
local function valid(folder)
 return folder and folder:FindFirstChild('CharacterContext')and folder:FindFirstChild('CameraContext')
  and folder:FindFirstChild('TransformerContext')and folder:FindFirstChild('VehicleContext')
end
function Input.get(module)
 assert(module and module:IsA('ModuleScript'),'A PlayerModule root is required')
 local existing=module:FindFirstChild('InputContexts')
 if valid(existing)then return existing end
 local cached=cache[module]
 if valid(cached)and cached.Parent then return cached end
 if RunService:IsClient()then
  local player=Players.LocalPlayer
  local live=player and player:FindFirstChild('InputContexts')
  if valid(live)then return live end
 end
 local root=RS:FindFirstChild('BackseatExpedition')
 local template=root and root:FindFirstChild('LegacyInputContexts')
 if not valid(template)then error('Exported input graph unavailable; use the clean standalone place.',2)end
 local clone=template:Clone();clone.Name='InputContexts';clone.Parent=module
 cache[module]=clone
 return clone
end
return Input
