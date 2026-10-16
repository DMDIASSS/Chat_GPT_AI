#!/usr/bin/env python3
"""Resumable, conservative Ballchasing ranked-doubles replay importer.

The documented API exposes ``grand-champion`` as the highest named rank
filter, NOT numeric GC3-SSL. This script must not label downloads GC3-SSL.
Requires BALLCHASING_TOKEN. Uses only Python standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen

BASE = "https://ballchasing.com/api"
MAX_FILE_BYTES = 64 * 1024 * 1024


class FetchError(RuntimeError):
    pass


def safe_page_url(url: str) -> bool:
    """Only follow pagination URLs returned by the official replays API."""
    u = urlparse(url)
    return (u.scheme == "https" and u.hostname == "ballchasing.com"
            and u.port is None and u.path == "/api/replays"
            and not u.username and not u.password and not u.fragment)


def acceptable_replay(entry: dict, min_duration: int) -> bool:
    """Reject mislabelled modes and incomplete/really short matches."""
    try:
        blue = entry["blue"]["players"]
        orange = entry["orange"]["players"]
        return (entry.get("playlist_id") == "ranked-doubles"
                and isinstance(blue, list) and len(blue) == 2
                and isinstance(orange, list) and len(orange) == 2
                and float(entry.get("duration") or 0) >= min_duration)
    except (KeyError, TypeError, ValueError):
        return False


class Api:
    def __init__(self, token: str, retries: int = 6, pause: float = 1.1):
        self.token = token
        self.retries = retries
        self.pause = pause
        self.last_request = 0.0

    def _open(self, url: str):
        for attempt in range(self.retries):
            delay = self.pause - (time.monotonic() - self.last_request)
            if delay > 0:
                time.sleep(delay)
            self.last_request = time.monotonic()
            request = Request(url, headers={"Authorization": self.token,
                                             "User-Agent": "offline-imitation-replay-import/1.0"})
            try:
                return urlopen(request, timeout=45)
            except HTTPError as e:
                if e.code in (401, 403):
                    raise FetchError(f"Ballchasing authorization failed (HTTP {e.code}). Check BALLCHASING_TOKEN.") from e
                if e.code not in (429, 500, 502, 503, 504) or attempt == self.retries - 1:
                    raise FetchError(f"Ballchasing request failed (HTTP {e.code}); URL: {url}") from e
                retry_header = e.headers.get("Retry-After", "")
                try:
                    retry_delay = min(120.0, max(0, float(retry_header)))
                except ValueError:
                    retry_delay = 0.0
                time.sleep(max(retry_delay, min(90, 2 ** attempt + random.uniform(0, 0.5))))
            except (URLError, TimeoutError) as e:
                if attempt == self.retries - 1:
                    raise FetchError(f"Network request failed: {e}") from e
                time.sleep(min(60, 2 ** attempt))
        raise AssertionError("retries exhausted")

    def get_json(self, url: str) -> dict:
        if not safe_page_url(url):
            raise FetchError(f"Refusing unexpected API pagination URL: {url}")
        with self._open(url) as resp:
            result = json.load(resp)
        if not isinstance(result, dict) or not isinstance(result.get("list"), list):
            raise FetchError("Unexpected replay list response")
        return result

    def download(self, replay_id: str, final_path: Path) -> str:
        if not (len(replay_id) <= 128 and all(c.isalnum() or c in "-_" for c in replay_id)):
            raise FetchError("Unsafe replay ID")
        url = f"{BASE}/replays/{replay_id}/file"
        temp_path = final_path.with_suffix(".replay.part")
        digest = hashlib.sha256()
        size = 0
        try:
            with self._open(url) as resp, open(temp_path, "wb") as f:
                content_type = resp.headers.get("Content-Type", "").lower()
                if "json" in content_type or "html" in content_type:
                    raise FetchError(f"Unexpected file response type {content_type}")
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        raise FetchError("Replay exceeds configured safe file size limit")
                    f.write(chunk)
                    digest.update(chunk)
            if size < 128:
                raise FetchError(f"Replay too small: {size} bytes")
            temp_path.replace(final_path)
            return digest.hexdigest()
        finally:
            if temp_path.exists():
                temp_path.unlink()


def previous_ids(path: Path) -> tuple[set[str], set[str]]:
    ids, rlids = set(), set()
    if not path.exists():
        return ids, rlids
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            file = path.parent / event.get("file", "")
            if (event.get("status") == "downloaded" and event.get("id")
                    and event.get("file") and file.is_file() and file.stat().st_size >= 128):
                ids.add(event["id"])
                if event.get("rocket_league_id"):
                    rlids.add(event["rocket_league_id"])
    return ids, rlids


def run(args: argparse.Namespace) -> int:
    token = os.environ.get("BALLCHASING_TOKEN", "").strip()
    if not token:
        raise FetchError("Set BALLCHASING_TOKEN in the environment; do not put it in scripts or logs.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "download_manifest.jsonl"
    downloaded, seen_rlids = previous_ids(manifest)
    api = Api(token, pause=args.pause)
    params = {"playlist": "ranked-doubles", "count": min(args.page_size, 200),
              "sort-by": "replay-date", "sort-dir": "desc"}
    if args.min_rank:
        params["min-rank"] = args.min_rank
    url = f"{BASE}/replays?{urlencode(params)}"
    found = 0
    selected = 0
    pages = 0
    visited = set()
    while url and pages < args.max_pages and selected < args.limit:
        if url in visited:
            raise FetchError("API repeated a pagination URL; stopping")
        visited.add(url)
        data = api.get_json(url)
        pages += 1
        for item in data["list"]:
            found += 1
            if not acceptable_replay(item, args.min_duration):
                continue
            rid = str(item.get("id") or "")
            rlid = str(item.get("rocket_league_id") or "")
            if not rid or rid in downloaded or (rlid and rlid in seen_rlids):
                continue
            if not all(c.isalnum() or c in "-_" for c in rid):
                continue
            selected += 1
            target = output / f"{rid}.replay"
            if args.dry_run:
                print(f"[dry-run] {rid} | {item.get('date','?')} | {item.get('duration','?')}s")
                downloaded.add(rid)
                if rlid:
                    seen_rlids.add(rlid)
            else:
                if target.exists():
                    raise FetchError(f"Untracked existing replay file, will not overwrite: {target}")
                print(f"[{selected}/{args.limit}] Downloading {rid}", flush=True)
                sha = api.download(rid, target)
                record = {"status": "downloaded", "id": rid, "rocket_league_id": rlid,
                          "playlist": "ranked-doubles", "rank_filter_api": args.min_rank,
                          "rank_verified_gc3_ssl": False,
                          "replay_date": item.get("date"), "duration": item.get("duration"),
                          "file": target.name, "sha256": sha}
                with manifest.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                downloaded.add(rid)
                if rlid:
                    seen_rlids.add(rlid)
            if selected >= args.limit:
                break
        url = data.get("next")
        if url and not safe_page_url(url):
            raise FetchError(f"Unexpected pagination URL: {url}")
    print(f"Checked {found} API entries across {pages} page(s); "
          f"selected {selected}; manifest: {manifest}")
    print("IMPORTANT: Rank range GC3–SSL has NOT been verified. API 'grand-champion' is a broad filter.")
    print("No reconstructed actions or RocketSim simulations were generated by this downloader.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=Path("data/replays/ranked-doubles"))
    p.add_argument("--limit", type=int, default=100, help="Maximum NEW downloads")
    p.add_argument("--max-pages", type=int, default=30)
    p.add_argument("--page-size", type=int, default=150)
    p.add_argument("--min-duration", type=int, default=90, help="Reject very short games")
    p.add_argument("--min-rank", choices=("grand-champion", "champion-3", "champion-2", ""),
                   default="grand-champion")
    p.add_argument("--pause", type=float, default=1.1, help="Minimum interval between ALL requests")
    p.add_argument("--dry-run", action="store_true", help="Print planned downloads, without downloading")
    args = p.parse_args()
    if args.limit < 1 or args.max_pages < 1 or not 1 <= args.page_size <= 200 or args.pause < 1.05 or args.min_duration < 0:
        p.error("Require positive limit and pages, page-size 1..200, pause >=1.05, min-duration >=0")
    try:
        return run(args)
    except (FetchError, OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
