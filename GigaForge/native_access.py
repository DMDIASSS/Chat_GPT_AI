"""Inspect native execution failures; repair only a verified download's zone mark."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parent

def inspect_file(path,expected=None):
 path=Path(path);result=dict(path=str(path.absolute()),exists=path.is_file(),expected_sha256=expected)
 if not result['exists']:return result
 try:
  raw=path.read_bytes();result.update(size=len(raw),sha256=hashlib.sha256(raw).hexdigest(),hash_matches=bool(expected and hashlib.sha256(raw).hexdigest()==expected))
  result['windows_executable']=len(raw)>64 and raw[:2]==b'MZ' and raw[int.from_bytes(raw[60:64],'little'):][:4]==b'PE\0\0'
 except OSError as e:result['read_error']=dict(type=type(e).__name__,winerror=getattr(e,'winerror',None))
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
 output=ROOT/'native_access_report.json';output.write_text(json.dumps(report,indent=2),encoding='utf8')
 return report,output

def main(repair=False):
 if os.name!='nt':raise RuntimeError('This check is for Windows execution permissions')
 path=ROOT/'native/GigaForge.exe';report,output=diagnostics(path)
 print('NATIVE_EXECUTABLE:',path);print('HASH_MATCH:',report.get('hash_matches',False));print('DIAGNOSTIC_REPORT:',output)
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
