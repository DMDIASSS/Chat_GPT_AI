-- Generated LOCAL model + telemetry + controls. Weights stay on this PC.
-- LOCAL_POLICY_HERE
-- LOCAL_KEYBOARD_HERE
local TEAM=0
local HZ=30 -- pose sampling; policy decisions target 15 Hz (tick skip 8 at 120 Hz)
local player=game:GetService("Players").LocalPlayer
local pg=assert(player:FindFirstChildOfClass("PlayerGui"),"Join first")
assert(not pg:FindFirstChild("Update271Standalone"),"Close the old standalone panel first")
local gui=Instance.new("ScreenGui")
gui.Name="Update271Standalone";gui.ResetOnSpawn=false;gui.DisplayOrder=1000072
local panel=Instance.new("Frame",gui)
panel.Size=UDim2.fromOffset(440,180);panel.Position=UDim2.fromOffset(20,20)
panel.BackgroundColor3=Color3.fromRGB(18,22,30)
local label=Instance.new("TextLabel",panel)
label.Position=UDim2.fromOffset(10,8);label.Size=UDim2.new(1,-20,0,125)
label.BackgroundTransparency=1;label.TextColor3=Color3.new(1,1,1)
label.TextSize=14;label.Font=Enum.Font.Code;label.TextWrapped=true
label.Text="Update271 LOCAL: loading private model..."
local start=Instance.new("TextButton",panel)
start.Position=UDim2.fromOffset(10,140);start.Size=UDim2.fromOffset(150,30)
start.Text="Start bot / F6";start.Active=false
local teamButton=Instance.new("TextButton",panel)
teamButton.Position=UDim2.fromOffset(170,140);teamButton.Size=UDim2.fromOffset(140,30)
teamButton.Text="Team: BLUE"
local close=Instance.new("TextButton",panel)
close.Position=UDim2.fromOffset(320,140);close.Size=UDim2.fromOffset(110,30);close.Text="Close"
gui.Parent=pg
local input=game:GetService("UserInputService")
local world=game:GetService("Workspace")
local alive,enabled,ready,armAt=true,false,false,0
local testingKeyboard=false
local epoch=0
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
end
local function controls()
    start.Visible=not enabled and not testingKeyboard
    teamButton.Visible=not enabled and not testingKeyboard
    close.Visible=not enabled and not testingKeyboard
end
local function stop(reason)
    epoch=epoch+1;enabled=false;testingKeyboard=false;release();controls()
    if reason then label.Text=reason end
end
local function toggle()
    if not ready then return end
    if enabled or testingKeyboard then stop("LOCAL paused. F6 starts; F8 stops.");return end
    epoch=epoch+1
    if keyboard.selected then enabled=true;armAt=os.clock()+.5;controls();return end
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
    end)
end
local function connect(signal,callback)
    local connection=signal:Connect(callback);connections[#connections+1]=connection
end
start.Activated:Connect(toggle)
teamButton.Activated:Connect(function()
    stop();TEAM=1-TEAM;teamButton.Text=TEAM==0 and "Team: BLUE"or "Team: ORANGE"
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
        local period=math.max(1/15,peak*1.3)
        local actions=Policy.actions()
        ready=true;start.Active=true
        label.Text=("Update271 LOCAL v2 ready | model self-test passed\nModel __MODEL_SHA__\nInference %.1f ms | target %.1f Hz\nF6 tests keyboard, then starts. F8 stops.")
            :format(peak*1000,1/period)
        local lastTick,lastDecision,lastUi=os.clock(),-math.huge,-math.huge
        local busy=false
        local count,rateStart,rate=0,os.clock(),0
        connect(game:GetService("RunService").Heartbeat,function()
            if not alive or busy then return end
            local now=os.clock()
            if now-lastTick<1/HZ then return end
            local elapsed=now-lastTick;lastTick=now
            busy=true
            local success,err=pcall(function()
                if enabled and(elapsed>.3 or not focus or input:GetFocusedTextBox()
                    or input:IsKeyDown(Enum.KeyCode.F8)or(activeWindow and not activeWindow()))then
                    stop("LOCAL paused: focus/chat/F8 or stalled frame. F6 restarts.")
                end
                local packet,reason=read()
                if not enabled or now<armAt then return end
                local keyboardOk,keyboardReason=keyboard:verify()
                assert(keyboardOk,keyboardReason)
                if not packet then
                    release();label.Text="LOCAL waiting: "..tostring(reason);return
                end
                if now-lastDecision<period then return end
                lastDecision=now
                local decisionEpoch=epoch
                local began=os.clock()
                local ground=packet.ground_estimate
                if ground and(not lastGround or previous[6]==0)then jumpAt=nil;usedFlip=false end
                lastGround=ground
                local hasFlip=ground or(not usedFlip and(not jumpAt or now-jumpAt<1.45))
                local query,entities=Policy.observe(packet,previous,hasFlip)
                local index=predict(query,entities)
                local wanted,actual=Policy.keys(actions[index],ground)
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
                for _,key in ipairs(order)do
                    if held[key]and not wanted[key]then event(key,false);held[key]=nil end
                end
                for _,key in ipairs(order)do
                    if wanted[key]and not held[key]then
                        held[key]=true;event(key,true)
                        if epoch~=decisionEpoch or not enabled or not focus then
                            -- A yielding press can complete after F8 already released it.
                            held[key]=true;release();return
                        end
                        assert(os.clock()-inputAt<.2,"Executor input calls exceeded 200ms")
                    end
                end
                local inputMs=(os.clock()-inputAt)*1000
                assert(inputMs<200,"Executor input calls exceeded 200ms")
                previous=actual;count=count+1
                if now-rateStart>=1 then rate=count/(now-rateStart);count=0;rateStart=now end
                if now-lastUi>=.2 then
                    lastUi=now
                    local names={};for _,key in ipairs(order)do if held[key]then names[#names+1]=key end end
                    label.Text=("LOCAL v2 | %.1f decisions/s | %s\nInference %.1f ms | inputs %.1f ms\nRequested %s | action %d\nKeyboard seen: %s | F6 pause; F8 stop")
                        :format(rate,keyboard.name,inferenceMs,inputMs,table.concat(names," "),index-1,keyboard:observed())
                end
            end)
            busy=false
            if not success then stop("LOCAL stopped: "..tostring(err))end
        end)
    end)
    if not ok and alive then stop("LOCAL startup stopped: "..tostring(errorText))end
end)
return {started=true,version="local-2"}
