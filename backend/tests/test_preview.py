import io
import os
import tempfile

from main import app


def test_preview_returns_image_for_done_job(client):
    # Upload
    response = client.post(
        "/api/upload",
        files=[("files", ("test.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png"))],
    )
    job_id = response.json()["jobs"][0]["id"]

    # Simulate processing complete — write a fake output file
    store = app.state.job_store
    job = store.get_job(job_id)
    job_dir = os.path.join(tempfile.gettempdir(), f"watermark-{job_id}")
    os.makedirs(job_dir, exist_ok=True)
    output_path = os.path.join(job_dir, "output.png")
    with open(output_path, "wb") as f:
        f.write(b"\x89PNG fake output")
    store.update_job(job_id, status="done", output_path=output_path, watermark_detected=True)

    # Get preview (processed)
    resp = client.get(f"/api/preview/{job_id}")
    assert resp.status_code == 200
    assert b"PNG" in resp.content

    # Get original
    resp_orig = client.get(f"/api/preview/{job_id}?type=original")
    assert resp_orig.status_code == 200


def test_map_to_original_page_no_removals():
    """No pages removed — identity mapping."""
    from routers.preview import _map_to_original_page
    assert _map_to_original_page(0, []) == 0
    assert _map_to_original_page(2, []) == 2
    assert _map_to_original_page(5, []) == 5


def test_map_to_original_page_first_removed():
    """Cover page 0 removed — all indices shift by 1."""
    from routers.preview import _map_to_original_page
    assert _map_to_original_page(0, [0]) == 1
    assert _map_to_original_page(1, [0]) == 2
    assert _map_to_original_page(2, [0]) == 3


def test_map_to_original_page_multiple_removed():
    """Pages 0 and 3 removed (cover + trailing)."""
    from routers.preview import _map_to_original_page
    # Original: [cover, c1, c2, trailing, c3]
    # Processed: [c1, c2, c3]
    assert _map_to_original_page(0, [0, 3]) == 1
    assert _map_to_original_page(1, [0, 3]) == 2
    assert _map_to_original_page(2, [0, 3]) == 4


def test_map_to_original_page_middle_removed():
    """A middle page removed."""
    from routers.preview import _map_to_original_page
    assert _map_to_original_page(0, [1]) == 0
    assert _map_to_original_page(1, [1]) == 2
    assert _map_to_original_page(2, [1]) == 3


def test_preview_not_found(client):
    resp = client.get("/api/preview/nonexistent")
    assert resp.status_code == 404


def test_preview_not_ready(client):
    response = client.post(
        "/api/upload",
        files=[("files", ("test.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png"))],
    )
    job_id = response.json()["jobs"][0]["id"]
    resp = client.get(f"/api/preview/{job_id}")
    assert resp.status_code == 400
