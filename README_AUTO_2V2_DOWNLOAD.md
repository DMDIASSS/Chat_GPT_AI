# Automatic GC3–SSL ranked 2v2 downloads

Extract this ZIP into **E:\Downloads\Chat_GPT_AI**, then double-click
**DOWNLOAD_2V2_ALL_PAGES.bat** to walk the full search, page by page. Use
**DOWNLOAD_2V2_GC3_SSL.bat** for a batch of up to 1,000 new unique files.
No new Python packages, PyTorch import or setup step
is required. The launcher uses your existing project Python, or `py -3`.
The previous **REPLAY_IL_DOWNLOAD_DUOS.bat** name also starts this downloader.

The program reuses `BALLCHASING_TOKEN` / `BALLCHASING_API_KEY`, or your existing
local token at `data/isolated/native_replay_supply/ballchasing_token.txt`.
If none exists, paste your token into the hidden local prompt and press Enter.
It saves that token in the same ignored local file for later launches. Nothing
appearing while you paste is normal. The ZIP, reports and download state contain
no token. **CONFIGURE_BALLCHASING_TOKEN.bat** replaces a saved token if necessary;
an environment variable takes precedence, so update it too when using one.

Files are saved in **data/replays/ranked-doubles**. The requested source filter is
`https://ballchasing.com/?playlist=11&min-rank=21&max-rank=22`.
The downloader uses API pagination, requesting **200 results per page**. It
probes a narrow `grand-champion-3` API search; if the server rejects those rank
or page-size settings with HTTP 400, it retries smaller pages and then the
documented broad Grand Champion search. The supported choice is saved for resume.
The website was blocked from this cloud environment, so identical HTML-list
membership is not claimed. Each accepted replay must have **two players per team,
all four with reported GC3 or SSL ranks (tiers 21–22)**. Unknown ranks, lower
ranks and other playlists are skipped. This verifies API rank metadata, not
independent player skill. It never substitutes GC1+ files when the strict filter
finds none. API responses are not available for account verification in cloud.

The local hourly budget now counts **180 file download attempts per hour**.
Search pages no longer spend that file budget. All API calls are still spaced
by at least 1.25 seconds. If that local limit or an
API HTTP 429 limit is reached, the window stays open and resumes after cooldown.
It honors `Retry-After` and retries temporary network/service failures with
backoff. Invalid credentials stop immediately. Six consecutive network/service
failures stop the attempt; rerunning retains the pending replay.

Use **PAUSE_2V2_DOWNLOAD.bat** or Ctrl+C to stop. Rerun the same launcher to resume.
**ALL_PAGES** follows the server's next-page links until the search is exhausted;
it does not refresh forever. The 1,000-file batch launcher retains a 1,000-page
budget and can finish short of its target if the search ends or ranks are unknown.
The first run of this upgrade restarts discovery from the top with the new rank
query, preserving pending candidates, existing files and quota history. Later
launches continue the saved cursor. `--refresh-search` explicitly revisits the
newest page after fresh replays have been uploaded.

At startup, a persistent local index scans the output folder and all replay
folders under `data/replays` plus the existing native replay supply downloads.
It skips IDs already present under any of those folders, including renamed files
whose Ballchasing `.source.json` records the ID. It also skips repeated IDs on
the same API page. Identical replay bytes under different IDs are stored once;
an alias is saved so later searches skip that ID without fetching it again.
For a renamed file without ID metadata, the first content comparison needs the
remote bytes; subsequent encounters use the alias. No files are moved or deleted.

The first scan hashes existing files. Later scans reuse hashes when file size and
timestamps are unchanged; edits invalidate the cache. Additional folders can be
included with `--existing "D:\Another replay folder"`. The index is stored in
`.replay_index.json` beside the download state. A recent quota from the previous
version is preserved conservatively through its first upgraded hour.

**STATUS_2V2_DOWNLOAD.bat** displays progress, including the next retry time.
State is in `data/replays/ranked-doubles/.imitation_download.json`; each accepted
file has a rank-provenance/checksum `.source.json` alongside it. Partial downloads
are not published as complete replays. Existing files are preserved.

For a different target or a fresh search, use CMD from your project folder:

```bat
DOWNLOAD_2V2_GC3_SSL.bat --count 3000
DOWNLOAD_2V2_ALL_PAGES.bat --refresh-search
```

Downloading does not start training or change a model. If an imitation dataset
was already finalized before these new replays arrived, prepare a new dataset
and training run to include them; an existing completed dataset stays immutable.

The tests use synthetic metadata and replay bytes to exercise authenticated
requests, all-player filtering, paging, cross-folder/content deduplication,
cached hashes, resume, cooldown, pause and credential redaction.
No account token or actual replay downloads were available in cloud.
