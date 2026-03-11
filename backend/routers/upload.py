import os
import tempfile

from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from services.job_store import JobStore
from services.rate_limiter import RateLimiter

router = APIRouter(prefix="/api")

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILES_PER_BATCH = 5


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def get_upload_limiter(request: Request) -> RateLimiter:
    return request.app.state.upload_limiter


def validate_file(upload: UploadFile) -> str | None:
    ext = os.path.splitext(upload.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return f"Unsupported file type '{ext}'. Accepted: PNG, JPG, JPEG, PDF"

    upload.file.seek(0, 2)
    size = upload.file.tell()
    upload.file.seek(0)
    if size > MAX_FILE_SIZE:
        return f"File too large ({size // (1024*1024)} MB). Maximum is 10 MB"

    return None


@router.post("/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(default=None),
    store: JobStore = Depends(get_job_store),
    upload_limiter: RateLimiter = Depends(get_upload_limiter),
):
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not upload_limiter.is_allowed(client_ip):
        retry = upload_limiter.retry_after(client_ip)
        return JSONResponse(
            status_code=429,
            content={"error": "RATE_LIMITED", "detail": "Too many uploads. Try again later."},
            headers={"Retry-After": str(retry or 60)},
        )

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Maximum is {MAX_FILES_PER_BATCH} per upload",
        )

    valid_files = []
    errors = []

    for f in files:
        error = validate_file(f)
        if error:
            errors.append({"filename": f.filename, "error": error})
        else:
            valid_files.append(f)

    if not valid_files:
        return {"batch_id": None, "jobs": [], "errors": errors}

    batch_id, jobs = store.create_batch(
        [{"filename": f.filename} for f in valid_files]
    )

    for f, job in zip(valid_files, jobs):
        job_dir = os.path.join(tempfile.gettempdir(), f"watermark-{job['id']}")
        os.makedirs(job_dir, exist_ok=True)
        input_path = os.path.join(job_dir, f.filename)
        with open(input_path, "wb") as out:
            content = await f.read()
            out.write(content)
        store.update_job(job["id"], input_path=input_path)

    # Dispatch processing for each job in background threads
    import threading
    from services.processor import _process_job

    for job in jobs:
        t = threading.Timer(0.1, _process_job, args=(store, job["id"]))
        t.daemon = True
        t.start()

    return {
        "batch_id": batch_id,
        "jobs": [
            {"id": j["id"], "filename": j["filename"], "status": j["status"]}
            for j in jobs
        ],
        "errors": errors,
    }
