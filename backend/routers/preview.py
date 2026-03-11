import os
import tempfile

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import FileResponse
from PIL import Image

from services.job_store import JobStore

router = APIRouter(prefix="/api")


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def _render_pdf_preview(pdf_path: str, job_id: str, preview_type: str) -> str:
    """Render all pages of a PDF as a single stacked PNG at 150 DPI."""
    preview_path = os.path.join(
        tempfile.gettempdir(), f"watermark-{job_id}", f"preview_{preview_type}.png"
    )
    if os.path.exists(preview_path):
        return preview_path

    os.makedirs(os.path.dirname(preview_path), exist_ok=True)

    doc = fitz.open(pdf_path)
    page_images = []
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        page_images.append(img)
    doc.close()

    if not page_images:
        raise HTTPException(status_code=400, detail="PDF has no pages")

    # Stack all pages vertically into one image
    total_width = max(img.width for img in page_images)
    total_height = sum(img.height for img in page_images)
    combined = Image.new("RGB", (total_width, total_height), (255, 255, 255))

    y_offset = 0
    for img in page_images:
        combined.paste(img, (0, y_offset))
        y_offset += img.height

    combined.save(preview_path, "PNG")
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

    # For PDFs, render all pages as stacked PNG preview
    if path.lower().endswith(".pdf"):
        path = _render_pdf_preview(path, job_id, type)

    return FileResponse(path)
