"""Offline index of supplied DiscordChatExporter HTMLs; never logs into Discord.

All indexed text and excerpts are private local research data under ignored data/.
The parser does not execute HTML, download attachments, or retain author identities.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
from typing import Callable

ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT / 'data' / 'isolated' / 'discord_research'
TOPICS = {
    'frameworks': r'\b(?:gigalearn|ggl|rust|custom framework|rlgym.learn|rlgym.ppo|rocketsim.rs)\b',
    'throughput': r'(?:\b(?:30\s*(?:m|million)|[\d,.]+\s*(?:million|m))\b.{0,100}\b(?:steps|sps|fps|frames)|\b(?:steps\s*(?:/|per)\s*(?:s|sec|second)|sps)\b)',
    'rewards': r'\b(?:reward|rewards|zero.sum|potential.based|reward.hack|curriculum)\b',
    'teacher_architecture': r'\b(?:distill\w*|teacher|imitation|attention|transformer|architecture|shared.head|kl.divergence)\b',
    'replays': r'\b(?:replay.pretraining|replicar|replay|ballchasing|input.reconstruction|inverse.dynamics)\b',
    'teams': r'\b(?:2v2|3v3|1v2|2v1|1v3|3v1|team.size|teammate|multi.agent|self.play)\b',
    'github': r'https?://(?:www\.)?github\.com/',
}
URL_RE = re.compile(r'https?://[^\s<>"\x00-\x20]+', re.I)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def archive_path(name: str) -> PurePosixPath:
    p = PurePosixPath(name.replace('\\', '/'))
    if p.is_absolute() or '..' in p.parts or any(':' in x for x in p.parts):
        raise ValueError('Unsafe archive member path')
    if not p.parts:
        raise ValueError('Empty archive member path')
    return p


def extract_archive(archive: Path, destination: Path) -> dict:
    """Allow only regular HTML/text/JSON files with bounded decompressed sizes."""
    try:
        import libarchive
    except ImportError as e:
        raise RuntimeError('RAR extraction needs optional libarchive-c (PyPI), plus libarchive') from e
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    inventory, total = [], 0
    with libarchive.file_reader(str(archive)) as entries:
        for entry in entries:
            name = archive_path(entry.pathname)
            if entry.isdir:
                continue
            if not entry.isfile or name.suffix.lower() not in {'.html', '.txt', '.json'}:
                raise ValueError('Archive contains an unsupported member')
            total += entry.size
            if entry.size > 128 * 1024**2 or total > 2 * 1024**3:
                raise ValueError('Archive exceeds research size limit')
            target = destination.joinpath(*name.parts)
            if destination not in target.resolve().parents:
                raise ValueError('Archive member escapes destination')
            target.parent.mkdir(parents=True, exist_ok=True)
            h, count = hashlib.sha256(), 0
            # Existing paths are deliberately not overwritten, including symlinks.
            with target.open('xb') as f:
                for block in entry.get_blocks():
                    count += len(block)
                    if count > 128 * 1024**2:
                        raise ValueError('Archive member exceeds decompression limit')
                    h.update(block)
                    f.write(block)
            inventory.append({'entry': str(name), 'bytes': count, 'sha256': h.hexdigest(),
                              'local_path': str(target)})
    return {'archive_sha256': digest(archive), 'files': inventory, 'total_bytes': total}


class MessageParser(HTMLParser):
    """Capture message bodies and URLs, excluding quoted replies and authors."""
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
            'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, emit: Callable[[dict], None]):
        super().__init__(convert_charrefs=True)
        self.emit = emit
        self.stack: list[tuple[str, set[str]]] = []
        self.message = None
        self.depth = 0
        self.body: list[str] = []
        self.urls: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get('class', '').split())
        if 'chatlog__message-container' in classes:
            if self.message is not None:
                self.finish()
            self.message = {'message_id': attrs.get('data-message-id') or
                            attrs.get('id', '').replace('chatlog__message-container-', ''),
                            'timestamp': ''}
            self.depth = len(self.stack)
            self.body, self.urls = [], set()
        if self.message is not None:
            if classes & {'chatlog__timestamp', 'chatlog__short-timestamp',
                          'chatlog__system-notification-timestamp'}:
                self.message['timestamp'] = attrs.get('title', '')
            # Public links are useful even when embedded rather than in body text.
            if tag == 'a' and attrs.get('href', '').startswith(('https://', 'http://')):
                if not any('chatlog__reply' in c for _, c in self.stack):
                    self.urls.add(attrs['href'])
            if tag == 'br' and self.in_content():
                self.body.append('\n')
        if tag not in self.VOID:
            self.stack.append((tag, classes))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if self.message is not None and i == self.depth:
                    self.finish()
                del self.stack[i:]
                break

    def in_content(self):
        return any('chatlog__content' in c for _, c in self.stack) and not any(
            c & {'chatlog__reply', 'chatlog__edited-timestamp'} for _, c in self.stack)

    def handle_data(self, data):
        if self.message is not None and self.in_content():
            if not any(t in {'script', 'style'} for t, _ in self.stack):
                self.body.append(data)

    def finish(self):
        if self.message is None:
            return
        text = re.sub(r'[ \t\r\f\v]+', ' ', ''.join(self.body)).strip()
        self.urls.update(u.rstrip(').,;') for u in URL_RE.findall(text))
        self.emit({**self.message, 'text': text, 'urls': sorted(self.urls)})
        self.message = None


def parse_file(path: Path, emit: Callable[[dict], None]):
    parser = MessageParser(emit)
    with path.open(encoding='utf-8-sig', errors='replace') as f:
        for block in iter(lambda: f.read(256 * 1024), ''):
            parser.feed(block)
    parser.close()
    parser.finish()


def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS files(
            sha256 TEXT PRIMARY KEY, path TEXT, bytes INTEGER, channel TEXT,
            parsed_messages INTEGER, first_timestamp TEXT, last_timestamp TEXT);
        CREATE TABLE IF NOT EXISTS messages(
            evidence_id TEXT PRIMARY KEY, channel TEXT, message_id TEXT,
            timestamp TEXT, text TEXT, urls TEXT, source_sha256 TEXT);
        CREATE INDEX IF NOT EXISTS message_channel ON messages(channel);
    ''')
    return db


def index(paths: list[Path], out: Path):
    """Scan every supplied HTML; duplicates by file hash and message ID count once."""
    out.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
    db = connect(out / 'index.sqlite3')
    files = sorted({p.resolve() for root in paths for p in
                    ([root] if root.is_file() else root.rglob('*.html'))
                    if p.suffix.lower() == '.html'})
    aliases, errors = [], []
    for path in files:
        sha = digest(path)
        if db.execute('SELECT 1 FROM files WHERE sha256=?', (sha,)).fetchone():
            aliases.append({'path': str(path), 'sha256': sha, 'already_indexed': True})
            continue
        channel = re.sub(r'\s*\[\d+\]$', '', path.stem)
        channel_id = re.search(r'\[(\d+)\]$', path.stem)
        namespace = channel_id.group(1) if channel_id else hashlib.sha256(channel.encode()).hexdigest()[:12]
        stats = {'count': 0, 'first': '', 'last': ''}

        def emit(row):
            stats['count'] += 1
            stats['first'] = stats['first'] or row['timestamp']
            stats['last'] = row['timestamp'] or stats['last']
            mid = row['message_id'] or f'ordinal{stats["count"]}'
            db.execute('INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?,?)',
                       (f'{namespace}:{mid}', channel, mid, row['timestamp'], row['text'],
                        json.dumps(row['urls']), sha))

        try:
            parse_file(path, emit)
            db.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?)',
                       (sha, str(path), path.stat().st_size, channel, stats['count'],
                        stats['first'], stats['last']))
            db.commit()
            print('DISCORD_INDEX', path.name, stats['count'], flush=True)
        except Exception as e:
            db.rollback()
            errors.append({'path': str(path), 'error': str(e)})
    rows = db.execute('SELECT sha256,path,bytes,channel,parsed_messages,first_timestamp,last_timestamp FROM files ORDER BY channel').fetchall()
    inventory = {'format': 1, 'created_utc': datetime.now(timezone.utc).isoformat(),
                 'input_html_files': len(files), 'distinct_file_hashes': len(rows),
                 'distinct_messages': db.execute('SELECT COUNT(*) FROM messages').fetchone()[0],
                 'files': [dict(zip(('sha256', 'path', 'bytes', 'channel', 'parsed_messages',
                                    'first_timestamp', 'last_timestamp'), row)) for row in rows],
                 'duplicate_files': aliases, 'errors': errors,
                 'privacy': 'Local excerpts may contain private conversation; do not publish index or search reports.'}
    (out / 'inventory.json').write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding='utf-8')
    db.close()
    return inventory


def search(database: Path, query: str, limit=80, context=2):
    pattern = re.compile(query, re.I | re.S)
    db = sqlite3.connect(database)
    # Scan all messages; do not pretend top hits were the entire export review.
    rows = db.execute('SELECT evidence_id,channel,message_id,timestamp,text,urls FROM messages ORDER BY channel,CAST(message_id AS INTEGER)').fetchall()
    matches, count = [], 0
    for i, row in enumerate(rows):
        text, urls = row[4], json.loads(row[5])
        if not pattern.search(text + '\n' + '\n'.join(urls)):
            continue
        count += 1
        if len(matches) >= limit:
            continue
        related = []
        for adjacent in rows[max(0, i-context):i+context+1]:
            if adjacent[1] == row[1]:
                related.append({'evidence_id': adjacent[0], 'timestamp': adjacent[3],
                                'text': adjacent[4][:4000], 'urls': json.loads(adjacent[5])})
        matches.append({'evidence_id': row[0], 'channel': row[1], 'timestamp': row[3],
                        'text': text[:6000], 'urls': urls, 'context': related})
    db.close()
    return {'query': query, 'total_matching_messages': count, 'returned': len(matches),
            'all_messages_scanned': len(rows), 'matches': matches,
            'interpretation': 'Community statements are leads, not verified performance benchmarks.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('extract'); p.add_argument('archive', type=Path)
    p.add_argument('--out', type=Path, default=DEFAULT/'raw_archive')
    p = subs.add_parser('index'); p.add_argument('inputs', nargs='+', type=Path)
    p.add_argument('--out', type=Path, default=DEFAULT)
    p = subs.add_parser('search'); p.add_argument('query')
    p.add_argument('--db', type=Path, default=DEFAULT/'index.sqlite3')
    p.add_argument('--out', type=Path); p.add_argument('--limit', type=int, default=80)
    p.add_argument('--context', type=int, default=2)
    p = subs.add_parser('topics'); p.add_argument('--db', type=Path, default=DEFAULT/'index.sqlite3')
    p.add_argument('--out', type=Path, default=DEFAULT/'topic_searches')
    p.add_argument('--limit', type=int, default=80)
    a = parser.parse_args()
    if a.command == 'extract':
        result = extract_archive(a.archive, a.out)
        path = a.out.parent/'archive_inventory.json'
    elif a.command == 'index':
        result = index(a.inputs, a.out)
        print(json.dumps({k: result[k] for k in ('input_html_files', 'distinct_file_hashes',
                                               'distinct_messages', 'errors')}, indent=2))
        return
    elif a.command == 'search':
        result = search(a.db, a.query, a.limit, a.context)
        path = a.out
    else:
        a.out.mkdir(parents=True, exist_ok=True)
        for name, pattern in TOPICS.items():
            result = search(a.db, pattern, a.limit)
            (a.out/f'{name}.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
            print(name, result['total_matching_messages'], flush=True)
        return
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        print(path)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
