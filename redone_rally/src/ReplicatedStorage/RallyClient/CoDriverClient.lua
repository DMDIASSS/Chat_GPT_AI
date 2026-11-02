--!strict
-- Route-distance co-driver. Geometry and notes are cached, then updated at 10 Hz.
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local SoundService = game:GetService("SoundService")
local VehicleController = require(script.Parent.VehicleController)
local StageRemotes = require(ReplicatedStorage.RallyShared.Remotes.StageRemotes)
local StageProgress = require(ReplicatedStorage.RallyShared.Splines.StageProgress)

export type ActiveCall = {
    Index: number, Severity: number, Direction: "Left" | "Right" | "Straight",
    Modifier: string, Description: string, DistanceRemaining: number,
    CountdownRatio: number, IsActive: boolean,
}
local CoDriverClient = {}
local activeCall: ActiveCall = {Index=0,Severity=6,Direction="Straight",Modifier="",Description="",DistanceRemaining=0,CountdownRatio=0,IsActive=false}
local upcomingNote = ""
local leadSeconds, volume, voiceEnabled = 3.0, 0.85, true
local progress, offRoute = 0, 0
local stage: Instance? = nil
local vehicle: Model? = nil
local samples, notes = {}, {}
local called: { [number]: boolean } = {}
local lastCallClock, manualUntil, accumulator = -math.huge, 0, 0
local displayed: any = nil
local radioGroup = Instance.new("SoundGroup")
radioGroup.Name = "CoDriverRadio"
radioGroup.Volume = volume
radioGroup.Parent = SoundService
local speechOutput: Instance? = nil
local speechCache: { [string]: any } = {}
local speechOrder: { string } = {}
local speechToken = 0

local function tone(severity: number)
    local sound = Instance.new("Sound")
    sound.SoundId = "rbxassetid://6042053626"
    sound.PlaybackSpeed = 0.85+(7-math.clamp(severity,1,6))*0.12
    sound.Volume = 0.5
    sound.SoundGroup = radioGroup
    sound.Parent = SoundService
    sound.Ended:Connect(function() sound:Destroy() end)
    task.delay(5,function() if sound.Parent then sound:Destroy() end end)
    sound:Play()
end

local function prepareSpeech(text: string)
    if not voiceEnabled or speechCache[text] then return end
    -- Built-in speech needs no private sound IDs. If Roblox doesn't permit
    -- speech in this experience, visual notes and the existing cue still work.
    local ok, source = pcall(function()
        if not speechOutput then
            speechOutput = Instance.new("AudioDeviceOutput")
            speechOutput.Name = "CoDriverOutput"
            speechOutput.Parent = SoundService
        end
        local tts = Instance.new("AudioTextToSpeech")
        tts.Name = "PaceNoteSpeech"
        tts.Text, tts.VoiceId, tts.Speed, tts.Volume = text, "1", 1.12, volume
        tts.Parent = SoundService
        local wire = Instance.new("Wire")
        wire.SourceInstance, wire.TargetInstance = tts, speechOutput
        wire.Parent = tts
        return tts
    end)
    local entry = {Source=ok and source or nil, Ready=false, Failed=not ok, Request=0}
    speechCache[text] = entry
    table.insert(speechOrder,text)
    while #speechOrder > 12 do
        local old = table.remove(speechOrder,1)
        local oldEntry = speechCache[old]
        speechCache[old] = nil
        if oldEntry and oldEntry.Source then oldEntry.Source:Destroy() end
    end
    if not ok then return end
    task.spawn(function()
        local loaded,status = pcall(function() return source:LoadAsync() end)
        entry.Ready = loaded and status == Enum.AssetFetchStatus.Success
        entry.Failed = not entry.Ready
        if entry.Request == speechToken and entry.Request > 0 and voiceEnabled and source.Parent then
            if entry.Ready then source:Play() else tone(entry.Severity or 6) end
        end
    end)
end

local function stopSpeech()
    speechToken += 1
    for _,entry in pairs(speechCache) do
        if entry.Ready and entry.Source then pcall(function() entry.Source:Stop() end) end
    end
end

local function speak(text: string, severity: number)
    stopSpeech()
    if not voiceEnabled then return end
    prepareSpeech(text)
    local entry = speechCache[text]
    if entry and not entry.Failed then
        entry.Request = speechToken
        entry.Severity = severity
        if entry.Ready then entry.Source:Play() end
    else tone(severity) end
end

function CoDriverClient.SetLeadTime(seconds: number) leadSeconds = math.clamp(seconds,1.5,5) end
function CoDriverClient.SetVoiceEnabled(enabled: boolean)
    voiceEnabled = enabled
    if not enabled then
        speechToken += 1
        for _,entry in pairs(speechCache) do if entry.Source then pcall(function() entry.Source:Stop() end) end end
    end
end
function CoDriverClient.SetVolume(value: number)
    volume = math.clamp(value,0,1)
    radioGroup.Volume = volume
    for _,entry in pairs(speechCache) do if entry.Source then entry.Source.Volume = volume end end
end
function CoDriverClient.GetActiveCall(): ActiveCall return activeCall end
function CoDriverClient.GetUpcomingNote(): string return upcomingNote end
function CoDriverClient.GetProgress(): number return progress end

local function readStage(data: Instance)
    samples,notes,called = {},{},{}
    displayed,progress,lastCallClock = nil,0,-math.huge
    local route = data:FindFirstChild("RouteSamples")
    if route then
        for _,point in ipairs(route:GetChildren()) do
            local position,distance = point:GetAttribute("Position"),point:GetAttribute("Distance")
            if typeof(position)=="Vector3" and type(distance)=="number" then table.insert(samples,{Position=position,Distance=distance}) end
        end
        table.sort(samples,function(a,b) return a.Distance < b.Distance end)
    end
    local folder = data:FindFirstChild("PaceNotes")
    if folder then
        for _,n in ipairs(folder:GetChildren()) do
            table.insert(notes,{
                Index=n:GetAttribute("Index") or 0,Distance=n:GetAttribute("Distance") or 0,
                EndDistance=n:GetAttribute("EndDistance") or n:GetAttribute("Distance") or 0,
                Severity=n:GetAttribute("Severity") or 6,Direction=n:GetAttribute("Direction") or "Straight",
                Modifier=n:GetAttribute("Modifier") or "",Description=n:GetAttribute("Description") or "",
            })
        end
        table.sort(notes,function(a,b) return a.Distance < b.Distance end)
    end
end

StageRemotes.GetEvent("CompanionSync").OnClientEvent:Connect(function(idx: number, description: string, severity: number?, direction: string?)
    if type(description)~="string" then return end
    manualUntil = os.clock()+3.2
    called[idx or 0] = true
    displayed = nil
    activeCall = {Index=idx or 0,Severity=severity or 4,Direction=(direction=="Left" or direction=="Right") and (direction :: any) or "Straight",
        Modifier="CO-DRIVER",Description=description:sub(1,160),DistanceRemaining=0,CountdownRatio=0,IsActive=true}
    speak(activeCall.Description,activeCall.Severity)
end)

RunService.Heartbeat:Connect(function(dt)
    accumulator += dt
    if accumulator < 0.1 then return end
    accumulator %= 0.1
    local currentVehicle = VehicleController.GetActiveVehicle()
    local data = ReplicatedStorage:FindFirstChild("ActiveStageData")
    if not currentVehicle or not currentVehicle.PrimaryPart or not data then
        if activeCall.IsActive then stopSpeech() end
        activeCall.IsActive=false; upcomingNote=""; return
    end
    if data~=stage or currentVehicle~=vehicle then
        stopSpeech()
        stage,vehicle = data,currentVehicle
        readStage(data)
        manualUntil=0
    elseif #samples ~= data:GetAttribute("SampleCount") or #notes ~= data:GetAttribute("NoteCount") then
        -- Replication can deliver the folder before its children.
        readStage(data)
    end
    if #samples<2 then activeCall.IsActive=false; return end
    local previous = progress
    progress,offRoute = StageProgress.Project(samples,currentVehicle.PrimaryPart.Position,progress)
    if previous-progress>100 then
        -- Checkpoint reset / restart: allow the upcoming section to be called again.
        stopSpeech()
        called,displayed,lastCallClock = {},nil,-math.huge
    end
    if os.clock()<manualUntil then return end
    if offRoute>140 then activeCall.IsActive=false; upcomingNote=""; return end
    local speed = currentVehicle.PrimaryPart.AssemblyLinearVelocity.Magnitude
    local nextUncalled: any = nil
    for _,note in ipairs(notes) do
        if note.EndDistance < progress-8 then called[note.Index]=true
        elseif not called[note.Index] then nextUncalled=note; break end
    end
    if nextUncalled then
        local distance = nextUncalled.Distance-progress
        local horizon = StageProgress.Lookahead(speed,nextUncalled.Severity,leadSeconds)
        if distance <= horizon*1.4 then prepareSpeech(nextUncalled.Description) end
        if distance <= horizon and (os.clock()-lastCallClock>=2.4 or distance < speed*0.6) then
            called[nextUncalled.Index] = true
            displayed,lastCallClock = nextUncalled,os.clock()
            speak(nextUncalled.Description,nextUncalled.Severity)
        end
    end
    if displayed and displayed.EndDistance >= progress-8 then
        local distance = math.max(0,displayed.Distance-progress)
        local horizon = StageProgress.Lookahead(speed,displayed.Severity,leadSeconds)
        activeCall = {Index=displayed.Index,Severity=displayed.Severity,Direction=displayed.Direction,
            Modifier=displayed.Modifier,Description=displayed.Description,DistanceRemaining=distance,
            CountdownRatio=1-math.clamp(distance/horizon,0,1),IsActive=true}
        upcomingNote=""
        for _,note in ipairs(notes) do
            if note.Index>displayed.Index then
                local gap = math.max(0,note.Distance-displayed.EndDistance)
                upcomingNote=(gap<=45 and "into " or (tostring(math.floor(gap*0.28/10+0.5)*10).." m, then "))..note.Description
                break
            end
        end
    else activeCall.IsActive=false; upcomingNote="" end
end)
return CoDriverClient
