CHAT GPT AI — BALLCHASING REPLAY DOWNLOADER
===========================================

WHAT THIS DOES
- Searches the Ballchasing API for replay IDs; downloads the existing .replay files.
- Does NOT upload or reupload any replay, and does NOT use browser scraping.
- Keeps a persistent hourly download-attempt budget (default 180/hour) and
  respects API 429 responses. You can press Ctrl+C safely and run it again.
- Requires your own private Ballchasing API token; it is NOT saved to disk.
- Skips replay IDs already downloaded, including after a restart.

BEFORE YOU START
1. Install Python 3.11 and run the original START_HERE.bat once.
2. Sign in with Steam at https://ballchasing.com/upload
3. Generate a Ballchasing API token in the Upload page.
4. Extract THIS ZIP directly into the original Chat_GPT_AI folder,
   alongside START_HERE.bat, train.py, replays_to_dataset.py, and pretrain.py.

EASIEST LAUNCHERS (Double click):
DOWNLOAD_1V1.bat        Attempts exact GC3/SSL ranked duels, 50 files/run.
DOWNLOAD_ALL_MODES.bat  Attempts exact GC3/SSL four modes, 200 files/run.
DOWNLOAD_SAVED_PAGE.bat Downloads exactly the 150 ranked-doubles IDs in the
                        saved HTML page supplied in the conversation.
PRETRAIN_1V1_DATA.bat  Converts saved 1v1 replays into .npz then pretrains.

The script will prompt for your API token; paste it then hit Enter. The prompt
hides the token and the script never prints it. You can alternatively set
BALLCHASING_TOKEN in the SAME command prompt.

COMMAND LINE EXAMPLES (Windows CMD, inside project folder):
  .venv\Scripts\python.exe download_ballchasing.py --playlist ranked-duels --rank gc3-ssl --max-files 50
  .venv\Scripts\python.exe download_ballchasing.py --playlist all --rank gc3-ssl --max-files 200
  .venv\Scripts\python.exe download_ballchasing.py --playlist ranked-duels --rank gc-plus --max-files 100
  .venv\Scripts\python.exe download_ballchasing.py --playlist all --rank gc3-ssl --max-files 0
  .venv\Scripts\python.exe download_ballchasing.py --playlist ranked-duels --rank gc3-ssl --list-only
  .venv\Scripts\python.exe download_ballchasing.py --from-ids saved_page_replay_ids.txt --max-files 150

IMPORTANT ABOUT RANKS
- The WEBSITE uses numeric min-rank=21 and max-rank=22 (GC3 and SSL).
- Its published API docs still only list 'grand-champion' as the top rank,
  while a third-party API library demonstrates SSL querying. This script
  tries min-rank=grand-champion-3 and max-rank=supersonic-legend, but there
  is no guarantee the API accepts those exact strings. It DOES NOT silently
  broaden the filter if the server rejects them: it displays a clear error.
- For a documented but BROADER GC-and-above search, use --rank gc-plus. That
  may include GC1/GC2 and should not be labeled a GC3/SSL-only collection.
- Saved-page manifest IDs are an EXACT snapshot of the 150 matches on the
  supplied page. It does not include page 2, page 3, etc.

RATE LIMITS
- Ballchasing official download endpoint currently limits regular users to
  1 download/sec and 200/hour; some patrons have higher limits.
- We use max 180 *attempts* per rolling hour for safety and 1.25 sec minimum
  delay between requests, retrying 429 with cooldown.
- The script can continue without a file-count limit (--max-files 0), but
  there could be many thousands of matching replays, so this can take days.
- Use --max-files 50 or 200 initially; press Ctrl+C to stop safely.
- If you access API from other programs at the same time, limits also apply.

DOWNLOADED FILES
- 1v1 -> data/replays/ranked-duels/<UUID>.replay
- all modes -> data/replays/all-ranked/<playlist>/<UUID>.replay
- saved snapshot -> data/replays/saved-page/<UUID>.replay
- State files (*.json) are stored alongside the output for safe resumption.
- Replay filenames are UUIDs; existing, nonempty files are skipped.

NEXT: PRETRAINING YOUR CURRENT BOT
- Use DOWNLOAD_1V1.bat, then PRETRAIN_1V1_DATA.bat.
- The current replays_to_dataset.py explicitly only accepts TWO cars (1v1).
  Your supplied 150-page snapshot contains 2v2 matches only; those will not
  generate usable examples with that script.
- Replay input reconstruction is approximate; the resulting policy is not
  guaranteed to perform high-level mechanics or defeat Nexto.
- Dataset conversion can be slow on your i5-10300H. Start with 10-50 replays.
- On successful pretraining, you should have data/bc_policy.pt. Then use
  train.py --fresh --init-policy data/bc_policy.pt for a fresh PPO run.

TROUBLESHOOTING
- 401: invalid or missing token.
- 400 in GC3/SSL mode: API may not support precise rank filter; try broad
  GC+ query, or download an exact collection selected on the WEBSITE.
- 403: access denied. Some replays may be private or restricted.
- 429: API rate limit; let it cool down and resume.
- Do not send your token to anyone or add it to public Git repositories.

References: https://ballchasing.com/doc/api
