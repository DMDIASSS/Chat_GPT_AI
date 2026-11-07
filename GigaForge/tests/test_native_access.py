import sys,hashlib,os
import pytest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from native_access import inspect_file
from native_access import windows_shared_read,read_reason

def test_only_matching_pe_file_is_verified(tmp_path):
 p=tmp_path/'native.exe';b=bytearray(80);b[:2]=b'MZ';b[60:64]=(64).to_bytes(4,'little');b[64:68]=b'PE\0\0';p.write_bytes(b)
 r=inspect_file(p,hashlib.sha256(b).hexdigest());assert r['hash_matches'] and r['windows_executable']
 p.write_bytes(b'wrong');r=inspect_file(p,hashlib.sha256(b).hexdigest());assert not r['hash_matches'] and not r['windows_executable']

def test_missing_executable_does_not_get_marked_verified(tmp_path):
 r=inspect_file(tmp_path/'missing.exe','0'*64);assert not r['exists'] and not r.get('hash_matches')

def test_unreadable_is_not_reported_as_a_hash_mismatch(tmp_path,monkeypatch):
 p=tmp_path/'native.exe';p.write_bytes(b'file')
 def denied(*a):raise PermissionError(13,'denied')
 monkeypatch.setattr(Path,'read_bytes',denied)
 if os.name=='nt':monkeypatch.setattr('native_access.windows_shared_read',denied)
 report=inspect_file(p,'0'*64)
 assert report['exists'] and 'hash_matches' not in report and report['read_error']

@pytest.mark.skipif(os.name!='nt',reason='Win32 sharing semantics')
def test_shared_read_recovers_crt_error_and_still_checks_hash(tmp_path,monkeypatch):
 p=tmp_path/'native.exe';p.write_bytes(b'correct bytes')
 def denied(*a):raise PermissionError(13,'CRT sharing failed')
 monkeypatch.setattr(Path,'read_bytes',denied)
 report=inspect_file(p,hashlib.sha256(b'correct bytes').hexdigest())
 assert report['hash_matches'] and report['read_method']=='win32_shared_read'
 assert not inspect_file(p,'0'*64)['hash_matches']

@pytest.mark.skipif(os.name!='nt',reason='Win32 exclusive handle')
def test_shared_read_does_not_override_exclusive_lock(tmp_path):
 import ctypes
 from ctypes import wintypes as w
 p=tmp_path/'locked.exe';p.write_bytes(b'locked')
 kernel=ctypes.WinDLL('kernel32',use_last_error=True)
 kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE];kernel.CreateFileW.restype=w.HANDLE
 kernel.CloseHandle.argtypes=[w.HANDLE]
 handle=kernel.CreateFileW(str(p),0x80000000,0,None,3,0,None)
 assert handle!=ctypes.c_void_p(-1).value
 try:
  with pytest.raises(OSError) as error:windows_shared_read(p)
  assert error.value.winerror in (32,33)
 finally:kernel.CloseHandle(handle)

def test_error_codes_distinguish_lock_from_security_or_permissions():
 assert read_reason(32)=='file_locked_or_in_use'
 assert read_reason(5)=='windows_access_denied'
 assert read_reason(225)=='windows_security_detection'
