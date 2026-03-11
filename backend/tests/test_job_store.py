import time
from services.job_store import JobStore

def test_create_batch_returns_batch_id_and_jobs():
    store = JobStore()
    batch_id, jobs = store.create_batch([{"filename": "a.jpg"}, {"filename": "b.pdf"}])
    assert batch_id.startswith("batch_")
    assert len(jobs) == 2
    assert jobs[0]["status"] == "queued"
    assert jobs[1]["filename"] == "b.pdf"

def test_get_job_returns_job():
    store = JobStore()
    batch_id, jobs = store.create_batch([{"filename": "a.jpg"}])
    job = store.get_job(jobs[0]["id"])
    assert job is not None
    assert job["filename"] == "a.jpg"

def test_get_job_unknown_returns_none():
    store = JobStore()
    assert store.get_job("nonexistent") is None

def test_get_batch_returns_all_jobs():
    store = JobStore()
    batch_id, jobs = store.create_batch([{"filename": "a.jpg"}, {"filename": "b.jpg"}])
    batch_jobs = store.get_batch(batch_id)
    assert len(batch_jobs) == 2

def test_get_batch_unknown_returns_none():
    store = JobStore()
    assert store.get_batch("nonexistent") is None

def test_update_job_status():
    store = JobStore()
    _, jobs = store.create_batch([{"filename": "a.jpg"}])
    store.update_job(jobs[0]["id"], status="processing")
    job = store.get_job(jobs[0]["id"])
    assert job["status"] == "processing"

def test_update_job_with_result():
    store = JobStore()
    _, jobs = store.create_batch([{"filename": "a.jpg"}])
    store.update_job(jobs[0]["id"], status="done", watermark_detected=True)
    job = store.get_job(jobs[0]["id"])
    assert job["status"] == "done"
    assert job["watermark_detected"] is True

def test_cleanup_removes_old_jobs():
    store = JobStore(cleanup_after_seconds=0)
    _, jobs = store.create_batch([{"filename": "a.jpg"}])
    store.update_job(jobs[0]["id"], status="done")
    store.get_job(jobs[0]["id"])
    time.sleep(0.1)
    store.cleanup()
    assert store.get_job(jobs[0]["id"]) is None
