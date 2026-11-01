# Country AI observations

These notes come from the supplied RoWorld place version 111. They describe the
inspected implementation, not a guarantee about a newer live server. No game
source or assets are included in this project.

## Identity and recruitment

Countries are kind 0, tribes kind 1, humans kind 2. IDs and names do not establish
whether an owner is human. Country AI has randomized aggression, reserve and
spending thresholds; its decisions also depend on difficulty and match age.
Country recruitment uses the same shaped curve, scaled by difficulty. A snapshot
cannot expose the AI's private random draws, grudges or complete planning state.

## Counterattacks

The defensive routine considers a recent incoming attack and requires a valid
shared border. A country with bank `B` can respond to incoming army `A` when
`B >= 1.1*A` and `A >= 0.02*B`. Its conditional response amount is
`B * clamp(1.25*A/B, 0.05, 0.4)`. It can skip a response when an existing
counterattack is already large enough. The bot treats this as a risk estimate,
not a promised future action. This amount was compared with the original
routine over 18 cases and matched.

Country wars are not based only on nearest distance: army ratios, active wars,
traitor flags, grudges, border width, leader status, difficulty and human grace
periods affect selection. Avoiding provocation while outnumbered matters.

## Buildings and proposed bait tactics

Building checks have a two-second minimum gap and require at least 100K gold.
Under eligible threat, a country with a city may try a defense post with a 35%
random check, subject to affordability, placement, a border-dependent cap and a
60-second defense-building gap. Otherwise it may pursue ports, factories,
cities or later SAMs/silos. Crowding can make it upgrade existing structures.

Therefore an attack cannot reliably force a specific construction. Provocation
can instead cause a counterattack, grudge or defense post. An active defense
post multiplies capture cost and slows attacks. Version 1.5 prefers observed
exposed assets rather than repeatedly spending troops to solicit hypothetical
buildings. Construction that has already appeared is ordinary visible state.

Captured buildings can be retained after recalling an attack, but recall is
neither instant nor free: the inspected rules delay it about two seconds and
retain 75% of an enemy-directed army. Neutral expansion recalls retain all
remaining troops. The strategy can bank a capture when the broader risk makes
further fighting unattractive; it can also continue a profitable conquest.

## Alliances

Country AI can betray partners when the balance of power changes, including a
much weaker bordering ally. Human grace and randomized checks modify this.
An allied country is not assumed to be a permanent safe wall. The bot preserves
an additional margin near dominant AI allies and does not attack immediately
after requesting an alliance itself.
