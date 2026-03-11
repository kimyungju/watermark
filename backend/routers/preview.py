import os
import tempfile

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import FileResponse

from services.job_store import JobStore

router = APIRouter(prefix="/api")


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def _render_pdf_preview(pdf_path: str, job_id: str) -> str:
    """Render first page of PDF as PNG at 150 DPI for preview."""
    preview_path = os.path.join(
        tempfile.gettempdir(), f"watermark-{job_id}", "preview.png"
    )
    if os.path.exists(preview_path):
        return preview_path
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(dpi=150)
    pix.save(preview_path)
    doc.close()
    return preview_path


@router.get("/preview/{job_id}")
async def get_preview(
    job_id: str,
    type: str = "processed",
    store: JobStore = Depends(get_job_store),
):
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not yet processed")

    if type == "original":
        path = job.get("input_path")
    else:
        path = job.get("output_path")

    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    # For PDFs, render first page as PNG preview
    if path.lower().endswith(".pdf"):
        path = _render_pdf_preview(path, job_id)

    return FileResponse(path)
