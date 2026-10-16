"""Curated-group scope, six-player checks, durable retry and deduplication."""
import json
import uuid
import urllib.parse
import pytest
from download_3v3_group import group_id,listing_url,eligible,download,DEFAULT_GROUP
from download_2v2_gc3_ssl import DownloadError


def meta(rid=None):
    return {'id':rid or str(uuid.uuid4()),'playlist_id':'ranked-standard',
        'blue':{'players':[{'car_name':'Octane'} for _ in range(3)]},
        'orange':{'players':[{'car_name':'Fennec'} for _ in range(3)]}}


def test_group_urls_remain_scoped_and_do_not_accept_external_hosts_or_teams():
    assert group_id('https://ballchasing.com/group/'+DEFAULT_GROUP)==DEFAULT_GROUP
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(listing_url(DEFAULT_GROUP)).query)['group']==[DEFAULT_GROUP]
    for url in ['https://other.example/group/x','https://ballchasing.com/group/../x','https://ballchasing.com/group/x?token=y']:
        with pytest.raises(ValueError):group_id(url)
    for url in ['https://other.example/api/replays','https://ballchasing.com/api/replays?group=another','https://ballchasing.com/api/groups/x']:
        with pytest.raises(ValueError):listing_url(DEFAULT_GROUP,url)
    assert eligible(meta())
    bad=meta();bad['orange']['players'].pop();assert not eligible(bad)
    bad=meta();bad['blue']=None;assert not eligible(bad)


def test_group_acquisition_follows_pages_skips_ids_and_content_and_keeps_provenance(tmp_path):
    a,b,c=meta(),meta(),meta();seen=[]
    def fetch(url,binary=False):
        seen.append((url,binary))
        if binary:return b'replay-binary-A' if a['id'] in url else b'replay-binary-B'
        if 'page=2' in url:return {'list':[a,c],'next':None}
        return {'list':[a,b,dict(meta(),playlist_id='ranked-doubles')],
            'next':'https://ballchasing.com/api/replays?page=2&group='+DEFAULT_GROUP}
    # b and c return identical bytes; keep one copy and remember the alias.
    first=download(folder=tmp_path,fetch=fetch,existing_roots=[],min_interval=0)
    assert first['status']=='COMPLETE' and first['downloaded']==2
    assert first['metadata_rejected']==1 and first['skipped_existing']==2
    assert len(list(tmp_path.glob('*.replay')))==2
    for path in tmp_path.glob('*.source.json'):
        source=json.loads(path.read_text());assert source['group']==DEFAULT_GROUP
        assert source['ranks']==[None]*6 and 'user supplied' in source['octane_hitbox_claim']
    before=len(seen)
    second=download(folder=tmp_path,fetch=fetch,existing_roots=[],min_interval=0)
    assert second['downloaded']==0 and len(seen)==before
    refreshed=download(folder=tmp_path,fetch=fetch,existing_roots=[],min_interval=0,refresh=True)
    assert refreshed['downloaded']==0 and len(list(tmp_path.glob('*.replay')))==2


def test_rate_limit_preserves_pending_replay_and_resumes_without_listing_again(tmp_path):
    item=meta();clock=[1000.]
    def limited(url,binary=False):
        if binary:raise DownloadError('API rate limit',retry_after=60,status=429)
        return {'list':[item],'next':None}
    first=download(folder=tmp_path,fetch=limited,existing_roots=[],min_interval=0,now=lambda:clock[0])
    assert first['status']=='RETRY_LATER' and first['retry_at_unix'] is not None
    def resumed(url,binary=False):
        assert binary
        return b'resumed-binary-replay'
    blocked=download(folder=tmp_path,fetch=resumed,existing_roots=[],min_interval=0,now=lambda:clock[0])
    assert blocked['status']=='RETRY_LATER' and blocked['downloaded']==0
    clock[0]+=61
    second=download(folder=tmp_path,fetch=resumed,existing_roots=[],min_interval=0,now=lambda:clock[0])
    assert second['status']=='COMPLETE' and second['downloaded']==1 and second['pages']==0
