# DuelForge watch clarification and read-only diagnostics

This patch adds launchers and diagnostics only. It does not change rewards, models, training or native physics.

Default watch (including 18_WATCH_LEARNING_V2) uses BLUE = latest learned duel02, ORANGE = its frozen random initial policy. Greedy inference of a random policy can keep choosing reverse. This initial opponent is not a trained teacher, nor does it describe the entire training-opponent pool.

The reference initial seed-41011 policy selected action 2, throttle -1, for both colors at all five kickoff starts in the server check. Rotating states 180 degrees and swapping teams gave identical observations, masks and learned-model actions across 1600 player decisions. This supports an initial-policy explanation for the observed reversing; it is not proof of the exact local user's weights or real-client behavior.

Windows: extract into E:\Downloads, merging chat_gpt_ai/duelforge. Run 21_WATCH_TRAINED_VS_TRAINED.bat to watch the exact same latest actor on both teams in varied open play. Run 22_CHECK_SIDE_SYMMETRY.bat to verify your local actor and record side_diagnostic.json inside runs/duel02. Include that file in the normal report ZIP.

Existing CLI, no update required:

```
_RUN.bat watch --run duel02 --opponent self --scene 5 --seconds 120
```

For Colab, copy the patch's tools/ and colab/ files into the existing /content/duelforge project (avoid nesting another chat_gpt_ai folder there). Run `bash colab/22_CHECK_SIDE_SYMMETRY.sh` and `bash colab/21_WATCH_TRAINED_VS_TRAINED.sh`. Headless watch creates an inspect.html recording; it does not open a desktop viewer on Colab.

Two identical policies can still play badly or look mirrored at symmetric kickoffs. Open-play starts avoid using that appearance alone as a correctness test. Missing learned weights fail explicitly; no other bot is substituted.
