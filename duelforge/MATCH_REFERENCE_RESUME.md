# Resume match-confirmed trajectory with a preserved reference

The uploaded 2,000-game result is against the frozen 57.17M-step curriculum parent:
917 wins, 1,078 draws, 5 losses; score 72.8%; reported paired 95% interval
71.41–74.19%; goals 1,835–228. It used the exact current 61.22M checkpoint,
1,000 unique seed pairs and 100 simulated seconds per game, with both colors.
This confirms improvement under this DuelForge panel, not tournament strength
or the older GigaForge direct-h2h-v1 protocol. It does not compare to Nexto.

Install: keep training paused, extract into E:\Downloads, merge chat_gpt_ai/duelforge.
If desired, export the tested current actor with 38_EXPORT_CONTACT_CURRICULUM.bat
before training. Then run 33_START_CONTACT_CURRICULUM.bat to continue.

On startup the code verifies the exact current checkpoint/parent hashes against
at least 2,000 recorded matches. It checks paired colors, unique seed pairs,
minimum duration, true goal outcomes, and recomputes the confidence interval from
raw rows rather than trusting the summary. Lower bound must exceed 50%.
Only then does it pin the current full checkpoint (actor, critic, Adam, counters)
and record match_reference.json plus the immutable evaluation proof hash.
If those files change, training stops rather than guessing a replacement.

The saved reference stays fixed during subsequent experiments. No actor or critic
reset, reward change, stage restart, environment reinstall or W&B run reset occurs.
The contact-only trajectory pause becomes a warning when that confirmed reference
exists. Every additional 5M steps, run 200 fresh-seed 100-second games against the
pinned 61.22M reference. If the upper 95% score bound is below 50%, save and pause
persistently. An uncertain comparison continues monitoring. The original parent
regression check also remains active. New candidates never overwrite the reference
or auto-promote themselves. Continuous healthy blocks and the separate W&B uploader
remain as installed in the previous update.

Checkpoints and reports are preserved. The extra match comparison costs evaluation
time and runs in the trainer; W&B upload waits remain confined to the uploader.
Send the combined report with 36 after another 5M additional learner steps.

Validation includes exact-report qualification, reference preservation and tamper
checks, sparse contact-only gates without qualifying evidence, a fixed-reference
regression evaluation test, and the existing native/CLI/learning suite. Actual
large-scale continuation of the uploaded weights runs on the user's PC.
