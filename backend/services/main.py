#!/usr/bin/env python3
"""
Run from the backend directory: python -m services.main

Standalone runner for:
- Constructive heuristic solver
- Simulated annealing optimizer (optional)

Examples:
    uv run ./services/main.py // python -m main
    uv run ./services/main.py --sa // python -m main --sa
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.solver import run_constructive_heuristic, build_tasks_from_trips
from services.simulated_annealing import (
    optimize_with_simulated_annealing,
    SAConfig,
    SAWeights,
)
from services.legality_checker import (
    SolverParameters,
    ConstraintsData,
    check_assignment_legality,
)


class Logger:
    """Simple logger for solver output."""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"

    @staticmethod
    def header(msg: str):
        print(f"\n{Logger.BOLD}{Logger.HEADER}{'='*60}{Logger.ENDC}")
        print(f"{Logger.BOLD}{Logger.HEADER}{msg:^60}{Logger.ENDC}")
        print(f"{Logger.BOLD}{Logger.HEADER}{'='*60}{Logger.ENDC}\n")

    @staticmethod
    def section(msg: str):
        print(f"\n{Logger.BOLD}{Logger.BLUE}>>> {msg}{Logger.ENDC}")
        print(f"{Logger.BLUE}{'-'*50}{Logger.ENDC}")

    @staticmethod
    def info(msg: str):
        print(f"{Logger.CYAN}[INFO]{Logger.ENDC} {msg}")

    @staticmethod
    def success(msg: str):
        print(f"{Logger.GREEN}[OK]{Logger.ENDC} {msg}")

    @staticmethod
    def warning(msg: str):
        print(f"{Logger.YELLOW}[WARN]{Logger.ENDC} {msg}")

    @staticmethod
    def error(msg: str):
        print(f"{Logger.RED}[ERROR]{Logger.ENDC} {msg}")

    @staticmethod
    def metric(name: str, value, unit: str = ""):
        print(
            f"  {Logger.CYAN}{name:.<30}{Logger.ENDC} {Logger.BOLD}{value}{Logger.ENDC} {unit}"
        )


def load_data(data_path: str = None) -> dict:
    """Load scheduling data from JSON file."""
    if data_path:
        path = Path(data_path)
    else:
        path = Path(__file__).parent.parent.parent / "data.json"
        if not path.exists():
            path = Path(__file__).parent.parent / "data.json"

    if not path.exists():
        raise FileNotFoundError(f"Data file not found. Tried: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_solver_with_logs(data: dict, verbose: bool = True) -> dict:
    """Run the solver with detailed logging."""

    Logger.header("KTEL BUS SCHEDULING SOLVER")

    Logger.section("Step 1: Loading Parameters")
    params = SolverParameters.from_data(data)
    Logger.metric("Max Duty Time", params.max_duty_minutes, "min")
    Logger.metric("Normal Duty Time", params.normal_duty_minutes, "min")
    Logger.metric("Max Work/Driving Time", params.max_work_minutes, "min")
    Logger.metric("Drive Time Before Break", params.drive_time_to_break, "min")
    Logger.metric("Min Break Duration", params.min_break_time, "min")
    Logger.metric("Transit Time", params.transit_minutes, "min")

    Logger.section("Step 2: Loading Data")
    trips = data.get("trips", [])
    resources = data.get("resources", [])
    constraints = data.get("constraints", {})

    Logger.metric("Total Trips", len(trips))
    Logger.metric("Total Resources (Drivers)", len(resources))
    Logger.metric(
        "Mandatory Sequences (Pairs)", len(constraints.get("mandatorySequences", []))
    )
    Logger.metric(
        "Mandatory Connections (Joints)",
        len(constraints.get("mandatoryConnections", [])),
    )
    Logger.metric(
        "Prohibited Buses", len(constraints.get("prohibited", {}).get("buses", []))
    )
    Logger.metric(
        "Prohibited Drivers", len(constraints.get("prohibited", {}).get("drivers", []))
    )
    Logger.metric("Driver Wishes", len(constraints.get("driverWishes", [])))

    Logger.section("Step 3: Building Tasks (Merging Chains)")
    tasks, total_connections = build_tasks_from_trips(trips, data)

    single_trips = sum(1 for t in tasks if not t["is_sequence"])
    chains = sum(1 for t in tasks if t["is_sequence"])

    Logger.metric("Single Trip Tasks", single_trips)
    Logger.metric("Chain Tasks", chains)
    Logger.metric("Total Tasks", len(tasks))
    Logger.metric("Connections Processed", total_connections)

    if verbose and chains > 0:
        Logger.info("Sample chains:")
        for task in tasks[:3]:
            if task["is_sequence"]:
                chain_ids = [t["id"] for t in task["sub_trips"]]
                print(f"    {task['id']}: {' -> '.join(chain_ids)}")

    Logger.section("Step 4: Running Constructive Heuristic")
    Logger.info("Sorting tasks by start time...")
    Logger.info("Assigning tasks to drivers...")

    start_time = time.time()

    drivers = [
        {"busId": r["busId"], "homeStation": r.get("homeStation", "")}
        for r in resources
    ]
    result = run_constructive_heuristic(trips, drivers, data)

    elapsed = time.time() - start_time

    Logger.section("Step 5: Results")
    metrics = result.get("metrics", {})

    assigned = metrics.get("assigned", 0)
    total = metrics.get("totalTrips", 0)
    pct = (assigned / total * 100) if total > 0 else 0

    if pct == 100:
        Logger.success(f"All trips assigned! ({assigned}/{total})")
    elif pct >= 90:
        Logger.warning(f"Most trips assigned: {assigned}/{total} ({pct:.1f}%)")
    else:
        Logger.error(f"Many trips unassigned: {assigned}/{total} ({pct:.1f}%)")

    Logger.metric("Trips Assigned", f"{assigned}/{total}", f"({pct:.1f}%)")
    Logger.metric("Trips Unassigned", metrics.get("unassigned", 0))
    Logger.metric("Buses Used", metrics.get("busesUsed", 0))
    Logger.metric("Total Idle Time", metrics.get("totalIdleTime", 0), "min")
    Logger.metric("Total Transfer Time", metrics.get("totalTransferTime", 0), "min")
    Logger.metric("Base Mismatch Count", metrics.get("baseMismatchCount", 0))
    Logger.metric("Total Driving Time", metrics.get("totalDrivingTime", 0), "min")
    Logger.metric("Chains Processed", metrics.get("chainsProcessed", 0))
    Logger.metric("Solver Time", f"{elapsed:.3f}", "sec")

    # unassigned trips if any
    unassigned = result.get("unassignedTrips", [])
    if unassigned and verbose:
        Logger.warning(
            f"Unassigned trip IDs: {unassigned[:10]}{'...' if len(unassigned) > 10 else ''}"
        )

    if verbose:
        Logger.section("Step 6: Driver Summary (Top 10 by trips)")
        bus_states = sorted(
            result.get("busStates", []),
            key=lambda x: len(x["assignedTrips"]),
            reverse=True,
        )

        print(f"  {'Driver':<10} {'Bus':<6} {'Trips':<8} {'Driving':<10} {'Idle':<10}")
        print(f"  {'-'*10} {'-'*6} {'-'*8} {'-'*10} {'-'*10}")

        for state in bus_states[:10]:
            driver = state.get("driverId", "?")
            bus = state.get("busId", "?")
            trips_count = len(state.get("assignedTrips", []))
            driving = state.get("totalDrivingTime", 0)
            idle = state.get("totalIdleTime", 0)
            print(f"  {driver:<10} {bus:<6} {trips_count:<8} {driving:<10} {idle:<10}")

    Logger.header("SOLVER COMPLETE")

    return result


def test_legality_check(data: dict):
    """Test legality checker with sample data."""
    Logger.header("LEGALITY CHECKER TEST")

    params = SolverParameters.from_data(data)
    constraints_data = ConstraintsData.from_data(data)

    trips = data.get("trips", [])
    resources = data.get("resources", [])

    if not trips or not resources:
        Logger.error("No trips or resources to test")
        return

    trip = trips[0]
    resource = resources[0]

    Logger.section(
        f"Testing Trip {trip['id']} with Driver {resource.get('driverId', '?')}"
    )
    Logger.info(f"Trip: {trip.get('startStation')} -> {trip.get('endStation')}")
    Logger.info(f"Time: {trip.get('start_time')} - {trip.get('end_time')}")
    Logger.info(f"Driver Home Station: {resource.get('homeStation', '?')}")
    Logger.info(f"Bus Type: {resource.get('busAttributes', {}).get('type', '?')}")

    is_legal, errors = check_assignment_legality(
        trip, resource, [], params, 1, constraints_data
    )

    if is_legal:
        Logger.success("Assignment is LEGAL")
    else:
        Logger.error("Assignment is ILLEGAL")
        for err in errors:
            Logger.warning(f"  - {err}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="KTEL Bus Scheduling Solver - Standalone",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m services.main                    # Run solver with default data.json
  python -m services.main -d custom.json     # Use custom data file
  python -m services.main --test-legality    # Test legality checker
  python -m services.main -q                 # Quiet mode (less output)
  python -m services.main --sa               # Simulated Annealing
  python -m services.main --output result.json  # Save result to file
        """,
    )

    parser.add_argument(
        "-d",
        "--data",
        default=None,
        help="Path to data JSON file (default: project root data.json)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Quiet mode (less verbose)"
    )
    parser.add_argument("-o", "--output", help="Save result to JSON file")
    parser.add_argument(
        "--test-legality", action="store_true", help="Run legality checker test"
    )
    parser.add_argument(
        "--metrics-only", action="store_true", help="Only print metrics (for scripts)"
    )

    parser.add_argument(
        "--sa",
        action="store_true",
        help="Run simulated annealing after greedy solver",
    )
    parser.add_argument(
        "--sa-iters",
        type=int,
        default=4000,
        help="Simulated annealing max iterations",
    )
    parser.add_argument(
        "--sa-temp",
        type=float,
        default=50.0,
        help="Simulated annealing starting temperature",
    )
    parser.add_argument(
        "--sa-cooling",
        type=float,
        default=0.99,
        help="Simulated annealing cooling multiplier",
    )

    args = parser.parse_args()

    try:
        data = load_data(args.data)
    except FileNotFoundError as e:
        Logger.error(str(e))
        sys.exit(1)

    if args.test_legality:
        test_legality_check(data)
        return

    if args.metrics_only:
        trips = data.get("trips", [])
        resources = data.get("resources", [])
        drivers = [
            {"busId": r["busId"], "homeStation": r.get("homeStation", "")}
            for r in resources
        ]
        result = run_constructive_heuristic(trips, drivers, data)
        print(json.dumps(result["metrics"], indent=2))
        return

    result = run_solver_with_logs(data, verbose=not args.quiet)

    if args.sa:
        Logger.section("Step 7: Simulated Annealing Optimization")
        sa_cfg = SAConfig(
            max_iters=args.sa_iters, start_temp=args.sa_temp, cooling=args.sa_cooling
        )
        sa_weights = SAWeights(
            fairness_term=1.0,
            overtime_minutes=4.0,
            idle_minutes=1.0,
        )

        params = SolverParameters.from_data(data)
        constraints_data = ConstraintsData.from_data(data)
        sa_result = optimize_with_simulated_annealing(
            full_data=data,
            greedy_result=result,
            params=params,
            constraints_data=constraints_data,
            config=sa_cfg,
            weights=sa_weights,
            verbose=not args.quiet,
        )

        greedy_metrics = result.get("metrics", {})
        sa_metrics = sa_result.get("metrics", {})
        sa_extra = sa_result.get("sa", {})

        Logger.metric("Greedy Idle Time", greedy_metrics.get("totalIdleTime", 0), "min")
        Logger.metric("SA Idle Time", sa_metrics.get("totalIdleTime", 0), "min")
        Logger.metric("SA Best Cost", f"{sa_extra.get('bestCost', 0):.1f}")

        best_m = sa_extra.get("bestMetrics", {})
        Logger.metric("SA Fairness", f"{best_m.get('fairness', 0):.1f}")
        Logger.metric("SA Over 8h", best_m.get("totalOver8h", 0), "min")
        Logger.metric("SA Transfer", best_m.get("totalTransfer", 0), "min")
        Logger.metric("SA Base Mismatch", best_m.get("baseMismatch", 0))
        Logger.metric("SA Unused Buses", best_m.get("unusedBuses", 0))
        Logger.metric("SA Unassigned Trips", best_m.get("unassigned", 0))

        result = sa_result

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        Logger.success(f"Result saved to {args.output}")


if __name__ == "__main__":
    main()
