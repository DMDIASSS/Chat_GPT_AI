Native RLBot v4 export

Extract this update into the project root. Restart only AFK Improved to see the new Native folder button; training can continue. No C++ rebuild required.

AFK Improved > RLBot export > Native folder: select the numbered checkpoint directory containing POLICY.lt, SHARED_HEAD.lt, CRITIC.lt and RUNNING_STATS.json. Keep Scripted Nexto kickoff checked to export the scripted version. Uncheck it and choose a different export name to export policy-only kickoff. A POLICY.lt path also works in the checkpoint entry.

For ranked_duels_train01/checkpoints/3711232, double-click NATIVE_EXPORT_RANKED3711232.bat to create both variants under data/rlbot_exports. Add each bot.cfg to RLBot v4. Existing export names are never overwritten; delete/move an old export or use a new name in the UI.

The learned version disables the external kickoff script; it does not imply the policy has mastered kickoff. All archive weights are copied unchanged. Standard Soccar 1v1/2v2/3v3 only, 120 FPS recommended. The portable package requires RLBot v4, NumPy and Torch; GigaLearn and CUDA are not required for inference.

Packet adaptation is approximate: Rocket League packets do not expose RocketSim contact normals or all internal jump timers. Timers are inferred, wheel contact cannot distinguish floor from wall, and low-rate packets cannot reproduce missed physics ticks. Offline exported-package inference and both kickoff settings were checked with native weights and packet fixtures; live Rocket League behavior parity has not been verified.

Validation: 12 export/addon tests passed, including actual native archive inference, both kickoff settings, unchanged source/copied weights, and refusal to overwrite exports.

Control scheduling fix: native actions now use the same one-old/seven-new cadence as the evaluator; Nexto's clock overrides only actual scripted kickoff frames. To update existing native exports, stop those bots in RLBot, double-click NATIVE_REFRESH_RLBOT_EXPORTS.bat, then reload them. Weight files and each export's kickoff setting are preserved; the previous bot.py is backed up. Training can continue. NATIVE_OUTPUT logs every five game seconds show the selected policy action, pending controls, sent controls and whether a kickoff script is applied. If both policy_controls and sent_controls stay zero after kickoff, the policy is choosing idle actions; the wrapper deliberately does not replace them with forced throttle.
