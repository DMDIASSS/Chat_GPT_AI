-- Studio EDIT mode: require(workspace.BackseatRallyExpansion.Installer).install()
-- Add only: never move, disable, or delete pre-existing instances.
local Installer={}
function Installer.install()
 local service=game:GetService('RunService')
 assert(service:IsStudio()and not service:IsRunning(),'Install in Studio edit mode, then press Play.')
 local rs=game:GetService('ReplicatedStorage');local sss=game:GetService('ServerScriptService')
 local sps=game:GetService('StarterPlayer'):WaitForChild('StarterPlayerScripts')
 if rs:FindFirstChild('BackseatExpedition')then return {installed=false,reason='Already installed; existing content preserved'}end
 assert(not sss:FindFirstChild('BackseatExpeditionServer')and not sps:FindFirstChild('BackseatExpeditionClient'),'Expansion folder name is already in use; nothing changed.')
 local payload=script.Parent:WaitForChild('Payload')
 local shared=payload.BackseatExpedition:Clone()
 shared:SetAttribute('AutoOpen',false)
 local server=payload.BackseatExpeditionServer:Clone()
 local client=payload.BackseatExpeditionClient:Clone()
 local cars,props=require(payload.BackseatExpedition.Shared.ImportAssets).harvest(shared)
 for _,container in ipairs({server,client})do
  for _,desc in ipairs(container:GetDescendants())do if desc:IsA('BaseScript')then desc.Disabled=false end end
 end
 shared.Parent=rs;server.Parent=sss;client.Parent=sps
 print('Backseat Expedition added. Existing scripts, bots, assets, lighting and settings preserved. Press Play, then EXPEDITION.')
 return {installed=true,cars=cars,props=props}
end
return Installer
