import pytest

from app.domain.workrules.legal import LEGAL_LIMITS
from app.domain.workrules.policy import LooserThanLawError, WorkRulePolicy, build_policy


def test_defaults_equal_legal():
    policy = build_policy({}, [], 0)
    assert policy.value("daily_rest") == 720
    assert policy.value("continuous_driving") == 270


def test_stricter_accepted():
    policy = build_policy({"daily_work_max": 570, "daily_rest": 750}, [], 1)
    assert policy.value("daily_work_max") == 570
    assert policy.value("daily_rest") == 750


def test_equal_to_law_accepted():
    assert build_policy({"daily_work_max": 600}, [], 1).value("daily_work_max") == 600


def test_looser_min_rejected():
    with pytest.raises(LooserThanLawError) as exc:
        build_policy({"daily_rest": 719}, [], 1)
    assert exc.value.rule_id == "daily_rest"
    assert exc.value.legal == 720


def test_looser_max_rejected():
    with pytest.raises(LooserThanLawError):
        build_policy({"daily_work_max": 601}, [], 1)


def test_fixed_not_overridable():
    with pytest.raises(LooserThanLawError):
        build_policy({"vehicle_check": 5}, [], 1)


def test_fixed_equal_accepted():
    assert build_policy({"vehicle_check": 10}, [], 1).value("vehicle_check") == 10


def test_unknown_rule_rejected():
    with pytest.raises(KeyError):
        build_policy({"nope": 1}, [], 1)


def test_unknown_warning_rule_rejected():
    with pytest.raises(KeyError):
        build_policy({}, ["nope"], 1)


def test_round_trip():
    policy = build_policy({"daily_rest": 750}, ["shift_rotation"], 3)
    assert WorkRulePolicy.from_dict(policy.to_dict()) == policy


def test_sources_cite_spec():
    assert LEGAL_LIMITS["overtime_year_absolute"].source == "PD 54/1998 Art. 6(3), 6(5)"
    assert LEGAL_LIMITS["vehicle_check"].source == "PD 54/1998 Art. 3(3)-(4)"
    assert LEGAL_LIMITS["eu_route_km"].source == "EU 561/2006 Art. 3(a)"
    assert LEGAL_LIMITS["interruptions_per_week"].source == "PD 54/1998 Art. 2(η), 5(1)"
