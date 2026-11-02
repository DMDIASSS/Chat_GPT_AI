"""Patch the newest uploaded game, retaining all original objects and properties.

Source overrides are explicit, hashed, and backed up in inert ServerStorage modules.
This does not install the older BackseatExpedition expansion.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO / 'backseat_rally_game/tools'))
from rbxl_addon import Place, chunk, instance_paths, property_rows, references, string, u32, verify_addition


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(base_path, output):
    before = base_path.read_bytes()
    manifest = json.loads((ROOT / 'BASE_MANIFEST.json').read_text())
    if sha(before) != manifest['sha256']:
        raise ValueError('Base does not match the newest redone upload; refusing to patch another version')
    place = Place(before)
    paths = instance_paths(place)
    by_path = {path: ref for ref, path in paths.items()}
    sources = property_rows(place, 'Source')
    updates, additions = {}, []
    for source_file in sorted((ROOT / 'src').rglob('*.lua')):
        path = '.'.join(source_file.relative_to(ROOT / 'src').with_suffix('').parts)
        source = source_file.read_text()
        if path in by_path:
            ref = by_path[path]
            if ref not in sources:
                raise ValueError(f'Cannot replace a non-script: {path}')
            if sources[ref] != source:
                updates[ref] = source
        else:
            parent_path, name = path.rsplit('.', 1)
            if parent_path not in by_path:
                raise ValueError(f'New module parent absent: {parent_path}')
            additions.append((name, source, by_path[parent_path]))

    next_ref = max(place.all_refs) + 1
    backup_folder = next_ref
    next_ref += 1
    module_rows, repairs = [], []
    for ref, source in sorted(updates.items()):
        backup_ref = next_ref
        next_ref += 1
        module_rows.append((backup_ref, f'{ref}_{place.names[ref]}', sources[ref], backup_folder))
        repairs.append(dict(ref=ref, path=paths[ref], backup_ref=backup_ref,
                            before_sha256=sha(sources[ref].encode()), after_sha256=sha(source.encode())))
    added_sources = []
    for name, source, parent in additions:
        module_rows.append((next_ref, name, source, parent))
        added_sources.append(dict(ref=next_ref, path=paths[parent]+'.'+name, sha256=sha(source.encode())))
        next_ref += 1

    folder_cid = max(place.classes) + 1
    module_cid = folder_cid + 1
    inserted = []
    def add_class(cid, name, refs):
        inserted.append(chunk(b'INST', u32(cid)+string(name)+b'\x00'+u32(len(refs))+references(refs)))
    def prop(cid, name, values):
        inserted.append(chunk(b'PROP', u32(cid)+string(name)+b'\x01'+b''.join(string(v) for v in values)))

    add_class(folder_cid, 'Folder', [backup_folder])
    prop(folder_cid, 'Name', ['DM_RedoneSourceBackups'])
    add_class(module_cid, 'ModuleScript', [row[0] for row in module_rows])
    prop(module_cid, 'Name', [row[1] for row in module_rows])
    prop(module_cid, 'Source', [row[2] for row in module_rows])
    for cid, (_, refs, _) in place.classes.items():
        if any(ref in updates for ref in refs):
            prop(cid, 'Source', [updates.get(ref, sources[ref]) for ref in refs])

    children = place.children + [backup_folder] + [row[0] for row in module_rows]
    parents = place.parents + [place.service('ServerStorage')] + [row[3] for row in module_rows]
    if parents[len(place.parents)] is None:
        raise ValueError('ServerStorage is absent')
    parent_chunk = chunk(b'PRNT', b'\x00'+u32(len(children))+references(children)+references(parents))
    header = bytearray(place.header)
    struct.pack_into('<II', header, 16, place.class_count+2, place.instance_count+len(module_rows)+1)
    blocks = [c.raw for c in place.chunks if c.tag not in (b'PRNT', b'END\x00')]
    end = next(c.raw for c in place.chunks if c.tag == b'END\x00')
    after = bytes(header) + b''.join(blocks+inserted+[parent_chunk,end])
    report = verify_addition(before, after, allowed_source_changes=repairs)
    report.update(version='Redone fixes 1.0.0', base_file=manifest['file_name'],
                  source_repairs=repairs, new_modules=added_sources,
                  notes='Original models, meshes, terrain, metadata, scripts, and hierarchy retained. Only listed Sources overridden.')
    output.mkdir(parents=True, exist_ok=True)
    artifact = output / 'Backseat_Rally_Redone_Fixed.rbxl'
    artifact.write_bytes(after)
    report_file = output / 'Backseat_Rally_Redone_PRESERVATION.json'
    report_file.write_text(json.dumps(report, indent=2)+'\n')
    with zipfile.ZipFile(output / 'Backseat_Rally_Redone_Fixed.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(artifact, artifact.name)
        archive.write(ROOT / 'START_HERE.txt', 'START_HERE.txt')
        archive.write(report_file, 'PRESERVATION.json')
        for source in sorted((ROOT / 'src').rglob('*.lua')):
            archive.write(source, 'source/'+str(source.relative_to(ROOT / 'src')))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, default=ROOT / 'base/Redone_Upload.rbxl')
    parser.add_argument('--output', type=Path, default=REPO / 'downloads')
    args = parser.parse_args()
    result = build(args.base, args.output)
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_repairs','new_modules')}, indent=2))
