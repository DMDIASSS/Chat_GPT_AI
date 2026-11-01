import json
from pathlib import Path

import pytest

import slater_discord_research as research


def exported_message(mid, text, timestamp='Monday, October 12, 2026 3:00 PM'):
    return f'''<div class=chatlog__message-container data-message-id={mid}>
      <div class=chatlog__message><span class=chatlog__author data-user-id=123>PRIVATE_AUTHOR</span>
      <span class=chatlog__timestamp title="{timestamp}">3:00 PM</span>
      <div class=chatlog__reply><div class=chatlog__reply-content>QUOTED_REPLY</div></div>
      <div class="chatlog__content chatlog__markdown">{text}</div></div></div>'''


def test_parser_preserves_content_and_links_without_authors_or_quoted_replies():
    rows = []
    parser = research.MessageParser(rows.append)
    raw = '<style>HIDDEN_STYLE</style><script>HIDDEN_SCRIPT</script>' + exported_message(
        '1234567890123456789', 'Rust &amp; C++<br><a href="https://github.com/org/repo">code</a>')
    # Exercise incremental parsing inside attributes/entities rather than whole-file feed.
    for start in range(0, len(raw), 17):
        parser.feed(raw[start:start+17])
    parser.close()
    parser.finish()
    assert len(rows) == 1
    assert rows[0]['text'] == 'Rust & C++\ncode'
    assert rows[0]['urls'] == ['https://github.com/org/repo']
    assert rows[0]['timestamp'].startswith('Monday')
    assert 'author' not in rows[0]
    assert 'PRIVATE_AUTHOR' not in json.dumps(rows)
    assert 'QUOTED_REPLY' not in json.dumps(rows)


@pytest.mark.parametrize('name', ['../outside.html', '/outside.html', r'..\outside.html',
                                 r'C:\outside.html', 'x/../../outside.html'])
def test_unsafe_archive_paths_rejected(name):
    with pytest.raises(ValueError):
        research.archive_path(name)


def test_index_deduplicates_hashes_and_overlapping_messages(tmp_path):
    raw = tmp_path/'raw'; raw.mkdir()
    (raw/'a').mkdir(); (raw/'b').mkdir()
    first = raw/'a'/'RLGym - test [42].html'
    first.write_text(exported_message('99', 'first reward') + exported_message('100', 'Rust framework'))
    (raw/'copy.html').write_bytes(first.read_bytes())
    (raw/'b'/'RLGym - test [42].html').write_text(exported_message('100', 'Rust framework') +
                                              exported_message('101', 'https://github.com/test/model'))
    result = research.index([raw], tmp_path/'research')
    assert result['input_html_files'] == 3
    assert result['distinct_file_hashes'] == 2
    assert result['distinct_messages'] == 3
    result = research.search(tmp_path/'research'/'index.sqlite3', r'Rust|github', limit=1)
    assert result['total_matching_messages'] == 2
    assert result['returned'] == 1
    assert result['all_messages_scanned'] == 3
    # Snowflakes must be sorted numerically: 99 then 100, not 100 then 99.
    assert result['matches'][0]['evidence_id'] == '42:100'
    assert result['matches'][0]['context'][0]['evidence_id'] == '42:99'


def test_empty_channel_is_distinguished_from_missing_file(tmp_path):
    empty = tmp_path/'RLGym - restricted [42].html'
    empty.write_text('<html><body>No messages</body></html>')
    result = research.index([empty], tmp_path/'research')
    assert result['distinct_messages'] == 0
    assert result['files'][0]['parsed_messages'] == 0
    assert not result['errors']
    with pytest.raises(FileNotFoundError):
        research.index([tmp_path/'not_uploaded.html'], tmp_path/'missing')
