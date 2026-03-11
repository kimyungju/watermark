from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse

from services.job_store import JobStore
from services.rate_limiter import RateLimiter

router = APIRouter(prefix="/api")


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def get_poll_limiter(request: Request) -> RateLimiter:
    return request.app.state.poll_limiter


def _job_to_response(job: dict) -> dict:
    resp = {
        "id": job["id"],
        "filename": job["filename"],
        "status": job["status"],
    }
    if job["status"] == "done":
        resp["watermark_detected"] = job.get("watermark_detected", True)
        resp["preview_url"] = f"/api/preview/{job['id']}"
        resp["original_url"] = f"/api/preview/{job['id']}?type=original"
    if job["status"] == "error":
        resp["error"] = job.get("error", "Processing failed")
    return resp


def _check_rate_limit(request: Request, limiter: RateLimiter):
    client_ip = request.client.host if request.client else "unknown"
    if not limiter.is_allowed(client_ip):
        retry = limiter.retry_after(client_ip)
        return JSONResponse(
            status_code=429,
            content={"error": "RATE_LIMITED", "detail": "Too many requests. Try again later."},
            headers={"Retry-After": str(retry or 60)},
        )
    return None


@router.get("/status/{job_id}")
async def get_job_status(
    job_id: str,
    request: Request,
    store: JobStore = Depends(get_job_store),
    poll_limiter: RateLimiter = Depends(get_poll_limiter),
):
    rate_resp = _check_rate_limit(request, poll_limiter)
    if rate_resp:
        return rate_resp

    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.get("/batch/{batch_id}")
async def get_batch_status(
    batch_id: str,
    request: Request,
    store: JobStore = Depends(get_job_store),
    poll_limiter: RateLimiter = Depends(get_poll_limiter),
):
    rate_resp = _check_rate_limit(request, poll_limiter)
    if rate_resp:
        return rate_resp

    jobs = store.get_batch(batch_id)
    if jobs is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {
        "batch_id": batch_id,
        "jobs": [_job_to_response(j) for j in jobs],
    }
