import io
import os
import tempfile

from main import app


def _create_done_job(client, filename="test.png"):
    response = client.post(
        "/api/upload",
        files=[("files", (filename, io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png"))],
    )
    data = response.json()
    job_id = data["jobs"][0]["id"]
    batch_id = data["batch_id"]

    store = app.state.job_store
    job_dir = os.path.join(tempfile.gettempdir(), f"watermark-{job_id}")
    os.makedirs(job_dir, exist_ok=True)
    output_path = os.path.join(job_dir, "output.png")
    with open(output_path, "wb") as f:
        f.write(b"\x89PNG processed content")
    store.update_job(job_id, status="done", output_path=output_path, watermark_detected=True)

    return job_id, batch_id


def test_download_single_file(client):
    job_id, _ = _create_done_job(client)
    resp = client.get(f"/api/download/{job_id}")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert "test.png" in resp.headers.get("content-disposition", "")


def test_download_not_found(client):
    resp = client.get("/api/download/nonexistent")
    assert resp.status_code == 404


def test_download_all_as_zip(client):
    # Create two done jobs in same batch
    files = [
        ("files", ("a.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
        ("files", ("b.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
    ]
    response = client.post("/api/upload", files=files)
    data = response.json()
    batch_id = data["batch_id"]

    store = app.state.job_store
    for job in data["jobs"]:
        job_dir = os.path.join(tempfile.gettempdir(), f"watermark-{job['id']}")
        os.makedirs(job_dir, exist_ok=True)
        output_path = os.path.join(job_dir, "output.png")
        with open(output_path, "wb") as f:
            f.write(b"\x89PNG processed")
        store.update_job(job["id"], status="done", output_path=output_path, watermark_detected=True)

    resp = client.get(f"/api/download-all/{batch_id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"


def test_download_all_skips_errored_jobs(client):
    files = [
        ("files", ("a.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
        ("files", ("b.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
    ]
    response = client.post("/api/upload", files=files)
    data = response.json()
    batch_id = data["batch_id"]

    store = app.state.job_store
    # First job succeeds
    job0 = data["jobs"][0]
    job_dir = os.path.join(tempfile.gettempdir(), f"watermark-{job0['id']}")
    os.makedirs(job_dir, exist_ok=True)
    output_path = os.path.join(job_dir, "output.png")
    with open(output_path, "wb") as f:
        f.write(b"\x89PNG processed")
    store.update_job(job0["id"], status="done", output_path=output_path, watermark_detected=True)

    # Second job errors
    store.update_job(data["jobs"][1]["id"], status="error", error="Processing failed")

    resp = client.get(f"/api/download-all/{batch_id}")
    assert resp.status_code == 200  # Still returns zip with successful file


def test_download_all_no_success_returns_404(client):
    response = client.post(
        "/api/upload",
        files=[("files", ("a.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png"))],
    )
    data = response.json()
    batch_id = data["batch_id"]
    store = app.state.job_store
    store.update_job(data["jobs"][0]["id"], status="error", error="fail")

    resp = client.get(f"/api/download-all/{batch_id}")
    assert resp.status_code == 404
