# RVQ background search and action playback update

## What the supplied reports established

The recorded stationary episode lasted 146.6 seconds while inference continued
at about 15 decisions per second, issuing almost zero throttle. No runtime error
was recorded. The last search snapshot had one candidate. This is a policy/search
problem, not evidence that the process stopped executing.

The trained codec's validation-fitted jump recall was approximately 95.3%;
greedy policy validation recall was 65.6%. Four actual jump press edges were
recorded in the live report. Value validation MSE was 0.214 versus 0.235 for
constant zero. These numbers identify limitations; none measures playing strength.

Loading the supplied frozen policy reproduced its idle codes at three saved
stationary poses with both all-active and all-inactive boost-pad assumptions.
At two of those poses, four-candidate search preferred a driving chunk over the
idle proposal. Actual pad states, jump timers and angular velocities were absent
from the old trace, so these were approximate physics reconstructions, not exact
game reproductions. At the third snapshot, an imminent goal made all candidates
tie on the terminal outcome; that snapshot cannot demonstrate a recovery gain.

The user's CPU timing varied greatly for the same checkpoint: an earlier
four-candidate median was 39.4 ms; the new one was 112.6 ms, p95 158.8 ms.
Eight and 16 candidates were slower. Power settings, contention and other
environment differences have not been isolated. The existing 64-candidate
real-time target is not met by those measurements.

## Runtime changes

- A single background worker performs search. `get_output()` does not wait for
  an unfinished search result. Physics snapshots are detached before submission.
- Adaptive search cannot shrink below two candidates automatically. An explicit
  configured maximum of one remains a direct-policy diagnostic option.
- The default maximum is four, matching a small laptop budget rather than 16.
- While search is pending, controls advance through the previous learned chunk.
  A synchronous stall could previously skip the middle of a chunk, including a
  jump press. The new scheduler preserves those edges when packets arrive.
- There is never more than one outstanding forecast, and no queue of old jobs.
- Reset, kickoff, inactive-round and demolition transitions invalidate old work.
- Plans more than 32 game ticks old are rejected by default. An exhausted chunk
  gets a fresh greedy-policy fallback rather than holding its final tick forever.
- Training sources, weights, codec thresholds and value-only ranking are unchanged.
  There is no forced jump, throttle, boost, anti-idle penalty or online learning.

The normal planning interval remains eight ticks. If a forecast misses that
interval, the runtime continues the existing chunk up to 32 ticks. A ready plan
starts at its first tick; it was evaluated from an older observed state. This
does not compensate latency or promise 15 searches per second. More detailed
predictive scheduling remains future work. The code fixes a blocking control
path and silent one-candidate degeneration; it does not establish competitive
strength, eliminate own goals or solve policy generalization.

## Install and re-export existing weights

Extract the update into `E:\Downloads\Chat_GPT_AI`, replacing included source.
Preserve `.venv`, all data and old exports. In CMD:

```bat
cd /d "E:\Downloads\Chat_GPT_AI"
REPLAY_RVQ.bat export --name ReplayRVQ01_Async
```

Load `data\rlbot_exports\ReplayRVQ01_Async\bot.cfg` in RLBot v4. Use another new
name if the folder already exists. No training, parsing or checkpoint conversion
is required. Do not copy individual runtime files into an old integrity-checked
export. New exports include all matching files and hashes.

Default `runtime.json` uses `mode: "search"`, `asynchronous: true`, adaptive
2..4 candidates, 32-tick maximum plan age and the existing scripted kickoff.
Set `asynchronous: false` only for a synchronous comparison; `mode: "policy"`
retains the direct-policy comparison. Neither comparison retrains the network.

## Check the result

`RVQ_DIAGNOSTICS_<car_index>.json` now records `asynchronous`, `pending_search`,
`control_update_ms`, `max_control_update_ms`, discarded plans/reasons, policy
fallback decisions, executed chunk offset and frames continuing beyond tick
eight. Worker forecast latency is separate from control-update cost; logging
cost is excluded from `control_update_ms`. Search reports record state age.

Compare old/new exports using the same existing weights. If it still idles or
own-goals, send the new diagnostics after the episode. The model's proposal and
value limitations can remain even when action execution is corrected.
