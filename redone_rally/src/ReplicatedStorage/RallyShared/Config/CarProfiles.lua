--!strict
-- CarProfiles.luau
-- Comprehensive rally car tuning specifications for 5 distinct era cars.

export type TorquePoint = { [number]: number } -- { RPM, TorqueMultiplier }

export type CarTuning = {
    Id: string,
    DisplayName: string,
    Class: string,
    Specs: {
        Power: string,
        Torque: string,
        Weight: string,
    },
    Chassis: {
        Mass: number,
        Wheelbase: number,
        TrackWidth: number,
        CGHeight: number,
        WeightDistributionFront: number,
        AxleOffset: number?, -- wheelbase midpoint relative to the saved shell
        WheelCenterY: number?,
        DriverEye: Vector3?,
    },
    Suspension: {
        Travel: number,
        Stiffness: number,
        Damping: number,
        AntiRollFront: number,
        AntiRollRear: number,
        SagFront: number,
        SagRear: number,
    },
    Tyres: {
        Radius: number,
        LateralGrip: number,
        LongitudinalGrip: number,
        PeakSlip: number,
        DriftWindow: number,
        Plateau: number,
        Tail: number,
        ForceLift: number,
        HandbrakeGrip: number,
        LiftOffOversteer: {
            GripReduction: number,
            Duration: number,
            MinSpeed: number,
        }?,
    },
    Steering: {
        MaxAngle: number,
        TurnRateDegrees: number, -- road-wheel degrees per second
        ReturnRateDegrees: number,
        Ackermann: number,
        Stability: number,
    },
    Engine: {
        IdleRPM: number,
        LaunchRPM: number,
        PeakRPM: number,
        Redline: number,
        BoostFrom: number,
        TorqueCurve: { { number } },
        Hybrid: {
            MaxCharge: number,
            DeployPower: number,
            DeployTime: number,
            DeployThrottleThreshold: number,
            RegenBraking: number,
            RegenLift: number,
        }?,
    },
    Transmission: {
        Type: "Manual" | "Sequential" | "Automatic",
        ShiftTime: number,
        FinalDrive: number,
        FrontShare: number,
        Ratios: { number },
        LSD: {
            FrontLock: number,
            CenterLock: number,
            RearLock: number,
        },
    },
    Brakes: {
        Force: number,
        FrontBias: number,
    },
}

local CarProfiles = {}

local BrennerS1: CarTuning = {
    Id = "BrennerS1",
    DisplayName = "Brenner S1 E2",
    Class = "Group B — Turbo 4WD",
    Specs = { Power = "510 hp", Torque = "590 Nm", Weight = "1090 kg" },
    Chassis = {
        Mass = 1090,
        Wheelbase = 8.3,
        TrackWidth = 5.6,
        AxleOffset = -0.25,
        WheelCenterY = -0.75,
        DriverEye = Vector3.new(-1.35, 2.1, 1),
        CGHeight = -0.95,
        WeightDistributionFront = 0.54,
    },
    Suspension = {
        Travel = 1.25,
        Stiffness = 38000,
        Damping = 4200,
        AntiRollFront = 0.54,
        AntiRollRear = 0.34,
        SagFront = 0.51,
        SagRear = 0.45,
    },
    Tyres = {
        Radius = 1.15,
        LateralGrip = 0.63,
        LongitudinalGrip = 0.68,
        PeakSlip = 6.2,
        DriftWindow = 21.0,
        Plateau = 0.91,
        Tail = 0.73,
        ForceLift = 0.55,
        HandbrakeGrip = 0.45,
    },
    Steering = {
        MaxAngle = 36.0,
        TurnRateDegrees = 60,
        ReturnRateDegrees = 75,
        Ackermann = 0.14,
        Stability = 3.1,
    },
    Engine = {
        IdleRPM = 1000,
        LaunchRPM = 5200,
        PeakRPM = 7400,
        Redline = 8100,
        BoostFrom = 3800,
        TorqueCurve = {
            { 1000, 0.28 },
            { 2500, 0.35 },
            { 3800, 0.52 },
            { 4500, 0.85 },
            { 5400, 1.00 },
            { 6600, 0.97 },
            { 7400, 0.88 },
            { 8100, 0.72 },
        },
    },
    Transmission = {
        Type = "Manual",
        ShiftTime = 0.12,
        FinalDrive = 4.35,
        FrontShare = 0.44,
        Ratios = { 14.6, 9.90, 7.45, 5.95, 4.85, 4.10 },
        LSD = {
            FrontLock = 0.55,
            CenterLock = 0.75,
            RearLock = 0.70,
        },
    },
    Brakes = {
        Force = 52.0,
        FrontBias = 0.60,
    },
}

local KazeRS: CarTuning = {
    Id = "KazeRS",
    DisplayName = "Kaze RS",
    Class = "Group A — 4WD Turbo Saloon",
    Specs = { Power = "320 hp", Torque = "480 Nm", Weight = "1230 kg" },
    Chassis = {
        Mass = 1230,
        Wheelbase = 9.0,
        TrackWidth = 5.214,
        AxleOffset = 0,
        WheelCenterY = -0.7,
        DriverEye = Vector3.new(-1.35, 2.2, 1),
        CGHeight = -1.10,
        WeightDistributionFront = 0.52,
    },
    Suspension = {
        Travel = 1.35,
        Stiffness = 32000,
        Damping = 3800,
        AntiRollFront = 0.48,
        AntiRollRear = 0.42,
        SagFront = 0.52,
        SagRear = 0.55,
    },
    Tyres = {
        Radius = 1.20,
        LateralGrip = 0.62,
        LongitudinalGrip = 0.66,
        PeakSlip = 6.8,
        DriftWindow = 24.0,
        Plateau = 0.92,
        Tail = 0.76,
        ForceLift = 0.50,
        HandbrakeGrip = 0.42,
    },
    Steering = {
        MaxAngle = 32.0,
        TurnRateDegrees = 60,
        ReturnRateDegrees = 75,
        Ackermann = 0.12,
        Stability = 2.6,
    },
    Engine = {
        IdleRPM = 900,
        LaunchRPM = 3800,
        PeakRPM = 5600,
        Redline = 7250,
        BoostFrom = 3000,
        TorqueCurve = {
            { 800,  0.42 },
            { 2000, 0.55 },
            { 3000, 0.75 },
            { 4600, 1.00 },
            { 5600, 0.98 },
            { 6400, 0.88 },
            { 7250, 0.70 },
        },
    },
    Transmission = {
        Type = "Sequential",
        ShiftTime = 0.15,
        FinalDrive = 4.44,
        FrontShare = 0.38,
        Ratios = { 16.0, 10.9, 8.30, 6.60, 5.50, 4.65 },
        LSD = {
            FrontLock = 0.45,
            CenterLock = 0.60,
            RearLock = 0.65,
        },
    },
    Brakes = {
        Force = 46.0,
        FrontBias = 0.62,
    },
}

local FalkeE3: CarTuning = {
    Id = "FalkeE3",
    DisplayName = "Falke E3",
    Class = "Historic — RWD Rally Saloon",
    Specs = { Power = "285 hp", Torque = "310 Nm", Weight = "1040 kg" },
    Chassis = {
        Mass = 1040,
        Wheelbase = 9.15,
        TrackWidth = 5.3,
        AxleOffset = -0.175,
        WheelCenterY = -0.75,
        DriverEye = Vector3.new(-1.35, 2.2, 1),
        CGHeight = -1.15,
        WeightDistributionFront = 0.50,
    },
    Suspension = {
        Travel = 1.10,
        Stiffness = 34000,
        Damping = 3600,
        AntiRollFront = 0.50,
        AntiRollRear = 0.40,
        SagFront = 0.53,
        SagRear = 0.49,
    },
    Tyres = {
        Radius = 1.15,
        LateralGrip = 0.56,
        LongitudinalGrip = 0.60,
        PeakSlip = 7.0,
        DriftWindow = 26.0,
        Plateau = 0.92,
        Tail = 0.76,
        ForceLift = 0.45,
        HandbrakeGrip = 0.54,
    },
    Steering = {
        MaxAngle = 35.0,
        TurnRateDegrees = 60,
        ReturnRateDegrees = 75,
        Ackermann = 0.10,
        Stability = 2.5,
    },
    Engine = {
        IdleRPM = 900,
        LaunchRPM = 4200,
        PeakRPM = 6800,
        Redline = 8250,
        BoostFrom = 100000,
        TorqueCurve = {
            { 800,  0.50 },
            { 2000, 0.66 },
            { 3500, 0.82 },
            { 4800, 0.98 },
            { 5800, 1.00 },
            { 6800, 0.96 },
            { 7600, 0.88 },
            { 8250, 0.78 },
        },
    },
    Transmission = {
        Type = "Manual",
        ShiftTime = 0.17,
        FinalDrive = 4.10,
        FrontShare = 0.00,
        Ratios = { 15.6, 10.5, 8.00, 6.50, 5.45 },
        LSD = {
            FrontLock = 0.00,
            CenterLock = 0.00,
            RearLock = 0.75,
        },
    },
    Brakes = {
        Force = 44.0,
        FrontBias = 0.64,
    },
}

local KumoR1: CarTuning = {
    Id = "KumoR1",
    DisplayName = "Kumo R1 Hybrid",
    Class = "Rally1 — Hybrid 4WD",
    Specs = { Power = "530 hp (Combustion + Hybrid)", Torque = "620 Nm", Weight = "1260 kg" },
    Chassis = {
        Mass = 1260,
        Wheelbase = 9.4,
        TrackWidth = 5.507,
        AxleOffset = 0,
        WheelCenterY = -0.65,
        DriverEye = Vector3.new(-1.35, 2.2, 1),
        CGHeight = -1.25,
        WeightDistributionFront = 0.51,
    },
    Suspension = {
        Travel = 1.40,
        Stiffness = 30000,
        Damping = 4400,
        AntiRollFront = 0.50,
        AntiRollRear = 0.44,
        SagFront = 0.58,
        SagRear = 0.58,
    },
    Tyres = {
        Radius = 1.20,
        LateralGrip = 0.66,
        LongitudinalGrip = 0.70,
        PeakSlip = 6.2,
        DriftWindow = 20.0,
        Plateau = 0.92,
        Tail = 0.76,
        ForceLift = 0.55,
        HandbrakeGrip = 0.62,
    },
    Steering = {
        MaxAngle = 35.0,
        TurnRateDegrees = 60,
        ReturnRateDegrees = 75,
        Ackermann = 0.15,
        Stability = 3.4,
    },
    Engine = {
        IdleRPM = 1100,
        LaunchRPM = 4800,
        PeakRPM = 5500,
        Redline = 7800,
        BoostFrom = 2400,
        TorqueCurve = {
            { 800,  0.55 },
            { 2000, 0.80 },
            { 3000, 0.95 },
            { 3500, 1.00 },
            { 5500, 1.00 },
            { 6500, 0.94 },
            { 7200, 0.85 },
            { 7800, 0.74 },
        },
        Hybrid = {
            MaxCharge = 1.0,
            DeployPower = 550.0,
            DeployTime = 3.5,
            DeployThrottleThreshold = 0.90,
            RegenBraking = 0.35,
            RegenLift = 0.05,
        },
    },
    Transmission = {
        Type = "Sequential",
        ShiftTime = 0.09,
        FinalDrive = 4.60,
        FrontShare = 0.42,
        Ratios = { 16.2, 10.9, 8.10, 6.35, 5.06 },
        LSD = {
            FrontLock = 0.50,
            CenterLock = 0.65,
            RearLock = 0.60,
        },
    },
    Brakes = {
        Force = 56.0,
        FrontBias = 0.60,
    },
}

local FrecciaHF: CarTuning = {
    Id = "FrecciaHF",
    DisplayName = "Freccia HF",
    Class = "Historic — FWD Coupe",
    Specs = { Power = "145 hp", Torque = "175 Nm", Weight = "880 kg" },
    Chassis = {
        Mass = 880,
        Wheelbase = 9.0,
        TrackWidth = 5.204,
        AxleOffset = -0.5,
        WheelCenterY = -0.75,
        DriverEye = Vector3.new(-1.35, 1.8, 1),
        CGHeight = -1.05,
        WeightDistributionFront = 0.62,
    },
    Suspension = {
        Travel = 1.05,
        Stiffness = 26000,
        Damping = 2900,
        AntiRollFront = 0.48,
        AntiRollRear = 0.44,
        SagFront = 0.57,
        SagRear = 0.46,
    },
    Tyres = {
        Radius = 1.10,
        LateralGrip = 0.62,
        LongitudinalGrip = 0.80,
        PeakSlip = 7.0,
        DriftWindow = 22.0,
        Plateau = 0.90,
        Tail = 0.74,
        ForceLift = 0.42,
        HandbrakeGrip = 0.46,
        LiftOffOversteer = {
            GripReduction = 0.82,
            Duration = 0.70,
            MinSpeed = 30.0,
        },
    },
    Steering = {
        MaxAngle = 35.0,
        TurnRateDegrees = 60,
        ReturnRateDegrees = 75,
        Ackermann = 0.12,
        Stability = 2.3,
    },
    Engine = {
        IdleRPM = 950,
        LaunchRPM = 4600,
        PeakRPM = 5800,
        Redline = 7400,
        BoostFrom = 100000,
        TorqueCurve = {
            { 800,  0.45 },
            { 2000, 0.62 },
            { 3000, 0.76 },
            { 4000, 0.88 },
            { 5000, 0.97 },
            { 5800, 1.00 },
            { 6600, 0.95 },
            { 7400, 0.76 },
        },
    },
    Transmission = {
        Type = "Manual",
        ShiftTime = 0.20,
        FinalDrive = 4.25,
        FrontShare = 1.00,
        Ratios = { 15.5, 10.4, 7.70, 6.10, 4.95 },
        LSD = {
            FrontLock = 0.40,
            CenterLock = 0.00,
            RearLock = 0.00,
        },
    },
    Brakes = {
        Force = 42.0,
        FrontBias = 0.64,
    },
}

CarProfiles.Cars = {
    BrennerS1 = BrennerS1,
    KazeRS = KazeRS,
    FalkeE3 = FalkeE3,
    KumoR1 = KumoR1,
    FrecciaHF = FrecciaHF,
}

function CarProfiles.Get(carId: string): CarTuning
    local car = CarProfiles.Cars[carId]
    if not car then
        return CarProfiles.Cars.KazeRS
    end
    return car
end

function CarProfiles.GetAllIds(): { string }
    return { "BrennerS1", "KazeRS", "FalkeE3", "KumoR1", "FrecciaHF" }
end

return CarProfiles
