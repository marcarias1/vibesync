from app.scheduler import REFRESH_JOB_ID, build_scheduler


def test_scheduler_registers_refresh_job():
    sched = build_scheduler(interval_hours=6)
    job = sched.get_job(REFRESH_JOB_ID)
    assert job is not None
    # el trigger es de intervalo (no arrancamos el scheduler en el test)
    assert "interval" in str(job.trigger).lower()
