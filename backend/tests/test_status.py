import io


def test_get_job_status(client):
    # Upload a file first
    response = client.post(
        "/api/upload",
        files=[("files", ("test.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png"))],
    )
    job_id = response.json()["jobs"][0]["id"]

    status_resp = client.get(f"/api/status/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["id"] == job_id
    assert data["status"] == "queued"


def test_get_job_status_unknown_returns_404(client):
    response = client.get("/api/status/nonexistent")
    assert response.status_code == 404


def test_get_batch_status(client):
    files = [
        ("files", ("a.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
        ("files", ("b.jpg", io.BytesIO(b"\xff\xd8" + b"\x00" * 100), "image/jpeg")),
    ]
    response = client.post("/api/upload", files=files)
    batch_id = response.json()["batch_id"]

    batch_resp = client.get(f"/api/batch/{batch_id}")
    assert batch_resp.status_code == 200
    data = batch_resp.json()
    assert data["batch_id"] == batch_id
    assert len(data["jobs"]) == 2


def test_get_batch_unknown_returns_404(client):
    response = client.get("/api/batch/nonexistent")
    assert response.status_code == 404
