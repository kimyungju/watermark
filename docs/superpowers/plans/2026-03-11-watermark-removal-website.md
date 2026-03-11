# Watermark Removal Website Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public web app that removes watermarks from images and PDFs, with before/after preview and batch download.

**Architecture:** React + Vite frontend (Vercel) communicates via REST API with a FastAPI Python backend (Render). Backend processes images via OpenCV detection + LaMa ONNX inpainting, and PDFs via PyMuPDF detection + pikepdf removal. Async job queue with polling.

**Tech Stack:** React, Vite, Tailwind CSS, FastAPI, PyMuPDF, pikepdf, OpenCV, ONNX Runtime, LaMa-small

**Spec:** `docs/superpowers/specs/2026-03-11-watermark-removal-website-design.md`

---

## File Structure

### Backend (`backend/`)

```
backend/
├── main.py                    # FastAPI app, CORS, lifespan, router mounting
├── requirements.txt           # Python dependencies
├── routers/
│   ├── health.py              # GET /api/health
│   ├── upload.py              # POST /api/upload (validation, job creation, dispatch)
│   ├── status.py              # GET /api/status/{job_id}, GET /api/batch/{batch_id}
│   ├── preview.py             # GET /api/preview/{job_id}
│   └── download.py            # GET /api/download/{job_id}, GET /api/download-all/{batch_id}
├── services/
│   ├── job_store.py           # In-memory job/batch store, cleanup scheduler
│   ├── rate_limiter.py        # Per-IP rate limiting
│   ├── processor.py           # Dispatch to image or PDF pipeline, thread pool
│   ├── image_processor.py     # OpenCV detection + LaMa inpainting
│   └── pdf_processor.py       # PyMuPDF detection + pikepdf removal + fallback
├── models/
│   └── schemas.py             # Pydantic models for Job, Batch, API responses
└── tests/
    ├── conftest.py            # Shared fixtures (test client, sample files)
    ├── test_health.py
    ├── test_upload.py
    ├── test_status.py
    ├── test_preview.py
    ├── test_download.py
    ├── test_job_store.py
    ├── test_rate_limiter.py
    ├── test_image_processor.py
    └── test_pdf_processor.py
```

### Frontend (`frontend/`)

```
frontend/
├── index.html
├── package.json
├── vite.config.js
├── postcss.config.js
├── src/
│   ├── main.jsx               # React entry point
│   ├── App.jsx                # Top-level layout, view state management
│   ├── api.js                 # API client (upload, poll, download helpers)
│   ├── components/
│   │   ├── Header.jsx         # Logo + nav links
│   │   ├── UploadZone.jsx     # Drag & drop, file validation
│   │   ├── ProcessingView.jsx # Progress cards, polling logic
│   │   ├── ResultView.jsx     # Before/after slider, download buttons
│   │   └── BeforeAfterSlider.jsx # Draggable comparison slider
│   └── index.css              # Tailwind imports + custom styles
└── __tests__/
    ├── App.test.jsx
    ├── UploadZone.test.jsx
    ├── ProcessingView.test.jsx
    └── ResultView.test.jsx
```

---

## Chunk 1: Project Scaffolding & Backend Foundation

### Task 1: Initialize Git Repository

- [ ] **Step 1: Initialize git repo**

```bash
cd C:/NUS/Projects/Watermark
git init
```

- [ ] **Step 2: Create .gitignore**

Create `.gitignore`:

```
# Python
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/

# Node
node_modules/
frontend/dist/

# Environment
.env
.env.local

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Project
.superpowers/
*.onnx
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: initialize repo with .gitignore"
```

### Task 2: Backend Project Setup

**Files:**
- Create: `backend/main.py`
- Create: `backend/requirements.txt`
- Create: `backend/models/schemas.py`
- Create: `backend/routers/health.py`
- Test: `backend/tests/test_health.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create requirements.txt**

Create `backend/requirements.txt`:

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
python-multipart==0.0.9
pymupdf==1.24.0
pikepdf==9.0.0
opencv-python-headless==4.10.0.84
onnxruntime==1.19.0
numpy==1.26.4
pytest==8.3.0
httpx==0.27.0
```

- [ ] **Step 2: Create virtual environment and install**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
```

- [ ] **Step 3: Create Pydantic schemas**

Create `backend/models/__init__.py` (empty) and `backend/models/schemas.py`:

```python
from pydantic import BaseModel


class JobResponse(BaseModel):
    id: str
    filename: str
    status: str  # queued, processing, done, error
    watermark_detected: bool | None = None
    preview_url: str | None = None
    original_url: str | None = None
    error: str | None = None


class BatchResponse(BaseModel):
    batch_id: str
    jobs: list[JobResponse]


class UploadResponse(BaseModel):
    batch_id: str
    jobs: list[JobResponse]
    errors: list[dict]


class ErrorResponse(BaseModel):
    error: str
    detail: str
```

- [ ] **Step 4: Write health endpoint test**

Create `backend/tests/__init__.py` (empty) and `backend/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)
```

Create `backend/tests/test_health.py`:

```python
def test_health_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 5: Run test to verify it fails**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_health.py -v
```

Expected: FAIL (no `main` module yet)

- [ ] **Step 6: Create health router**

Create `backend/routers/__init__.py` (empty) and `backend/routers/health.py`:

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Create main.py**

Create `backend/main.py`:

```python
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import health

app = FastAPI(title="Watermark Remover API")

frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
```

- [ ] **Step 8: Run test to verify it passes**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_health.py -v
```

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/
git commit -m "feat: scaffold backend with FastAPI, health endpoint, and tests"
```

### Task 3: Job Store Service

**Files:**
- Create: `backend/services/__init__.py`
- Create: `backend/services/job_store.py`
- Test: `backend/tests/test_job_store.py`

- [ ] **Step 1: Write job store tests**

Create `backend/tests/test_job_store.py`:

```python
import time

from services.job_store import JobStore


def test_create_batch_returns_batch_id_and_jobs():
    store = JobStore()
    batch_id, jobs = store.create_batch(
        [{"filename": "a.jpg"}, {"filename": "b.pdf"}]
    )
    assert batch_id.startswith("batch_")
    assert len(jobs) == 2
    assert jobs[0]["status"] == "queued"
    assert jobs[1]["filename"] == "b.pdf"


def test_get_job_returns_job():
    store = JobStore()
    batch_id, jobs = store.create_batch([{"filename": "a.jpg"}])
    job = store.get_job(jobs[0]["id"])
    assert job is not None
    assert job["filename"] == "a.jpg"


def test_get_job_unknown_returns_none():
    store = JobStore()
    assert store.get_job("nonexistent") is None


def test_get_batch_returns_all_jobs():
    store = JobStore()
    batch_id, jobs = store.create_batch(
        [{"filename": "a.jpg"}, {"filename": "b.jpg"}]
    )
    batch_jobs = store.get_batch(batch_id)
    assert len(batch_jobs) == 2


def test_get_batch_unknown_returns_none():
    store = JobStore()
    assert store.get_batch("nonexistent") is None


def test_update_job_status():
    store = JobStore()
    _, jobs = store.create_batch([{"filename": "a.jpg"}])
    store.update_job(jobs[0]["id"], status="processing")
    job = store.get_job(jobs[0]["id"])
    assert job["status"] == "processing"


def test_update_job_with_result():
    store = JobStore()
    _, jobs = store.create_batch([{"filename": "a.jpg"}])
    store.update_job(
        jobs[0]["id"],
        status="done",
        watermark_detected=True,
    )
    job = store.get_job(jobs[0]["id"])
    assert job["status"] == "done"
    assert job["watermark_detected"] is True


def test_cleanup_removes_old_jobs():
    store = JobStore(cleanup_after_seconds=0)
    _, jobs = store.create_batch([{"filename": "a.jpg"}])
    store.update_job(jobs[0]["id"], status="done")
    store.get_job(jobs[0]["id"])  # mark completed_at
    time.sleep(0.1)
    store.cleanup()
    assert store.get_job(jobs[0]["id"]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_job_store.py -v
```

Expected: FAIL (no `services.job_store` module)

- [ ] **Step 3: Implement job store**

Create `backend/services/__init__.py` (empty) and `backend/services/job_store.py`:

```python
import time
import uuid
import threading


class JobStore:
    def __init__(self, cleanup_after_seconds: int = 600):
        self._jobs: dict[str, dict] = {}
        self._batches: dict[str, list[str]] = {}
        self._lock = threading.Lock()
        self._cleanup_after = cleanup_after_seconds

    def create_batch(self, files: list[dict]) -> tuple[str, list[dict]]:
        batch_id = f"batch_{uuid.uuid4().hex[:12]}"
        jobs = []
        with self._lock:
            job_ids = []
            for f in files:
                job_id = uuid.uuid4().hex[:12]
                job = {
                    "id": job_id,
                    "batch_id": batch_id,
                    "filename": f["filename"],
                    "status": "queued",
                    "watermark_detected": None,
                    "error": None,
                    "created_at": time.time(),
                    "completed_at": None,
                    "input_path": None,
                    "output_path": None,
                }
                self._jobs[job_id] = job
                job_ids.append(job_id)
                jobs.append(dict(job))
            self._batches[batch_id] = job_ids
        return batch_id, jobs

    def get_job(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def get_batch(self, batch_id: str) -> list[dict] | None:
        with self._lock:
            job_ids = self._batches.get(batch_id)
            if job_ids is None:
                return None
            return [dict(self._jobs[jid]) for jid in job_ids if jid in self._jobs]

    def update_job(self, job_id: str, **kwargs) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in kwargs.items():
                job[key] = value
            if job["status"] in ("done", "error") and job["completed_at"] is None:
                job["completed_at"] = time.time()

    def cleanup(self) -> None:
        import shutil
        import tempfile

        now = time.time()
        with self._lock:
            expired = [
                jid
                for jid, job in self._jobs.items()
                if job["completed_at"] is not None
                and (now - job["completed_at"]) > self._cleanup_after
            ]
            for jid in expired:
                job = self._jobs.pop(jid, None)
                if job:
                    # Delete temp files from disk
                    job_dir = os.path.join(
                        tempfile.gettempdir(), f"watermark-{jid}"
                    )
                    if os.path.exists(job_dir):
                        shutil.rmtree(job_dir, ignore_errors=True)
                    bid = job.get("batch_id")
                    if bid in self._batches:
                        self._batches[bid] = [
                            j for j in self._batches[bid] if j != jid
                        ]
                        if not self._batches[bid]:
                            del self._batches[bid]
```

Add `import os` at the top of `job_store.py`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_job_store.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/ backend/tests/test_job_store.py
git commit -m "feat: add in-memory job store with batch support and cleanup"
```

### Task 4: Rate Limiter Service

**Files:**
- Create: `backend/services/rate_limiter.py`
- Test: `backend/tests/test_rate_limiter.py`

- [ ] **Step 1: Write rate limiter tests**

Create `backend/tests/test_rate_limiter.py`:

```python
import time

from services.rate_limiter import RateLimiter


def test_allows_requests_under_limit():
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    for _ in range(5):
        assert limiter.is_allowed("127.0.0.1") is True


def test_blocks_requests_over_limit():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.is_allowed("1.1.1.1") is True
    assert limiter.is_allowed("1.1.1.1") is True
    assert limiter.is_allowed("1.1.1.1") is False


def test_different_ips_tracked_separately():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.is_allowed("1.1.1.1") is True
    assert limiter.is_allowed("2.2.2.2") is True
    assert limiter.is_allowed("1.1.1.1") is False


def test_window_expires():
    limiter = RateLimiter(max_requests=1, window_seconds=0.1)
    assert limiter.is_allowed("1.1.1.1") is True
    assert limiter.is_allowed("1.1.1.1") is False
    time.sleep(0.15)
    assert limiter.is_allowed("1.1.1.1") is True


def test_retry_after_returns_seconds():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.is_allowed("1.1.1.1")
    limiter.is_allowed("1.1.1.1")
    retry = limiter.retry_after("1.1.1.1")
    assert retry is not None
    assert 0 < retry <= 60
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_rate_limiter.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement rate limiter**

Create `backend/services/rate_limiter.py`:

```python
import time
import threading
from collections import defaultdict


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int | float):
        self._max = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _clean(self, ip: str, now: float) -> None:
        cutoff = now - self._window
        self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        with self._lock:
            self._clean(ip, now)
            if len(self._requests[ip]) >= self._max:
                return False
            self._requests[ip].append(now)
            return True

    def retry_after(self, ip: str) -> int | None:
        now = time.time()
        with self._lock:
            self._clean(ip, now)
            if len(self._requests[ip]) < self._max:
                return None
            oldest = self._requests[ip][0]
            return max(1, int(oldest + self._window - now + 1))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_rate_limiter.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/rate_limiter.py backend/tests/test_rate_limiter.py
git commit -m "feat: add per-IP rate limiter with sliding window"
```

---

## Chunk 2: Upload, Status & Download Endpoints

### Task 5: Upload Endpoint

**Files:**
- Create: `backend/routers/upload.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_upload.py`

- [ ] **Step 1: Write upload endpoint tests**

Create `backend/tests/test_upload.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_upload.py -v
```

Expected: FAIL

- [ ] **Step 3: Update conftest with app.state fixtures**

Update `backend/tests/conftest.py`:

```python
import pytest
from fastapi.testclient import TestClient

from main import app
from services.job_store import JobStore
from services.rate_limiter import RateLimiter


@pytest.fixture
def client():
    app.state.job_store = JobStore()
    app.state.upload_limiter = RateLimiter(max_requests=100, window_seconds=60)
    app.state.poll_limiter = RateLimiter(max_requests=100, window_seconds=60)
    return TestClient(app)
```

- [ ] **Step 4: Create main.py with app.state dependency pattern**

Replace `backend/main.py`:

```python
import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routers import health, upload
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
```

- [ ] **Step 5: Implement upload router with rate limiting**

Create `backend/routers/upload.py`:

```python
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

    return {
        "batch_id": batch_id,
        "jobs": [
            {"id": j["id"], "filename": j["filename"], "status": j["status"]}
            for j in jobs
        ],
        "errors": errors,
    }
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_upload.py tests/test_health.py -v
```

Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: add upload endpoint with validation and file storage"
```

### Task 6: Status & Batch Endpoints

**Files:**
- Create: `backend/routers/status.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_status.py`

- [ ] **Step 1: Write status endpoint tests**

Create `backend/tests/test_status.py`:

```python
import io


def test_get_job_status(client):
    # Upload a file first
    response = client.post(
        "/api/upload",
        files=[("files", ("test.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png"))],
    )
    job_id = response.json()["jobs"][0]["id"]

    status_resp = client.get(f"/api/status/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["id"] == job_id
    assert data["status"] == "queued"


def test_get_job_status_unknown_returns_404(client):
    response = client.get("/api/status/nonexistent")
    assert response.status_code == 404


def test_get_batch_status(client):
    files = [
        ("files", ("a.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
        ("files", ("b.jpg", io.BytesIO(b"\xff\xd8" + b"\x00" * 100), "image/jpeg")),
    ]
    response = client.post("/api/upload", files=files)
    batch_id = response.json()["batch_id"]

    batch_resp = client.get(f"/api/batch/{batch_id}")
    assert batch_resp.status_code == 200
    data = batch_resp.json()
    assert data["batch_id"] == batch_id
    assert len(data["jobs"]) == 2


def test_get_batch_unknown_returns_404(client):
    response = client.get("/api/batch/nonexistent")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_status.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement status router**

Create `backend/routers/status.py`:

```python
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
```

- [ ] **Step 4: Register status router in main.py**

Add to `backend/main.py` imports and registration:

```python
from routers import health, upload, status
# ...
app.include_router(status.router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_status.py tests/test_health.py tests/test_upload.py -v
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "feat: add status and batch polling endpoints"
```

### Task 7: Preview & Download Endpoints

**Files:**
- Create: `backend/routers/preview.py`
- Create: `backend/routers/download.py`
- Modify: `backend/main.py`
- Test: `backend/tests/test_preview.py`
- Test: `backend/tests/test_download.py`

- [ ] **Step 1: Write preview endpoint tests**

Create `backend/tests/test_preview.py`:

```python
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
```

- [ ] **Step 2: Write download endpoint tests**

Create `backend/tests/test_download.py`:

```python
import io
import os
import tempfile

from main import app


def _create_done_job(client, filename="test.png"):
    response = client.post(
        "/api/upload",
        files=[("files", (filename, io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png"))],
    )
    data = response.json()
    job_id = data["jobs"][0]["id"]
    batch_id = data["batch_id"]

    store = app.state.job_store
    job_dir = os.path.join(tempfile.gettempdir(), f"watermark-{job_id}")
    os.makedirs(job_dir, exist_ok=True)
    output_path = os.path.join(job_dir, "output.png")
    with open(output_path, "wb") as f:
        f.write(b"\x89PNG processed content")
    store.update_job(job_id, status="done", output_path=output_path, watermark_detected=True)

    return job_id, batch_id


def test_download_single_file(client):
    job_id, _ = _create_done_job(client)
    resp = client.get(f"/api/download/{job_id}")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert "test.png" in resp.headers.get("content-disposition", "")


def test_download_not_found(client):
    resp = client.get("/api/download/nonexistent")
    assert resp.status_code == 404


def test_download_all_as_zip(client):
    # Create two done jobs in same batch
    files = [
        ("files", ("a.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
        ("files", ("b.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
    ]
    response = client.post("/api/upload", files=files)
    data = response.json()
    batch_id = data["batch_id"]

    store = app.state.job_store
    for job in data["jobs"]:
        job_dir = os.path.join(tempfile.gettempdir(), f"watermark-{job['id']}")
        os.makedirs(job_dir, exist_ok=True)
        output_path = os.path.join(job_dir, "output.png")
        with open(output_path, "wb") as f:
            f.write(b"\x89PNG processed")
        store.update_job(job["id"], status="done", output_path=output_path, watermark_detected=True)

    resp = client.get(f"/api/download-all/{batch_id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"


def test_download_all_skips_errored_jobs(client):
    files = [
        ("files", ("a.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
        ("files", ("b.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png")),
    ]
    response = client.post("/api/upload", files=files)
    data = response.json()
    batch_id = data["batch_id"]

    store = app.state.job_store
    # First job succeeds
    job0 = data["jobs"][0]
    job_dir = os.path.join(tempfile.gettempdir(), f"watermark-{job0['id']}")
    os.makedirs(job_dir, exist_ok=True)
    output_path = os.path.join(job_dir, "output.png")
    with open(output_path, "wb") as f:
        f.write(b"\x89PNG processed")
    store.update_job(job0["id"], status="done", output_path=output_path, watermark_detected=True)

    # Second job errors
    store.update_job(data["jobs"][1]["id"], status="error", error="Processing failed")

    resp = client.get(f"/api/download-all/{batch_id}")
    assert resp.status_code == 200  # Still returns zip with successful file


def test_download_all_no_success_returns_404(client):
    response = client.post(
        "/api/upload",
        files=[("files", ("a.png", io.BytesIO(b"\x89PNG" + b"\x00" * 100), "image/png"))],
    )
    data = response.json()
    batch_id = data["batch_id"]
    store = app.state.job_store
    store.update_job(data["jobs"][0]["id"], status="error", error="fail")

    resp = client.get(f"/api/download-all/{batch_id}")
    assert resp.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_preview.py tests/test_download.py -v
```

Expected: FAIL

- [ ] **Step 4: Implement preview router**

Create `backend/routers/preview.py`:

```python
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
```

- [ ] **Step 5: Implement download router**

Create `backend/routers/download.py`:

```python
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
```

- [ ] **Step 6: Register routers in main.py**

Add to `backend/main.py`:

```python
from routers import health, upload, status, preview, download
# ...
app.include_router(preview.router)
app.include_router(download.router)
```

- [ ] **Step 7: Run all backend tests**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: add preview and download endpoints with zip batch support"
```

---

## Chunk 3: Image & PDF Processing Pipelines

### Task 8: Image Watermark Processor

**Files:**
- Create: `backend/services/image_processor.py`
- Test: `backend/tests/test_image_processor.py`

- [ ] **Step 1: Write image processor tests**

Create `backend/tests/test_image_processor.py`:

```python
import os
import tempfile

import cv2
import numpy as np
import pytest

from services.image_processor import ImageProcessor


@pytest.fixture
def processor():
    return ImageProcessor()


@pytest.fixture
def sample_image_path():
    """Create a test image with a simulated text watermark."""
    img = np.ones((200, 300, 3), dtype=np.uint8) * 200  # Light gray background
    # Add "watermark" text in semi-transparent style
    cv2.putText(img, "SAMPLE", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (180, 180, 180), 3)
    path = os.path.join(tempfile.gettempdir(), "test_watermark.png")
    cv2.imwrite(path, img)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def clean_image_path():
    """Create a test image without watermark."""
    img = np.ones((200, 300, 3), dtype=np.uint8) * 100
    path = os.path.join(tempfile.gettempdir(), "test_clean.png")
    cv2.imwrite(path, img)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_detect_watermark_returns_mask(processor, sample_image_path):
    img = cv2.imread(sample_image_path)
    mask = processor.detect_watermark(img)
    assert mask is not None
    assert mask.shape[:2] == img.shape[:2]
    assert mask.dtype == np.uint8


def test_process_returns_output_path(processor, sample_image_path):
    output_dir = tempfile.mkdtemp()
    result = processor.process(sample_image_path, output_dir)
    assert "output_path" in result
    assert os.path.exists(result["output_path"])


def test_process_preserves_format_jpg(processor):
    img = np.ones((200, 300, 3), dtype=np.uint8) * 200
    cv2.putText(img, "SAMPLE", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (180, 180, 180), 3)
    path = os.path.join(tempfile.gettempdir(), "test_wm.jpg")
    cv2.imwrite(path, img)
    output_dir = tempfile.mkdtemp()

    result = processor.process(path, output_dir)
    assert result["output_path"].endswith(".jpg")


def test_process_clean_image_returns_unchanged(processor, clean_image_path):
    output_dir = tempfile.mkdtemp()
    result = processor.process(clean_image_path, output_dir)
    assert result["watermark_detected"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_image_processor.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement image processor**

Create `backend/services/image_processor.py`:

```python
import os

import cv2
import numpy as np

# LaMa model loaded lazily
_lama_session = None


def _get_lama_session():
    global _lama_session
    if _lama_session is None:
        import onnxruntime as ort

        model_path = os.environ.get(
            "LAMA_MODEL_PATH",
            os.path.join(os.path.dirname(__file__), "..", "models", "lama.onnx"),
        )
        if os.path.exists(model_path):
            _lama_session = ort.InferenceSession(
                model_path, providers=["CPUExecutionProvider"]
            )
    return _lama_session


class ImageProcessor:
    def detect_watermark(self, img: np.ndarray) -> np.ndarray | None:
        """Detect watermark regions. Returns a binary mask or None if no watermark found."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Method 1: Detect semi-transparent overlaid text/logos
        # Look for high-frequency low-contrast patterns
        blurred = cv2.GaussianBlur(gray, (21, 21), 0)
        diff = cv2.absdiff(gray, blurred)

        # Threshold to find subtle watermark patterns
        _, thresh = cv2.threshold(diff, 8, 255, cv2.THRESH_BINARY)

        # Method 2: Edge detection for sharper watermarks
        edges = cv2.Canny(gray, 30, 100)
        dilated_edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

        # Combine both methods
        combined = cv2.bitwise_or(thresh, dilated_edges)

        # Morphological operations to clean up the mask
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=3)
        mask = cv2.dilate(mask, kernel, iterations=2)

        # Check if enough watermark pixels detected (at least 0.5% of image)
        watermark_ratio = np.count_nonzero(mask) / (h * w)
        if watermark_ratio < 0.005:
            return None

        return mask

    def inpaint(self, img: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Remove watermark using inpainting."""
        session = _get_lama_session()

        if session is not None:
            return self._lama_inpaint(session, img, mask)

        # Fallback to OpenCV inpainting if LaMa model not available
        return cv2.inpaint(img, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)

    def _lama_inpaint(self, session, img: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Run LaMa ONNX model for inpainting."""
        h, w = img.shape[:2]

        # Resize to model input size (typically 512x512)
        img_resized = cv2.resize(img, (512, 512))
        mask_resized = cv2.resize(mask, (512, 512))

        # Normalize
        img_input = img_resized.astype(np.float32) / 255.0
        img_input = np.transpose(img_input, (2, 0, 1))  # HWC -> CHW
        img_input = np.expand_dims(img_input, 0)  # Add batch dim

        mask_input = (mask_resized > 127).astype(np.float32)
        mask_input = np.expand_dims(np.expand_dims(mask_input, 0), 0)  # 1x1xHxW

        outputs = session.run(None, {"image": img_input, "mask": mask_input})
        result = outputs[0][0]  # Remove batch dim

        # Convert back: CHW -> HWC, denormalize
        result = np.transpose(result, (1, 2, 0))
        result = np.clip(result * 255, 0, 255).astype(np.uint8)

        # Resize back to original dimensions
        return cv2.resize(result, (w, h))

    def process(self, input_path: str, output_dir: str) -> dict:
        """Process a single image. Returns dict with output_path and watermark_detected."""
        img = cv2.imread(input_path)
        if img is None:
            raise ValueError(f"Cannot read image: {input_path}")

        ext = os.path.splitext(input_path)[1].lower()
        output_path = os.path.join(output_dir, f"output{ext}")

        mask = self.detect_watermark(img)
        if mask is None:
            # No watermark detected — copy original
            cv2.imwrite(output_path, img)
            return {"output_path": output_path, "watermark_detected": False}

        result = self.inpaint(img, mask)
        cv2.imwrite(output_path, result)
        return {"output_path": output_path, "watermark_detected": True}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_image_processor.py -v
```

Expected: All PASS (falls back to OpenCV inpainting without LaMa model file)

- [ ] **Step 5: Commit**

```bash
git add backend/services/image_processor.py backend/tests/test_image_processor.py
git commit -m "feat: add image watermark detection and inpainting processor"
```

### Task 9: PDF Watermark Processor

**Files:**
- Create: `backend/services/pdf_processor.py`
- Test: `backend/tests/test_pdf_processor.py`

- [ ] **Step 1: Write PDF processor tests**

Create `backend/tests/test_pdf_processor.py`:

```python
import os
import tempfile

import fitz  # PyMuPDF
import pytest

from services.pdf_processor import PdfProcessor


@pytest.fixture
def processor():
    return PdfProcessor()


@pytest.fixture
def watermarked_pdf_path():
    """Create a test PDF with a text watermark."""
    path = os.path.join(tempfile.gettempdir(), "test_watermark.pdf")
    doc = fitz.open()
    for _ in range(3):
        page = doc.new_page(width=595, height=842)
        # Normal content
        page.insert_text((72, 72), "This is normal content.", fontsize=12)
        # Watermark: light gray text repeated on every page
        page.insert_text(
            (100, 400),
            "CONFIDENTIAL",
            fontsize=48,
            color=(0.8, 0.8, 0.8),
        )
    doc.save(path)
    doc.close()
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def clean_pdf_path():
    """Create a test PDF without watermark."""
    path = os.path.join(tempfile.gettempdir(), "test_clean.pdf")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Clean content only.", fontsize=12)
    doc.save(path)
    doc.close()
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_detect_text_watermark(processor, watermarked_pdf_path):
    doc = fitz.open(watermarked_pdf_path)
    watermarks = processor.detect_watermarks(doc)
    doc.close()
    assert len(watermarks) > 0


def test_process_returns_output_pdf(processor, watermarked_pdf_path):
    output_dir = tempfile.mkdtemp()
    result = processor.process(watermarked_pdf_path, output_dir)
    assert result["output_path"].endswith(".pdf")
    assert os.path.exists(result["output_path"])


def test_process_output_is_valid_pdf(processor, watermarked_pdf_path):
    output_dir = tempfile.mkdtemp()
    result = processor.process(watermarked_pdf_path, output_dir)
    doc = fitz.open(result["output_path"])
    assert len(doc) == 3  # Same page count
    doc.close()


def test_process_clean_pdf(processor, clean_pdf_path):
    output_dir = tempfile.mkdtemp()
    result = processor.process(clean_pdf_path, output_dir)
    assert result["watermark_detected"] is False


def test_rejects_too_many_pages(processor):
    path = os.path.join(tempfile.gettempdir(), "test_large.pdf")
    doc = fitz.open()
    for _ in range(25):
        doc.new_page()
    doc.save(path)
    doc.close()

    with pytest.raises(ValueError, match="20 pages"):
        processor.process(path, tempfile.mkdtemp())

    os.remove(path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_pdf_processor.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement PDF processor**

Create `backend/services/pdf_processor.py`:

```python
import os
import re
from collections import Counter

import fitz  # PyMuPDF
import numpy as np

from services.image_processor import ImageProcessor

MAX_PDF_PAGES = 20

WATERMARK_PATTERNS = re.compile(
    r"\b(DRAFT|CONFIDENTIAL|SAMPLE|COPY|DO NOT DISTRIBUTE|WATERMARK|PREVIEW)\b",
    re.IGNORECASE,
)


class PdfProcessor:
    def __init__(self):
        self._image_processor = ImageProcessor()

    def detect_watermarks(self, doc: fitz.Document) -> list[dict]:
        """Detect watermark elements across all pages."""
        watermarks = []

        if len(doc) < 1:
            return watermarks

        # Strategy 1: Find text that appears on every page
        page_texts = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            texts = set()
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if text:
                                texts.add(text)
            page_texts.append(texts)

        if len(page_texts) > 1:
            # Text appearing on every page is likely a watermark
            common_texts = page_texts[0]
            for texts in page_texts[1:]:
                common_texts = common_texts & texts

            for text in common_texts:
                if WATERMARK_PATTERNS.search(text):
                    watermarks.append({"type": "text", "text": text})

        # Strategy 2: Check for light-colored (near white/gray) large text
        for page_num, page in enumerate(doc):
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            color = span.get("color", 0)
                            size = span.get("size", 12)
                            text = span["text"].strip()

                            # Large, light-colored text is likely a watermark
                            if size > 24 and text:
                                r = (color >> 16) & 0xFF
                                g = (color >> 8) & 0xFF
                                b = color & 0xFF
                                # Light gray or near-white
                                if r > 180 and g > 180 and b > 180:
                                    watermarks.append({
                                        "type": "text",
                                        "text": text,
                                        "page": page_num,
                                    })

                            if WATERMARK_PATTERNS.search(text):
                                watermarks.append({
                                    "type": "text",
                                    "text": text,
                                    "page": page_num,
                                })

        # Deduplicate
        seen = set()
        unique = []
        for w in watermarks:
            key = (w["type"], w["text"])
            if key not in seen:
                seen.add(key)
                unique.append(w)
        return unique

    def _remove_text_watermarks(
        self, input_path: str, output_path: str, watermarks: list[dict]
    ) -> None:
        """Remove detected text watermarks using redaction."""
        doc = fitz.open(input_path)
        watermark_texts = {w["text"] for w in watermarks if w["type"] == "text"}

        for page in doc:
            for text in watermark_texts:
                areas = page.search_for(text)
                for area in areas:
                    page.add_redact_annot(area, fill=(1, 1, 1))
            page.apply_redactions()

        doc.save(output_path)
        doc.close()

    def _rasterize_and_inpaint(self, input_path: str, output_path: str) -> None:
        """Fallback: convert pages to images, inpaint, reassemble as PDF."""
        import cv2

        doc = fitz.open(input_path)
        output_doc = fitz.open()

        for page in doc:
            # Render page to image at 150 DPI
            pix = page.get_pixmap(dpi=150)
            img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 4:  # RGBA
                img_bgr = cv2.cvtColor(img_data, cv2.COLOR_RGBA2BGR)
            else:
                img_bgr = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)

            # Detect and remove watermark
            mask = self._image_processor.detect_watermark(img_bgr)
            if mask is not None:
                img_bgr = self._image_processor.inpaint(img_bgr, mask)

            # Convert back to RGB for PDF
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

            # Create new page with same dimensions
            new_page = output_doc.new_page(
                width=page.rect.width, height=page.rect.height
            )
            # Encode cleaned image as PNG bytes and insert
            import cv2
            _, png_bytes = cv2.imencode(".png", cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR))
            new_page.insert_image(new_page.rect, stream=png_bytes.tobytes())

        output_doc.save(output_path)
        output_doc.close()
        doc.close()

    def process(self, input_path: str, output_dir: str) -> dict:
        """Process a PDF file. Returns dict with output_path and watermark_detected."""
        doc = fitz.open(input_path)

        if len(doc) > MAX_PDF_PAGES:
            doc.close()
            raise ValueError(
                f"PDF has {len(doc)} pages. Maximum is {MAX_PDF_PAGES} pages"
            )

        watermarks = self.detect_watermarks(doc)
        doc.close()

        output_path = os.path.join(output_dir, "output.pdf")

        if not watermarks:
            # No watermark detected — copy original
            import shutil

            shutil.copy2(input_path, output_path)
            return {"output_path": output_path, "watermark_detected": False}

        # Try text-based removal first
        text_watermarks = [w for w in watermarks if w["type"] == "text"]
        if text_watermarks:
            self._remove_text_watermarks(input_path, output_path, watermarks)
        else:
            # Fallback to rasterize + inpaint
            self._rasterize_and_inpaint(input_path, output_path)

        return {"output_path": output_path, "watermark_detected": True}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_pdf_processor.py -v
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/pdf_processor.py backend/tests/test_pdf_processor.py
git commit -m "feat: add PDF watermark detection and removal processor"
```

### Task 10: Processing Dispatcher

**Files:**
- Create: `backend/services/processor.py`
- Create: `backend/tests/test_processor.py`
- Modify: `backend/routers/upload.py`

- [ ] **Step 1: Write dispatcher tests**

Create `backend/tests/test_processor.py`:

```python
import os
import tempfile
import asyncio

import pytest

from services.job_store import JobStore
from services.processor import dispatch_job, _process_job


@pytest.fixture
def store():
    return JobStore()


@pytest.fixture
def image_job(store):
    """Create a job with a real image file."""
    import cv2
    import numpy as np

    batch_id, jobs = store.create_batch([{"filename": "test.png"}])
    job = jobs[0]
    job_dir = os.path.join(tempfile.gettempdir(), f"watermark-{job['id']}")
    os.makedirs(job_dir, exist_ok=True)
    # Create image with simulated watermark
    img = np.ones((200, 300, 3), dtype=np.uint8) * 200
    cv2.putText(img, "SAMPLE", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (180, 180, 180), 3)
    input_path = os.path.join(job_dir, "test.png")
    cv2.imwrite(input_path, img)
    store.update_job(job["id"], input_path=input_path)
    return job["id"]


def test_process_job_sets_done(store, image_job):
    _process_job(store, image_job)
    job = store.get_job(image_job)
    assert job["status"] == "done"
    assert job["output_path"] is not None
    assert os.path.exists(job["output_path"])


def test_process_job_unknown_id_no_error(store):
    _process_job(store, "nonexistent")  # Should not raise


def test_dispatch_job_async(store, image_job):
    asyncio.run(dispatch_job(store, image_job))
    job = store.get_job(image_job)
    assert job["status"] == "done"


def test_process_job_error_sets_error_status(store):
    batch_id, jobs = store.create_batch([{"filename": "bad.png"}])
    job = jobs[0]
    store.update_job(job["id"], input_path="/nonexistent/path.png")
    _process_job(store, job["id"])
    result = store.get_job(job["id"])
    assert result["status"] == "error"
    assert result["error"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_processor.py -v
```

Expected: FAIL (no `services.processor` module)

- [ ] **Step 3: Implement processing dispatcher**

Create `backend/services/processor.py`:

```python
import os
import asyncio
import tempfile
from concurrent.futures import ThreadPoolExecutor

from services.job_store import JobStore
from services.image_processor import ImageProcessor
from services.pdf_processor import PdfProcessor

_executor = ThreadPoolExecutor(max_workers=2)
_image_processor = ImageProcessor()
_pdf_processor = PdfProcessor()

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
PDF_EXTENSIONS = {".pdf"}


def _process_job(store: JobStore, job_id: str) -> None:
    """Synchronous processing function to run in thread pool."""
    job = store.get_job(job_id)
    if job is None:
        return

    store.update_job(job_id, status="processing")

    try:
        input_path = job["input_path"]
        ext = os.path.splitext(job["filename"])[1].lower()
        output_dir = os.path.join(
            tempfile.gettempdir(), f"watermark-{job_id}"
        )
        os.makedirs(output_dir, exist_ok=True)

        if ext in IMAGE_EXTENSIONS:
            result = _image_processor.process(input_path, output_dir)
        elif ext in PDF_EXTENSIONS:
            result = _pdf_processor.process(input_path, output_dir)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        store.update_job(
            job_id,
            status="done",
            output_path=result["output_path"],
            watermark_detected=result["watermark_detected"],
        )

    except Exception as e:
        store.update_job(job_id, status="error", error=str(e))


async def dispatch_job(store: JobStore, job_id: str) -> None:
    """Dispatch a job to the thread pool with timeout."""
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(_executor, _process_job, store, job_id),
            timeout=60.0,
        )
    except asyncio.TimeoutError:
        store.update_job(job_id, status="error", error="Processing timed out (60s limit)")
    except Exception as e:
        store.update_job(job_id, status="error", error=str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/test_processor.py -v
```

Expected: All PASS

- [ ] **Step 5: Wire dispatcher into upload endpoint**

Add to the end of `upload_files` in `backend/routers/upload.py`, before the return statement:

```python
    # Dispatch processing for each job
    from services.processor import dispatch_job

    for job in jobs:
        asyncio.create_task(dispatch_job(store, job["id"]))
```

Add `import asyncio` at the top of `backend/routers/upload.py`.

- [ ] **Step 6: Run all backend tests**

```bash
cd C:/NUS/Projects/Watermark/backend
python -m pytest tests/ -v
```

Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat: add async processing dispatcher with thread pool and timeout"
```

---

## Chunk 4: Frontend Scaffolding & Upload

### Task 11: Frontend Project Setup

**Files:**
- Create: `frontend/` project via Vite scaffolding
- Create: `frontend/tailwind.config.js`
- Create: `frontend/src/index.css`

- [ ] **Step 1: Scaffold React project with Vite**

```bash
cd C:/NUS/Projects/Watermark
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install -D tailwindcss @tailwindcss/vite
```

- [ ] **Step 2: Configure Tailwind**

Update `frontend/vite.config.js`:

```javascript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

Replace `frontend/src/index.css`:

```css
@import "tailwindcss";
```

- [ ] **Step 3: Clean up default Vite files**

Delete `frontend/src/App.css`. Replace `frontend/src/App.jsx`:

```jsx
function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <h1 className="text-lg font-bold">WatermarkOff</h1>
          <nav className="flex gap-4 text-sm text-gray-400">
            <a href="#how" className="hover:text-white">How it works</a>
            <a href="#faq" className="hover:text-white">FAQ</a>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-6 py-16 text-center">
        <h2 className="text-3xl font-bold">Remove Watermarks Instantly</h2>
        <p className="mt-2 text-gray-400">Images & PDFs — free, no signup</p>
      </main>
    </div>
  );
}

export default App;
```

- [ ] **Step 4: Verify frontend runs**

```bash
cd C:/NUS/Projects/Watermark/frontend
npm run dev
```

Open http://localhost:5173 — should show dark page with "WatermarkOff" header and hero text. Stop the dev server after verification.

- [ ] **Step 5: Commit**

```bash
cd C:/NUS/Projects/Watermark
git add frontend/
git commit -m "feat: scaffold frontend with React, Vite, and Tailwind dark theme"
```

### Task 12: API Client Module

**Files:**
- Create: `frontend/src/api.js`

- [ ] **Step 1: Create API client**

Create `frontend/src/api.js`:

```javascript
const API_BASE = "/api";

export async function healthCheck() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export async function uploadFiles(files) {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

export async function getBatchStatus(batchId) {
  const res = await fetch(`${API_BASE}/batch/${batchId}`);
  if (!res.ok) {
    if (res.status === 404) {
      throw new Error("SESSION_EXPIRED");
    }
    throw new Error("Failed to fetch status");
  }
  return res.json();
}

export function previewUrl(jobId, type = "processed") {
  const param = type === "original" ? "?type=original" : "";
  return `${API_BASE}/preview/${jobId}${param}`;
}

export function downloadUrl(jobId) {
  return `${API_BASE}/download/${jobId}`;
}

export function downloadAllUrl(batchId) {
  return `${API_BASE}/download-all/${batchId}`;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat: add API client module with upload, polling, and download helpers"
```

### Task 13: UploadZone Component

**Files:**
- Create: `frontend/src/components/UploadZone.jsx`

- [ ] **Step 1: Create UploadZone component**

Create `frontend/src/components/UploadZone.jsx`:

```jsx
import { useState, useRef, useCallback } from "react";

const ACCEPTED_TYPES = [".png", ".jpg", ".jpeg", ".pdf"];
const MAX_SIZE = 10 * 1024 * 1024;
const MAX_FILES = 5;

function validateFiles(fileList) {
  const valid = [];
  const errors = [];

  for (const file of fileList) {
    const ext = "." + file.name.split(".").pop().toLowerCase();
    if (!ACCEPTED_TYPES.includes(ext)) {
      errors.push(`${file.name}: unsupported file type`);
    } else if (file.size > MAX_SIZE) {
      errors.push(`${file.name}: exceeds 10 MB limit`);
    } else {
      valid.push(file);
    }
  }

  if (valid.length > MAX_FILES) {
    errors.push(`Too many files. Maximum is ${MAX_FILES}.`);
    return { valid: valid.slice(0, MAX_FILES), errors };
  }

  return { valid, errors };
}

export default function UploadZone({ onUpload, disabled }) {
  const [dragOver, setDragOver] = useState(false);
  const [clientErrors, setClientErrors] = useState([]);
  const inputRef = useRef(null);

  const handleFiles = useCallback(
    (fileList) => {
      setClientErrors([]);
      const { valid, errors } = validateFiles(Array.from(fileList));
      if (errors.length > 0) {
        setClientErrors(errors);
      }
      if (valid.length > 0) {
        onUpload(valid);
      }
    },
    [onUpload]
  );

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragOver(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  return (
    <div className="mt-10">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
          dragOver
            ? "border-blue-400 bg-blue-400/10"
            : "border-gray-700 hover:border-gray-500"
        } ${disabled ? "pointer-events-none opacity-50" : ""}`}
      >
        <div className="text-4xl">📁</div>
        <p className="mt-3 text-gray-300">Drop files here or click to upload</p>
        <p className="mt-1 text-sm text-gray-500">
          PNG, JPG, PDF — max 10 MB, up to 5 files
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.pdf"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {clientErrors.length > 0 && (
        <div className="mt-4 rounded-lg bg-red-900/30 p-3 text-sm text-red-300">
          {clientErrors.map((err, i) => (
            <p key={i}>{err}</p>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/UploadZone.jsx
git commit -m "feat: add UploadZone component with drag-and-drop and validation"
```

---

## Chunk 5: Frontend Processing & Results Views

### Task 14: ProcessingView Component

**Files:**
- Create: `frontend/src/components/ProcessingView.jsx`

- [ ] **Step 1: Create ProcessingView component**

Create `frontend/src/components/ProcessingView.jsx`:

```jsx
import { useState, useEffect, useRef } from "react";
import { getBatchStatus } from "../api";

const STATUS_ICONS = {
  queued: "⏳",
  processing: "⚙️",
  done: "✅",
  error: "❌",
};

export default function ProcessingView({ batchId, onComplete, onSessionExpired }) {
  const [jobs, setJobs] = useState([]);
  const intervalRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const data = await getBatchStatus(batchId);
        if (cancelled) return;
        setJobs(data.jobs);

        const allDone = data.jobs.every(
          (j) => j.status === "done" || j.status === "error"
        );
        if (allDone) {
          clearInterval(intervalRef.current);
          onComplete(data.jobs);
        }
      } catch (err) {
        if (err.message === "SESSION_EXPIRED") {
          clearInterval(intervalRef.current);
          onSessionExpired();
        }
      }
    }

    poll(); // Initial poll
    intervalRef.current = setInterval(poll, 2000);

    return () => {
      cancelled = true;
      clearInterval(intervalRef.current);
    };
  }, [batchId, onComplete, onSessionExpired]);

  return (
    <div className="mt-10 space-y-3">
      <h3 className="text-lg font-semibold">Processing...</h3>
      {jobs.map((job) => (
        <div
          key={job.id}
          className="flex items-center gap-3 rounded-lg bg-gray-900 p-4"
        >
          <span className="text-xl">{STATUS_ICONS[job.status] || "⏳"}</span>
          <div className="flex-1">
            <p className="text-sm font-medium">{job.filename}</p>
            <p className="text-xs text-gray-500 capitalize">{job.status}</p>
          </div>
          {job.status === "processing" && (
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ProcessingView.jsx
git commit -m "feat: add ProcessingView component with polling and status cards"
```

### Task 15: BeforeAfterSlider Component

**Files:**
- Create: `frontend/src/components/BeforeAfterSlider.jsx`

- [ ] **Step 1: Create BeforeAfterSlider component**

Create `frontend/src/components/BeforeAfterSlider.jsx`:

```jsx
import { useState, useEffect, useRef, useCallback } from "react";

export default function BeforeAfterSlider({ beforeSrc, afterSrc }) {
  const [position, setPosition] = useState(50);
  const [containerWidth, setContainerWidth] = useState(0);
  const containerRef = useRef(null);
  const dragging = useRef(false);

  // Track container width for before image sizing
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      setContainerWidth(entries[0].contentRect.width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const updatePosition = useCallback((clientX) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const x = Math.max(0, Math.min(clientX - rect.left, rect.width));
    setPosition((x / rect.width) * 100);
  }, []);

  const handleMouseDown = () => {
    dragging.current = true;
  };

  const handleMouseMove = useCallback(
    (e) => {
      if (dragging.current) {
        updatePosition(e.clientX);
      }
    },
    [updatePosition]
  );

  const handleMouseUp = () => {
    dragging.current = false;
  };

  const handleTouchMove = useCallback(
    (e) => {
      updatePosition(e.touches[0].clientX);
    },
    [updatePosition]
  );

  return (
    <div
      ref={containerRef}
      className="relative cursor-col-resize select-none overflow-hidden rounded-lg"
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onTouchMove={handleTouchMove}
    >
      {/* After image (full width, bottom layer) */}
      <img src={afterSrc} alt="After" className="block w-full" draggable={false} />

      {/* Before image (clipped) */}
      <div
        className="absolute inset-0 overflow-hidden"
        style={{ width: `${position}%` }}
      >
        <img
          src={beforeSrc}
          alt="Before"
          className="block w-full"
          style={{ width: `${containerWidth}px` }}
          draggable={false}
        />
      </div>

      {/* Slider handle */}
      <div
        className="absolute top-0 bottom-0 w-1 cursor-col-resize bg-white shadow-lg"
        style={{ left: `${position}%`, transform: "translateX(-50%)" }}
        onMouseDown={handleMouseDown}
        onTouchStart={handleMouseDown}
      >
        <div className="absolute top-1/2 left-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white shadow-lg">
          <span className="text-xs text-gray-800">⟷</span>
        </div>
      </div>

      {/* Labels */}
      <div className="absolute top-2 left-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">
        Before
      </div>
      <div className="absolute top-2 right-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">
        After
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/BeforeAfterSlider.jsx
git commit -m "feat: add BeforeAfterSlider component with draggable comparison"
```

### Task 16: ResultView Component

**Files:**
- Create: `frontend/src/components/ResultView.jsx`

- [ ] **Step 1: Create ResultView component**

Create `frontend/src/components/ResultView.jsx`:

```jsx
import BeforeAfterSlider from "./BeforeAfterSlider";
import { previewUrl, downloadUrl, downloadAllUrl } from "../api";

export default function ResultView({ jobs, batchId, onReset }) {
  const doneJobs = jobs.filter((j) => j.status === "done");
  const errorJobs = jobs.filter((j) => j.status === "error");

  return (
    <div className="mt-10">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">
          Results ({doneJobs.length} of {jobs.length} processed)
        </h3>
        <div className="flex gap-2">
          {doneJobs.length > 1 && (
            <a
              href={downloadAllUrl(batchId)}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium hover:bg-blue-500"
            >
              Download All
            </a>
          )}
          <button
            onClick={onReset}
            className="rounded-lg bg-gray-800 px-4 py-2 text-sm font-medium hover:bg-gray-700"
          >
            Remove more
          </button>
        </div>
      </div>

      {errorJobs.length > 0 && (
        <div className="mt-4 rounded-lg bg-red-900/30 p-3 text-sm text-red-300">
          {errorJobs.map((job) => (
            <p key={job.id}>
              {job.filename}: {job.error || "Processing failed"}
            </p>
          ))}
        </div>
      )}

      <div className="mt-6 space-y-6">
        {doneJobs.map((job) => (
          <div key={job.id} className="rounded-xl bg-gray-900 p-4">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <p className="font-medium">{job.filename}</p>
                {job.watermark_detected === false && (
                  <p className="text-xs text-yellow-400">
                    No watermark detected — file returned as-is
                  </p>
                )}
              </div>
              <a
                href={downloadUrl(job.id)}
                className="rounded-lg bg-gray-700 px-3 py-1.5 text-sm hover:bg-gray-600"
              >
                Download
              </a>
            </div>
            {job.watermark_detected !== false && (
              <BeforeAfterSlider
                beforeSrc={previewUrl(job.id, "original")}
                afterSrc={previewUrl(job.id)}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ResultView.jsx
git commit -m "feat: add ResultView component with before/after preview and downloads"
```

### Task 17: Wire Up App.jsx with Full Flow

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Update App.jsx with state machine**

Replace `frontend/src/App.jsx`:

```jsx
import { useState, useEffect, useCallback } from "react";
import { healthCheck, uploadFiles } from "./api";
import UploadZone from "./components/UploadZone";
import ProcessingView from "./components/ProcessingView";
import ResultView from "./components/ResultView";

function App() {
  const [view, setView] = useState("upload"); // upload | processing | result
  const [batchId, setBatchId] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [uploadError, setUploadError] = useState(null);
  const [serverErrors, setServerErrors] = useState([]);
  const [uploading, setUploading] = useState(false);

  // Wake backend on page load
  useEffect(() => {
    healthCheck();
  }, []);

  const handleUpload = useCallback(async (files) => {
    setUploadError(null);
    setServerErrors([]);
    setUploading(true);

    try {
      const data = await uploadFiles(files);
      if (data.errors?.length > 0) {
        setServerErrors(data.errors);
      }
      if (data.jobs.length > 0) {
        setBatchId(data.batch_id);
        setJobs(data.jobs);
        setView("processing");
      }
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploading(false);
    }
  }, []);

  const handleComplete = useCallback((completedJobs) => {
    setJobs(completedJobs);
    setView("result");
  }, []);

  const handleSessionExpired = useCallback(() => {
    setUploadError("Session expired — please re-upload your files");
    setView("upload");
  }, []);

  const handleReset = useCallback(() => {
    setView("upload");
    setBatchId(null);
    setJobs([]);
    setUploadError(null);
    setServerErrors([]);
  }, []);

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <h1
            className="cursor-pointer text-lg font-bold"
            onClick={handleReset}
          >
            WatermarkOff
          </h1>
          <nav className="flex gap-4 text-sm text-gray-400">
            <a href="#how" className="hover:text-white">
              How it works
            </a>
            <a href="#faq" className="hover:text-white">
              FAQ
            </a>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-16">
        {view === "upload" && (
          <div className="text-center">
            <h2 className="text-3xl font-bold">Remove Watermarks Instantly</h2>
            <p className="mt-2 text-gray-400">
              Images & PDFs — free, no signup
            </p>
            <UploadZone onUpload={handleUpload} disabled={uploading} />
            {uploading && (
              <p className="mt-4 text-sm text-gray-400">Uploading...</p>
            )}
            {uploadError && (
              <div className="mt-4 rounded-lg bg-red-900/30 p-3 text-sm text-red-300">
                {uploadError}
              </div>
            )}
            {serverErrors.length > 0 && (
              <div className="mt-4 rounded-lg bg-yellow-900/30 p-3 text-sm text-yellow-300">
                {serverErrors.map((e, i) => (
                  <p key={i}>
                    {e.filename}: {e.error}
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

        {view === "processing" && batchId && (
          <ProcessingView
            batchId={batchId}
            onComplete={handleComplete}
            onSessionExpired={handleSessionExpired}
          />
        )}

        {view === "result" && (
          <ResultView jobs={jobs} batchId={batchId} onReset={handleReset} />
        )}
      </main>
    </div>
  );
}

export default App;
```

- [ ] **Step 2: Verify frontend compiles**

```bash
cd C:/NUS/Projects/Watermark/frontend
npm run build
```

Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
cd C:/NUS/Projects/Watermark
git add frontend/
git commit -m "feat: wire up full App flow — upload, processing, results"
```

---

## Chunk 6: Integration & Polish

### Task 18: End-to-End Manual Test

- [ ] **Step 1: Start backend**

```bash
cd C:/NUS/Projects/Watermark/backend
source .venv/Scripts/activate
uvicorn main:app --reload --port 8000
```

- [ ] **Step 2: Start frontend**

In a second terminal:

```bash
cd C:/NUS/Projects/Watermark/frontend
npm run dev
```

- [ ] **Step 3: Test the full flow**

1. Open http://localhost:5173
2. Verify dark theme loads with "WatermarkOff" header
3. Drag an image with a watermark into the upload zone
4. Verify processing view appears with status cards
5. Verify result view appears with before/after slider
6. Click "Download" and verify file downloads
7. Click "Remove more" and verify reset to upload view
8. Test with a PDF file
9. Test uploading an unsupported file type (should show error)
10. Test uploading a file > 10 MB (should show error)

- [ ] **Step 4: Fix any issues found during manual testing**

- [ ] **Step 5: Commit any fixes**

Stage only changed files explicitly and commit:

```bash
git add backend/ frontend/src/
git commit -m "fix: integration fixes from manual testing"
```

### Task 19: Add Render Deployment Config

**Files:**
- Create: `backend/Procfile`

- [ ] **Step 1: Create Procfile for Render**

Create `backend/Procfile`:

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

- [ ] **Step 2: Commit**

```bash
git add backend/Procfile
git commit -m "chore: add Render deployment Procfile"
```

### Task 20: Add Vercel Frontend Config

**Files:**
- Create: `frontend/vercel.json`

- [ ] **Step 1: Create Vercel config with API rewrites**

Create `frontend/vercel.json`:

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://YOUR-RENDER-APP.onrender.com/api/:path*"
    }
  ]
}
```

Note: Replace `YOUR-RENDER-APP` with the actual Render URL after deployment.

- [ ] **Step 2: Commit**

```bash
git add frontend/vercel.json
git commit -m "chore: add Vercel config with API rewrite proxy"
```

### Task 21: Run Full Test Suite

- [ ] **Step 1: Run all backend tests**

```bash
cd C:/NUS/Projects/Watermark/backend
source .venv/Scripts/activate
python -m pytest tests/ -v --tb=short
```

Expected: All tests pass

- [ ] **Step 2: Run frontend build**

```bash
cd C:/NUS/Projects/Watermark/frontend
npm run build
```

Expected: Build succeeds with no errors

- [ ] **Step 3: Commit if any remaining changes**

Only commit if there are staged changes from fixes:

```bash
cd C:/NUS/Projects/Watermark
git status
# If changes exist, stage specific files and commit:
# git add backend/ frontend/
# git commit -m "chore: final fixes from test suite run"
```
