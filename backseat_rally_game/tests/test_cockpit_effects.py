import unittest
import test_game as harness
roblox = harness.roblox


class CockpitEffectsTests(unittest.TestCase):
    run_lua = harness.GameTests.run_lua
    def test_native_cabin_instruments_and_steering_are_bounded(self):
        self.run_lua(roblox('''
local Cockpit=require(nodes['Client/Cockpit.lua'])
local cabin=Cockpit.new(workspace,{shiftRpm=6500})
local before=#created
local state={v=40,steer=.5,rpm=4200,gear=3,damage=0,tyres={{pressure=.9},{pressure=.9},{pressure=1},{pressure=1}}}
local transform=CFrame.new(300,22,190)*CFrame.Angles(.03,.8,.02)
for i=1,600 do cabin:update(transform,state,1/60,false)end
assert(#created==before,'Cabin allocated objects while driving')
assert(#cabin.parts<50 and #cabin.wheel==15,'Unbounded cockpit geometry')
assert(cabin.speed.Text=='040'and cabin.gear.Text=='3'and cabin.rpm.Text=='4200 RPM','Dashboard did not show live telemetry')
assert(cabin.pressure.Text=='TYRES  95%','Tyre pressures not shown')
local steeringPart=cabin.wheel[1].part
local angled=steeringPart.CFrame
state.steer=-.5;cabin:update(transform,state,.1,false)
assert((steeringPart.Position-angled.Position).Magnitude>.1,'Wheel did not turn with steering')
state.tyres[1].punctured=true;cabin:update(transform,state,.11,true)
assert(cabin.status.Text=='PUNCTURE / PIT','Cabin did not warn about puncture')
cabin:setVisible(false);for _,entry in ipairs(cabin.parts)do assert(entry.part.Transparency==1)end
cabin:setVisible(true);assert(cabin.model['Padded dashboard'].Transparency==0)
cabin:destroy();assert(not cabin.model.Parent)
''', server=False))

    def test_crash_overlays_have_options_and_fade_without_allocations(self):
        self.run_lua(roblox('''
local Effects=require(nodes['Client/Effects.lua'])
local fx=Effects.new(localPlayer.PlayerGui)
local count=#created
fx:update({v=110,impact=1,crashes=1},.01,{crashEffects='blackout'},false)
assert(fx.black.BackgroundTransparency==0,'Severe hit did not black out with option enabled')
for i=1,160 do fx:update({v=0,impact=0,crashes=1},.016,{crashEffects='blackout'},false)end
assert(fx.black.BackgroundTransparency==1 and fx.red.BackgroundTransparency==1,'Crash left a permanent screen')
fx:update({v=30,impact=1,crashes=2},.01,{crashEffects='blackout'},false)
assert(fx.black.BackgroundTransparency==1 and fx.red.BackgroundTransparency<1,'Minor hit should show only red')
fx:update({v=110,impact=1,crashes=3},.01,{crashEffects='off'},false)
assert(fx.red.BackgroundTransparency==1 and fx.black.BackgroundTransparency==1,'Disabled crash effects remained')
fx:update({v=110,impact=1,crashes=4},.01,{crashEffects='blackout'},true)
assert(fx.black.BackgroundTransparency==1 and fx.red.BackgroundTransparency==1,'Replay camera blacked out')
assert(#created==count,'Impacts allocated objects per frame')
fx:reset();assert(fx.strength==0);fx:destroy();assert(not fx.root.Parent)
''', server=False))

    def test_weather_quality_caps_and_dry_reset(self):
        self.run_lua(roblox('''
local Effects=require(nodes['Client/Effects.lua']);local fx=Effects.new(localPlayer.PlayerGui)
local count=#created
local function visible()local n=0;for _,drop in ipairs(fx.rain)do if drop.Visible then n+=1 end end;return n end
fx:update({},.016,{quality='low'},false,{wetness=.6});assert(visible()==8)
for i=1,300 do fx:update({},.016,{quality='high'},false,{wetness=.6})end
assert(visible()==24 and #created==count,'Rain escaped its quality budget')
fx:update({},.016,{quality='high'},false,{wetness=.1});assert(visible()==0,'Rain stayed on dry road')
''', server=False))
