import unittest
import test_game as game
APP=game.APP


def preferences(extra):
    return 'local P=(function()\n'+(APP/'src/Shared/Preferences.lua').read_text()+'\nend)()\n'+extra


def settings_mock(extra):
    text=(APP/'tests/roblox_mock.luau').read_text()
    text+="\nlocal nodes={}\nlocal root=Instance.new('Folder',services.ReplicatedStorage);root.Name='BackseatExpedition'\nlocal shared=Instance.new('Folder',root);shared.Name='Shared'\n"
    for group,name,parent in [('Shared','Preferences','shared'),('Client','Settings','sps')]:
        key=f'{group}/{name}.lua'
        text+=f"nodes['{key}']=Instance.new('ModuleScript',{parent});nodes['{key}'].Name='{name}'\n"
        text+=f"modules[nodes['{key}']]=function(script)\n"+(APP/'src'/group/f'{name}.lua').read_text()+'\nend\n'
    return text+extra


class SettingsTests(unittest.TestCase):
    run_lua = game.GameTests.run_lua

    def test_preferences_reject_nonfinite_and_out_of_range_values(self):
        self.run_lua(preferences('''
local d=P.defaults();assert(d.values.assists and d.values.damage)
local s=P.normalize({values={fov=1000,seatHeight=-900,shake=0/0,damage=false,assists=false,quality='ultra',tyrePressure=math.huge}})
assert(s.values.fov==100 and s.values.seatHeight==-.5)
assert(s.values.shake==.5 and s.values.damage==false and s.values.assists==false)
assert(s.values.quality=='medium'and s.values.tyrePressure==1)
assert(P.value('unknown',123)==nil)
assert(P.value('fov',62.7)==65)
'''))

    def test_key_collisions_swap_and_settings_copies_are_isolated(self):
        self.run_lua(preferences('''
local s=P.defaults();assert(P.rebind(s.bindings,'throttle','S'))
assert(s.bindings.throttle=='S'and s.bindings.brake=='W','Collision removed the brake binding')
assert(not P.rebind(s.bindings,'throttle','Escape'))
assert(not P.rebind(s.bindings,'unknown','F1'))
local map=P.keyMap(s.bindings);assert(map.S=='throttle'and map.W=='brake')
local copy=P.copy(s);copy.values.fov=100;copy.bindings.throttle='Z'
assert(s.values.fov==78 and s.bindings.throttle=='S')
local dirty=P.normalize({bindings={throttle='S',brake='S',left='S',right='S'}})
local seen={};for action,key in pairs(dirty.bindings)do assert(not seen[key],'Duplicate key after load');seen[key]=action end
'''))

    def test_panel_capture_rebind_and_close_without_allocating_per_frame(self):
        self.run_lua(settings_mock('''
local Settings=require(nodes['Client/Settings.lua'])
local gui=Instance.new('ScreenGui',localPlayer.PlayerGui);local changes=0;local latest
local settings=Settings.new(gui,function(values)changes+=1;latest=values end)
assert(not settings:isOpen()and not settings:capture({KeyCode=Enum.KeyCode.W}))
settings:toggle(true);assert(settings:isOpen())
settings.section='Controls';settings:_render()
settings.bindingRows.throttle.Activated:Fire()
assert(settings:capture({KeyCode=Enum.KeyCode.S,UserInputType=Enum.UserInputType.Keyboard}))
assert(settings:binds().S=='throttle'and settings:binds().W=='brake'and changes==1)
settings:set('damage',false);assert(latest.damage==false)
settings:set('fov',999);assert(latest.fov==100)
assert(settings:capture({KeyCode=Enum.KeyCode.Escape}));assert(not settings:isOpen())
local before=#created
for i=1,100 do settings:values();settings:binds()end
assert(#created==before,'Reading settings builds GUI nodes')
settings:destroy();assert(gui:FindFirstChild('RallySettingsOverlay')==nil)
'''))
