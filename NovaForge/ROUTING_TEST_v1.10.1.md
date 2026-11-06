# Greedy versus sampled routing pilot

Launcher 25 in sibling triadbot evaluates the saved selector04 latest actor without training or promotion. PPO samples expert choices while training; the deployed gate chooses the largest logit. A policy can change probabilities without ever changing its greedy choice. This test measures whether that distinction matters here; sampling is not assumed to improve play.

1. Pause selector04 with 19 and wait until its training console finishes saving. Stop watch sessions.
2. Run 25_EVALUATE_ROUTING.bat. It prints loading, game starts, running heartbeats, scores and a final report path.
3. Share the selector04_routing_*.zip in triadbot/reports. The ZIP contains results and provenance, no weights or keys.

The default is 40 games: latest greedy, latest sampled, initialization sampled, fixed Chronos and fixed frozen Fusion, each against Chronos/Galactus/Nexto/Ripple with both colors, 30 simulated seconds per game. All use the run's car body and identical initial observations for each seed/color. Three-expert runs omit fixed Fusion, making 32 games.

The sampled conditions draw from the actor's softmax only when the option expires and retain the selected expert for eight decisions. There is no fairness correction, temperature, forced exploration or averaging of controls. Each timed match has an independent NumPy stream, retained across goals and separate from simulator/Torch randomness. Initial/latest sampled conditions share stream seeds, but visit different states and need not select the same expert. Expert counts in each trial distinguish free choices from held control decisions.

This pilot uses seed bank 451000001, separate from existing diagnostics and promotion checks. Native stochastic respawns still prevent bitwise trajectory reproducibility. One stream per match and eight games per condition are exploratory. Repeat promising results with fresh seeds and longer matches before changing deployment. Repeated examination makes a seed bank development data. Results include paired comparisons against fixed Chronos and between routing modes; they do not automatically replace a champion.

For an additional run from the triadbot directory:

```bat
..\novaforge\.venv\Scripts\python.exe -u run.py selector-routing-evaluate --run selector04 --pairs 2 --seconds 60 --routing-seed 471000001
```

Ctrl+C cancels and preserves the previous complete report. Active training is rejected with instructions to pause. Protected checkpoint/config/status hashes are checked before and after. Results have their own routing/latest.json pointer; earlier W/D/L and diagnostic pointers remain available. Watch/export still use the existing greedy gate. This release does not alter training settings, teacher adapters or model weights.

Install NovaForge v1.10.1 and TriadBot v1.3.1 together by copying the ZIP's two folders into the existing Chat_GPT_AI and replacing program files. Preserve .venv, assets, runs and exports; no retraining or dependency reinstall is needed. The source archive does not include your saved models.
