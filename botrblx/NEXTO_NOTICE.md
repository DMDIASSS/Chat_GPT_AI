# Ready-to-run Nexto adaptation

`TurboBall_Nexto.lua` contains the original public Nexto model from the Nexto
contributors at [Rolv-Arild/Necto](https://github.com/Rolv-Arild/Necto), converted
to numeric Luau inference and adapted to rendered Roblox state and controls.
It is a frozen actor; these changes do not retrain its weights.

Source: https://raw.githubusercontent.com/Rolv-Arild/Necto/master/rlbot-support/Nexto/nexto-model.pt

Source SHA256: `bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa`

The upstream model and this generated adaptation use **CC BY-NC-SA 4.0**:
https://creativecommons.org/licenses/by-nc-sa/4.0/
The complete license is in `NEXTO_LICENSE.txt`. Preserve attribution and the
license when sharing; adapted versions must follow its noncommercial and
share-alike terms. The generated file contains the verified public model, not a
user's private checkpoint. Other projects in this repository are not relicensed.

The adapter supplies six verified nearby boost pads and up to five other cars.
This bounds local inference cost and differs from supplying every Rocket League
pad. It starts with ground assist and scripted teammate yielding OFF, so the
actor chooses its driving actions with kickoff, bounded stuck recovery and the
separate conservative ground goal-safety guard. Goal safety can be toggled while
paused. Applying manual calibration updates goal bounds for the guards and optional
ground planner; it does not retrain the actor.
