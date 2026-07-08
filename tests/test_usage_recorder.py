from briefing.core.stores.usage import UsageRecorder, EST_CERTIFY_USD_PER_ENTAILMENT


def test_recorder_accumulates_and_snapshots():
    r = UsageRecorder()
    assert r.total() == 0.0
    r.add(0.039)
    r.add(0.016)
    assert round(r.total(), 3) == 0.055


def test_est_certify_constant_is_positive():
    assert EST_CERTIFY_USD_PER_ENTAILMENT > 0
