"""Geometry utilities with no RLGym dependencies (unit-testable offline)."""
import numpy as np


def safe_unit(v: np.ndarray) -> np.ndarray:
    a = np.asarray(v, dtype=np.float64)
    norm = float(np.linalg.norm(a))
    return a / max(norm, 1e-9)


def facing_matrix(direction: np.ndarray) -> np.ndarray:
    """Rows: forward/right/up (RLGym rotation convention)."""
    d = np.array(direction, dtype=float, copy=True)
    d[2] = 0.
    norm = float(np.linalg.norm(d))
    if norm < 1e-9:
        d = np.array([0., 1., 0.])
    else:
        d /= norm
    right = np.array([-d[1], d[0], 0.])
    return np.stack([d, right, np.array([0., 0., 1.])])
