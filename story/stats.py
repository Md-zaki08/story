"""Distribution / z-score / cosine helpers shared by clustering and sampling."""

from __future__ import annotations

import numpy as np


def zscore(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    sd = float(x.std())
    if sd < 1e-12:
        return np.zeros_like(x)
    return (x - float(x.mean())) / sd


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    m = np.asarray(matrix, dtype=np.float64)
    if m.ndim == 1:
        m = m.reshape(1, -1)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms < 1e-12] = 1.0
    return m / norms


def mean_pairwise_cosine(vectors: np.ndarray) -> float:
    v = np.asarray(vectors, dtype=np.float64)
    n = len(v)
    if n < 2:
        return 1.0
    v = normalize_rows(v)
    sims = v @ v.T
    iu = np.triu_indices(n, 1)
    return float(sims[iu].mean())


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if a.size < 2:
        return 0.0
    sa, sb = float(a.std()), float(b.std())
    if sa < 1e-12 or sb < 1e-12:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])
