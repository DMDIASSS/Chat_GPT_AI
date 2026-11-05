# NovaForge v1.8.0 and TriadBot v1.1 downloads

[Download NovaForge v1.8.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/NovaForge-v1.8.0.zip)

[Download TriadBot v1.1.0](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/TriadBot-v1.1.0.zip)

Extract into the parent of chat_gpt_ai, copying contents over the existing novaforge and triadbot folders and replacing source files. Keep environments, assets and runs. Stop running training/viewers before updating. Existing Chronos weights and numbered launchers are preserved.

TriadBot's reported v5 startup issue was a missing INSTALL step, confirmed by the user. New local exports need no second installation: their primary TOML uses the existing Python environment. Portable exports still use INSTALL.bat and bot.portable.bot.toml. Startup.log and DIAGNOSE.bat provide startup diagnostics. Generated exports specify fixed Breakout/Octane loadouts.

[Triad selector, hitboxes and export instructions](NovaForge/TRIAD_SELECTOR_v1.1.md) · [TriadBot launchers](TriadBot/README.md)

The new Opti-inspired 1v1 PPO selector chooses among frozen Chronos, GalactusV2 and Ripple v1.1, committing for eight decisions (~0.53 seconds). It trains only the selector and preserves each expert's native control values. No Opti code or pretrained selector is bundled. Ripple queue/common timing remains an adaptation limit.

Triad launchers: 0 check; 1 random watch; 2 random export; 3 random W/D/L; 4 selector training/resume; 5 latest selector watch; 6 champion selector export; 7 selector W/D/L; 8 pause selector; 9 status. The initial champion routes to Chronos until a candidate passes automatic comparisons and fresh confirmation. Substantial regression stops training. These safeguards do not guarantee stronger play.

Chronos uses Breakout in its pinned loadout. New runs use Breakout; older saved runs without an explicit body preserve Octane. Frozen Chronos opponents use Breakout, and GalactusV2/Ripple opponents use Octane. A live car cannot change its hitbox whenever the chosen controller changes.

[Main training, self-play and both model export formats](NovaForge/FINISH_AND_FUSION.md) · [Validation](NovaForge/VALIDATION.md) · [Attribution](NovaForge/THIRD_PARTY.md)

Source ZIPs contain no weights. Local exports bundle downloaded models and notices; no new license rights over those originals are implied. Native GigaLearn speed and improved live-match strength are not claimed. Published on codex/novaforge-v1; main remains unchanged.
