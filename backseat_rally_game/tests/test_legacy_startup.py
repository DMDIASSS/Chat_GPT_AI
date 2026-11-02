"""Preserved-export repairs: input graphs, Zone recursion, and profile listeners."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import test_game as harness

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from tools.rbxl_addon import (Place, add_expansion, chunk, instance_paths,
                             legacy_source_repairs, property_rows, string, u32,
                             verify_addition)


def isolated(extra):
    text = (APP / 'tests/roblox_mock.luau').read_text()
    text += "\nlocal replicated=Instance.new('Folder',services.ReplicatedStorage);replicated.Name='BackseatExpedition'\n"
    text += "local nodes={['Shared/LegacyInput.lua']=Instance.new('ModuleScript',replicated)}\n"
    text += "modules[nodes['Shared/LegacyInput.lua']]=function(script)\n"
    text += (APP / 'src/Shared/LegacyInput.lua').read_text() + '\nend\n'
    return text + extra


class LegacyRuntimeTests(unittest.TestCase):
    run_lua = harness.GameTests.run_lua

    def test_input_resolver_reuses_native_graph_and_repairs_only_missing_runtime_copy(self):
        self.run_lua(isolated('''
local resolver=require(nodes['Shared/LegacyInput.lua'])
function runService:IsClient()return true end
local template=Instance.new('Folder',replicated);template.Name='LegacyInputContexts'
for _,name in ipairs({'CharacterContext','CameraContext','TransformerContext','VehicleContext'})do
 local c=Instance.new('InputContext',template);c.Name=name
 local action=Instance.new('InputAction',c);action.Name='Action';action.Type='Direction2D'
 local binding=Instance.new('InputBinding',action);binding.Name='Binding';binding.KeyCode='W';binding.Scale=.75
end
local playerModule=Instance.new('ModuleScript',sps)
local actual=resolver.get(playerModule)
assert(actual~=template and actual.Parent==playerModule and actual.Name=='InputContexts')
assert(actual.CharacterContext.Action.Binding.KeyCode=='W' and actual.CharacterContext.Action.Binding.Scale==.75)
assert(resolver.get(playerModule)==actual,'Resolver duplicated the native graph')
assert(template.Parent==replicated and #template:GetDescendants()==12,'Preserved template was changed')
actual:Destroy();template:Destroy()
local ok,message=pcall(resolver.get,playerModule)
assert(not ok and tostring(message):find('Exported input graph unavailable',1,true),'Missing graph should fail with a bounded error')
'''))


class OriginalExportTests(unittest.TestCase):
    run_lua = harness.GameTests.run_lua

    @classmethod
    def setUpClass(cls):
        path = os.environ.get('BACKSEAT_BASE_RBXL')
        if not path:
            raise unittest.SkipTest('Set BACKSEAT_BASE_RBXL to exercise actual exported sources')
        cls.base = Path(path).read_bytes()
        cls.place = Place(cls.base)
        cls.repairs = legacy_source_repairs(cls.place)
        cls.output, cls.report = add_expansion(cls.base, APP / 'src')
        cls.result = Place(cls.output)

    def repair(self, suffix):
        return next(r for r in self.repairs if r['path'].endswith(suffix))['after']

    def test_targeted_sources_compile_and_have_exact_inert_original_backups(self):
        self.assertEqual(len(self.repairs), 14)
        self.assertEqual(self.report['native_input_graph_objects_added'], 109)
        originals = property_rows(self.place, 'Source')
        sources = property_rows(self.result, 'Source')
        for repair in self.report['legacy_source_changes']:
            self.assertEqual(sources[repair['backup_ref']], originals[repair['ref']])
        with tempfile.TemporaryDirectory() as td:
            for repair in self.repairs:
                path = Path(td) / (str(repair['ref']) + '.lua')
                path.write_text(repair['after'])
                proc = subprocess.run([harness.COMPILE, str(path)], text=True, capture_output=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
        verify_addition(self.base, self.output, self.report['legacy_source_changes'])
        with self.assertRaisesRegex(AssertionError, 'Unapproved Source'):
            verify_addition(self.base, self.output)

    def test_native_input_properties_and_hierarchy_are_copied_exactly(self):
        old_paths, new_paths = instance_paths(self.place), instance_paths(self.result)
        prefix = 'StarterPlayer.PlayerModule.InputContexts'
        target = 'ReplicatedStorage.BackseatExpedition.LegacyInputContexts'
        selected = {ref: path for ref, path in old_paths.items() if path.startswith(prefix + '.')}
        reverse = {path: ref for ref, path in new_paths.items()}
        mapped = {ref: reverse[target + path[len(prefix):]] for ref, path in selected.items()}
        self.assertEqual(len(mapped), 108)
        def props(place):
            out = {}
            for block in place.chunks:
                if block.tag == b'PROP':
                    cid, n = struct.unpack_from('<II', block.payload)
                    name = block.payload[8:8+n].decode()
                    out[(cid, name)] = block.payload[8+n:]
            return out
        old, new = props(self.place), props(self.result)
        for cid, (kind, refs, _) in self.place.classes.items():
            if not set(refs) & set(selected):
                continue
            new_id = next(i for i, (k, rr, _) in self.result.classes.items()
                          if rr == [mapped[ref] for ref in refs])
            self.assertEqual(kind, self.result.classes[new_id][0])
            for (group, name), encoded in old.items():
                if group == cid and name not in ('UniqueId', 'HistoryId'):
                    self.assertEqual(encoded, new[(new_id, name)], f'{kind}.{name} changed')
        # Property changes cannot be hidden behind retained original PROP chunks.
        block = next(c for c in self.place.chunks if c.tag == b'PROP')
        cid, n = struct.unpack_from('<II', block.payload)
        bad_prop = u32(cid) + string('DMInjectedProperty') + b'\x02' + bytes(len(self.place.classes[cid][1]))
        end = self.result.chunks[-1]
        bad = self.output[:-len(end.raw)] + chunk(b'PROP', bad_prop) + end.raw
        with self.assertRaisesRegex(AssertionError, 'effective property changed'):
            verify_addition(self.base, bad, self.report['legacy_source_changes'])

    def test_zone_self_reference_does_not_require_itself(self):
        source = self.repair('ReplicatedStorage.Shared.Zone')
        self.run_lua(isolated('''
function runService:IsClient()return true end
services.HttpService=Instance.new('HttpService')
local zone=Instance.new('ModuleScript');zone.Name='Zone'
local controller=Instance.new('ModuleScript',zone);controller.Name='ZoneController'
for _,name in ipairs({'Tracker','CollectiveWorldModel'})do local n=Instance.new('ModuleScript',controller);n.Name=name end
for _,name in ipairs({'Enum','Janitor','Signal','ZonePlusReference'})do local n=Instance.new('ModuleScript',zone);n.Name=name end
local reference=Instance.new('ObjectValue');reference.Value=zone
local marker=Instance.new('BoolValue',reference);marker.Name='Client'
local registered=0
local referenceModule={getObject=function()return reference end,addToReplicatedStorage=function()registered+=1 end}
local function require(target)
 assert(target~=zone,'Zone tried to require itself')
 if target==zone.ZonePlusReference then return referenceModule end
 if target==zone.Enum then return {enums={}}end
 return {}
end
local result=(function(script)
''' + source + '''
end)(zone)
assert(type(result.new)=='function' and registered==1,'Zone did not initialize its own implementation')
'''))

    def test_data_controller_has_one_listener_and_throttles_waiting_without_losing_data(self):
        source = self.repair('Client.Init.Data.DataController')
        self.run_lua(isolated('''
services.TweenService=Instance.new('TweenService')
local legacy=Instance.new('Folder',services.ReplicatedStorage);legacy.Name='Shared'
local util=Instance.new('Folder',legacy);util.Name='RBXUtil'
for _,name in ipairs({'Net','Trove','Signal'})do local n=Instance.new('ModuleScript',util);n.Name=name end
local client=Instance.new('Folder');local state=Instance.new('ModuleScript',client);state.Name='StateManager'
local init=Instance.new('Folder',client);init.Name='Init'
local data=Instance.new('Folder',init);data.Name='Data'
local replicaModule=Instance.new('ModuleScript',data);replicaModule.Name='ReplicaClient'
local controller=Instance.new('ModuleScript',data)
function methods:FindFirstAncestor(name)local p=self.Parent;while p do if p.Name==name then return p end;p=p.Parent end end
local count,callback=0,nil
local replicaClient={OnNew=function(token,fn)assert(token=='PlayerProfile');count+=1;callback=fn end}
local function require(target)
 if target==util.Signal then return {new=event}end
 if target==replicaModule then return replicaClient end
 return {}
end
local result=(function(script)
''' + source + '''
end)(controller)
result.Initialize();result.Initialize();assert(count==1,'Export registered duplicate profile listeners')
for i=1,1000 do assert(result:GetLocalData()==nil)end
assert(#warnings==1,'Waiting profile logged every frame')
local got=0;result.PlayerDataAdded:Connect(function(player,replica)assert(player==localPlayer and replica.Data.Settings.MusicVolume==.8);got+=1 end)
local cleanup
local profile={Tags={Player=localPlayer},Data={Settings={MusicVolume=.8}},Maid={Add=function(_,fn)cleanup=fn end}}
callback(profile)
assert(got==1 and result:GetLocalData()==profile,'Actual replica was not published')
local waited;task.spawn(function()waited=result:WaitForLocalData()end);advance(.1);assert(waited==profile)
cleanup();assert(result:GetLocalData()==nil and #warnings==2,'Removal did not reset the bounded warning')
'''))


if __name__ == '__main__':
    unittest.main()
