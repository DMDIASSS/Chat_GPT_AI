# Choose a watch opponent

Keep training paused. Stop the current viewer with Ctrl+C. Merge BOTH folders
from the update (chat_gpt_ai/gigaforge and chat_gpt_ai/novaforge) into the project.
Open 19_WATCH_TRIAL38_VS_ORIGINAL_CHRONOS.bat.

BLUE/car 1: your pinned trained Chronos trial 38, Breakout.
ORANGE: original frozen Chronos, Breakout.

The same camera and saved candidate are used. This changes only the watch matchup;
training settings, checkpoints, champions and evaluation results are preserved.
No native executable or runtime installation is included or required.

Command Prompt in gigaforge:
_RUN.bat run watch --run research02 --family chronos --trial 38 --opponent chronos

Choose --opponent galactus to return to original Galactus. Omitting the option
keeps the previous default of the other family. Match logs name the actual opponent.
