"""Artifact and preservation checks for the additive binary deliverable."""
import hashlib
import json
import os
import re
from pathlib import Path
import struct
import sys
import unittest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from tools.rbxl_addon import Place, add_expansion, verify_addition


class PlaceTests(unittest.TestCase):
    def setUp(self):
        self.downloads = APP.parent / 'downloads'
        self.path = self.downloads / 'DM_Backseat_Rally.rbxl'
        if not self.path.exists():
            self.skipTest('Build with --base-place to validate the full binary artifact')
        self.data = self.path.read_bytes()
        self.place = Place(self.data)

    def test_artifact_hash_counts_and_original_hierarchy(self):
        report = json.loads((self.downloads / 'DM_PRESERVATION.json').read_text())
        self.assertEqual(hashlib.sha256(self.data).hexdigest(), report['result_sha256'])
        self.assertEqual(self.place.instance_count, report['result_instances'])
        self.assertEqual(report['original_instances'] + report['added_instances'], self.place.instance_count)
        added = report['added_objects']
        self.assertEqual(len(added), report['added_instances'])
        for obj in added:
            self.assertEqual(self.place.names[obj['ref']], obj['name'])
            self.assertEqual(self.place.parent_map[obj['ref']], obj['parent'])
        self.assertTrue(set(self.place.parents) - {-1} <= self.place.all_refs)

    def test_embedded_expansion_sources_match_reviewable_sources(self):
        report = json.loads((self.downloads / 'DM_PRESERVATION.json').read_text())
        added = {n['ref'] for n in report['added_objects']}
        backups = {n['ref'] for n in report['added_objects'] if n.get('source_backup')}
        sources = []
        for block in self.place.chunks:
            if block.tag != b'PROP':
                continue
            class_id, length = struct.unpack_from('<II', block.payload)
            refs = self.place.classes[class_id][1]
            if not set(refs) <= added:
                continue
            name = block.payload[8:8 + length].decode()
            if name == 'Source':
                at = 9 + length
                for ref in refs:
                    size = struct.unpack_from('<I', block.payload, at)[0]
                    if ref not in backups:
                        sources.append(block.payload[at + 4:at + 4 + size].decode())
                    at += 4 + size
            elif name == 'Disabled':
                self.assertEqual(block.payload[9 + length:], bytes(len(refs)))
        self.assertCountEqual(sources, [p.read_text() for p in (APP / 'src').glob('*/*.lua')])

    def test_existing_expansion_is_rejected_without_changing_input(self):
        before = self.data
        with self.assertRaisesRegex(ValueError, 'already contains'):
            add_expansion(before, APP / 'src')
        self.assertEqual(before, self.path.read_bytes())

    def test_every_original_chunk_and_parent_is_preserved(self):
        path = os.environ.get('BACKSEAT_BASE_RBXL')
        if not path:
            self.skipTest('Set BACKSEAT_BASE_RBXL for comparison with the original input')
        base = Path(path).read_bytes()
        manifest = json.loads((self.downloads / 'DM_PRESERVATION.json').read_text())
        report = verify_addition(base, self.data, manifest.get('legacy_source_changes', []))
        self.assertEqual(report['original_instances'], 82861)
        # Corrupting an original property must fail the preservation check.
        original = Place(base)
        prop = next(c for c in original.chunks if c.tag == b'PROP')
        bad = self.data.replace(prop.raw, bytes(len(prop.raw)), 1)
        with self.assertRaises((ValueError, AssertionError, struct.error, UnicodeError)):
            verify_addition(base, bad)

    def test_clean_standalone_has_native_floor_correct_script_container_and_no_imported_assets(self):
        config=(APP/'src/Shared/Config.lua').read_text()
        version=re.search(r"C.Version\s*=\s*['\"]([^'\"]+)['\"]", config)
        if not version:
            version=re.search(r"Version\s*=\s*['\"]([^'\"]+)['\"]", config)
        self.assertIsNotNone(version,'Config.Version missing')
        path=APP.parent/'downloads'/f'DM_Rally_Standalone_v{version[1]}.rbxl'
        if not path.exists():
            self.skipTest('Build standalone artifact for current Config.Version')
        standalone=Place(path.read_bytes())
        classes={ref:cls for cls,refs,_ in standalone.classes.values()for ref in refs}
        self.assertNotIn('MeshPart',classes.values())
        self.assertNotIn('SpecialMesh',classes.values())
        self.assertNotIn('Sound',classes.values())
        self.assertEqual(list(classes.values()).count('Script'),1)
        self.assertEqual(list(classes.values()).count('LocalScript'),1)
        player=standalone.service('StarterPlayer')
        scripts=standalone.service('StarterPlayerScripts')
        self.assertEqual(standalone.parent_map[scripts],player)
        container=next(row for row in standalone.classes.values()if row[0]=='StarterPlayerScripts')
        self.assertFalse(container[2],'StarterPlayerScripts must be a child container, not a GetService request')
        self.assertIn('PreviewFloor',standalone.names.values())
        self.assertIn('PreviewSpawn',standalone.names.values())


if __name__ == '__main__':
    unittest.main()
