from testing_agent_perf_worker.worker.lease import ExecutionWindow


def test_late_renewal_cannot_resurrect_expired_lease():
    window = ExecutionWindow.start(60, 5, started_monotonic=100.0)
    assert window.active(now=154.0)
    assert window.renew(60, started_monotonic=90.0, now=160.0) is False
    assert window.lost is True
    assert window.active(now=161.0) is False


def test_renewal_extends_from_request_start():
    window = ExecutionWindow.start(60, 5, started_monotonic=100.0)
    assert window.renew(60, started_monotonic=150.0, now=151.0) is True
    assert window.active(now=204.0)
    assert window.active(now=206.0) is False


def test_stop_blocks_new_work_but_not_lease_liveness():
    window = ExecutionWindow.start(60, 5, started_monotonic=100.0)
    window.stop()
    assert window.active(now=110.0) is False
    assert window.alive(now=110.0) is True
