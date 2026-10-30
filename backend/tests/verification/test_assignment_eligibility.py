from datetime import date
from app.domain.optimization.contracts import SolverProblem, TripSnapshot, ResourceSnapshot, Assignment
from app.domain.verification.verifier import HardRuleVerifier


def test_rejects_ineligible_bus_and_unknown_resource():
    problem = SolverProblem('P', '1', date(2026,10,30),
        (TripSnapshot('T', 'A', 'B', 0, 60, 60, allowed_bus_types=('02',)),),
        (ResourceSnapshot('R', 'D', 'B', 'A', bus_type='01'),), ())
    for resource, expected in [('R', 'RULE_BUS_ELIGIBILITY'), ('unknown', 'RULE_KNOWN_RESOURCE')]:
        report = HardRuleVerifier().verify(problem, [Assignment(resource, 'T', 0, 60, 'A', 'B')])
        assert not report.valid
        assert expected in [v.rule_id for v in report.violations]
