# TriadBot: three frozen experts

This is a second project alongside NovaForge. It keeps original Chronos, Galactus and Ripple loaded, and selects **one teacher per eight-tick decision**. Each car receives one control vector at a time. All three models propose distributions; the chosen model supplies the action, with the common seven-tick planned delay.

Extract into the parent of chat_gpt_ai, merging chat_gpt_ai/triadbot. Update the sibling novaforge to v1.7.0 and keep its installed Python environment.

1. Run **0_CHECK_TRIAD.bat** to fetch/verify the three teachers and exercise actual simulation controls.
2. Run **1_WATCH_TRIAD.bat** to watch against Chronos with the automatic learner camera. Ctrl+C stops viewing.
3. Run **2_EXPORT_TRIAD_V5.bat** to create a portable personal export under triadbot/exports.
4. The exported folder contains all three models, matching source, notices, integrity hashes, INSTALL.bat and bot.bot.toml. Run its INSTALL.bat with Python 3.11 x64, then import bot.bot.toml into RLBot v5 for offline 1v1. The generated ZIP is next to that folder.
5. **3_COMPARE_WDL.bat** compares the random router and original Chronos against all four frozen opponents using timed 60-second matches on both colors; results go to triadbot/reports.

Waiting teachers gain probability. Frequent recent teachers lose probability, and the teacher just used receives a repeat penalty. All probabilities remain positive. The recent window is 60 decisions; logs show selection counts, time waiting and next probabilities. Selection history persists across kickoff resets. There is no training or model-weight update in TriadBot.

This is a three-network runtime bundle, not a single merged .pt/.lt. Chronos/Galactus use a 90-action interface; Ripple's 276 actions are projected onto it and its longer queue is approximated using held controls. Switching can disrupt mechanics. This experimental controller is not claimed to outperform any teacher. Main-project fusion instead distills a separate single network for ordinary .pt/.cfg or .lt/.toml export.

The downloadable source ZIP contains no teacher weights. Generated exports contain the user's locally downloaded originals and their notices; no new license grant for those originals is implied.
