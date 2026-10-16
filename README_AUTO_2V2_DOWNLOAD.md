# Automatic GC3–SSL ranked 2v2 downloads

Extract this ZIP into **E:\Downloads\Chat_GPT_AI**, then double-click
**DOWNLOAD_2V2_GC3_SSL.bat**. No new Python packages, PyTorch import or setup step
is required. The launcher uses your existing project Python, or `py -3`.
The previous **REPLAY_IL_DOWNLOAD_DUOS.bat** name also starts this downloader.

The program reuses `BALLCHASING_TOKEN` / `BALLCHASING_API_KEY`, or your existing
local token at `data/isolated/native_replay_supply/ballchasing_token.txt`.
If none exists, paste your token into the hidden local prompt and press Enter.
It saves that token in the same ignored local file for later launches. Nothing
appearing while you paste is normal. The ZIP, reports and download state contain
no token. **CONFIGURE_BALLCHASING_TOKEN.bat** replaces a saved token if necessary;
an environment variable takes precedence, so update it too when using one.

The default target is **up to 1,000 new replays per launch**, saved in
**data/replays/ranked-doubles**. Listing uses the documented broad Grand Champion
API search; each accepted replay must then have **exactly two players per team,
all four with reported GC3 or SSL ranks (tiers 21–22)**. Unknown ranks, lower
ranks and other playlists are skipped. This verifies API rank metadata, not
independent player skill. It never substitutes GC1+ files when the strict filter
finds none. API responses are not available for account verification in cloud.

Both metadata and file requests count toward a conservative **180 API attempts
per hour**. Calls are spaced by at least 1.25 seconds. If that local limit or an
API HTTP 429 limit is reached, the window stays open and resumes after cooldown.
It honors `Retry-After` and retries temporary network/service failures with
backoff. Invalid credentials stop immediately. Six consecutive network/service
failures stop the attempt; rerunning retains the pending replay.

Use **PAUSE_2V2_DOWNLOAD.bat** or Ctrl+C to stop. Double-click START again to
resume saved pagination and skip files already present. The target counts new
files in that launch. A single launch also has a 1,000-page search limit; search
exhaustion, the page limit or unavailable rank metadata can produce fewer files
than the target. It does not loop forever on an exhausted search.

**STATUS_2V2_DOWNLOAD.bat** displays progress, including the next retry time.
State is in `data/replays/ranked-doubles/.imitation_download.json`; each accepted
file has a rank-provenance/checksum `.source.json` alongside it. Partial downloads
are not published as complete replays. Existing files are preserved.

For a different target, use CMD from your project folder:

```bat
DOWNLOAD_2V2_GC3_SSL.bat --count 3000
```

Downloading does not start training or change a model. If an imitation dataset
was already finalized before these new replays arrived, prepare a new dataset
and training run to include them; an existing completed dataset stays immutable.

The tests use synthetic metadata and replay bytes to exercise authenticated
requests, all-player filtering, resume, cooldown, pause and credential redaction.
No account token or actual replay downloads were available in cloud.
