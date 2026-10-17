"""Pairwise preference learning (PRD section 7D).

P(A>B) = sigmoid(w . (x_A - x_B)). On each buyer choice between two candidates, nudge the
weight vector by gradient ascent on that logistic likelihood, with L2 regularization and a hard
cap per weight so a single click can't flip the whole ranking. Sessions with little feedback
default to the buyer's explicitly stated weights (``MultiObjectiveRanker`` already does this by
using ``profile.soft_weights`` when no learned weights are supplied).
"""

from __future__ import annotations

import math

LEARNING_RATE = 0.15
L2_REGULARIZATION = 0.02
WEIGHT_CAP = 1.5
WEIGHT_FLOOR = -0.5


def _sigmoid(x: float) -> float:
    try:
        return 1 / (1 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def update_weights(
    weights: dict[str, float],
    chosen_factors: dict[str, float],
    rejected_factors: dict[str, float],
    learning_rate: float = LEARNING_RATE,
) -> dict[str, float]:
    """Returns a new weights dict; does not mutate the input."""
    all_keys = set(weights) | set(chosen_factors) | set(rejected_factors)
    diff = {k: chosen_factors.get(k, 0.0) - rejected_factors.get(k, 0.0) for k in all_keys}
    w_dot_diff = sum(weights.get(k, 0.0) * diff[k] for k in all_keys)
    p_chosen_wins = _sigmoid(w_dot_diff)
    gradient_scale = 1 - p_chosen_wins  # how "surprised" the model was by this choice

    updated = dict(weights)
    for key in all_keys:
        current = weights.get(key, 0.0)
        gradient = gradient_scale * diff[key] - L2_REGULARIZATION * current
        new_value = current + learning_rate * gradient
        updated[key] = max(WEIGHT_FLOOR, min(WEIGHT_CAP, new_value))
    return updated
