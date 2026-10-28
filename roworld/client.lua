-- Policy and Adapter are embedded by build.py in the standalone script.
local Services = {
    Players = game:GetService("Players"),
    CoreGui = game:GetService("CoreGui"),
    UserInputService = game:GetService("UserInputService"),
    RunService = game:GetService("RunService"),
    ReplicatedStorage = game:GetService("ReplicatedStorage"),
}
local env = (type(getgenv) == "function" and getgenv()) or _G
local previous = env.__RoWorldBot
if type(previous) == "table" and type(previous.destroy) == "function" then pcall(previous.destroy) end
local api = {enabled = false, alive = true, connections = {}}
env.__RoWorldBot = api

local gui = Instance.new("ScreenGui")
gui.Name = "RoWorldBot"
gui.ResetOnSpawn = false
gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
gui.DisplayOrder = 10000
local parent = type(gethui) == "function" and gethui() or Services.CoreGui
local attached = pcall(function() gui.Parent = parent end)
if not attached then gui.Parent = Services.Players.LocalPlayer:WaitForChild("PlayerGui") end
local panel = Instance.new("Frame")
panel.Size = UDim2.fromOffset(410, 278)
panel.Position = UDim2.new(1, -426, 0, 60)
panel.BackgroundColor3 = Color3.fromRGB(20, 29, 42)
panel.BorderSizePixel = 0
panel.Parent = gui
local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 10)
corner.Parent = panel
local title = Instance.new("TextLabel")
title.Name = "Title"
title.Size = UDim2.new(1, -24, 0, 22)
title.Position = UDim2.fromOffset(12, 8)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBold
title.TextSize = 14
title.TextColor3 = Color3.fromRGB(221, 231, 242)
title.Text = "RoWorld 1.9.0 | live strategy"
title.TextXAlignment = Enum.TextXAlignment.Left
title.Parent = panel
local button = Instance.new("TextButton")
button.Name = "Toggle"
button.Size = UDim2.new(1, -24, 0, 40)
button.Position = UDim2.fromOffset(12, 36)
button.Font = Enum.Font.GothamBold
button.TextSize = 17
button.TextColor3 = Color3.fromRGB(255, 255, 255)
button.BorderSizePixel = 0
button.Parent = panel
local buttonCorner = corner:Clone()
buttonCorner.Parent = button
local status = Instance.new("TextLabel")
status.Name = "Status"
status.Size = UDim2.new(1, -24, 0, 51)
status.Position = UDim2.fromOffset(12, 82)
status.BackgroundTransparency = 1
status.Font = Enum.Font.Gotham
status.TextSize = 13
status.TextColor3 = Color3.fromRGB(221, 231, 242)
status.TextWrapped = true
status.TextXAlignment = Enum.TextXAlignment.Left
status.Parent = panel

local stats = Instance.new("TextLabel")
stats.Name = "Stats"
stats.Size = UDim2.new(1, -24, 0, 88)
stats.Position = UDim2.fromOffset(12, 136)
stats.BackgroundTransparency = 1
stats.Font = Enum.Font.Gotham
stats.TextSize = 12
stats.TextColor3 = Color3.fromRGB(176, 206, 225)
stats.TextWrapped = true
stats.TextXAlignment = Enum.TextXAlignment.Left
stats.Text = "Waiting for observed match statistics"
stats.Parent = panel
local export = Instance.new("TextButton")
export.Name = "ExportReport"
export.Size = UDim2.new(1, -24, 0, 32)
export.Position = UDim2.fromOffset(12, 234)
export.Font = Enum.Font.GothamBold
export.TextSize = 13
export.TextColor3 = Color3.fromRGB(255, 255, 255)
export.BackgroundColor3 = Color3.fromRGB(48, 76, 102)
export.BorderSizePixel = 0
export.Text = "Save match report"
export.Parent = panel
local exportCorner = corner:Clone();exportCorner.Parent = export

local function repaint(message)
    if not api.alive then return end
    button.Text = api.enabled and "Stop bot" or "Start bot"
    button.BackgroundColor3 = api.enabled and Color3.fromRGB(166, 58, 65) or Color3.fromRGB(33, 133, 99)
    status.Text = message or "Stopped - press Start bot (F6 also toggles)"
end

local adapter = Adapter.new(Services, require, nil, {
    getidentity = getthreadidentity or getidentity,
    setidentity = setthreadidentity or setidentity,
    getgc = getgc,
    getconnections = getconnections,
    getupvalues = getupvalues or (debug and debug.getupvalues),
    getupvalue = getupvalue or (debug and debug.getupvalue),
    getfenv = getfenv,
    getsenv = getsenv,
    getrenv = getrenv,
})
adapter.network = Network.new(Services,Wire,Mirror,os.clock,task.spawn,function() task.wait() end,function(bytes)
    return game:GetService("EncodingService"):DecompressBuffer(bytes,Enum.CompressionAlgorithm.Zstd)
end)
local reported
function api.diagnostics() return adapter:diagnostics() end
local function reportAccessFailure()
    if not adapter.discoveryError then return end
    local report = adapter:diagnostics()
    if report == reported then return end
    reported = report
    if type(writefile) == "function" then pcall(writefile, "RoWorld_Diagnostics.txt", report) end
    warn(report)
end
local policy = Policy.new()
local runtime={decisions=0,skipped=0,blocked_orders=0,last_decision_ms=0,mean_decision_ms=0}
local function updateStats()
    local info=policy.state and policy.state.owners[policy.me]
    if not info then return end
    local b=policy.strategy and policy.strategy.board or {}
    local eco=policy.economyPlan or {}
    stats.Text=string.format("%s | Tick %d | Land %d | Troops %.0f / %.0f\nGold %.0f | Income %.0f | Incoming %.0f\n%s | Decision %.1f ms | Blocked %d\n%s",
        info.alive and (b.mode or 'observing') or 'eliminated',policy.state.tick or 0,info.tiles or 0,info.troops or 0,info.max_troops or 0,
        info.gold or 0,info.income or 0,b.incoming or 0,
        b.core and b.core.at_risk and 'Core at risk' or 'Core stable',runtime.last_decision_ms,runtime.blocked_orders,
        eco.saving_for and ('Saving for '..eco.saving_for) or b.relocation_reason or 'Public-state observations; future orders unknown')
end
local lastReport=-math.huge
local endReported=false
local reportState
local reportTag
function api.report() return policy:report() end
local function saveMatchReport(force,reason)
    if type(writefile)~="function" then return false,"Executor file writing unavailable" end
    if not policy.state then return false,"No match observed yet" end
    if not force and os.clock()-lastReport<30 then return false end
    lastReport=os.clock()
    local ok,encoded=pcall(function()
        local report=policy:report();report.saved_reason=reason
        return game:GetService("HttpService"):JSONEncode(report)
    end)
    if not ok then return false,tostring(encoded) end
    local saved,err=pcall(writefile,"RoWorld_Match_Report.json",encoded)
    if saved and force then
        reportTag=reportTag or (tostring(os.time()).."_"..tostring(math.floor(os.clock()*1000)))
        local archived,archiveError=pcall(writefile,"RoWorld_Match_Report_"..reportTag..".json",encoded)
        if not archived then return false,"Latest report saved; archive failed: "..tostring(archiveError) end
    end
    return saved,saved and "Saved RoWorld_Match_Report.json in executor workspace" or tostring(err)
end
table.insert(api.connections,export.Activated:Connect(function()
    local _,message=saveMatchReport(true,"manual export")
    repaint(message)
end))
local lastCommand, lastCommandAt = "", -math.huge
local evaluatedState,evaluatedTick,evaluatedAt
local function toggle()
    api.enabled = not api.enabled
    if api.enabled then
        policy = Policy.new()
        runtime={decisions=0,skipped=0,blocked_orders=0,last_decision_ms=0,mean_decision_ms=0}
        evaluatedState,evaluatedTick,evaluatedAt=nil,nil,nil
        endReported=false;reportTag=nil
        repaint("Connecting to your RoWorld match...")
    else
        saveMatchReport(true,"stopped by user")
        repaint("Stopped - no new orders; existing game attacks continue")
    end
end
table.insert(api.connections, button.Activated:Connect(toggle))
table.insert(api.connections, Services.UserInputService.InputBegan:Connect(function(input, consumed)
    if not consumed and input.KeyCode == Enum.KeyCode.F6 then toggle() end
end))
function api.destroy()
    saveMatchReport(true,"script replaced or closed")
    api.alive, api.enabled = false, false
    adapter.network:destroy()
    for _, connection in ipairs(api.connections) do connection:Disconnect() end
    gui:Destroy()
    if env.__RoWorldBot == api then env.__RoWorldBot = nil end
end
table.insert(api.connections, gui.AncestryChanged:Connect(function(_, newParent)
    if newParent == nil then api.alive, api.enabled = false, false end
end))
repaint()
task.spawn(function()
    while api.alive do
        if api.enabled then
            local ok, message = adapter:call(function()
                local frame, reason = adapter:frame()
                if not api.enabled or not api.alive then return end
                if not frame then return reason end
                if evaluatedState==frame.state and evaluatedTick==frame.state.tick and frame.now-(evaluatedAt or 0)<.5 then
                    runtime.skipped+=1
                    return policy.lastWaiting or 'Watching for a fresh game update'
                end
                evaluatedState,evaluatedTick,evaluatedAt=frame.state,frame.state.tick,frame.now
                -- The normal client sends a rate-limited activity heartbeat
                -- from user input. Keep that same heartbeat while autoplay is on.
                if type(frame.session.note_activity) == "function" then frame.session:note_activity() end
                local started=os.clock()
                local action, waiting = policy:decide(frame)
                local ms=(os.clock()-started)*1000
                runtime.decisions+=1;runtime.last_decision_ms=ms
                runtime.mean_decision_ms+=(ms-runtime.mean_decision_ms)/runtime.decisions
                policy.runtime=runtime
                policy.lastWaiting=action and action.label or waiting
                if not api.enabled or not api.alive then return end
                if action then
                    local sent, blocked = adapter:send(action, frame)
                    if sent then
                        policy:sent(action, frame.now)
                        lastCommand, lastCommandAt = action.label, os.clock()
                        return "Order sent: " .. action.label
                    else
                        runtime.blocked_orders+=1;runtime.last_blocked_reason=tostring(blocked)
                        policy.lastWaiting=blocked
                        return blocked
                    end
                else
                    local suffix = os.clock() - lastCommandAt < 5 and ("\nLast: " .. lastCommand) or ""
                    return (waiting or "Watching the match") .. suffix
                end
            end)
            -- UI and executor file operations run after the identity is restored.
            if ok then
                reportAccessFailure()
                repaint(message)
                updateStats()
                if policy.state~=reportState then
                    reportState=policy.state;endReported=false;lastReport=-math.huge;reportTag=nil
                end
                local info=policy.state and policy.state.owners[policy.me]
                local ended=info and (not info.alive or policy.state.phase==2 or adapter.network.closed)
                saveMatchReport(ended and not endReported,ended and "match ended" or "periodic")
                if ended then endReported=true end
            else
                api.enabled = false
                runtime.last_error=tostring(message);policy.runtime=runtime
                saveMatchReport(true,"runtime error")
                repaint("Stopped after an error: " .. tostring(message))
                warn("[RoWorldBot] " .. tostring(message))
            end
        end
        task.wait(.1)
    end
end)
