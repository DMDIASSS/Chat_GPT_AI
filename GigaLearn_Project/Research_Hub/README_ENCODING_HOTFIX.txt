GigaLearn Research Hub — Encoding Startup Hotfix v1

Fix: hub_core.py used an invalid Python codec spelling, utf8-sig,
when checking the patched GigaLearn C++ sources before a run.
Replaced with the valid spelling utf-8-sig.

INSTALL
1. Close Research Hub. Ensure no Research Hub C++ training process is running.
2. Extract this ZIP into E:\Downloads\Chat_GPT_AI.
3. Allow replacement of GigaLearn_Project\Research_Hub\hub_core.py
   and tests\test_research_hub.py.
4. Reopen Research Hub; select the already-created experiment smoke_balanced_01.
5. Click Start selected -> Yes. Do not click Create experiment again.
6. Confirm PPO steps change in the C++ training log. To finish, click Request safe save + stop.

This hotfix does NOT require rebuilding C++, and contains no checkpoint, policy, dataset or C++ modifications.
Python tests: 12 passed locally including an added regression test.
If a new error appears, send screenshot or Research_Hub\experiments\smoke_balanced_01\reports\training.log.
