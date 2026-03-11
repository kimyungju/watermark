import os
import tempfile
import asyncio

import pytest

from services.job_store import JobStore
from services.processor import dispatch_job, _process_job


@pytest.fixture
def store():
    return JobStore()


@pytest.fixture
def image_job(store):
    """Create a job with a real image file."""
    import cv2
    import numpy as np

    batch_id, jobs = store.create_batch([{"filename": "test.png"}])
    job = jobs[0]
    job_dir = os.path.join(tempfile.gettempdir(), f"watermark-{job['id']}")
    os.makedirs(job_dir, exist_ok=True)
    # Create image with simulated watermark
    img = np.ones((200, 300, 3), dtype=np.uint8) * 200
    cv2.putText(img, "SAMPLE", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (180, 180, 180), 3)
    input_path = os.path.join(job_dir, "test.png")
    cv2.imwrite(input_path, img)
    store.update_job(job["id"], input_path=input_path)
    return job["id"]


def test_process_job_sets_done(store, image_job):
    _process_job(store, image_job)
    job = store.get_job(image_job)
    assert job["status"] == "done"
    assert job["output_path"] is not None
    assert os.path.exists(job["output_path"])


def test_process_job_unknown_id_no_error(store):
    _process_job(store, "nonexistent")  # Should not raise


def test_dispatch_job_async(store, image_job):
    asyncio.run(dispatch_job(store, image_job))
    job = store.get_job(image_job)
    assert job["status"] == "done"


def test_process_job_error_sets_error_status(store):
    batch_id, jobs = store.create_batch([{"filename": "bad.png"}])
    job = jobs[0]
    store.update_job(job["id"], input_path="/nonexistent/path.png")
    _process_job(store, job["id"])
    result = store.get_job(job["id"])
    assert result["status"] == "error"
    assert result["error"] is not None
