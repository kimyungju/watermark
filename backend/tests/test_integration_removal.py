"""End-to-end integration tests: upload → process → download pipeline."""

import io
import time

import fitz
from fastapi.testclient import TestClient

from main import app
from services.job_store import JobStore
from services.rate_limiter import RateLimiter


def _make_watermarked_pdf() -> bytes:
    """Create a 3-page PDF with main content and StuDocu-style watermarks."""
    doc = fitz.open()

    for page_num in range(3):
        page = doc.new_page(width=595, height=842)

        # Legitimate academic content
        page.insert_text(
            (72, 100),
            f"Academic content on page {page_num + 1}",
            fontsize=14,
            color=(0, 0, 0),
        )
        page.insert_text(
            (72, 140),
            "This is important study material for the course.",
            fontsize=11,
            color=(0, 0, 0),
        )

        # StuDocu watermark text (light gray, typical watermark style)
        page.insert_text(
            (72, 750),
            "Downloaded by lOMoARcPSD|12345678",
            fontsize=9,
            color=(0.85, 0.85, 0.85),
        )
        page.insert_text(
            (72, 770),
            "This document is available on studocu.com",
            fontsize=9,
            color=(0.85, 0.85, 0.85),
        )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _create_client() -> TestClient:
    """Create a fresh TestClient with clean app state."""
    app.state.job_store = JobStore()
    app.state.upload_limiter = RateLimiter(max_requests=100, window_seconds=60)
    app.state.poll_limiter = RateLimiter(max_requests=100, window_seconds=60)
    return TestClient(app)


def _upload_and_wait(client: TestClient, pdf_bytes: bytes):
    """Upload a PDF and poll until processing completes. Returns (batch_id, job_id, batch_data)."""
    upload_resp = client.post(
        "/api/upload",
        files=[("files", ("test_watermarked.pdf", io.BytesIO(pdf_bytes), "application/pdf"))],
    )
    assert upload_resp.status_code == 200
    upload_data = upload_resp.json()
    batch_id = upload_data["batch_id"]
    job_id = upload_data["jobs"][0]["id"]

    # Poll until done (max 20 iterations * 0.5s = 10s)
    batch_data = None
    for _ in range(20):
        time.sleep(0.5)
        poll_resp = client.get(f"/api/batch/{batch_id}")
        assert poll_resp.status_code == 200
        batch_data = poll_resp.json()
        status = batch_data["jobs"][0]["status"]
        if status in ("done", "error"):
            break

    assert batch_data is not None
    assert batch_data["jobs"][0]["status"] == "done", (
        f"Job did not complete successfully: {batch_data['jobs'][0]}"
    )

    return batch_id, job_id, batch_data


def test_full_pipeline_removes_watermarks():
    """Upload a watermarked PDF, process it, download, and verify watermarks are removed."""
    client = _create_client()
    pdf_bytes = _make_watermarked_pdf()

    batch_id, job_id, batch_data = _upload_and_wait(client, pdf_bytes)

    # Watermark should have been detected
    assert batch_data["jobs"][0]["watermark_detected"] is True

    # Download the processed file
    download_resp = client.get(f"/api/download/{job_id}")
    assert download_resp.status_code == 200

    # Open the downloaded PDF and verify contents
    output_doc = fitz.open(stream=download_resp.content, filetype="pdf")

    assert len(output_doc) == 3, f"Expected 3 pages, got {len(output_doc)}"

    for page_idx in range(3):
        page_text = output_doc[page_idx].get_text()

        # Legitimate content must be preserved
        assert "Academic content" in page_text, (
            f"Page {page_idx}: legitimate text missing. Text: {page_text!r}"
        )

        # Watermark text must be removed
        assert "lOMoARcPSD" not in page_text, (
            f"Page {page_idx}: watermark 'lOMoARcPSD' still present. Text: {page_text!r}"
        )
        assert "studocu" not in page_text.lower(), (
            f"Page {page_idx}: watermark 'studocu' still present. Text: {page_text!r}"
        )

    output_doc.close()


def test_full_pipeline_preview_page_count():
    """Upload a watermarked PDF, process it, and verify preview endpoints work for all pages."""
    client = _create_client()
    pdf_bytes = _make_watermarked_pdf()

    _, job_id, _ = _upload_and_wait(client, pdf_bytes)

    # Check preview info returns correct page count
    info_resp = client.get(f"/api/preview/{job_id}/info")
    assert info_resp.status_code == 200
    info_data = info_resp.json()
    assert info_data["page_count"] == 3

    # Verify original previews for all pages
    for page in range(3):
        resp = client.get(f"/api/preview/{job_id}?type=original&page={page}")
        assert resp.status_code == 200, (
            f"Original preview page {page} failed with status {resp.status_code}"
        )
        assert resp.headers["content-type"] == "image/png"

    # Verify processed previews for all pages
    for page in range(3):
        resp = client.get(f"/api/preview/{job_id}?type=processed&page={page}")
        assert resp.status_code == 200, (
            f"Processed preview page {page} failed with status {resp.status_code}"
        )
        assert resp.headers["content-type"] == "image/png"
