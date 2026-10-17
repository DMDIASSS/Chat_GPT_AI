"""Local-only native Nexto checkpoint converter for the Chrome extension."""
from pathlib import Path
import hashlib, io, json, zipfile, os
from http.server import HTTPServer, BaseHTTPRequestHandler
import torch

ROOT=Path(__file__).resolve().parent
LAYOUT=json.loads((ROOT/'model-layout.json').read_text())
MAX_BYTES=256*1024*1024

def actor_state(data):
    stream=io.BytesIO(data)
    try: return torch.jit.load(stream,map_location='cpu').state_dict()
    except (RuntimeError,ValueError):
        stream.seek(0)
        obj=torch.load(stream,map_location='cpu',weights_only=True)
        if isinstance(obj,dict):
            for key in ('actor','state_dict','model_state_dict'):
                if isinstance(obj.get(key),dict):return obj[key]
            if set(obj)=={item['tensor'] for item in LAYOUT}:return obj
        raise ValueError('Requires a native Nexto actor checkpoint or compatible TorchScript. Other architectures need another adapter.')

def pack_state(state):
    if set(state)!={item['tensor'] for item in LAYOUT}:
        raise ValueError('Incompatible architecture: expected the native Nexto 44-tensor actor.')
    chunks=[]
    for item in LAYOUT:
        tensor=state[item['tensor']]
        if not torch.is_tensor(tensor) or tuple(tensor.shape)!=tuple(item['shape']):
            raise ValueError('Incompatible tensor shape: '+item['tensor'])
        tensor=tensor.detach().cpu().to(torch.float32).contiguous()
        if not torch.isfinite(tensor).all():raise ValueError('Model contains nonfinite weights.')
        chunks.append(tensor.numpy().astype('<f4',copy=False).tobytes())
    out=b''.join(chunks)
    if len(out)!=1776128:raise ValueError('Incorrect browser weight length')
    return out

def convert(data):
    if len(data)>MAX_BYTES:raise ValueError('Select a checkpoint/export smaller than 256 MiB.')
    # Export archives often contain learned/scripted variants of the same actor.
    # Compare converted weights; never pick among distinct actors silently.
    stream=io.BytesIO(data)
    if zipfile.is_zipfile(stream):
        with zipfile.ZipFile(stream) as z:
            files=[i for i in z.infolist() if i.filename.lower().endswith('.pt') and not i.is_dir()]
            if files:
                if len(files)>64 or sum(i.file_size for i in files)>512*1024*1024:
                    raise ValueError('ZIP contains too many/too large checkpoints; choose one .pt file.')
                unique={}
                for item in files:
                    weights=pack_state(actor_state(z.read(item)))
                    unique[hashlib.sha256(weights).hexdigest()]=weights
                if len(unique)!=1:raise ValueError('ZIP contains different actors. Choose the individual .pt you want.')
                return next(iter(unique.values()))
    return pack_state(actor_state(data))

class Handler(BaseHTTPRequestHandler):
    def origin(self):
        origin=self.headers.get('Origin','')
        host=self.headers.get('Host','')
        if not origin.startswith('chrome-extension://') or host!='127.0.0.1:8765':
            self.send_error(403,'Only the local extension can use this importer.');return None
        return origin
    def reply(self,status,data,content_type,origin):
        self.send_response(status);self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store')
        self.send_header('Access-Control-Allow-Origin',origin)
        self.send_header('Access-Control-Allow-Methods','POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.end_headers();self.wfile.write(data)
    def do_OPTIONS(self):
        origin=self.origin()
        if origin:self.reply(204,b'','text/plain',origin)
    def do_POST(self):
        origin=self.origin()
        if not origin:return
        try:
            if self.path!='/convert':raise ValueError('Unknown importer endpoint')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_BYTES:raise ValueError('File must be smaller than 256 MiB.')
            data=self.rfile.read(length)
            if len(data)!=length:raise ValueError('Incomplete upload')
            self.reply(200,convert(data),'application/octet-stream',origin)
        except Exception as e:self.reply(400,json.dumps({'error':str(e)}).encode(),'application/json',origin)
    def log_message(self,*args):pass

if __name__=='__main__':
    torch.set_num_threads(2)
    if os.name=='nt' and not (ROOT/'g9-weights.bin').exists():
        g9=Path(r'E:\Downloads\Chat_GPT_AI\data\isolated\v041_overnight\overnight01\trials\g00009_leader_small_2\g00009_leader_small_2_u0073.pt')
        if g9.is_file():
            try:
                (ROOT/'g9-weights.bin').write_bytes(convert(g9.read_bytes()))
                print('Prepared your local G9 u0073 model with scripted kickoff support.',flush=True)
            except Exception as e:print('Could not prepare G9: '+str(e),flush=True)
    print('Local model importer ready at http://127.0.0.1:8765. Keep this window open while importing .pt/.zip files.',flush=True)
    print('Files are converted in memory on this PC. No remote upload or checkpoint overwrite.',flush=True)
    try:HTTPServer(('127.0.0.1',8765),Handler).serve_forever()
    except KeyboardInterrupt:pass
