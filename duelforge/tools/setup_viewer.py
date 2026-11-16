"""Send current simulated physics to ZealanL/RocketSimVis; not replay playback."""
from pathlib import Path
import hashlib,json,os,socket,subprocess,sys,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[1]
COMMIT='074a4368f31668ccd651087eebf6a1b459564ad7'
URL='https://codeload.github.com/ZealanL/RocketSimVis/zip/'+COMMIT
# Source archive hash is checked by the installer; filled from the pinned download.
SOURCE_SHA256='b58ec3af47550ea7173f72d65b1ff9d239d29e007820b7ac1abd071bb0b061ff'

def install():
    target=ROOT/'third_party/RocketSimVis';target.parent.mkdir(exist_ok=True)
    archive=target.parent/'RocketSimVis-source.zip'
    if not target.exists():
        with urllib.request.urlopen(URL,timeout=60) as r:data=r.read(8*1024*1024)
        if hashlib.sha256(data).hexdigest()!=SOURCE_SHA256:raise ValueError('RocketSimVis pinned source checksum mismatch')
        archive.write_bytes(data)
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist():
                p=Path(*Path(entry.filename).parts[1:])
                if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe viewer archive')
                if str(p)=='.' or entry.is_dir():continue
                out=target/p;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(z.read(entry))
        (target/'DUELFORGE_UPSTREAM.txt').write_text('RocketSimVis by ZealanL and contributors; upstream '+COMMIT+'\n'+URL+'\n')
    # Upstream moderngl-window 2.x requires NumPy 1.x. Keep this GUI in its own
    # tiny environment so the user's NumPy/Torch/RLViser environment is untouched.
    import venv
    env=target/'.venv';python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    ready=env/'duelforge_gui_ready.json'
    if not python.is_file():venv.EnvBuilder(with_pip=True).create(env)
    if not ready.exists():
        packages=['numpy>=1.26,<2','moderngl>=5.8,<6','moderngl-window>=2.4,<3','PyOpenGL>=3.1,<4','pyrr>=0.10,<1','PyWavefront>=1.3,<2','PyQt5>=5.15,<5.16']
        subprocess.run([str(python),'-m','pip','install',*packages],check=True)
        ready.write_text(json.dumps(dict(source_commit=COMMIT,source_archive_sha256=SOURCE_SHA256,scope='GUI only; no Torch/CUDA installation')))
    print('ROCKETSIMVIS_READY:',target,flush=True);return target

if __name__=="__main__":install()
