"""
Solver Version Registry.
Controls which solver implementations are allowed in production workflows.
Guarantees that standalone research/benchmark algorithms cannot be invoked as production engines.
"""

from __future__ import annotations
from typing import Dict, List, Type

from app.domain.optimization.contracts import SchedulingSolver
from app.domain.optimization.cv_legacy import CVLegacyV0


class InvalidSolverSelectionError(ValueError):
    """Raised when an unapproved, unknown, or research-only solver version is requested."""
    pass


# Production allowlist mapping version ID -> Solver class
_PRODUCTION_SOLVERS: Dict[str, Type[SchedulingSolver]] = {
    "cv-legacy-v0": CVLegacyV0,
}

ALLOWED_PRODUCTION_SOLVERS = {"cv-bounded-v1", "cv-legacy-v0"}


def register_solver(version: str, solver_cls: Type[SchedulingSolver]) -> None:
    """Registers a solver implementation in the production allowlist."""
    _PRODUCTION_SOLVERS[version] = solver_cls


def list_available_solvers() -> List[str]:
    """Returns all currently approved production solver versions."""
    return sorted(list(_PRODUCTION_SOLVERS.keys()))


def get_production_solver(version: str = "cv-bounded-v1") -> SchedulingSolver:
    """
    Returns an instance of the requested approved production solver.
    Raises InvalidSolverSelectionError if the solver is unknown or research-only.
    """
    if version in ("greedy", "simulated_annealing", "lahc"):
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
