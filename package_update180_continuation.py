"""Build the continuation repair with every hashed trainer code dependency."""
import ast
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent

def dependencies(root=ROOT):
    tree = ast.parse((root/'slater_versatile_trainer.py').read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='code_identity')
    names = next(ast.literal_eval(n.value) for n in function.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id=='names' for t in n.targets))
    return set(names)

def files(root=ROOT):
    result = dependencies(root) | {'slater_continue_update180.py','SLATER_UPDATE180_CONTINUATION_README.md',
        'requirements-slater-versatile.txt','SLATER_VERSATILE_README.md','docs/UPDATE180_CRITIC_REPAIR.md'}
    result.update(p.name for p in root.glob('SLATER_20_*.bat'))
    # Optional read-only diagnostics are included for existing native campaigns.
    result.update({'slater_native_inspect.py','native_inspection_viewer.html','slater_replay_input_audit.py',
                   'SLATER_NATIVE_DIAGNOSTICS_README.md'})
    result.update(p.name for p in root.glob('NATIVE_1[679]*.bat'))
    missing = [name for name in result if not (root/name).is_file()]
    if missing: raise FileNotFoundError('Missing bundle dependencies: '+str(missing))
    return sorted(result)

def build(root=ROOT):
    out = root/'Slater_Update180_Continuation_Update.zip'
    names = files(root)
    with ZipFile(out,'w',ZIP_DEFLATED) as archive:
        for name in names: archive.write(root/name,name)
    with ZipFile(out) as archive:
        if archive.testzip(): raise ValueError('Invalid ZIP')
        if not dependencies(root) <= set(archive.namelist()): raise ValueError('Incomplete code identity')
    print(out.name, len(names), out.stat().st_size)
    return out

if __name__ == '__main__': build()
