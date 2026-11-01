# All-format replay imitation update

Extract into **E:\Downloads\Chat_GPT_AI**, replacing the included source files.
Preserve `.venv` and all of `data`. This is an update for the existing project.

Your last log completed 287 replay inputs, saving **196,132 accepted samples**,
with 12 rejected files. Training stopped afterwards because the old launcher
required accepted 3v3 samples. It did not erase your chunks.

In CMD:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_IL_FINAL.bat cache
REPLAY_IL_FINAL.bat start --device cuda
```

The cache command checks the completed dataset's shard hashes and prints the
actual saved sample count without starting training. The start command also
verifies the cache, then trains or resumes. A completed dataset prints
`REUSING_COMPLETED_DATASET` and is not parsed again. Missing/corrupted files
produce an error, never an invented cache-success message.

The unchanged paths are:

```text
data\isolated\replay_imitation\dataset_mixed3v3_02\manifest.json
data\isolated\replay_imitation\dataset_mixed3v3_02\shards\*.npz
data\isolated\replay_imitation\runs\replay_mixed3v3_02\
```

The legacy `3v3` names are retained only to preserve your saved work. The final
workflow accepts **1v1, 2v2 and 3v3**, and a valid duels/doubles dataset can train
without any 3v3 matches. Independent validation/test matches are still reserved;
training does not optimize on those matches. Rejected or duplicate matches are
not misrepresented as usable demonstrations. The 12 rejected files remain
excluded; eight need a compatible replay reader for their protocol.

For fresh datasets, every `.replay` subfolder under `data\replays` is searched.
The default no longer selects only 3,000 replay files; the supported limit is
100,000. Existing frozen snapshots keep their original inputs and budgets, so
new downloads cannot invalidate current training. A completed dataset remains
immutable; use a new dataset/run to change its inputs. Chunk sampling still
follows the saved sample budget and reconstruction quality checks.

The optional `--require-3v3` flag restores a strict 3v3 quota. The old
`REPLAY_IL_START_3V3.bat` also remains strict; use `REPLAY_IL_FINAL.bat` here.

Pause from a second CMD and wait for the training window to finish saving:

```bat
REPLAY_IL_FINAL.bat pause
```

Resume with the same start command. When complete or early-stopped:

```bat
REPLAY_IL_FINAL.bat results
REPLAY_IL_FINAL.bat analyze --device cuda
REPLAY_IL_FINAL.bat export --name ReplayAllFormats --scripted-kickoff
```

Load `data\rlbot_exports\ReplayAllFormats\bot.cfg` in RLBot v4. Use a different
export name if that folder already exists. Scripted kickoff assistance is basic
and separate from learned control. The export uses direct policy inference.
See [REPLAY_FINAL_GUIDE.md](REPLAY_FINAL_GUIDE.md) for complete instructions.

The downloader's binary check was also corrected: a binary replay header can
start with `{` or `<` without being JSON/HTML. Actual JSON/HTML error documents
are still rejected, and failed downloads remain pending. Authenticated live
Ballchasing downloading must be verified on your PC.

The fingerprinted parser/trainer code and existing checkpoint protocols are
unchanged. Learning remains purely offline imitation, without RL or self-play.
