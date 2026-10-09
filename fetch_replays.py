"""Download publicly listed GC 1v1 replays from Ballchasing using YOUR API token.

Set environment variable BALLCHASING_TOKEN; default max 20 files and 1.25s delay.
Respects API rate limits; no token is shipped in this project.
"""
import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from chatgpt_ai.config import ROOT

BASE = "https://ballchasing.com/api/"


def get(url: str, token: str) -> tuple[bytes, dict]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "ballchasing.com" or not parsed.path.startswith("/api/"):
        raise ValueError("Invalid ballchasing URL")
    req = urllib.request.Request(url, headers={"Authorization": token, "User-Agent": "Chat-GPT-AI/0.1"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read(30_000_000 + 1), dict(r.headers)


def main():
    p = argparse.ArgumentParser(description="Fetch high-rank public 1v1 .replay files")
    p.add_argument("--count", type=int, default=20)
    p.add_argument("--min-rank", default="grand-champion")
    p.add_argument("--output", type=Path, default=ROOT / 'data' / 'replays')
    args = p.parse_args()
    if not 1 <= args.count <= 200:
        p.error("count must be 1..200")
    token = os.environ.get("BALLCHASING_TOKEN")
    if not token:
        p.error("Set BALLCHASING_TOKEN from https://ballchasing.com/upload before downloading")
    args.output.mkdir(parents=True, exist_ok=True)
    query = urllib.parse.urlencode({
        'playlist': 'ranked-duels', 'min-rank': args.min_rank,
        'count': min(50, args.count), 'sort-by': 'replay-date', 'sort-dir': 'desc',
    })
    next_url = BASE + 'replays?' + query
    saved = 0
    while next_url and saved < args.count:
        payload, _ = get(next_url, token)
        response = json.loads(payload)
        next_url = response.get('next')
        time.sleep(1.25)
        for item in response.get('list', []):
            if saved >= args.count:
                break
            if item.get('visibility') not in (None, 'public'):
                continue
            if item.get('playlist_id') != 'ranked-duels':
                continue
            rid = item.get('id', '')
            if not (len(rid) == 36 and all(c in '0123456789abcdef-' for c in rid.lower())):
                continue
            target = args.output / f'{rid}.replay'
            if target.exists() and target.stat().st_size > 0:
                print('Already downloaded:', target.name)
                saved += 1
                continue
            try:
                content, _ = get(BASE + f'replays/{rid}/file', token)
                if not content or len(content) > 30_000_000:
                    print('Skipping empty/oversized replay:', rid)
                else:
                    target.write_bytes(content)
                    print('Downloaded:', target.name)
                    saved += 1
            except Exception as e:
                print('Download error for', rid, ':', e)
            time.sleep(1.25)
    print(f'Done; found {saved} files under {args.output}')


if __name__ == '__main__':
    main()
