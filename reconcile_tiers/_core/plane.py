from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

import numpy as np


class FitFailure(StrEnum):
    TOO_FEW_POINTS = "too_few_points"
    NEAR_VERTICAL = "near_vertical"
    DEGENERATE = "degenerate"


@dataclass(frozen=True, slots=True)
class Plane:
    a: float
    b: float
    c: float
    d: float

    MIN_NY: ClassVar[float] = 0.087

    @classmethod
    def fit(cls, corners: Sequence[Sequence[float]]) -> Plane | FitFailure:
        try:
            pts = np.asarray(corners, dtype=float)
        except (TypeError, ValueError):
            return FitFailure.DEGENERATE
        if pts.ndim != 2 or pts.shape[1] != 3:
            return FitFailure.DEGENERATE
        if pts.shape[0] < 3:
            return FitFailure.TOO_FEW_POINTS

        centroid = pts.mean(axis=0)
        centered = pts - centroid
        if np.linalg.matrix_rank(centered) < 2:
            return FitFailure.DEGENERATE

        _, _, vh = np.linalg.svd(centered, full_matrices=False)
        normal = vh[-1].astype(float)
        norm = float(np.linalg.norm(normal))
        if norm <= 1e-12:
            return FitFailure.DEGENERATE
        normal /= norm
        if normal[1] < 0:
            normal *= -1.0

        a, b, c = (float(v) for v in normal)
        if abs(b) < cls.MIN_NY:
            return FitFailure.NEAR_VERTICAL
        d = float(normal @ centroid)
        return cls(a=a, b=b, c=c, d=d)

    def y_at(self, x: float, z: float) -> float | None:
        if abs(self.b) < self.MIN_NY:
            return None
        return (self.d - self.a * x - self.c * z) / self.b
