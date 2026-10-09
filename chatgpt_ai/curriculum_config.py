"""Scenario sampling with no simulator imports."""
import random

DISTRIBUTIONS = {
    "smoke":        (("kickoff", 1.0),),
    "fundamentals": (("kickoff", .50), ("ground", .35), ("defense", .15)),
    "grounded":     (("kickoff", .10), ("ground", .65), ("defense", .25)),
    "balanced":     (("kickoff", .25), ("ground", .30), ("defense", .20), ("aerial", .15), ("wall", .10)),
    "mechanics":    (("kickoff", .15), ("ground", .15), ("defense", .10), ("aerial", .35), ("wall", .25)),
    "competitive":  (("kickoff", .30), ("ground", .25), ("defense", .20), ("aerial", .15), ("wall", .10)),
}


def choose_scenario(preset: str, rng=random) -> str:
    weights = DISTRIBUTIONS[preset]
    return rng.choices([x[0] for x in weights], weights=[x[1] for x in weights], k=1)[0]
