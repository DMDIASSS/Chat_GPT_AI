"""Ballchasing replay downloader for Chat GPT AI (Python 3.11, no pip dependencies).

API only; authenticates with user-provided token. No website scraping.
Ratelimits regular API users conservatively. Files are saved by replay UUID.
"""
import argparse
import collections
import datetime as dt
import getpass
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API_ROOT = 'https://ballchasing.com/api/'
PLAYLISTS = ['ranked-duels', 'ranked-doubles', 'ranked-solo-standard', 'ranked-standard']
MAX_BYTES = 30 * 1024 * 1024


def valid_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or parts.hostname != 'ballchasing.com' or parts.port is not None:
        raise ValueError('Refusing non-Ballchasing API URL: ' + url)
    if not parts.path.startswith('/api/'):
        raise ValueError('Refusing non-API URL: ' + url)
    return url


def replay_id(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def atomic_json(path, data):
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    tmp.replace(path)


class RequestError(Exception):
    def __init__(self, status, body='', retry_after=None):
        super().__init__(f'HTTP {status}: {body[:350]}')
        self.status = status
        self.retry_after = retry_after


class Client:
    def __init__(self, token, delay=1.25, opener=None):
        self.token = token
        self.delay = delay
        self._last = None
        self.opener = opener or urllib.request.urlopen

    def get(self, url, binary=False):
        valid_url(url)
        for attempt in range(5):
            if self._last is not None:
                time.sleep(max(0.0, self.delay - (time.monotonic() - self._last)))
            self._last = time.monotonic()
            request = urllib.request.Request(url, headers={
                'Authorization': self.token,
                'User-Agent': 'ChatGPT-AI-ReplayDownloader/1.0',
                'Accept': 'application/octet-stream' if binary else 'application/json',
            })
            try:
                with self.opener(request, timeout=60) as response:
                    content = response.read(MAX_BYTES + 1 if binary else 5_000_000)
                    if binary:
                        if not content or len(content) > MAX_BYTES:
                            raise ValueError('Replay empty or larger than 30 MiB')
                        if content.lstrip().startswith((b'{', b'<!doctype', b'<html')):
                            raise ValueError('Expected replay bytes; received text/JSON')
                        return content
                    return json.loads(content)
            except urllib.error.HTTPError as exc:
                body = exc.read(4000).decode('utf-8', 'replace')
                if exc.code in (401, 403, 400, 404):
                    raise RequestError(exc.code, body) from exc
                if exc.code == 429 or exc.code >= 500:
                    retry_after = exc.headers.get('Retry-After')
                    try:
                        pause = max(float(retry_after), 1) if retry_after else (70 if exc.code == 429 else 2 ** (attempt + 2))
                    except ValueError:
                        pause = 70
                    if attempt == 4:
                        raise RequestError(exc.code, body, pause) from exc
                    print(f'  HTTP {exc.code}; waiting {pause:.0f} seconds before retry (Ctrl+C to stop)...', flush=True)
                    time.sleep(pause)
                    continue
                raise RequestError(exc.code, body) from exc
            except (TimeoutError, urllib.error.URLError) as exc:
                if attempt == 4:
                    raise RuntimeError(f'Network error after retries: {exc}') from exc
                time.sleep(2 ** (attempt + 2))
        raise RuntimeError('Unreachable')


class HourlyBudget:
    """Persists download *attempts* (including 429s) so restarts cannot exceed local rate budget."""
    def __init__(self, path, hourly_limit=180):
        self.path = path
        self.limit = hourly_limit
        try:
            self.events = collections.deque(json.loads(path.read_text(encoding='utf-8')))
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            self.events = collections.deque()

    def before_download(self):
        while True:
            now = time.time()
            while self.events and now - self.events[0] >= 3600:
                self.events.popleft()
            if len(self.events) < self.limit:
                self.events.append(now)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(list(self.events)), encoding='utf-8')
                return
            wait = max(2, self.events[0] + 3601 - now)
            print(f'Hourly download budget reached ({self.limit}); pausing {wait/60:.1f} min. Ctrl+C is safe.', flush=True)
            time.sleep(wait)


def args_parser():
    p = argparse.ArgumentParser(description='Download public Rocket League replays via Ballchasing API')
    p.add_argument('--playlist', choices=['all'] + PLAYLISTS, default='ranked-duels',
                   help='all means ranked 1v1, 2v2, solo 3v3, standard 3v3')
    p.add_argument('--rank', choices=['gc3-ssl', 'gc-plus'], default='gc3-ssl',
                   help='gc3-ssl attempts precise API rank filter; gc-plus uses documented broader filter')
    p.add_argument('--max-files', type=int, default=50, help='New downloads to make in this run; 0 = keep paginating to the end')
    p.add_argument('--from-ids', type=Path, help='Download UUIDs from a text file instead of querying the search API')
    p.add_argument('--output', type=Path, default=ROOT/'data'/'replays')
    p.add_argument('--hour-limit', type=int, default=180,
                   help='Limit replay download attempts per hour; default safely below regular-user limit of 200')
    p.add_argument('--page-size', type=int, default=150, help='API result items per page (1..200)')
    p.add_argument('--list-only', action='store_true', help='Check that search works and print first 10 replay IDs; download nothing')
    return p


def search_url(playlist, rank, page_size):
    q = [('playlist', item) for item in (PLAYLISTS if playlist == 'all' else [playlist])]
    # The website accepts numeric ranks, but API docs do not clearly describe GC3/SSL.
    # A community API wrapper indicates SSL is supported. Let server validate values.
    if rank == 'gc3-ssl':
        q.extend([('min-rank', 'grand-champion-3'), ('max-rank', 'supersonic-legend')])
    else:
        q.append(('min-rank', 'grand-champion'))
    q.extend([('count', str(page_size)), ('sort-by', 'replay-date'), ('sort-dir', 'desc')])
    return API_ROOT + 'replays?' + urllib.parse.urlencode(q)


def load_ids(path):
    values = []
    for raw in path.read_text(encoding='utf-8').splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith('#'):
            continue
        rid = replay_id(stripped)
        if not rid:
            raise ValueError('Invalid replay UUID in manifest: ' + stripped)
        if rid not in values:
            values.append(rid)
    return values


def store_file(client, budget, rid, output):
    target = output / (rid + '.replay')
    if target.exists() and target.stat().st_size > 0:
        return 'skip'
    budget.before_download()
    content = client.get(API_ROOT + 'replays/' + rid + '/file', binary=True)
    temp = target.with_suffix('.replay.part')
    try:
        with temp.open('wb') as f:
            f.write(content)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    print('  DOWNLOADED', target, f'({len(content):,} bytes)', flush=True)
    return 'new'


def run(args, client, budget):
    if args.max_files < 0 or not 1 <= args.page_size <= 200 or not 1 <= args.hour_limit <= 200:
        raise ValueError('max-files must be >=0, page-size 1..200 and hour-limit 1..200')
    args.output.mkdir(parents=True, exist_ok=True)
    new_files = skipped = failed = 0
    if args.from_ids:
        ids = load_ids(args.from_ids)
        print(f'Using {len(ids)} replay IDs from {args.from_ids} (NOT paginating beyond that saved list).')
        if args.list_only:
            print('\n'.join(ids[:10]))
            return 0
        out = args.output/'saved-page'
        out.mkdir(parents=True, exist_ok=True)
        for index, rid in enumerate(ids, 1):
            if args.max_files and new_files >= args.max_files:
                break
            try:
                result = store_file(client, budget, rid, out)
            except RequestError as exc:
                if exc.status in (401, 403):
                    raise
                failed += 1
                print('  FAILED', rid, exc)
                if exc.status == 429:
                    raise
                continue
            if result == 'new':
                new_files += 1
            else:
                skipped += 1
        print(f'Done: new={new_files} existing={skipped} failed={failed}.')
        return new_files

    out = args.output / ('all-ranked' if args.playlist == 'all' else args.playlist)
    out.mkdir(parents=True, exist_ok=True)
    first = search_url(args.playlist, args.rank, args.page_size)
    key = hashlib.sha256(first.encode('utf-8')).hexdigest()[:12]
    state_path = out / f'download_state_{key}.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    if state.get('finished'):
        print('Search reached its last page in an earlier run; no new results for this sorted snapshot.')
        print('To search newer matches later, delete', state_path)
        return 0
    next_url = state.get('next_url') or first
    page_no = 0
    seen_page_urls = set()
    while next_url:
        if next_url in seen_page_urls:
            raise RuntimeError('API repeated a pagination cursor; stopping to prevent a loop')
        seen_page_urls.add(next_url)
        valid_url(next_url)
        try:
            payload = client.get(next_url)
        except RequestError as exc:
            if exc.status == 400 and args.rank == 'gc3-ssl':
                raise RuntimeError(
                    'Ballchasing rejected the experimental GC3-SSL API rank values. '
                    'No broader replays were downloaded. Re-run with --rank gc-plus '
                    '(GC1 and above, NOT your exact filter), or save the precise website search as HTML.') from exc
            raise
        items = payload.get('list', [])
        after = payload.get('next')
        page_no += 1
        print(f'Page {page_no}: API returned {len(items)} records. Downloaded this run: {new_files}.', flush=True)
        if args.list_only:
            for item in items[:10]:
                print(' ', item.get('id'), item.get('playlist_id'), item.get('replay_title', ''))
            return 0
        for item in items:
            if args.max_files and new_files >= args.max_files:
                break
            rid = replay_id(item.get('id'))
            if not rid or item.get('visibility') not in ('public', None):
                continue
            if item.get('playlist_id') not in (PLAYLISTS if args.playlist == 'all' else [args.playlist]):
                continue
            destination = out / item['playlist_id'] if args.playlist == 'all' else out
            destination.mkdir(parents=True, exist_ok=True)
            try:
                result = store_file(client, budget, rid, destination)
                if result == 'new':
                    new_files += 1
                else:
                    skipped += 1
            except RequestError as exc:
                if exc.status in (401, 403, 429):
                    raise
                failed += 1
                print('  FAILED', rid, exc, flush=True)
            except (ValueError, RuntimeError, OSError) as exc:
                failed += 1
                print('  FAILED', rid, exc, flush=True)
        # If we stopped partway through this page, resume this same page next time.
        done_page = (not args.max_files or new_files < args.max_files)
        if done_page:
            next_url = after
            atomic_json(state_path, {'next_url': next_url, 'finished': not bool(next_url), 'last_page': page_no})
        else:
            atomic_json(state_path, {'next_url': next_url, 'finished': False, 'last_page': page_no})
            break
    print(f'Finished: new={new_files}, already-on-disk={skipped}, failed={failed}.')
    return new_files


def main(argv=None):
    args = args_parser().parse_args(argv)
    if args.playlist != 'ranked-duels' and not args.from_ids:
        print('NOTE: Your existing behavior-cloning converter currently accepts ONLY 1v1.', flush=True)
    if args.rank == 'gc3-ssl' and not args.from_ids:
        print('NOTE: Exact GC3-SSL API ranks are experimental; site may reject them.', flush=True)
    token = os.environ.get('BALLCHASING_TOKEN', '').strip()
    if not token:
        token = getpass.getpass('Paste your Ballchasing API token (hidden): ').strip()
    if not token:
        raise ValueError('No token entered. Generate one at https://ballchasing.com/upload')
    output = args.output.resolve()
    budget = HourlyBudget(output / '.download_attempts_last_hour.json', args.hour_limit)
    client = Client(token)
    client.get(API_ROOT)  # fail early for wrong token
    print('API login OK. Saving to:', output)
    return run(args, client, budget)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nStopped safely. Run the same command to resume.')
    except RequestError as exc:
        print('ERROR:', exc)
        if exc.status == 401:
            print('Invalid token. Check it at https://ballchasing.com/upload')
        elif exc.status == 403:
            print('Access denied: replay may be private or token lacks access.')
        elif exc.status == 429:
            print('Rate limited. Wait and resume later.')
        sys.exit(1)
    except (ValueError, RuntimeError, OSError) as exc:
        print('ERROR:', exc)
        sys.exit(1)
