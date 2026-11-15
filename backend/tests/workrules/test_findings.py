from datetime import date

from app.domain.workrules.findings import WorkRuleFinding, caused_by


def made(rule_id, measured, limit):
    return WorkRuleFinding(rule_id, "legal", "d1", date(2026, 6, 2), ("T1",), measured, limit, "law", {}, f"workrules.{rule_id}")


def test_shorter_rest_is_worse():
    assert caused_by([made("WR_DAILY_REST", 500, 600)], [made("WR_DAILY_REST", 550, 600)])
    assert not caused_by([made("WR_DAILY_REST", 550, 600)], [made("WR_DAILY_REST", 500, 600)])
    assert caused_by([made("WR_WEEKLY_REST_BASE", 2000, 2880)], [made("WR_WEEKLY_REST_BASE", 2500, 2880)])
    assert not caused_by([made("WR_WEEKLY_REST_BASE", 2500, 2880)], [made("WR_WEEKLY_REST_BASE", 2000, 2880)])


def test_more_work_is_worse():
    assert caused_by([made("WR_DAILY_WORK", 650, 600)], [made("WR_DAILY_WORK", 620, 600)])
    assert not caused_by([made("WR_DAILY_WORK", 620, 600)], [made("WR_DAILY_WORK", 650, 600)])


def measure(kind, measured, limit):
    return WorkRuleFinding(
        "WR_INTERRUPTIONS", "legal", "d1", date(2026, 6, 2), ("T1",), measured, limit, "law", {"measure": kind}, "workrules.WR_INTERRUPTIONS"
    )


def test_same_day_measures_compared_separately():
    before = [measure("count", 4, 3), measure("minutes", 500, 240)]
    worse_count = [measure("count", 5, 3), measure("minutes", 500, 240)]
    assert [f.hint["measure"] for f in caused_by(worse_count, before)] == ["count"]
    same = [measure("count", 4, 3), measure("minutes", 500, 240)]
    assert not caused_by(same, list(reversed(before)))


def rest(trip, measured):
    return WorkRuleFinding("WR_DAILY_REST", "legal", "d1", date(2026, 6, 2), (trip,), measured, 720, "law", {}, "workrules.WR_DAILY_REST")


def test_two_duties_on_one_day_compared_by_their_own_trips():
    before = [rest("morning", 500), rest("evening", 630)]
    assert not caused_by(before, before)
    assert [f.trip_ids for f in caused_by([rest("morning", 480), rest("evening", 630)], before)] == [("morning",)]
