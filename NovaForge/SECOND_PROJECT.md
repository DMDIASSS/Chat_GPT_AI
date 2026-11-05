# TriadBot second project

Download the separate TriadBot-v1.0.0.zip from the project's GitHub download page and merge its **chat_gpt_ai/triadbot** folder alongside **chat_gpt_ai/novaforge**. NovaForge v1.7.0 supplies its installed setup runtime.

Run 0_CHECK_TRIAD.bat, then 1_WATCH_TRIAD.bat to watch or 2_EXPORT_TRIAD_V5.bat to create a portable personal runtime package. The exported folder has INSTALL.bat, bot.bot.toml, all three local teacher models, matching code, notices and file hashes. Install it and import the TOML into RLBot v5 for offline 1v1.

One teacher controls each eight-tick decision. Waiting teachers receive higher probability; frequently selected teachers and immediate repeats receive lower probability. Logs show probabilities, ages and selection counts. Selection history survives kickoff resets. The three models stay frozen. This is not a single .pt/.lt neural network and is not claimed to improve playing strength.
