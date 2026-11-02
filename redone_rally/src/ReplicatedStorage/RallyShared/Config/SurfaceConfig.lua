--!strict
-- SurfaceConfig.luau
-- Surface properties dictionary with friction, rolling resistance, bump agitation, and Pacejka parameters.

export type SurfaceProperties = {
    Name: string,
    Lateral: number,
    Longitudinal: number,
    RollingResistance: number,
    BumpAmplitude: number,
    BumpFrequency: number,
    PeakSlip: number,
    DriftWindow: number,
    Plateau: number,
    Tail: number,
    Pacejka: {
        B: number, -- Stiffness
        C: number, -- Shape
        D: number, -- Peak
        E: number, -- Curvature
    },
    Material: Enum.Material,
    Color: Color3,
    TireParticleColor: Color3,
}

local SurfaceConfig = {}

local Surfaces: { [string]: SurfaceProperties } = {
    Tarmac = {
        Name = "Tarmac",
        Lateral = 1.35,
        Longitudinal = 1.30,
        RollingResistance = 0.015,
        BumpAmplitude = 0.02,
        BumpFrequency = 4.0,
        PeakSlip = 4.0,
        DriftWindow = 4.0, -- Tight drift window (4° to 8°)
        Plateau = 0.88,
        Tail = 0.65,
        Pacejka = { B = 10.5, C = 1.65, D = 1.35, E = -0.4 },
        Material = Enum.Material.Asphalt,
        Color = Color3.fromRGB(55, 55, 60),
        TireParticleColor = Color3.fromRGB(180, 180, 180),
    },
    Gravel = {
        Name = "Gravel",
        Lateral = 1.00,
        Longitudinal = 1.00,
        RollingResistance = 0.055,
        BumpAmplitude = 0.12,
        BumpFrequency = 16.0,
        PeakSlip = 15.0,
        DriftWindow = 20.0, -- Wide drift plateau (15° to 35°)
        Plateau = 0.92,
        Tail = 0.78,
        Pacejka = { B = 6.2, C = 1.35, D = 1.00, E = 0.1 },
        Material = Enum.Material.Sandstone,
        Color = Color3.fromRGB(138, 115, 85),
        TireParticleColor = Color3.fromRGB(160, 140, 110),
    },
    Mud = {
        Name = "Mud",
        Lateral = 0.65,
        Longitudinal = 0.62,
        RollingResistance = 0.120,
        BumpAmplitude = 0.18,
        BumpFrequency = 8.0,
        PeakSlip = 15.0,
        DriftWindow = 20.0, -- Wide drift plateau (15° to 35°)
        Plateau = 0.89,
        Tail = 0.72,
        Pacejka = { B = 4.0, C = 1.20, D = 0.65, E = 0.2 },
        Material = Enum.Material.Mud,
        Color = Color3.fromRGB(82, 58, 40),
        TireParticleColor = Color3.fromRGB(90, 65, 45),
    },
    Wet = {
        Name = "Wet",
        Lateral = 0.88,
        Longitudinal = 0.82,
        RollingResistance = 0.035,
        BumpAmplitude = 0.05,
        BumpFrequency = 5.0,
        PeakSlip = 6.8,
        DriftWindow = 20.0,
        Plateau = 0.85,
        Tail = 0.68,
        Pacejka = { B = 7.5, C = 1.45, D = 0.88, E = -0.2 },
        Material = Enum.Material.Concrete,
        Color = Color3.fromRGB(70, 75, 80),
        TireParticleColor = Color3.fromRGB(200, 210, 220),
    },
    Grass = {
        Name = "Grass",
        Lateral = 0.60,
        Longitudinal = 0.58,
        RollingResistance = 0.080,
        BumpAmplitude = 0.14,
        BumpFrequency = 10.0,
        PeakSlip = 8.0,
        DriftWindow = 22.0,
        Plateau = 0.86,
        Tail = 0.70,
        Pacejka = { B = 5.0, C = 1.25, D = 0.60, E = 0.15 },
        Material = Enum.Material.Grass,
        Color = Color3.fromRGB(75, 110, 50),
        TireParticleColor = Color3.fromRGB(95, 130, 65),
    },
    Snow = {
        Name = "Snow",
        Lateral = 0.45,
        Longitudinal = 0.48,
        RollingResistance = 0.040,
        BumpAmplitude = 0.06,
        BumpFrequency = 3.0,
        PeakSlip = 8.0,
        DriftWindow = 26.0,
        Plateau = 0.87,
        Tail = 0.72,
        Pacejka = { B = 3.8, C = 1.20, D = 0.45, E = 0.2 },
        Material = Enum.Material.Snow,
        Color = Color3.fromRGB(230, 235, 240),
        TireParticleColor = Color3.fromRGB(240, 245, 255),
    },
}

SurfaceConfig.Surfaces = Surfaces

-- Material fallback mapping
local MaterialMap: { [Enum.Material]: string } = {
    [Enum.Material.Asphalt] = "Tarmac",
    [Enum.Material.Concrete] = "Tarmac",
    [Enum.Material.Cobblestone] = "Tarmac",
    [Enum.Material.Sandstone] = "Gravel",
    [Enum.Material.Rock] = "Gravel",
    [Enum.Material.Sand] = "Gravel",
    [Enum.Material.Ground] = "Gravel",
    [Enum.Material.Mud] = "Mud",
    [Enum.Material.Grass] = "Grass",
    [Enum.Material.LeafyGrass] = "Grass",
    [Enum.Material.Snow] = "Snow",
    [Enum.Material.Ice] = "Snow",
    [Enum.Material.Water] = "Wet",
}

function SurfaceConfig.Get(surfaceName: string?): SurfaceProperties
    if surfaceName and Surfaces[surfaceName] then
        return Surfaces[surfaceName]
    end
    return Surfaces.Gravel
end

function SurfaceConfig.GetFromMaterial(mat: Enum.Material): SurfaceProperties
    local name = MaterialMap[mat] or "Gravel"
    return Surfaces[name]
end

function SurfaceConfig.Detect(hitPart: BasePart?, hitMaterial: Enum.Material?): SurfaceProperties
    if not hitPart then
        return Surfaces.Gravel
    end
    local attr = hitPart:GetAttribute("SurfaceType")
    if typeof(attr) == "string" and Surfaces[attr] then
        return Surfaces[attr]
    end
    if hitMaterial and MaterialMap[hitMaterial] then
        return Surfaces[MaterialMap[hitMaterial]]
    end
    return Surfaces.Gravel
end

return SurfaceConfig
