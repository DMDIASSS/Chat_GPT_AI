--!strict
-- Pace notes derived from signed horizontal curvature and measured vertical grades.
local CatmullRom = require(script.Parent.CatmullRom)
export type PaceNote = {
    Index: number, Position: Vector3, ProgressRatio: number,
    DistanceAlongTrack: number, EndDistance: number, Severity: number,
    Direction: "Left" | "Right" | "Straight", Modifier: string?,
    CornerLength: number, Description: string,
}
local CurvatureAnalyzer = {}
CurvatureAnalyzer.SEVERITY = { VERY_TIGHT=1, TIGHT=2, SHARP=3, MEDIUM=4, FAST=5, FLAT_OUT=6, HAIRPIN=7, SQUARE=8, FLAT=9 }

function CurvatureAnalyzer.ClassifyCorner(radius: number, deflection: number): (number, string)
    local angle = math.abs(deflection)
    if radius <= 65 and angle >= 115 then return 7, "Hairpin"
    elseif radius <= 90 and angle >= 75 and angle <= 110 then return 8, "Square"
    elseif radius <= 64 then return 1, "1"
    elseif radius <= 110 then return 2, "2"
    elseif radius <= 185 then return 3, "3"
    elseif radius <= 290 then return 4, "4"
    elseif radius <= 420 then return 5, "5"
    elseif radius <= 800 then return 6, "6" end
    return 9, "Flat"
end

function CurvatureAnalyzer.ComputeDiscreteCurvature(a: Vector3, b: Vector3, c: Vector3): (number, number)
    local u, v = b-a, c-b
    local flatU, flatV = Vector3.new(u.X,0,u.Z), Vector3.new(v.X,0,v.Z)
    if flatU.Magnitude < 1e-4 or flatV.Magnitude < 1e-4 then return 0, 1 end
    -- Negative heading change means LEFT in Roblox's X/Z plane.
    local angle = math.atan2(flatV.Z,flatV.X) - math.atan2(flatU.Z,flatU.X)
    angle = (angle + math.pi) % (2*math.pi) - math.pi
    local ds = math.max(0.1, (u.Magnitude+v.Magnitude)*0.5)
    return math.abs(angle)/ds, (angle < 0 and -1 or 1)
end

function CurvatureAnalyzer.AnalyzeStage(samples: { CatmullRom.SplineSample }): { PaceNote }
    if #samples < 4 then return {} end
    local notes: { PaceNote } = {}
    local curvature: { number } = {}
    for i=2,#samples-1 do
        local k, sign = CurvatureAnalyzer.ComputeDiscreteCurvature(samples[i-1].Position,samples[i].Position,samples[i+1].Position)
        curvature[i] = k*sign
    end
    curvature[1],curvature[#samples] = 0,0
    local smooth: { number } = {}
    for i=1,#samples do
        smooth[i] = (curvature[math.max(1,i-1)]+curvature[i]*2+curvature[math.min(#samples,i+1)])*0.25
    end
    local startIndex, endIndex, direction, peak, deflection = 0,0,0,0,0
    local function finishCorner()
        if startIndex == 0 then return end
        local a,b = samples[startIndex],samples[endIndex]
        local length = b.Distance-a.Distance
        if length >= 12 and math.abs(deflection) >= 4 then
            local severity, name = CurvatureAnalyzer.ClassifyCorner(1/math.max(1e-6,peak),deflection)
            if severity ~= 9 then
                local dir = direction < 0 and "Left" or "Right"
                local modifiers = {}
                if length >= 180 then table.insert(modifiers,"Long") end
                local entry,exit = math.abs(smooth[math.min(endIndex,startIndex+1)]), math.abs(smooth[math.max(startIndex,endIndex-1)])
                if exit > math.max(0.002,entry*1.6) then table.insert(modifiers,"tightens")
                elseif entry > math.max(0.002,exit*1.6) then table.insert(modifiers,"opens") end
                local modifier = table.concat(modifiers,", ")
                table.insert(notes,{
                    Index=0,Position=a.Position,ProgressRatio=a.Progress,
                    DistanceAlongTrack=a.Distance,EndDistance=b.Distance,
                    Severity=severity,Direction=dir,Modifier=modifier,
                    CornerLength=length,Description=dir.." "..name..(modifier~="" and (", "..modifier) or ""),
                })
            end
        end
        startIndex,endIndex,direction,peak,deflection = 0,0,0,0,0
    end
    for i=2,#samples-1 do
        local k = smooth[i]
        local sign = k < 0 and -1 or 1
        local threshold = startIndex > 0 and 0.0008 or 0.00125
        if math.abs(k) >= threshold then
            if startIndex > 0 and direction ~= sign then finishCorner() end
            if startIndex == 0 then startIndex,direction = i,sign end
            endIndex = math.min(#samples,i+1)
            peak = math.max(peak,math.abs(k))
            deflection += math.deg(k*(samples[i+1].Distance-samples[i].Distance))
        else
            finishCorner()
        end
    end
    finishCorner()
    -- One crest per vertical feature, rather than a new warning every eight slices.
    local lastCrestDistance = -math.huge
    for i=4,#samples-3 do
        local a,b,c = samples[i-3],samples[i],samples[i+3]
        local gradeIn = (b.Position.Y-a.Position.Y)/math.max(1,b.Distance-a.Distance)
        local gradeOut = (c.Position.Y-b.Position.Y)/math.max(1,c.Distance-b.Distance)
        if gradeIn > 0.035 and gradeOut < -0.035 and gradeOut-gradeIn < -0.15 and b.Distance-lastCrestDistance >= 120 then
            lastCrestDistance = b.Distance
            table.insert(notes,{Index=0,Position=b.Position,ProgressRatio=b.Progress,
                DistanceAlongTrack=b.Distance,EndDistance=b.Distance+25,
                Severity=9,Direction="Straight",Modifier="Crest",CornerLength=25,Description="Crest"})
        end
    end
    table.sort(notes,function(a,b) return a.DistanceAlongTrack < b.DistanceAlongTrack end)
    for i,note in ipairs(notes) do note.Index=i end
    return notes
end

function CurvatureAnalyzer.FormatPaceNote(note: any): string
    return note.Description or (tostring(note.Direction or "Straight").." "..tostring(note.Severity or 6))
end
return CurvatureAnalyzer
