#!/usr/bin/env python3
"""
Bus Scheduling Framework - Run and compare solvers.

Usage (from backend/):
    python -m framework.run
    python -m framework.run --no-sa
    python -m framework.run -d custom_data.json
    python -m framework.run -o results.json
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from framework.problem import Problem
from framework.solution import Solution, compare
from framework.greedy_sa_solver import GreedySASolver
from services.simulated_annealing import SAConfig, SAWeights


def main():
    parser = argparse.ArgumentParser(description="Bus Scheduling - Solver Framework")
    parser.add_argument("-d", "--data", default=None, help="Path to data JSON file")
    parser.add_argument(
        "--no-sa", action="store_true", help="Skip Simulated Annealing (Greedy only)"
    )
    parser.add_argument(
        "--iters", type=int, default=200000, help="SA iterations (default: 200000)"
    )
    parser.add_argument("-o", "--output", help="Save results to JSON file")
    args = parser.parse_args()

    if args.data:
        data_path = Path(args.data)
    else:
        data_path = Path(__file__).parent.parent.parent / "data.json"
        if not data_path.exists():
            data_path = Path(__file__).parent.parent / "data.json"

    if not data_path.exists():
        print(f"Error: data file not found at {data_path}")
        sys.exit(1)

    problem = Problem.from_json(str(data_path))
    print(f"\n{problem}")
    print(f"  Chains: {problem.num_chains}")
    print(
        f"  Parameters: max_duty={problem.parameters.max_duty_minutes}min, "
        f"max_work={problem.parameters.max_work_minutes}min"
    )

    solutions = []

    print("\n--- Running Greedy ---")
    greedy = GreedySASolver(use_sa=False)
    greedy_sol = greedy.solve(problem)
    solutions.append(greedy_sol)
    print(f"  {greedy_sol}")

    # if not args.no_sa:
    #     print("\n--- Running Greedy + SA ---")
    #     sa_config = SAConfig(max_iters=args.iters, start_temp=100.0, cooling=0.9999)
    #     sa_solver = GreedySASolver(use_sa=True, sa_config=sa_config)
    #     sa_sol = sa_solver.solve(problem)
    #     solutions.append(sa_sol)
    #     print(f"  {sa_sol}")

    from framework.solver_interface import CustomSolver

    custom_solver = CustomSolver()
    print(f"\n--- Running {custom_solver.name} ---")
    custom_sol = custom_solver.solve(problem)
    solutions.append(custom_sol)
    print(f"  {custom_sol}")
    
    from framework.cv_solver import CustomSolver as CVSolver

    custom_solver = CVSolver()
    print(f"\n--- Running {custom_solver.name} ---")
    custom_sol = custom_solver.solve(problem)
    solutions.append(custom_sol)
    print(f"  {custom_sol}")


    # try:
    #     custom_solver = CustomSolver()
    #     print(f"\n--- Running {custom_solver.name} ---")
    #     custom_sol = custom_solver.solve(problem)
    #     solutions.append(custom_sol)
    #     print(f"  {custom_sol}")
    # except NotImplementedError:
    #     pass
    # except Exception as e:
    #     print(f"\n[Custom Solver Error] {e}")

    print("\n" + compare(solutions))

    if args.output:
        out = {s.solver_name: s.to_dict() for s in solutions}
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
