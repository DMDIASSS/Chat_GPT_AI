"""Local JSON mailbox. No HTTP, executor internals, or model files are exposed."""
import json
import logging
from pathlib import Path
import secrets
import time

BEGIN = "-- BRIDGE_TRANSPORT_BEGIN"
END = "-- BRIDGE_TRANSPORT_END"


def file_client_source(app_dir):
    source = (app_dir / "client271.lua").read_text(encoding="utf-8")
    start, end = source.index(BEGIN), source.index(END) + len(END)
    transport = (app_dir / "templates/file_transport.lua").read_text(encoding="utf-8").strip()
    return source[:start] + transport + source[end:]


def select_workspace(args, config_path):
    workspace = args.workspace
    if workspace is None and not args.reset_workspace and config_path.is_file():
        workspace = Path(json.loads(config_path.read_text(encoding="utf-8"))["workspace"])
    if workspace is None and args.choose_workspace:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        try:
            selected = filedialog.askdirectory(
                title="Select JJSploit's workspace folder (the root used by readfile/writefile)",
                mustexist=True,
            )
        finally:
            root.destroy()
        if selected: workspace = Path(selected)
    if workspace is None:
        raise ValueError("File mode needs JJSploit's workspace folder. Use --workspace or --choose-workspace.")
    workspace = workspace.expanduser().resolve()
    if not workspace.is_dir():
        raise ValueError("Executor workspace does not exist: " + str(workspace))
    config_path.write_text(json.dumps({"workspace":str(workspace)},indent=2),encoding="utf-8")
    return workspace


def install_client(workspace, app_dir):
    (workspace / "botrblx_exchange").mkdir(exist_ok=True)
    source = file_client_source(app_dir)
    (workspace / "botrblx_client.lua").write_text(source,encoding="utf-8")
    logging.info("Installed file client: %s",workspace / "botrblx_client.lua")


class FileExchange:
    def __init__(self, bridge, workspace, wall_clock=time.time):
        self.bridge, self.wall_clock = bridge, wall_clock
        self.folder = Path(workspace) / "botrblx_exchange"
        self.folder.mkdir(exist_ok=True)
        self.request = self.folder / "request.json"
        self.response = self.folder / "response.json"
        self.temporary = self.folder / "response.tmp"
        self.server = secrets.token_hex(16)
        self.session, self.last_id = None, -1
        self.last_request, self.pending = None, None
        # Only our two mailboxes are reset; never reuse frames from an earlier run.
        for path in (self.request,self.response,self.temporary):
            path.unlink(missing_ok=True)

    def _handle(self, request, mtime):
        session, request_id = request["session"], request["id"]
        def reply(status_code, **data):
            return dict(session=session,id=request_id,server=self.server,status=status_code,data=data)
        if self.wall_clock()-mtime > .35 or mtime-self.wall_clock() > 1:
            with self.bridge.lock: self.bridge.release("PAUSED: stale file telemetry",True)
            return reply(408,error="Stale file telemetry; reconnect",disarmed=True)
        route = request.get("route")
        if route == "/hello":
            if session == self.session and request_id <= self.last_id:
                return reply(409,error="Old file request")
            self.session, self.last_id = session, request_id
            return reply(200,**self.bridge.hello())
        if session != self.session or not secrets.compare_digest(str(request.get("token","")),self.bridge.token):
            return reply(401,error="Reconnect file client")
        if request_id <= self.last_id:
            return reply(409,error="Old file request")
        self.last_id = request_id
        if route != "/frame": return reply(404,error="Unknown file route")
        try:
            result = self.bridge.frame(request["packet"])
            return reply(200,**result)
        except Exception as error:
            with self.bridge.lock: self.bridge.release("ERROR: " + str(error)[:150],True)
            logging.exception("File frame rejected")
            return reply(400,error=str(error)[:150],disarmed=True)

    def _flush(self):
        if self.pending is None: return
        try:
            self.temporary.write_text(json.dumps(self.pending,allow_nan=False),encoding="utf-8")
            self.temporary.replace(self.response)
            self.pending = None
        except PermissionError:
            # Windows may briefly lock a file while readfile is using it. Retry
            # the cached reply on the next poll, without repeating inference.
            pass

    def poll(self):
        try:
            with self.request.open("rb") as stream:
                mtime = self.request.stat().st_mtime
                raw = stream.read(16385)
            if not raw or len(raw)>16384: return
            request = json.loads(raw)
        except (FileNotFoundError,PermissionError,ValueError,UnicodeError):
            self._flush()
            return  # A client write may be incomplete. The watchdog still runs.
        if not isinstance(request,dict): return
        session, request_id = request.get("session"),request.get("id")
        if not isinstance(session,str) or not 1<=len(session)<=128 or type(request_id) is not int or request_id<1:
            return
        key = session,request_id
        if key != self.last_request:
            self.last_request = key
            self.pending = self._handle(request,mtime)
        self._flush()
