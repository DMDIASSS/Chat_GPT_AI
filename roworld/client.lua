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
panel.Size = UDim2.fromOffset(330, 116)
panel.Position = UDim2.new(1, -346, 0, 60)
panel.BackgroundColor3 = Color3.fromRGB(20, 29, 42)
panel.BorderSizePixel = 0
panel.Parent = gui
local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 10)
corner.Parent = panel
local button = Instance.new("TextButton")
button.Name = "Toggle"
button.Size = UDim2.new(1, -24, 0, 40)
button.Position = UDim2.fromOffset(12, 10)
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
status.Position = UDim2.fromOffset(12, 56)
status.BackgroundTransparency = 1
status.Font = Enum.Font.Gotham
status.TextSize = 13
status.TextColor3 = Color3.fromRGB(221, 231, 242)
status.TextWrapped = true
status.TextXAlignment = Enum.TextXAlignment.Left
status.Parent = panel

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
local lastReport=-math.huge
local endReported=false
local reportState
function api.report() return policy:report() end
local function saveMatchReport(force,reason)
    if type(writefile)~="function" or not policy.state then return end
    if not force and os.clock()-lastReport<30 then return end
    lastReport=os.clock()
    local ok,encoded=pcall(function()
        local report=policy:report();report.saved_reason=reason
        return game:GetService("HttpService"):JSONEncode(report)
    end)
    if ok then pcall(writefile,"RoWorld_Match_Report.json",encoded) end
end
local lastCommand, lastCommandAt = "", -math.huge
local function toggle()
    api.enabled = not api.enabled
    if api.enabled then
        policy = Policy.new()
        endReported=false
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
                -- The normal client sends a rate-limited activity heartbeat
                -- from user input. Keep that same heartbeat while autoplay is on.
                if type(frame.session.note_activity) == "function" then frame.session:note_activity() end
                local action, waiting = policy:decide(frame)
                if not api.enabled or not api.alive then return end
                if action then
                    local sent, blocked = adapter:send(action, frame)
                    if sent then
                        policy:sent(action, frame.now)
                        lastCommand, lastCommandAt = action.label, os.clock()
                        return "Order sent: " .. action.label
                    else
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
                if policy.state~=reportState then
                    reportState=policy.state;endReported=false;lastReport=-math.huge
                end
                local info=policy.state and policy.state.owners[policy.me]
                local ended=info and (not info.alive or policy.state.phase==2 or adapter.network.closed)
                saveMatchReport(ended and not endReported,ended and "match ended" or "periodic")
                if ended then endReported=true end
            else
                api.enabled = false
                repaint("Stopped after an error: " .. tostring(message))
                warn("[RoWorldBot] " .. tostring(message))
            end
        end
        task.wait(.55)
    end
end)
