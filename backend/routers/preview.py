import os
import tempfile

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from services.job_store import JobStore

router = APIRouter(prefix="/api")


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def _render_page_preview(pdf_path: str, job_id: str, preview_type: str, page: int) -> str:
    """Render a single page of a PDF as PNG at 150 DPI."""
    preview_dir = os.path.join(tempfile.gettempdir(), f"watermark-{job_id}")
    preview_path = os.path.join(preview_dir, f"preview_{preview_type}_p{page}.png")

    if os.path.exists(preview_path):
        return preview_path

    os.makedirs(preview_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    if page >= len(doc):
        doc.close()
        raise HTTPException(status_code=400, detail=f"Page {page} out of range (0-{len(doc)-1})")

    pix = doc[page].get_pixmap(dpi=150)
    pix.save(preview_path)
    doc.close()
    return preview_path


def _get_page_count(pdf_path: str) -> int:
    """Get the number of pages in a PDF."""
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count


@router.get("/preview/{job_id}")
async def get_preview(
    job_id: str,
    type: str = "processed",
    page: int = 0,
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

    # For PDFs, render requested page as PNG preview
    if path.lower().endswith(".pdf"):
        path = _render_page_preview(path, job_id, type, page)

    return FileResponse(path)


@router.get("/preview/{job_id}/info")
async def get_preview_info(
    job_id: str,
    store: JobStore = Depends(get_job_store),
):
    """Return page count for the processed PDF."""
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not yet processed")

    path = job.get("output_path") or job.get("input_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    page_count = 1
    if path.lower().endswith(".pdf"):
        page_count = _get_page_count(path)

    return JSONResponse({"page_count": page_count})
