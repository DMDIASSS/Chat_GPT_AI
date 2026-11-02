"""Regressions for the reported old-garage stall and incomplete imported visuals."""
import unittest
import test_game as harness
roblox=harness.roblox


SKIN = '''
local C=require(nodes['Shared/Config.lua']);local Assets=require(nodes['Shared/Assets.lua'])
local library=Instance.new('Folder',replicated);library.Name='ImportedCars'
local template=Instance.new('Model',library);template.Name=C.Cars[1].template
local anchor=Instance.new('Part',template);anchor.Name='SkinRoot';anchor.Transparency=1;template.PrimaryPart=anchor
local shell=Instance.new('MeshPart',template);shell.Name='Shell';shell.MeshId='rbxassetid://123456789';shell.Transparency=0
'''


class StartupAssetTests(unittest.TestCase):
    run_lua=harness.GameTests.run_lua

    def test_default_startup_opens_menu_builds_road_and_restores_original_view(self):
        self.run_lua(roblox('''
    local ui=localPlayer.PlayerGui.ExpeditionUI
    assert(ui.ResponsiveCanvas.Visible and ui.ResponsiveCanvas.GarageMenu.Visible,'Working rally menu did not open automatically')
    assert(not oldGarage.Enabled,'Incomplete original garage still covers startup')
    local preview=ui.ResponsiveCanvas.GarageMenu.CarPreview
    assert(preview.CurrentCamera and preview:FindFirstChildOfClass('WorldModel'),'Car preview missing')
    local complete=false
    for _,p in ipairs(preview:GetDescendants())do if p.Name=='Chassis'and p.Transparency==0 then complete=true end end
    assert(complete,'Car preview depends on unavailable mesh assets')
    local function click(text)
     for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==text then o.Activated:Fire();return end end
     error('Missing button '..text)
    end
    ui.ResponsiveCanvas.GarageMenu.CourseSeed.Text='5'
    click('TAKE THE ROAD →');advance(7,true)
    local road=0;for _,o in ipairs(created)do if o.Name=='Road'and o.Parent then road+=1 end end
    assert(road>30 and ui.ResponsiveCanvas.DrivingHUD.Visible,'Starting from the default menu did not build a playable road')
    assert(services.Lighting.FogEnd==6000 and haze.Density==.18 and not blur.Enabled,'Original fog or blur obscures the road')
    services.Lighting.FogEnd=30;haze.Density=.9;blur.Enabled=true;advance(.1,true)
    assert(services.Lighting.FogEnd==6000 and haze.Density==.18 and not blur.Enabled,'Legacy effects reclaimed the new scene')
    click('RETURN TO ORIGINAL');advance(4,true)
    assert(oldGarage.Enabled and services.Lighting.FogStart==2 and services.Lighting.FogEnd==70)
    assert(haze.Density==.7 and haze.Haze==4 and blur.Enabled,'Original environment was not restored')
    ''',client=True,before_client='''
    local oldGarage=Instance.new('ScreenGui',localPlayer.PlayerGui);oldGarage.Name='OriginalGarage';oldGarage.Enabled=true
    services.Lighting.FogStart=2;services.Lighting.FogEnd=70
    local haze=Instance.new('Atmosphere',services.Lighting);haze.Density=.7;haze.Haze=4;haze.Glare=.3;haze.Offset=.2
    local blur=Instance.new('DepthOfFieldEffect',services.Lighting);blur.Enabled=true
    '''))


    def test_failed_mesh_download_keeps_complete_car_body(self):
        self.run_lua(roblox(SKIN+'''
    content.status=Enum.AssetFetchStatus.Failure
    local visual=Assets.car(workspace,C.Cars[1],false,true)
    assert(visual.model.Chassis.Transparency==0,'Body hidden before asset validation')
    advance(.3)
    assert(visual.model:GetAttribute('VisualSource')=='BuiltIn'and visual.model.Chassis.Transparency==0)
    assert(not visual.model:FindFirstChild('Original exterior'),'Failed mesh was shown instead of a complete body')
    assert(shell.Parent==template and shell.Transparency==0,'Source asset was changed')
    '''))


    def test_slow_mesh_download_cannot_replace_body_after_timeout(self):
        self.run_lua(roblox(SKIN+'''
    content.delay=20
    local visual=Assets.car(workspace,C.Cars[1],false,true)
    advance(9)
    assert(visual.model.Chassis.Transparency==0 and visual.model:GetAttribute('VisualSource')=='BuiltIn')
    advance(13)
    assert(visual.model.Chassis.Transparency==0 and not visual.model:FindFirstChild('Original exterior'),'Timed-out asset replaced the fallback late')
    '''))

    def test_unconfirmed_preload_cannot_hide_complete_car(self):
        self.run_lua(roblox(SKIN+'''
    function content:PreloadAsync()end
    local visual=Assets.car(workspace,C.Cars[1],false,true);advance(.3)
    assert(visual.model.Chassis.Transparency==0 and not visual.model:FindFirstChild('Original exterior'),'A preload without confirmed assets hid the body')
    '''))


    def test_loaded_skin_attaches_at_current_pose_and_preloads_once(self):
        self.run_lua(roblox(SKIN+'''
    content.delay=1
    local a=Assets.car(workspace,C.Cars[1],false,true)
    local b=Assets.car(workspace,C.Cars[1],false,true)
    local target=CFrame.new(123,7,45)*CFrame.Angles(0,.6,0);a.model:PivotTo(target)
    advance(.5)
    assert(a.model.Chassis.Transparency==0 and not a.model:FindFirstChild('Original exterior'))
    advance(1)
    assert(#content.calls==1,'The same template was preloaded repeatedly')
    assert(a.model:GetAttribute('VisualSource')=='Original'and b.model:GetAttribute('VisualSource')=='Original')
    local skin=a.model:FindFirstChild('Original exterior');assert(skin and a.model.Chassis.Transparency==1)
    assert((skin.PrimaryPart.Position-(target*CFrame.new(0,0,-C.Cars[1].wheelbase*(C.Cars[1].rearShare-.5))).Position).Magnitude<.001,'Late skin attached at the old origin')
    for _,wheel in ipairs(a.wheels)do assert(wheel.tyre.Transparency==0,'Skin hid the animated tyres')end
    assert(shell.Parent==template and shell.Transparency==0)
    '''))


    def test_unavailable_scenery_uses_generated_trees_and_complete_road(self):
        self.run_lua(roblox('''
    local C=require(nodes['Shared/Config.lua']);local Route=require(nodes['Shared/Route.lua']);local Stream=require(nodes['Client/RoadStream.lua'])
    local props=Instance.new('Folder',replicated);props.Name='ImportedProps'
    local template=Instance.new('Model',props);template.Name='ImportedSpruce'
    local mesh=Instance.new('MeshPart',template);mesh.Name='UnavailableTree';mesh.MeshId='rbxassetid://987654321'
    content.status=Enum.AssetFetchStatus.Failure
    local stream=Stream.new(workspace);stream:reset(Route.new(0,0,C),1,0);stream:update(800);stream:work(.003)
    advance(.3)
    local trees,roads=0,0
    for _,entry in pairs(stream.chunks)do for _,p in ipairs(entry.model:GetDescendants())do
     if p.Name=='Pine canopy'then trees+=1 elseif p.Name=='Road'then roads+=1 elseif p.Name=='UnavailableTree'then error('Unloaded scenery was cloned')end
    end end
    assert(trees>0 and roads>30 and stream:ready(800),'Asset failure interrupted road generation')
    '''))
