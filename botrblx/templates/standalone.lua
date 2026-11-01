-- Generated LOCAL model + telemetry + controls. Weights stay on this PC.
-- LOCAL_POLICY_HERE
-- LOCAL_KEYBOARD_HERE
-- LOCAL_ARENA_HERE
-- LOCAL_PADS_HERE
-- LOCAL_TEAMS_HERE
-- LOCAL_CARS_HERE
-- LOCAL_KICKOFF_HERE
-- LOCAL_PHYSICS_HERE
-- LOCAL_INTERCEPT_HERE
-- LOCAL_TIMING_HERE
local PROFILE=
-- ARENA_PROFILE_HERE
local arenaAdapter=Arena.new(PROFILE)
local padReader=Pads.new(PROFILE)
local carReader=Cars.new(PROFILE,Arena)
local kickoff=Kickoff.new(PROFILE)
local physics=Physics.new(PROFILE,arenaAdapter)
local intercept=Intercept.new(PROFILE,arenaAdapter,physics)
-- MODEL_SETTINGS_HERE
local timing=Timing.new(15)
local TEAM,manualTeam=nil,nil
local HZ=30 -- pose sampling; policy decisions target 15 Hz (tick skip 8 at 120 Hz)
local player=game:GetService("Players").LocalPlayer
local pg=assert(player:FindFirstChildOfClass("PlayerGui"),"Join first")
local teamReader=Teams.new(player)
carReader.teams=teamReader
assert(not pg:FindFirstChild("Update271Standalone"),"Close the old standalone panel first")
local gui=Instance.new("ScreenGui")
gui.Name="Update271Standalone";gui.ResetOnSpawn=false;gui.DisplayOrder=1000072
local panel=Instance.new("Frame",gui)
panel.Size=UDim2.fromOffset(480,296);panel.Position=UDim2.fromOffset(20,20)
panel.BackgroundColor3=Color3.fromRGB(18,22,30)
local label=Instance.new("TextLabel",panel)
label.Position=UDim2.fromOffset(10,8);label.Size=UDim2.new(1,-20,0,172)
label.BackgroundTransparency=1;label.TextColor3=Color3.new(1,1,1)
label.TextSize=14;label.Font=Enum.Font.Code;label.TextWrapped=true
label.Text=MODEL_NAME.." LOCAL: loading model..."
local start=Instance.new("TextButton",panel)
start.Position=UDim2.fromOffset(10,185);start.Size=UDim2.fromOffset(150,30)
start.Text="Start bot / F6";start.Active=false
local teamButton=Instance.new("TextButton",panel)
teamButton.Position=UDim2.fromOffset(170,185);teamButton.Size=UDim2.fromOffset(140,30)
teamButton.Text="Team: AUTO"
local close=Instance.new("TextButton",panel)
close.Position=UDim2.fromOffset(320,185);close.Size=UDim2.fromOffset(150,30);close.Text="Close"
local physicsButton=Instance.new("TextButton",panel)
physicsButton.Position=UDim2.fromOffset(10,222);physicsButton.Size=UDim2.fromOffset(220,28)
physicsButton.Text=physicsEnabled and "Physics assist: ON"or "Physics assist: OFF"
local reportButton=Instance.new("TextButton",panel)
reportButton.Position=UDim2.fromOffset(240,222);reportButton.Size=UDim2.fromOffset(230,28)
reportButton.Text="Save physics report"
local supportButton=Instance.new("TextButton",panel)
supportButton.Position=UDim2.fromOffset(10,259);supportButton.Size=UDim2.fromOffset(460,28)
supportButton.Text="Yield to teammate: OFF"
gui.Parent=pg
local input=game:GetService("UserInputService")
local world=game:GetService("Workspace")
local alive,enabled,ready,armAt=true,false,false,0
local lastStopReason,lastStopAt,lastReadReason
local testingKeyboard=false
local epoch=0
local sampleAt,decisionAt,previousPeriod=nil,nil,nil
local held,connections={},{}
local pressLeft,releaseLeft,pressRight,releaseRight
local activeWindow=isrbxactive or isgameactive
local keyboard=Keyboard.new(input)
local keyboardKey={W=true,S=true,A=true,D=true,Q=true,E=true,SHIFT=true}
local order={"W","S","A","D","Q","E","SHIFT","LMB","RMB"}
local previous=table.create(8,0)
local jumpAt,usedFlip,lastGround=nil,false,true
local focus=true
local function event(key,down)
    if keyboardKey[key]then keyboard:event(key,down)
    elseif key=="LMB"then (down and pressLeft or releaseLeft)()
    else (down and pressRight or releaseRight)()end
end
local function release()
    for _,key in ipairs(order)do
        if held[key]then
            -- Try every release even if one executor API fails.
            if pcall(event,key,false)then held[key]=nil end
        end
    end
    previous=table.create(8,0);jumpAt=nil;usedFlip=false
    keyboard:release()
    arenaAdapter:resetRecovery()
    kickoff:reset()
    intercept:reset();physics.plan=nil
    decisionAt=nil;previousPeriod=nil
end
local function controls()
    start.Visible=not enabled and not testingKeyboard
    teamButton.Visible=not enabled and not testingKeyboard
    close.Visible=not enabled and not testingKeyboard
    physicsButton.Visible=not enabled and not testingKeyboard
    reportButton.Visible=not enabled and not testingKeyboard
    supportButton.Visible=not enabled and not testingKeyboard
end
local function runtimeSnapshot(now)
    local keys={};for _,key in ipairs(order)do if held[key]then keys[#keys+1]=key end end
    local phase=not alive and "closed"or(testingKeyboard and "keyboard test"
        or(enabled and(now<armAt and "arming"or(lastReadReason and "waiting"or "running"))or "paused"))
    return {enabled=enabled,ready=ready,phase=phase,focused=focus,keyboard=keyboard.name,
        keyboard_observed=keyboard:observed(),held_inputs=keys,last_stop_reason=lastStopReason,
        last_stop_time=lastStopAt,read_reason=lastReadReason,time=now}
end
local function stop(reason)
    epoch=epoch+1;enabled=false;testingKeyboard=false;release();controls()
    lastStopReason=reason or "paused by control";lastStopAt=os.clock()
    physics:mark("stop",lastStopAt,lastStopReason)
    physics.runtime=runtimeSnapshot(lastStopAt)
    if reason then label.Text=reason end
end
local function saveReport(filename,savedFrom)
    assert(type(writefile)=="function","Executor writefile is unavailable")
    physics.runtime=runtimeSnapshot(os.clock())
    local report=physics:report()
    report.physics_assist_enabled=physicsEnabled;report.saved_from=savedFrom
    report.teammate_yield_enabled=intercept.supportEnabled;report.model_name=MODEL_NAME
    report.performance=timing:report()
    report.performance.last_active_age=timing.last and os.clock()-timing.last.time or nil
    report.model_sha256="__MODEL_SHA__";report.place=game.PlaceId
    local body=game:GetService("HttpService"):JSONEncode(report)
    writefile(filename,body)
end
local function toggle()
    if not ready then return end
    if enabled or testingKeyboard then stop("LOCAL paused. F6 starts; F8 stops.");return end
    epoch=epoch+1
    if keyboard.selected then
        enabled=true;armAt=os.clock()+.5;physics:mark("start",os.clock());controls();return
    end
    testingKeyboard=true;controls()
    local testEpoch=epoch
    task.spawn(function()
        local function cancelled()
            return epoch~=testEpoch or not alive or not focus or input:GetFocusedTextBox()
                or input:IsKeyDown(Enum.KeyCode.F8)or(activeWindow and not activeWindow())
        end
        local ok,passed,reason=pcall(function()
            -- Let the launch hotkey/button settle before testing physical inputs.
            task.wait(.3)
            if cancelled()then return false,"Keyboard test cancelled"end
            return keyboard:probe(cancelled,function(message)label.Text="LOCAL keyboard test\n"..message end)
        end)
        if epoch~=testEpoch or not alive then keyboard:release();return end
        testingKeyboard=false
        if not ok or not passed then
            stop("LOCAL keyboard stopped: "..tostring(ok and reason or passed));return
        end
        label.Text="LOCAL keyboard verified: "..keyboard.name.."\nStarting model. F8 stops."
        enabled=true;armAt=os.clock()+.3;controls()
        physics:mark("start",os.clock(),"keyboard verified")
    end)
end
local function connect(signal,callback)
    local connection=signal:Connect(callback);connections[#connections+1]=connection
end
start.Activated:Connect(toggle)
teamButton.Activated:Connect(function()
    stop();manualTeam=manualTeam==nil and 0 or(manualTeam==0 and 1 or nil)
    teamReader.at=-math.huge
    teamButton.Text=manualTeam==nil and "Team: AUTO"or(manualTeam==0 and "Manual: BLUE"or "Manual: ORANGE")
end)
physicsButton.Activated:Connect(function()
    stop();physicsEnabled=not physicsEnabled
    physicsButton.Text=physicsEnabled and "Physics assist: ON"or "Physics assist: OFF"
    label.Text=physicsEnabled and "Physics ground approach enabled. F6 starts."
        or "Model only. Ball monitoring remains active. F6 starts."
end)
supportButton.Activated:Connect(function()
    stop();intercept.supportEnabled=not intercept.supportEnabled
    supportButton.Text=intercept.supportEnabled and "Yield to teammate: ON"or "Yield to teammate: OFF"
    label.Text=intercept.supportEnabled and "Ground assist may yield to a nearby, aligned teammate actively approaching the ball."
        or "Scripted teammate yielding disabled. F6 starts."
end)
reportButton.Activated:Connect(function()
    local savedFrom=runtimeSnapshot(os.clock())
    stop("Paused to save physics report.")
    local ok,reason=pcall(function()
        saveReport("TurboBall_Physics_Report.json",savedFrom)
    end)
    label.Text=ok and "Saved TurboBall_Physics_Report.json in the executor workspace."
        or("Could not save physics report: "..tostring(reason))
end)
connect(input.InputBegan,function(key,processed)
    if key.KeyCode==Enum.KeyCode.F8 then stop("STOPPED by F8. F6 starts again.")
    elseif not processed and key.KeyCode==Enum.KeyCode.F6 then toggle()end
end)
connect(input.WindowFocusReleased,function()focus=false;stop("Paused: Roblox lost focus. F6 restarts.")end)
connect(input.WindowFocused,function()focus=true end)
close.Activated:Connect(function()
    alive=false;stop()
    for _,connection in ipairs(connections)do connection:Disconnect()end
    gui:Destroy()
end)
local function teamChanged()
    if testingKeyboard then stop("Team changed during keyboard test. F6 restarts.");return end
    epoch=epoch+1;release();carReader.tracked={};carReader.scanAt=-math.huge
    lastGround=true;armAt=os.clock()+.15
end
-- POSE_READER_HERE
local function loadTensors()
-- MODEL_TENSORS_HERE
end
task.spawn(function()
    local ok,errorText=pcall(function()
        assert(player.Name=="Deadline_coolgun"and game.PlaceId==101880234193261,
            "This adapter targets Deadline_coolgun / place 101880234193261")
        assert(not pg:FindFirstChild("Update271Bridge"),
            "Close the old bridge panel and stop START_FILE_BOT.bat before using LOCAL mode")
        pressLeft,releaseLeft=mouse1press,mouse1release
        pressRight,releaseRight=mouse2press,mouse2release
        for name,fn in pairs({mouse1press=pressLeft or false,mouse1release=releaseLeft or false,
            mouse2press=pressRight or false,mouse2release=releaseRight or false})do
            assert(type(fn)=="function","Missing executor input function: "..name)
        end
        if type(activeWindow)~="function"then activeWindow=nil end
        local predict=Policy.new(loadTensors())
        local cases=
-- MODEL_CASES_HERE
        local peak=0
        for _,case in ipairs(cases)do
            local began=os.clock()
            local action,logits=predict(case.query,case.entities)
            peak=math.max(peak,os.clock()-began)
            for i,value in ipairs(logits)do
                assert(math.abs(value-case.logits[i])<.0003+math.abs(case.logits[i])*.0001,
                    "Runtime model parity check failed at logit "..i)
            end
            assert(action==case.action,"Runtime model action check failed")
        end
        cases=nil
        if not alive then return end
        assert(peak<.2,"Local inference exceeds 200ms: this runtime is too slow")
        local period=1/15 -- target cadence; missed slots are skipped, never replayed in a burst
        local actions=Policy.actions()
        ready=true;start.Active=true
        label.Text=(MODEL_NAME.." LOCAL v6.3 ready | model self-test passed\nModel __MODEL_SHA__\nInference peak %.1f ms | target %.1f Hz\nGround assist %s | teammate yield OFF | F6 starts.")
            :format(peak*1000,1/period,physicsEnabled and "ON"or "OFF")
        local lastTick,lastUi=os.clock(),-math.huge
        local busy=false
        local rate=0
        connect(game:GetService("RunService").Heartbeat,function()
            if not alive or busy then return end
            local now=os.clock()
            local sampleDue,nextSample=Timing.due(now,sampleAt,enabled and 1/HZ or .1)
            if not sampleDue then return end
            sampleAt=nextSample
            local elapsed=now-lastTick;lastTick=now
            busy=true
            local stage="frame guard"
            local attemptAt=os.clock()
            local success,err=pcall(function()
                if enabled and(elapsed>.3 or not focus or input:GetFocusedTextBox()
                    or input:IsKeyDown(Enum.KeyCode.F8)or(activeWindow and not activeWindow()))then
                    stop("LOCAL paused: focus/chat/F8 or stalled frame. F6 restarts.")
                end
                stage="reading poses"
                local poseAt=os.clock()
                local packet,reason=read()
                local poseMs=(os.clock()-poseAt)*1000
                if reason~=lastReadReason then physics:mark(packet and "poses ready"or "waiting",now,reason)end
                lastReadReason=reason
                physics.runtime=runtimeSnapshot(now)
                stage="observing ball physics"
                local observeAt=os.clock()
                physics:observe(packet,now)
                local observeMs=(os.clock()-observeAt)*1000
                if not enabled or now<armAt then return end
                stage="verifying keyboard"
                local keyboardOk,keyboardReason=keyboard:verify()
                assert(keyboardOk,keyboardReason)
                if not packet then
                    release();label.Text="LOCAL waiting: "..tostring(reason);return
                end
                stage="kickoff"
                local override,recovery=kickoff:step(packet,now,pg)
                local decisionPeriod=override and 1/30 or period
                if previousPeriod~=decisionPeriod then decisionAt=nil;previousPeriod=decisionPeriod end
                local due,nextDecision,late=Timing.due(now,decisionAt,decisionPeriod)
                if not due then return end
                decisionAt=nextDecision
                local decisionEpoch=epoch
                local began=os.clock()
                local ground=packet.ground_estimate
                if ground and(not lastGround or previous[6]==0)then jumpAt=nil;usedFlip=false end
                lastGround=ground
                local hasFlip=ground or(not usedFlip and(not jumpAt or now-jumpAt<PROFILE.physics.DOUBLEJUMP_MAX_DELAY))
                local action=override
                local modelMs,planningMs,entityCount=0,0,0
                local modelRan=false
                physics.plan=nil
                if not action then
                    stage="recovery"
                    action,recovery=arenaAdapter:recovery(packet,previous,now)
                    local needsPolicy
                    if not action and physicsEnabled then
                        stage="ground interception"
                        local planningAt=os.clock()
                        action,recovery,needsPolicy=intercept:step(packet,nil,now)
                        planningMs=(os.clock()-planningAt)*1000
                    end
                    if not action then
                        stage="model observation"
                        local query,entities=Policy.observe(packet,previous,hasFlip)
                        entityCount=#entities
                        stage="model inference"
                        local modelAt=os.clock()
                        local index=predict(query,entities)
                        modelMs=(os.clock()-modelAt)*1000;modelRan=true
                        action=actions[index]
                        if needsPolicy then
                            stage="ground interception"
                            local planningAt=os.clock()
                            local assisted,mode=intercept:step(packet,action,now)
                            planningMs=planningMs+(os.clock()-planningAt)*1000
                            if assisted then action,recovery=assisted,mode end
                        end
                    end
                end
                stage="mapping inputs"
                local wanted,actual=Policy.keys(action,ground)
                local inferenceMs=(os.clock()-began)*1000
                assert(inferenceMs<200,"Local inference exceeded 200ms")
                -- Recheck before pressing: executor calls and prediction can yield.
                if epoch~=decisionEpoch or not enabled or not alive or not focus or input:GetFocusedTextBox()
                    or input:IsKeyDown(Enum.KeyCode.F8)or(activeWindow and not activeWindow())then
                    stop("LOCAL stopped before applying inputs");return
                end
                if actual[6]==1 and previous[6]==0 then
                    if ground then jumpAt=now else usedFlip=true end
                end
                local inputAt=os.clock()
                stage="releasing inputs"
                for _,key in ipairs(order)do
                    if held[key]and not wanted[key]then event(key,false);held[key]=nil end
                end
                for _,key in ipairs(order)do
                    if wanted[key]and not held[key]then
                        stage="pressing "..key
                        held[key]=true;event(key,true)
                        if epoch~=decisionEpoch or not enabled or not focus then
                            -- A yielding press can complete after F8 already released it.
                            held[key]=true;release();return
                        end
                        assert(os.clock()-inputAt<.2,"Executor input calls exceeded 200ms")
                    end
                end
                local inputMs=(os.clock()-inputAt)*1000
                stage="input timing"
                assert(inputMs<200,"Executor input calls exceeded 200ms")
                physics.decision={time=now,mode=recovery or "model",milliseconds=inferenceMs,
                    input_milliseconds=inputMs,action=table.clone(actual),model_milliseconds=modelMs,
                    planning_milliseconds=planningMs,model_ran=modelRan,entity_count=entityCount}
                timing:record({time=now,model_ran=modelRan,entities=entityCount,pose_ms=poseMs,observe_ms=observeMs,
                    model_ms=modelMs,planning_ms=planningMs,decision_ms=inferenceMs,input_ms=inputMs,schedule_late_ms=late*1000})
                previous=actual;rate=timing.rate
                if now-lastUi>=.2 then
                    stage="panel update"
                    lastUi=now
                    local names={};for _,key in ipairs(order)do if held[key]then names[#names+1]=key end end
                    label.Text=(MODEL_NAME.." v6.3 | %.1f Hz | %s\nDecision %.1f ms | inputs %.1f ms | %s\n%s %s | want %s | seen %s\nOpponents %d | teammates %d | unknown %d\nPads %d/%d -> %d | car %s%s\nBall %.2f%s | contacts %d | F8 stop\nPhysics %s | g %.0f | flight error %s")
                        :format(rate,keyboard.name,inferenceMs,inputMs,recovery or "model",manualTeam==nil and "AUTO"or "MANUAL",TEAM==0 and "BLUE"or "ORANGE",table.concat(names," "),keyboard:observed(),
                            packet.opponents or 0,packet.teammates or 0,packet.unknown_cars or 0,
                            packet.boost_known or 0,packet.boost_total or 0,#(packet.boost_pads or {}),
                            packet.car_preset or "standard",packet.car_size_verified and ""or "?",
                            packet.ball_radius or PROFILE.physics.BALL_RADIUS,packet.ball_size_verified and ""or "?",packet.wheel_contacts or 0,
                            physics.mismatch and "MISMATCH / model"or physics.status,physics.gravity,
                            physics.error and("%.1f units"):format(physics.error)or "unmeasured")
                end
            end)
            busy=false
            -- Keep the first stopped-run error. A broken pose source can also
            -- fail while paused; never overwrite the useful report every frame.
            if not success and(enabled or not physics.lastError)then
                local beforeStop=runtimeSnapshot(os.clock())
                physics.lastError={time=now,stage=stage,reason=tostring(err),
                    frame_seconds=elapsed,attempt_milliseconds=(os.clock()-attemptAt)*1000}
                stop("LOCAL stopped at "..stage..": "..tostring(err))
                if type(writefile)=="function"then
                    local saved=pcall(saveReport,"TurboBall_Last_Error.json",beforeStop)
                    if saved then label.Text=label.Text.."\nSaved TurboBall_Last_Error.json"end
                end
            end
        end)
    end)
    if not ok and alive then stop("LOCAL startup stopped: "..tostring(errorText))end
end)
return {started=true,version="local-6.3"}
