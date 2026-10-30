"""Different crew-pair IDs cannot hide a simultaneous duty for one driver or bus."""
from datetime import date
import pytest
from app.domain.optimization.contracts import Assignment,ResourceSnapshot,SolverProblem,TripSnapshot
from app.domain.verification.verifier import HardRuleVerifier


def verify(driver2='D2',bus2='B2',start2=30,driver1='D1',bus1='B1'):
    trips=(TripSnapshot('T1','A','A',0,60,60),TripSnapshot('T2','A','A',start2,start2+60,60))
    resources=(ResourceSnapshot('PAIR1',driver1,bus1,'A'),ResourceSnapshot('PAIR2',driver2,bus2,'A'))
    problem=SolverProblem('P','1',date(2026,6,1),trips,resources,())
    assignments=[Assignment('PAIR1','T1',0,60,'A','A'),Assignment('PAIR2','T2',start2,start2+60,'A','A')]
    return HardRuleVerifier().verify(problem,assignments)

@pytest.mark.parametrize('driver,bus,rule',[('D1','B2','RULE_DRIVER_OVERLAP'),('D2','B1','RULE_VEHICLE_OVERLAP')])
def test_distinct_pairs_sharing_underlying_identity_reject_overlap(driver,bus,rule):
    report=verify(driver,bus)
    finding=next(v for v in report.violations if v.rule_id==rule)
    assert not report.valid and {'T1','T2'}<=set(finding.entity_ids)

@pytest.mark.parametrize('driver,bus,start',[('D2','B2',30),('D1','B2',60),('D2','B1',61)])
def test_unrelated_or_non_overlapping_assignments_do_not_create_identity_overlap(driver,bus,start):
    assert not {'RULE_DRIVER_OVERLAP','RULE_VEHICLE_OVERLAP'} & {v.rule_id for v in verify(driver,bus,start).violations}

@pytest.mark.parametrize('driver,bus',[(None,'B1'),('D1',None),('','B1'),('D1','')])
def test_missing_underlying_identity_is_reported(driver,bus):
    report=verify(driver1=driver,bus1=bus)
    assert not report.valid and 'RULE_RESOURCE_IDENTITY' in {v.rule_id for v in report.violations}


def test_same_vehicle_across_pairs_requires_verified_travel_time():
    trips=(TripSnapshot('T1','A','B',0,60,60),TripSnapshot('T2','C','D',70,120,50))
    resources=(ResourceSnapshot('P1','D1','BUS','A'),ResourceSnapshot('P2','D2','BUS','C'))
    assignments=[Assignment('P1','T1',0,60,'A','B'),Assignment('P2','T2',70,120,'C','D')]
    problem=SolverProblem('P','1',date(2026,6,1),trips,resources,(),stations=('A','B','C','D'),transfer_matrix=((0,0,0,0),(0,0,30,0),(0,0,0,0),(0,0,0,0)))
    report=HardRuleVerifier().verify(problem,assignments)
    assert not report.valid and 'RULE_VEHICLE_CONTINUITY' in {v.rule_id for v in report.violations}


def test_driver_changing_vehicles_at_different_stations_requires_review():
    trips=(TripSnapshot('T1','A','B',0,60,60),TripSnapshot('T2','C','D',120,180,60))
    resources=(ResourceSnapshot('P1','D1','BUS1','A'),ResourceSnapshot('P2','D1','BUS2','C'))
    assignments=[Assignment('P1','T1',0,60,'A','B'),Assignment('P2','T2',120,180,'C','D')]
    report=HardRuleVerifier().verify(SolverProblem('P','1',date(2026,6,1),trips,resources,()),assignments)
    assert not report.valid and 'RULE_DRIVER_RELOCATION_UNCONFIRMED' in {v.rule_id for v in report.violations}
