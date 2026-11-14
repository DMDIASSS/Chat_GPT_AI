from pathlib import Path
import urllib.request,tarfile,hashlib
ROOT=Path(__file__).resolve().parents[1]
COMMIT='c2baacb8f4b441dd8505e63c2aeb5a1679b60b02'
SHA256='024f22ca36d6328331480e0e45bdc51ba52a4aee82560d1a17898a7ffa8fb28c'
def main():
    target=ROOT/'third_party';target.mkdir(exist_ok=True);archive=target/'rs.tar.gz'
    with urllib.request.urlopen('https://codeload.github.com/ZealanL/RocketSim/tar.gz/'+COMMIT,timeout=90) as r:data=r.read(20*1024*1024)
    if hashlib.sha256(data).hexdigest()!=SHA256:raise ValueError('RocketSim source checksum mismatch')
    archive.write_bytes(data)
    with tarfile.open(archive) as t:
        for m in t.getmembers():
            p=Path(m.name)
            if p.is_absolute() or '..' in p.parts or m.issym() or m.islnk():raise ValueError('Unsafe source archive')
        t.extractall(target)
    print('PINNED_ROCKETSIM_SOURCE_READY:',COMMIT)
if __name__=='__main__':main()
