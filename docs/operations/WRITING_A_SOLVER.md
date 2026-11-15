# Writing a solver

A production solver turns one `SolverProblem` into a `SolverResult`. It never reads the database, and the verifier re-checks everything it returns.

## 1. Implement the protocol

Implement `SchedulingSolver` from `backend/app/domain/optimization/contracts.py`:

```python
class MySolver:
    algorithm_id = "my-solver"
    version = "my-solver-v1"

    def solve(self, problem: SolverProblem, config: SolverConfig, progress: ProgressSink | None = None) -> SolverResult:
        ...
```

- Use `config.seed` for all randomness and stay within `config.time_limit_seconds`.
- Every trip ends up either in `assignments` or in `unassigned_trip_ids`, never in both. If a trip can't be covered legally, leave it unassigned.
- If `problem.availability_enforced` is set, respect each resource's `available_windows`.

## 2. Read the work rules from the problem

The job worker attaches these with `workrules.loader.attach_work_context` before it calls `solve`:

- `problem.work_policy` holds the company policy (`WorkRulePolicy.to_dict()`), or `None` for old snapshots. Rebuild it with `WorkRulePolicy.from_dict`.
- `problem.driver_budgets` holds one `DriverDayBudget.to_dict()` per driver, keyed by `driver_id`. Map it to resources through `ResourceSnapshot.driver_id`. A budget gives:
  - `earliest_start_minutes` / `latest_end_minutes`: the duty window that keeps the 720' daily rest before and after the day.
  - `max_work_minutes`: what is left of the daily, weekly and yearly-overtime limits.
  - `max_long_route_driving_minutes`: what is left of the EU daily, weekly and fortnight driving limits.
  - `forbidden_route_ids`, `forbidden_vehicle_route_ids`, `preferred_route_ids`, plus the driver's overnight, split-shift and return-to-base flags.

  Minutes are counted from the frozen service-day origin, the same origin as the `TripSnapshot` times.
- Each trip carries `route_id`, `urban`, `long_route`, `origin_is_depot` and `destination_is_depot`. Older snapshots fall back to `long_route=True`: a route of unknown length is treated as over 50 km.

## 3. Check candidate duties with `legal_duty`

Before you keep a driver's duty, check it:

```python
from app.domain.workrules.budget import legal_duty
ok, findings = legal_duty(duty, timeline, policy, transfer_minutes)
```

`legal_duty` reports only the legal findings the duty itself causes. Check the budget limits as well. `cv_bounded.legal_assignments` does both: it builds each duty from the problem, checks it against the budget and `legal_duty`, and releases trailing trips (with their chain mates) until the duty passes. Reuse it as a final pass.

## 4. Register it

Add the class to `_PRODUCTION_SOLVERS` in `backend/app/domain/optimization/registry.py`. `ALLOWED_PRODUCTION_SOLVERS` is derived from that dict.

The `framework/` package (greedy, simulated annealing, LAHC) is for research only. Never register those solvers.

## 5. The verifier is the final gate

`HardRuleVerifier` re-verifies every candidate, using the full driver history (`WorkContext`), at every gate: worker candidate, patch, request-approval, approve and publish. A solver that ignores the work rules still can't publish an illegal duty, but its candidates will show as invalid.

Tests to copy: `backend/tests/optimization/test_work_budgets_solver.py`.
