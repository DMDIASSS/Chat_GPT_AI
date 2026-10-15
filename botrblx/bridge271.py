"""Local, read-only Roblox telemetry -> update271 -> focused Windows input.

Run with the project's existing Python environment. --dry-run never sends keys.
"""
import argparse
import ctypes
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = Path(__file__).resolve().parent


def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(APP_DIR / "bridge.log", encoding="utf-8")],
    )


if __name__ == "__main__":
    configure_logging()

try:
    import numpy as np
    import torch
except ImportError:
    if __name__ == "__main__":
        logging.exception("Project dependencies missing. Use START_BOT.bat with the existing training project's .venv.")
        raise SystemExit(1)
    raise

PORT = 28771
ACCOUNT = "Deadline_coolgun"
PLACE = 101880234193261
ZERO = np.zeros(8, dtype=np.float32)
PADS = np.array([
    [0,-4240,70],[-1792,-4184,70],[1792,-4184,70],[-3072,-4096,73],
    [3072,-4096,73],[-940,-3308,70],[940,-3308,70],[0,-2816,70],
    [-3584,-2484,70],[3584,-2484,70],[-1788,-2300,70],[1788,-2300,70],
    [-2048,-1036,70],[0,-1024,70],[2048,-1036,70],[-3584,0,73],
    [-1024,0,70],[1024,0,70],[3584,0,73],[-2048,1036,70],
    [0,1024,70],[2048,1036,70],[-1788,2300,70],[1788,2300,70],
    [-3584,2484,70],[3584,2484,70],[0,2816,70],[-940,3310,70],
    [940,3308,70],[-3072,4096,73],[3072,4096,73],[-1792,4184,70],
    [1792,4184,70],[0,4240,70]], dtype=np.float32)


def lookup_table():
    actions = []
    for throttle in (-1, 0, 1):
        for steer in (-1, 0, 1):
            for boost in (0, 1):
                for brake in (0, 1):
                    if boost and throttle != 1:
                        continue
                    actions.append([throttle or boost, steer, 0, steer, 0, 0, boost, brake])
    for pitch in (-1, 0, 1):
        for yaw in (-1, 0, 1):
            for roll in (-1, 0, 1):
                for jump in (0, 1):
                    for boost in (0, 1):
                        if (jump and yaw != 0) or pitch == roll == jump == 0:
                            continue
                        brake = int(bool(jump and (pitch or yaw or roll)))
                        actions.append([boost, yaw, pitch, yaw, roll, jump, boost, brake])
    return np.array(actions, dtype=np.float32)


def vec(value):
    out = np.asarray(value, dtype=np.float32)
    if out.shape != (3,) or not np.isfinite(out).all():
        raise ValueError("Missing or non-finite pose vector")
    return out


def observations(packet, previous, has_flip):
    car, ball = packet["car"], packet["ball"]
    kv = np.zeros((36, 24), dtype=np.float32)
    mask = np.zeros(36, dtype=np.float32)
    kv[0, :3] = (1, 1, 0) if packet["team"] == 0 else (1, 0, 1)
    kv[1, 3] = 1
    for row, body in ((0, car), (1, ball)):
        kv[row, 5:8] = vec(body["position"])
        kv[row, 8:11] = vec(body["velocity"])
        kv[row, 17:20] = vec(body["angular_velocity"])
    kv[0, 11:14], kv[0, 14:17] = vec(car["forward"]), vec(car["up"])
    boost = float(packet["boost"])
    if not math.isfinite(boost) or not 0 <= boost <= 100:
        raise ValueError("Numeric boost HUD value is required")
    kv[0, 20:24] = [boost / 100, 0, bool(packet["ground_estimate"]), has_flip]
    kv[2:, 4], kv[2:, 5:8] = 1, PADS
    kv[2:, 20] = np.where(PADS[:, 2] > 72, 1, .12)
    # Pad availability is NOT observable from the supplied recordings.
    # Mask these entities instead of inventing 34 active-pad states.
    mask[2:] = 1
    if packet["team"] == 1:
        kv[:, 5:20] *= np.tile([-1, -1, 1], 5)
        kv[:, [1, 2]] = kv[:, [2, 1]]
    kv[:, 5:11] /= 2300
    kv[:, 17:20] /= 5.5
    q = np.concatenate([kv[0].copy(), previous]).astype(np.float32)
    kv[:, 5:8] -= q[5:8]
    theta = math.atan2(q[11], q[12])
    ct, st = math.cos(theta), math.sin(theta)
    x, y = kv[:, 5:20:3].copy(), kv[:, 6:20:3].copy()
    kv[:, 5:20:3], kv[:, 6:20:3] = ct*x-st*y, st*x+ct*y
    return tuple(torch.from_numpy(x) for x in (q[None, None], kv[None], mask[None]))


def mapped_keys(action, ground):
    throttle, steer, pitch, yaw, roll, jump, boost, brake = action
    # WASD couples throttle/pitch and steer/yaw. Preserve pitch when airborne.
    longitudinal = throttle if ground else -pitch
    lateral = steer if ground else yaw
    keys = set()
    if longitudinal > .5: keys.add("W")
    if longitudinal < -.5: keys.add("S")
    if lateral > .5: keys.add("D")
    if lateral < -.5: keys.add("A")
    if roll > .5: keys.add("E")
    if roll < -.5: keys.add("Q")
    if jump: keys.add("RMB")
    if boost: keys.add("LMB")
    # Shift also activates free air-roll, so use it for ground powerslide only.
    if brake and ground: keys.add("SHIFT")
    t = int("W" in keys)-int("S" in keys)
    s = int("D" in keys)-int("A" in keys)
    r = int("E" in keys)-int("Q" in keys)
    y = s if r or "SHIFT" not in keys else 0
    r = r or (s if "SHIFT" in keys else 0)
    actual = np.array([t,s,-t,y,r,"RMB" in keys,"LMB" in keys,"SHIFT" in keys], dtype=np.float32)
    return keys, actual


class Output:
    """Windows keyboard/mouse events; calls release only for keys this owns."""
    VK = {"W":0x57,"S":0x53,"A":0x41,"D":0x44,"Q":0x51,"E":0x45,"SHIFT":0xA0}

    def __init__(self, dry=False):
        self.dry, self.held = dry, set()
        if dry:
            return
        if os.name != "nt":
            raise RuntimeError("Real input requires Windows; use --dry-run here")
        from ctypes import wintypes as w
        self.u, self.k = ctypes.WinDLL("user32",use_last_error=True), ctypes.WinDLL("kernel32",use_last_error=True)
        self.u.GetForegroundWindow.restype = w.HWND
        self.u.GetWindowThreadProcessId.argtypes = [w.HWND,ctypes.POINTER(w.DWORD)]
        self.k.OpenProcess.argtypes = [w.DWORD,w.BOOL,w.DWORD]
        self.k.OpenProcess.restype = w.HANDLE
        self.k.QueryFullProcessImageNameW.argtypes = [w.HANDLE,w.DWORD,w.LPWSTR,ctypes.POINTER(w.DWORD)]
        self.k.CloseHandle.argtypes = [w.HANDLE]
        self.u.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.u.GetAsyncKeyState.restype = ctypes.c_short
        self.u.keybd_event.argtypes = [w.BYTE,w.BYTE,w.DWORD,ctypes.c_size_t]
        self.u.mouse_event.argtypes = [w.DWORD,w.DWORD,w.DWORD,w.DWORD,ctypes.c_size_t]

    def focused(self):
        if self.dry: return True
        from ctypes import wintypes as w
        pid = w.DWORD()
        self.u.GetWindowThreadProcessId(self.u.GetForegroundWindow(),ctypes.byref(pid))
        handle = self.k.OpenProcess(0x1000,False,pid.value)
        if not handle: return False
        try:
            size, text = w.DWORD(32768), ctypes.create_unicode_buffer(32768)
            ok = self.k.QueryFullProcessImageNameW(handle,0,text,ctypes.byref(size))
            return bool(ok and Path(text.value).name.lower() in ("robloxplayerbeta.exe","robloxplayer.exe"))
        finally:
            self.k.CloseHandle(handle)

    def stopped(self):
        return not self.dry and bool(self.u.GetAsyncKeyState(0x77) & 0x8000)

    def event(self, key, down):
        if self.dry: return
        if key in ("LMB","RMB"):
            flag = (2 if down else 4) if key == "LMB" else (8 if down else 16)
            self.u.mouse_event(flag,0,0,0,0)
        else:
            vk = self.VK[key]
            self.u.keybd_event(vk,self.u.MapVirtualKeyW(vk,0),0 if down else 2,0)

    def apply(self, wanted):
        for key in sorted(self.held-wanted):
            self.event(key,False)
            self.held.remove(key)
        for key in sorted(wanted-self.held):
            self.held.add(key)
            self.event(key,True)


class Bridge:
    def __init__(self, model, output, clock=time.monotonic):
        self.model, self.output, self.clock = model, output, clock
        self.lock, self.infer_lock = threading.RLock(), threading.Lock()
        self.token = secrets.token_hex(24)
        self.seq, self.last_seen, self.blocked, self.enabled = -1, 0, False, False
        self.epoch = 0
        self.previous, self.jump_at, self.used_flip = ZERO.copy(), None, False
        self.last_ground, self.status = True, "PAUSED - click Start bot"
        self.frames = 0
        self.actions = lookup_table()

    def release(self, message, latch=False):
        self.output.apply(set())
        self.previous = ZERO.copy()
        self.status = message
        if latch: self.blocked = True

    def reply(self, **extra):
        return dict(status=self.status,disarmed=self.blocked,keys=sorted(self.output.held),**extra)

    def hello(self):
        with self.lock:
            self.enabled, self.blocked, self.seq = False, False, -1
            self.epoch += 1
            self.token = secrets.token_hex(24)
            self.release("Connected - click Start bot")
            logging.info("CLIENT_HELLO: Lua client connected; waiting for telemetry/start")
            return {"token":self.token,"protocol":1}

    def watchdog(self):
        with self.lock:
            if self.output.stopped():
                self.release("STOPPED by F8 - click Start bot again",True)
            elif self.enabled and not self.output.focused():
                self.release("PAUSED: Roblox lost focus - click Start bot",True)
            elif self.enabled and self.clock()-self.last_seen > .4:
                self.release("PAUSED: telemetry timeout - click Start bot",True)

    def frame(self, packet):
        received = self.clock()
        if packet.get("account") != ACCOUNT or packet.get("place") != PLACE:
            raise ValueError("Wrong account/place")
        seq = packet.get("seq")
        if type(seq) is not int or seq < 0:
            raise ValueError("Invalid sequence")
        with self.lock:
            if seq <= self.seq: return self.reply(ignored=True)
            self.seq, self.last_seen = seq, received
            self.enabled = packet.get("enabled") is True
            if not self.enabled:
                self.blocked = False
                self.release("PAUSED - click Start bot")
                return self.reply()
            self.watchdog()
            if self.blocked: return self.reply()
            if packet.get("valid") is not True:
                self.jump_at, self.used_flip = None, False
                self.release("WAITING: "+str(packet.get("reason","goal/reset"))[:100])
                return self.reply()
            if packet.get("team") not in (0,1) or type(packet.get("ground_estimate")) is not bool:
                raise ValueError("Missing team/ground estimate")
            ground = packet["ground_estimate"]
            if ground and (not self.last_ground or not self.previous[5]):
                self.jump_at, self.used_flip = None, False
            self.last_ground = ground
            has_flip = ground or (not self.used_flip and (self.jump_at is None or received-self.jump_at<1.45))
            obs = observations(packet,self.previous.copy(),has_flip)
            epoch = self.epoch
        with self.infer_lock, torch.inference_mode():
            logits = self.model(obs)[0].reshape(-1)
            if logits.shape != (90,) or not torch.isfinite(logits).all():
                raise ValueError("Model must return 90 finite logits")
            action_id = int(logits.argmax())
        keys, actual = mapped_keys(self.actions[action_id],ground)
        with self.lock:
            if seq != self.seq or epoch != self.epoch: return self.reply(ignored=True)
            self.watchdog()
            if self.blocked or self.clock()-received>.35:
                self.release("PAUSED: inference/connection too slow",True)
                return self.reply()
            if actual[5] and not self.previous[5]:
                if ground: self.jump_at = received
                else: self.used_flip = True
            self.output.apply(keys)
            self.previous = actual
            self.status = "RUNNING update271"+ (" [DRY RUN]" if self.output.dry else "")
            self.frames += 1
            if self.frames % 60 == 0:
                logging.info("RUNNING frames=%s action=%s keys=%s inference=%.1fms",self.frames,action_id," ".join(sorted(keys)),(self.clock()-received)*1000)
            return self.reply(action=action_id,ms=round((self.clock()-received)*1000,1))


def make_handler(bridge, client_source):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def send(self, status, body, content_type="application/json"):
            data = (json.dumps(body,allow_nan=False) if isinstance(body,dict) else body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type",content_type)
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError): pass

        def allowed(self):
            return not self.headers.get("Origin") and self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.allowed(): return self.send(403,{"error":"Loopback clients only"})
            if self.path in ("/", "/health"):
                with bridge.lock:
                    return self.send(200,{
                        "service":"botrblx", "version":2, "model_loaded":True,
                        "client_connected":bridge.seq >= 0 and bridge.clock()-bridge.last_seen < 1,
                        "status":bridge.status, "frames":bridge.frames,
                        "next_step":"Execute JJSploit_Launch.lua in Roblox, then click Start bot or press F6.",
                    })
            if self.path == "/client":
                logging.info("CLIENT_DOWNLOAD: launcher requested /client")
                return self.send(200,client_source,"text/plain; charset=utf-8")
            if self.path == "/hello":
                return self.send(200,bridge.hello())
            return self.send(404,{"error":"Unknown route"})

        def do_POST(self):
            if not self.allowed(): return self.send(403,{"error":"Loopback clients only"})
            if self.path != "/frame": return self.send(404,{"error":"Unknown route"})
            if not secrets.compare_digest(self.headers.get("X-Bridge-Token",""),bridge.token):
                return self.send(401,{"error":"Reconnect client"})
            try:
                length = int(self.headers.get("Content-Length","0"))
                if not 0 < length <= 16384: raise ValueError("Invalid frame size")
                if self.headers.get_content_type() != "application/json": raise ValueError("Expected JSON")
                packet = json.loads(self.rfile.read(length))
                result = bridge.frame(packet)
                return self.send(200,result)
            except Exception as error:
                with bridge.lock: bridge.release("ERROR: "+str(error)[:150],True)
                logging.exception("Frame rejected")
                return self.send(400,{"error":str(error)[:150],"disarmed":True})
    return Handler


def load_model(model_path, base_path):
    # Both TorchScript exports and native {'actor': state_dict} checkpoints.
    import zipfile
    is_script = False
    if zipfile.is_zipfile(model_path):
        with zipfile.ZipFile(model_path) as archive:
            is_script = any("/code/" in name and name.endswith(".py") for name in archive.namelist())
    if is_script:
        model = torch.jit.load(str(model_path),map_location="cpu")
    else:
        weights = torch.load(str(model_path),map_location="cpu",weights_only=True)["actor"]
        model = torch.jit.load(str(base_path),map_location="cpu")
        model.load_state_dict(weights,strict=True)
    return model.eval()


def resolve_paths(args):
    root = args.project_root.expanduser().resolve()
    model = args.model or root / "data/isolated/mechanics_curriculum/selected7_mechanics01/update_000271.pt"
    base = args.base or root / "vendor/nexto/nexto-model.pt"
    for label, path in (("model", model), ("base wrapper", base)):
        if not path.is_file():
            raise FileNotFoundError(f"Missing {label}: {path}. Check --project-root or supply --model / --base.")
    return root, model, base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=APP_DIR.parent)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--transport", choices=("http","files"), default="http")
    parser.add_argument("--workspace", type=Path, help="Executor workspace root for file mode")
    parser.add_argument("--choose-workspace", action="store_true", help="Open a folder picker if no file workspace is saved")
    parser.add_argument("--reset-workspace", action="store_true", help="Ignore the saved workspace and choose again")
    parser.add_argument("--self-check", action="store_true", help="Verify files and model inference without starting input or HTTP")
    args = parser.parse_args()
    root, model_path, base_path = resolve_paths(args)
    client_source = (APP_DIR / "client271.lua").read_text(encoding="utf-8")
    logging.info("Project: %s | Python: %s", root, os.sys.executable)
    logging.info("Model: %s | Log: %s", model_path, APP_DIR / "bridge.log")
    torch.set_num_threads(1)
    model = load_model(model_path,base_path)
    with torch.inference_mode():
        warm = model((torch.zeros(1,1,32),torch.zeros(1,36,24),torch.zeros(1,36)))[0]
        if warm.shape != (1,90) or not torch.isfinite(warm).all():
            raise ValueError("Model must return 90 finite logits")
    if args.self_check:
        logging.info("SELF_CHECK_OK: model returns 90 finite logits; client271.lua found. No inputs sent.")
        return
    output = Output(args.dry_run)
    bridge = Bridge(model,output)
    server = None
    exchange = None
    if args.transport == "files":
        from file_transport import FileExchange, install_client, select_workspace
        workspace = select_workspace(args, APP_DIR / "file_connection.json")
        install_client(workspace,APP_DIR)
        exchange = FileExchange(bridge,workspace)
    else:
        server = ThreadingHTTPServer(("127.0.0.1",PORT),make_handler(bridge,client_source))
    done = threading.Event()
    def monitor():
        while not done.wait(.02):
            try: bridge.watchdog()
            except Exception:
                with bridge.lock: bridge.release("Input error - stopped",True)
                logging.exception("Input watchdog")
    worker = threading.Thread(target=monitor,daemon=True)
    worker.start()
    if exchange:
        logging.info("READY FILE MODE | workspace %s | no HTTP server",workspace)
        logging.info("Execute JJSploit_File_Launch.lua. Requires executor readfile/writefile support.")
    else:
        logging.info("READY http://127.0.0.1:%s | model %s",PORT,model_path)
    logging.info("Model SHA256 %s",hashlib.sha256(model_path.read_bytes()).hexdigest())
    logging.info("F8 releases bot inputs. Focus loss/stale telemetry pauses. Ctrl+C exits.")
    logging.info("Freeplay adapter: ground/flip estimated; unavailable pads masked; other cars omitted.")
    try:
        if exchange:
            while not done.wait(.005): exchange.poll()
        else:
            server.serve_forever(poll_interval=.1)
    except KeyboardInterrupt: pass
    finally:
        done.set()
        with bridge.lock: bridge.release("Stopped")
        if server: server.server_close()
        worker.join(timeout=1)


if __name__ == "__main__":
    try: main()
    except Exception:
        logging.exception("STARTUP FAILED")
        raise SystemExit(1)
