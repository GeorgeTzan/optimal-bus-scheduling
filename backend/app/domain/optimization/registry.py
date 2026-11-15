"""
Solver Version Registry.
Controls which solver implementations are allowed in production workflows.
Guarantees that standalone research/benchmark algorithms cannot be invoked as production engines.
"""

from __future__ import annotations
from typing import Dict, List, Type

from app.domain.optimization.contracts import SchedulingSolver
from app.domain.optimization.cv_bounded import CVBoundedV1
from app.domain.optimization.cv_legacy import CVLegacyV0

RESEARCH_SOLVERS = frozenset({"greedy", "simulated_annealing", "lahc"})


class InvalidSolverSelectionError(ValueError):
    """Raised when an unapproved, unknown, or research-only solver version is requested."""
    pass


_PRODUCTION_SOLVERS: Dict[str, Type[SchedulingSolver]] = {
    "cv-legacy-v0": CVLegacyV0,
    "cv-bounded-v1": CVBoundedV1,
}

ALLOWED_PRODUCTION_SOLVERS = frozenset(_PRODUCTION_SOLVERS)


def list_available_solvers() -> List[str]:
    """Returns all currently approved production solver versions."""
    return sorted(list(_PRODUCTION_SOLVERS.keys()))


def get_production_solver(version: str = "cv-bounded-v1") -> SchedulingSolver:
    """
    Returns an instance of the requested approved production solver.
    Raises InvalidSolverSelectionError if the solver is unknown or research-only.
    """
    if version in RESEARCH_SOLVERS:
        raise InvalidSolverSelectionError(
            f"Solver '{version}' is a research/benchmark solver and is prohibited in production routes."
        )

    solver_cls = _PRODUCTION_SOLVERS.get(version)
    if solver_cls is None:
        raise InvalidSolverSelectionError(
            f"Requested solver version '{version}' is not an approved production solver. "
            f"Available: {list_available_solvers()}"
        )

    return solver_cls()
