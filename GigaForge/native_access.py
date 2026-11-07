"""Inspect native execution failures; repair only a verified download's zone mark."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parent

def windows_shared_read(path):
 """Normal Win32 read access with full sharing; never overrides another lock."""
 import ctypes
 from ctypes import wintypes as w
 kernel=ctypes.WinDLL('kernel32',use_last_error=True)
 kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE];kernel.CreateFileW.restype=w.HANDLE
 kernel.ReadFile.argtypes=[w.HANDLE,w.LPVOID,w.DWORD,ctypes.POINTER(w.DWORD),w.LPVOID];kernel.ReadFile.restype=w.BOOL
 kernel.CloseHandle.argtypes=[w.HANDLE];kernel.CloseHandle.restype=w.BOOL
 handle=kernel.CreateFileW(str(path),0x80000000,7,None,3,0x08000000,None)
 if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
 try:
  chunks=[];buffer=ctypes.create_string_buffer(65536);count=w.DWORD()
  while True:
   if not kernel.ReadFile(handle,buffer,len(buffer),ctypes.byref(count),None):raise ctypes.WinError(ctypes.get_last_error())
   if not count.value:break
   chunks.append(buffer.raw[:count.value])
  return b''.join(chunks)
 finally:kernel.CloseHandle(handle)

def read_reason(error,encrypted=False):
 if error in (32,33):return 'file_locked_or_in_use'
 if error in (225,226):return 'windows_security_detection'
 if encrypted:return 'encrypted_file_access_denied'
 if error==5:return 'windows_access_denied'
 return 'file_read_failed'

def inspect_file(path,expected=None):
 path=Path(path);result=dict(path=str(path.absolute()),exists=path.is_file(),expected_sha256=expected)
 if not result['exists']:return result
 raw=None
 try:raw=path.read_bytes();result['read_method']='python'
 except OSError as e:
  result['read_error']=dict(type=type(e).__name__,winerror=getattr(e,'winerror',None))
  if os.name=='nt':
   try:
    raw=windows_shared_read(path);result['read_method']='win32_shared_read';result['recovered_read_error']=result.pop('read_error')
   except OSError as native:
    result['read_error']=dict(type=type(native).__name__,winerror=getattr(native,'winerror',None),message=str(native))
 if raw is not None:
  result.update(size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),hash_matches=bool(expected and hashlib.sha256(raw).hexdigest()==expected))
  result['windows_executable']=len(raw)>64 and raw[:2]==b'MZ' and raw[int.from_bytes(raw[60:64],'little'):][:4]==b'PE\0\0'
 if result.get('read_error'):result['read_error']['reason']=read_reason(result['read_error'].get('winerror'))
 if os.name=='nt':
  try:result['download_zone']=Path(str(path)+':Zone.Identifier').read_text(errors='replace')[:512]
  except OSError:result['download_zone']=None
 return result

def powershell(script,path,timeout=12):
 env=dict(os.environ);env['GIGAFORGE_CHECK_EXE']=str(path)
 return subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],env=env,capture_output=True,text=True,errors='replace',timeout=timeout)

def diagnostics(path):
 expected=None
 try:expected=json.loads((ROOT/'native_release.json').read_text(encoding='utf8'))['executable_sha256']
 except (OSError,ValueError,KeyError):pass
 report=inspect_file(path,expected)
 if os.name=='nt':
  try:
   r=subprocess.run(['icacls',str(path)],capture_output=True,text=True,errors='replace',timeout=10)
   report['file_permissions']=r.stdout[-4000:];report['permissions_exit_code']=r.returncode
  except (OSError,subprocess.TimeoutExpired) as e:report['permissions_check']=type(e).__name__
  try:
   r=powershell("$ErrorActionPreference='Stop'; try { $p=$env:GIGAFORGE_CHECK_EXE; $hits=@(Get-MpThreatDetection | Where-Object { ($_.Resources -join ' ') -like ('*'+$p+'*') }); @{matching_detection_count=$hits.Count} | ConvertTo-Json -Compress } catch { @{check_unavailable=$true} | ConvertTo-Json -Compress }",path)
   report['windows_security']=json.loads(r.stdout) if r.returncode==0 else dict(check_unavailable=True)
  except (OSError,ValueError,subprocess.TimeoutExpired):report['windows_security']=dict(check_unavailable=True)
  try:
   r=powershell("$ErrorActionPreference='Stop'; @(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct | Select-Object -ExpandProperty displayName) | ConvertTo-Json -Compress",path)
   report['security_providers']=json.loads(r.stdout) if r.returncode==0 and r.stdout.strip() else None
  except (OSError,ValueError,subprocess.TimeoutExpired):report['security_providers']=None
 output=ROOT/'native_access_report.json';output.write_text(json.dumps(report,indent=2),encoding='utf8')
 return report,output

def main(repair=False):
 if os.name!='nt':raise RuntimeError('This check is for Windows execution permissions')
 path=ROOT/'native/GigaForge.exe';report,output=diagnostics(path)
 print('NATIVE_EXECUTABLE:',path);print('HASH_MATCH:',report.get('hash_matches','NOT_CHECKED'));print('DIAGNOSTIC_REPORT:',output)
 if report.get('read_error'):
  error=report['read_error'];print('READ_FAILED: Windows error',error.get('winerror'),error.get('reason'))
  if error.get('winerror') in (32,33):print('Another program holds the file open. Close trainers and archive/extraction windows, then retry 16. A Windows restart can release a stale lock.')
  else:print('Windows prevented reading, so no hash comparison was possible. Check your security app alerts and share the new native_access_report.json. No permissions or security settings were changed.')
  return 1
 if not report.get('hash_matches') or not report.get('windows_executable'):
  print('The file is missing, unreadable or differs from the release. Re-extract the native folder from the verified research ZIP; keep runs and environments.');return 1
 if report.get('windows_security',{}).get('matching_detection_count',0):
  print('Windows Security has a detection for this file. Review Protection history before proceeding. No security settings or file blocks were changed.');return 1
 if repair and report.get('download_zone'):
  r=powershell("$ErrorActionPreference='Stop'; Unblock-File -LiteralPath $env:GIGAFORGE_CHECK_EXE",path)
  if r.returncode:print('Windows could not clear the download mark. Review the file Properties and security policy.');return 1
  print('Removed the download mark from the hash-verified executable only.')
 # The runtime runner supplies the matching torch/Python DLL search paths.
 import run
 try:r=subprocess.run([str(path),'--research-selftest'],env=run.environment(),cwd=ROOT,check=False)
 except PermissionError:
  print('Windows still denies execution. Check Protection history and the file Security tab. Share native_access_report.json. No antivirus exclusions, elevation or permission resets were applied.');return 1
 if r.returncode:print('The executable started but the self-test failed. Keep the output above.');return r.returncode
 print('NATIVE_LAUNCH_PASS: now run 9_VERIFY.bat, then 3_START_OR_RESUME.bat.');return 0

def install_error_handler():
 previous=sys.excepthook
 def handle(kind,error,tb):
  frame=tb;native_spawn=False
  while frame is not None:
   if frame.tb_frame.f_code.co_name=='_execute_child' and 'gigaforge.exe' in str(frame.tb_frame.f_locals.get('args','')).lower():native_spawn=True
   frame=frame.tb_next
  if native_spawn and isinstance(error,PermissionError) and getattr(error,'winerror',None)==5:
   print('NATIVE_LAUNCH_DENIED: Windows refused access before the executable could start. Run 16_CHECK_NATIVE_ACCESS.bat. Keep models and checkpoints; this is not a training failure.',file=sys.stderr)
  else:previous(kind,error,tb)
 sys.excepthook=handle

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repair',action='store_true');a=p.parse_args();raise SystemExit(main(a.repair))
