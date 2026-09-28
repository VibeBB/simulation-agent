from __future__ import annotations

from sim.gates import GateCheck, aggregate


def test_aggregate_is_fail_first_and_empty_is_unknown() -> None:
    passed = GateCheck("pass", "test", "pass", "")
    unknown = GateCheck("unknown", "test", "unknown", "")
    failed = GateCheck("fail", "test", "fail", "")

    assert aggregate([]) == "unknown"
    assert aggregate([passed]) == "pass"
    assert aggregate([passed, unknown]) == "unknown"
    assert aggregate([unknown, failed]) == "fail"
