import io


def test_upload_single_image(client):
    file = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    response = client.post(
        "/api/upload",
        files=[("files", ("test.png", file, "image/png"))],
    )
    assert response.status_code == 200
    data = response.json()
    assert "batch_id" in data
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["filename"] == "test.png"
    assert data["jobs"][0]["status"] == "queued"
    assert data["errors"] == []


def test_upload_multiple_files(client):
    files = [
        ("files", ("a.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
        ("files", ("b.jpg", io.BytesIO(b"\xff\xd8" + b"\x00" * 100), "image/jpeg")),
    ]
    response = client.post("/api/upload", files=files)
    assert response.status_code == 200
    assert len(response.json()["jobs"]) == 2


def test_upload_rejects_unsupported_type(client):
    file = io.BytesIO(b"hello world")
    response = client.post(
        "/api/upload",
        files=[("files", ("test.txt", file, "text/plain"))],
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 0
    assert len(data["errors"]) == 1
    assert "Unsupported" in data["errors"][0]["error"]


def test_upload_partial_success(client):
    files = [
        ("files", ("good.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
        ("files", ("bad.txt", io.BytesIO(b"text"), "text/plain")),
    ]
    response = client.post("/api/upload", files=files)
    data = response.json()
    assert len(data["jobs"]) == 1
    assert len(data["errors"]) == 1


def test_upload_no_files_returns_400(client):
    response = client.post("/api/upload")
    assert response.status_code == 400


def test_upload_too_many_files(client):
    files = [
        ("files", (f"f{i}.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png"))
        for i in range(6)
    ]
    response = client.post("/api/upload", files=files)
    assert response.status_code == 400


def test_upload_file_too_large(client):
    # 11 MB file
    big_file = io.BytesIO(b"\x89PNG" + b"\x00" * (11 * 1024 * 1024))
    response = client.post(
        "/api/upload",
        files=[("files", ("big.png", big_file, "image/png"))],
    )
    data = response.json()
    assert len(data["jobs"]) == 0
    assert len(data["errors"]) == 1
    assert "10 MB" in data["errors"][0]["error"]
