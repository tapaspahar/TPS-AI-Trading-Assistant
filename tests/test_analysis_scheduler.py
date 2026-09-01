from threading import Event

from services.analysis_scheduler import AnalysisScheduler


def test_scheduler_skips_duplicate_active_job():
    entered, release, finished = Event(), Event(), Event()
    key = "test-duplicate-job"

    def work():
        entered.set()
        release.wait(2)
        finished.set()

    assert AnalysisScheduler.submit_unique(key, work)
    assert entered.wait(1)
    assert not AnalysisScheduler.submit_unique(key, work)
    release.set()
    assert finished.wait(1)
    metrics = AnalysisScheduler.metrics()[key]
    assert metrics["skipped"] >= 1


def test_stagger_is_stable_and_bounded():
    first = AnalysisScheduler.stagger_ms("expiry-observation", 8_000)
    assert first == AnalysisScheduler.stagger_ms("expiry-observation", 8_000)
    assert 500 <= first < 8_500
