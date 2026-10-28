# Analysis of the supplied v1.8 match

The bot peaked at 36,195 land cells and finished with 203, no buildings, no
warships, 163,259 home troops and 572,664 gold. `alive=true` means its remnant
survived; this is not a victory. The report does not identify the winner or store
complete opponent gameplay.

## Evidence and changes in v1.9

- **Unproductive distant engagements.** The last 64 orders include repeated human
  landings, including six against the same target between ticks 4129 and 5600,
  interleaved with other wars. Those orders did not establish durable growth:
  land remained around 31,000. This does not prove the raids caused retaliation.
  Human beachheads now require a substantial observed third-party attack, a
  nearby capturable structure and a strong army margin, in addition to existing
  safety checks. Only one transport expedition can be at sea at a time.
- **Defense spending during a losing invasion.** At tick 5866 incoming troops
  were 2,936,746 versus 2,180,888 at home. By tick 6373 land had fallen from
  26,066 to 2,636. Ten defense orders were sent between ticks 5750 and 6312.
  The emergency path called the builder without the normal three-post check.
  The shared builder now limits all paths to three owned posts, including
  construction, and three post purchases per rolling minute. Losing a post
  cannot immediately restart an unlimited replacement loop.
- **Air-defense savings could be interrupted.** The final report has seven
  hostile silos and zero owned SAMs. It cannot establish which missile caused
  which loss. An uncovered productive core with an existing factory now saves
  for a SAM when hostile silos are ready, rather than repeatedly buying cheaper
  economic upgrades. This applies in quiet conditions; urgent land defense
  retains priority. Saving cannot produce an unaffordable SAM instantly.
- **Recovery deadlock.** From tick 7285 onward the remnant sat at 203 land; it was
  at its troop cap for roughly the final 100 seconds. The core had only 1.1%
  owned coverage but 146 'clearable' samples, many of which can be enemy tiles.
  That prevented the old zero-clearable relocation test from triggering.
  A ruined asset-free core with sustained stalled growth can now enter relocation
  despite those samples or nearby allied territory. Genuine new growth resets
  the stall timer. Routes, neutral destinations and troop reserves still apply;
  a landlocked or surrounded position can have no safe escape.

## What we can learn from other players

The old report is insufficient to copy their gameplay: it contains final leader
banks/land and selected local interactions, not their complete actions. v1.9 adds
public player summaries, ten-second samples of us and up to twelve land leaders,
plus observed attacks, construction changes and missiles. It retains the first
60 samples and the latest 120, and the latest 256 events, with dropped counts.
The observer never requests hidden information or records guessed intentions as
facts. Events can be missed between one-second scans. Building kind keys follow
the source game: 0 city, 1 port, 2 factory, 3 defense, 4 SAM, 5 silo.

The dashboard displays the current decision, bank/capacity, land, income,
incoming troops, core risk, savings goal and measured decision time. Reports
include blocked-order counts/reason, last waiting reason and runtime errors.
Save match report writes a latest file and an archive in the executor workspace.
There is no automatic upload.

## Learning versus rules

This release fixes observed policy errors and adds evidence collection; it does
not contain a trained neural network or online weight updates. A useful learning
experiment needs recorded states, actual legal actions and repeatable evaluation.
These coarse reports alone are not an imitation dataset. A reasonable next
experiment is simulation-based tuning of strategic choices against several
opponent styles, with fixed unseen maps/seeds and delayed decisions matching the
live runtime. Only keep changes that improve that evaluation, then validate in
live matches. Offline survival against built-in country AI does not establish
human win rate or guarantee an unbeatable bot.

Verification: 139 offline behavior scenarios, dashboard/report export lifecycle,
and standalone Luau compilation passed. A three-minute engineering world using
the supplied original simulator survived with 4,005 land, 1,266,372 troops and
four buildings. This matches the earlier smoke result; it is not evidence of a
competitive improvement. Live strength of v1.9 remains unverified.
