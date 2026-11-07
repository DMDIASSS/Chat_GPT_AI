import sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from native_access import inspect_file

def test_only_matching_pe_file_is_verified(tmp_path):
 p=tmp_path/'native.exe';b=bytearray(80);b[:2]=b'MZ';b[60:64]=(64).to_bytes(4,'little');b[64:68]=b'PE\0\0';p.write_bytes(b)
 r=inspect_file(p,hashlib.sha256(b).hexdigest());assert r['hash_matches'] and r['windows_executable']
 p.write_bytes(b'wrong');r=inspect_file(p,hashlib.sha256(b).hexdigest());assert not r['hash_matches'] and not r['windows_executable']

def test_missing_executable_does_not_get_marked_verified(tmp_path):
 r=inspect_file(tmp_path/'missing.exe','0'*64);assert not r['exists'] and not r.get('hash_matches')
