import io
import os
import zipfile

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from services.job_store import JobStore

router = APIRouter(prefix="/api")


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


@router.get("/download/{job_id}")
async def download_file(
    job_id: str,
    store: JobStore = Depends(get_job_store),
):
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not yet processed")

    path = job.get("output_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path,
        filename=job["filename"],
        headers={"Content-Disposition": f'attachment; filename="{job["filename"]}"'},
    )


@router.get("/download-all/{batch_id}")
async def download_all(
    batch_id: str,
    store: JobStore = Depends(get_job_store),
):
    jobs = store.get_batch(batch_id)
    if jobs is None:
        raise HTTPException(status_code=404, detail="Batch not found")

    done_jobs = [
        j for j in jobs
        if j["status"] == "done" and j.get("output_path") and os.path.exists(j["output_path"])
    ]

    if not done_jobs:
        raise HTTPException(status_code=404, detail="No successfully processed files")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for job in done_jobs:
            zf.write(job["output_path"], job["filename"])
    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="watermark-removed.zip"'},
    )
