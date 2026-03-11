import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routers import health, upload, status
from services.job_store import JobStore
from services.rate_limiter import RateLimiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: begin cleanup loop
    async def _cleanup():
        while True:
            app.state.job_store.cleanup()
            await asyncio.sleep(60)

    task = asyncio.create_task(_cleanup())
    yield
    task.cancel()


app = FastAPI(title="Watermark Remover API", lifespan=lifespan)

frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.job_store = JobStore()
app.state.upload_limiter = RateLimiter(max_requests=10, window_seconds=60)
app.state.poll_limiter = RateLimiter(max_requests=60, window_seconds=60)


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception):
    """Ensure all errors follow spec's {error, detail} format."""
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "detail": str(exc)},
    )


app.include_router(health.router)
app.include_router(upload.router)
app.include_router(status.router)
