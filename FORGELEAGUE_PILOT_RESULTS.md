# ForgeLeague public-native pilot, 2026-11-06

Decision: neither privileged critic demonstrated a reliable advantage. Ordinary training was retained for both families. Neither fine-tuned candidate passed the champion-promotion rule, so the original deployment parents were preserved.

One training seed, 8,192 decisions per arm, 32,768 training decisions total. Each comparison used 24 timed 60-second candidate games and 24 matched reference games, with both colors against initial Chronos-family, initial Galactus-family and Nexto. Total: 192 simulator games. This used public native weights, not the user's trained Fusion. Wall time was 12.9 minutes on the cloud CPU, not the laptop.

| Comparison | Candidate W/D/L | Reference W/D/L | Paired score-rate change | Approximate 99% interval |
|---|---:|---:|---:|---:|
| chronos: private vs ordinary critic | 15/4/5 | 15/5/4 | -2.1 percentage points | [-25.1, +20.9] |
| galactus: private vs ordinary critic | 11/6/7 | 13/3/8 | -2.1 percentage points | [-38.1, +33.9] |
| chronos: ordinary fine tune vs initialization | 16/4/4 | 13/5/6 | +10.4 percentage points | [-14.9, +35.8] |
| galactus: ordinary fine tune vs initialization | 12/4/8 | 13/3/8 | -2.1 percentage points | [-43.5, +39.4] |

Chronos fine tuning was promising on raw W/D/L, but its interval included a regression. Galactus did not show a gain. No confirmation round was justified, and no stronger champion is claimed. The selected ordinary candidate optimizers remain the starting point for subsequent league blocks; the retained exports stay protected.

This is a small pilot and a test of the decision process, not evidence that long training will improve either bot. Replicate promising changes across training seeds and run the separate 300-second held-out panel before claiming strength. Simulator ports, short matches, omitted goal pauses/overtime, Octane transfer, native demo randomness and live-game input timing limit generalization.

[Machine-readable results](FORGELEAGUE_PILOT_RESULTS.json) · [Full trial/config/provenance report](research/ForgeLeague-public-pilot-report.zip) · [Exact training source reconstructed and verified against every recorded source hash](research/ForgeLeague-public-pilot-source.zip)

The experiment source archive is a research record, not the installer. Use the [complete current source update](NOVAFORGE_DOWNLOAD.md) for the working project and Windows launchers.
