# Watch trial 38 Chronos versus original Chronos

[Download the watch-opponent update](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/GigaForge-Watch-Opponent-Update.zip)

Stop the current viewer with Ctrl+C. Merge BOTH chat_gpt_ai/gigaforge and chat_gpt_ai/novaforge into your existing folder. Open gigaforge/19_WATCH_TRIAL38_VS_ORIGINAL_CHRONOS.bat.

Blue/car 1 is your pinned trained Chronos trial 38; orange is original frozen Chronos. Both cars use Breakout. Training stays paused, and the camera settings are unchanged.

Command Prompt in gigaforge:
```
_RUN.bat run watch --run research02 --family chronos --trial 38 --opponent chronos
```

Choose --opponent galactus to return to original Galactus. Omitting the option preserves the earlier default opponent. Match logs now explicitly identify the selected original opponent.

[Instructions](GigaForge/WATCH_OPPONENT.md) · [Passed Windows checks](https://github.com/DMDIASSS/Chat_GPT_AI/actions/runs/42403332906)

A real headless Chronos-vs-original-Chronos match verified both Breakout hitboxes, opponent identity and valid actor actions. Test weights came from the public teacher, not the user's private trial 38. No model weights, native executable or runtime changes are included.

ZIP SHA256: `a29a472d94a10fa0ce5f538730611169be3516681dbbbfdf9400b2ba8ef62b56`.
