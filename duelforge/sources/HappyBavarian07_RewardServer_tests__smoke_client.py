"""Protocol smoke test for a running reward_server; needs no Rocket League.

    python tests/smoke_client.py --config reward.json [--port 42069] [--tasks]

Start the server first, for example:
    reward_server.exe --config reward.json --tasks examples/example_tasks.json
"""
import argparse
import json
import math
import socket
import sys

CAR = {"pos": [0.0, -2000.0, 17.0], "vel": [0.0, 800.0, 0.0], "ang_vel": [0, 0, 0],
       "rot_mat": [1, 0, 0, 0, 1, 0, 0, 0, 1], "boost": 50.0, "is_on_ground": 1,
       "has_jumped": 0, "has_double_jumped": 0, "has_flipped": 0, "is_demoed": 0,
       "demo_respawn_timer": 0.0, "is_ball_touched": 0, "team": 0}
BALL = {"pos": [0.0, 0.0, 93.0], "vel": [0, 0, 0], "ang_vel": [0, 0, 0], "rot_mat": [1, 0, 0, 0, 1, 0, 0, 0, 1]}
GAME = {"blue_score": 0, "orange_score": 0, "boost_pad_states": [1] * 34, "boost_pad_timers": [0.0] * 34}


class Connection:
    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.buffer = b""

    def rpc(self, request):
        raw = request if isinstance(request, bytes) else (json.dumps(request) + "\n").encode()
        self.sock.sendall(raw)
        while b"\n" not in self.buffer:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("server closed the connection")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)


def check_basics(conn):
    hello = conn.rpc({"cmd": "hello"})
    assert hello["ok"] and hello["proto"] == 1, hello
    for command in ("eval", "load", "reload", "save_clip", "get_tasks"):
        assert command in hello["commands"], f"hello does not advertise {command}"
    assert conn.rpc({"cmd": "ping"})["ok"]
    assert not conn.rpc({"cmd": "no_such_command"})["ok"]
    assert conn.rpc(b"{not json\n") == {"ok": False, "error": "bad json"}
    assert not conn.rpc([1, 2, 3])["ok"]


def check_reward(conn, config):
    loaded = conn.rpc({"cmd": "load", "config": config})
    assert loaded["ok"], loaded
    assert loaded["count"] > 0 and len(loaded["names"]) == loaded["count"]
    result = conn.rpc({"cmd": "eval", "step": 500_000_000, "force_all": True,
                       "cars": [CAR], "ball": BALL, "game": GAME})
    assert result["ok"], result
    for key in ("names", "values", "weights"):
        assert len(result[key]) == loaded["count"], key
    assert not math.isnan(result["total"])
    top = sorted(zip(result["names"], result["values"]), key=lambda kv: -abs(kv[1]))[:5]
    for name, value in top:
        print(f"  {name:<32} {value: .5f}")
    reloaded = conn.rpc({"cmd": "reload"})
    assert reloaded["ok"] and reloaded["count"] == loaded["count"], reloaded
    assert conn.rpc({"cmd": "reset"})["ok"]
    return loaded["count"]


def check_clips(conn):
    info = conn.rpc({"cmd": "clip_info"})
    assert info["ok"] and info["window_seconds"] >= 1.0, info
    assert conn.rpc({"cmd": "set_clip_window", "seconds": 0.1})["window_seconds"] == 1.0
    assert not conn.rpc({"cmd": "create_clip_folder", "path": "../escape"})["ok"]
    assert not conn.rpc({"cmd": "move_clip", "source": "..\\x.rlpr", "folder": "y"})["ok"]
    assert conn.rpc({"cmd": "list_clips"})["ok"]


def check_tasks(conn):
    tasks = conn.rpc({"cmd": "get_tasks"})
    assert tasks["ok"] and isinstance(tasks["tasks"], list), tasks
    assert not conn.rpc({"cmd": "set_active_task", "index": 10_000})["ok"]
    if tasks["tasks"]:
        assert conn.rpc({"cmd": "set_active_task", "index": 0})["active_index"] == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=42069)
    parser.add_argument("--config", required=True)
    parser.add_argument("--tasks", action="store_true", help="also exercise the task commands")
    args = parser.parse_args()
    conn = Connection(args.host, args.port)
    check_basics(conn)
    terms = check_reward(conn, args.config)
    check_clips(conn)
    if args.tasks:
        check_tasks(conn)
    print(f"SMOKE OK ({terms} terms)")


if __name__ == "__main__":
    sys.exit(main())

