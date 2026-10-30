from datetime import date
from app.domain.optimization.contracts import SolverProblem,TripSnapshot,ResourceSnapshot,SolverConfig
from app.domain.optimization.cv_bounded import CVBoundedV1
from app.domain.verification.verifier import verify_schedule


def test_bounded_cv_handles_a_real_one_vehicle_fleet_without_padding_resources():
    problem=SolverProblem('small-fleet','1',date(2026,6,1),
        (TripSnapshot('T1','A','A',480,540,60,allowed_bus_types=('02',)),),
        (ResourceSnapshot('R1','D1','B1','A',bus_type='02'),),(),stations=('A',),transfer_matrix=((0,),))
    result=CVBoundedV1().solve(problem,SolverConfig(seed=42,time_limit_seconds=2,iterations=1))
    assert len(result.assignments)==1
    assert result.assignments[0].resource_id=='R1'
    assert verify_schedule(problem,result.assignments).valid
