# Chronos model and adapter attribution

The actor is Chronos V2.1 by KingJake, from the public repository:
https://github.com/KingJake3113/Chronos/tree/4f8fdd27e4802d977b33b9ade4759ff6aeaca5aa

`SHARED_HEAD.lt` and `POLICY.lt` are the actual public inference archives at that
revision. Their SHA256s and source pins are in `chronos_manifest.json`. The port
reconstructs the published C++ Sequential configuration without retraining,
distillation, pruning or weight quantization. Values remain float32; Luau
accumulates arithmetic in its normal numeric representation.

The model configuration and observation/action conventions were read from
`src/RLBotMain.cpp`, `inc/GigaLearnCPP/Models.h`,
`inc/RLGymCPP/ObsBuilders/AdvancedObsPadded.cpp`,
`inc/RLGymCPP/GameStates/StateUtil.cpp`, and
`inc/RLGymCPP/ActionParsers/DefaultAction.cpp` in that revision.

The pinned Chronos repository has no separate top-level LICENSE. It is listed as
a submodule of the official RLBot v5 botpack, whose README specifies MIT as the
default for submodules without an individual license:
https://github.com/RLBot/botpack/blob/master/README.md#licensing

The Roblox adapter is derived from the supplied botrblx local v6.8 implementation
at `DMDIASSS/Chat_GPT_AI@37ff8491df5d3075e4b6213812efd4cc788d30e7`, including its
rendered pose readers, decoder, keyboard mapping, UI and calibration/safety code.
That supplied adaptation states CC BY-NC-SA 4.0. The adapter changes retain those
attribution, noncommercial and share-alike terms; the complete text is retained
in `NEXTO_LICENSE.txt`. This notice does not relicense the separate upstream
Chronos model. No Nexto actor weights are embedded in TurboBall_Chronos.lua.

Adaptation work: a Chronos-specific 225-value observation builder, reflection,
action mask, Sequential inference and verified public weight exporter; observed
pad transition timing; and shared adapter integration. See the validation and
comparison reports for test scope and limitations.
