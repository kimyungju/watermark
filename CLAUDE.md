# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Backend
cd backend && source .venv/Scripts/activate   # Activate venv (Windows/Git Bash)
python -m pytest tests/ -v                     # Run all tests (56 tests)
python -m pytest tests/test_upload.py -v       # Run single test file
python -m pytest tests/test_upload.py::test_upload_valid_pdf -v  # Run single test
uvicorn main:app --reload                      # Dev server on :8000

# Frontend
cd frontend && npm run dev                     # Dev server on :5173 (proxies /api → :8000)
npm run build                                  # Production build
npm run lint                                   # ESLint
```

## Architecture

**Full-stack watermark removal app:** FastAPI backend + React 19 / Vite frontend.

### Backend (`backend/`)

Request flow: **Upload → Dispatch → Process → Poll → Download**

- `main.py` — FastAPI app with lifespan cleanup loop. Services injected via `app.state` (not module singletons). CORS origin from `FRONTEND_ORIGIN` env var.
- `routers/` — REST endpoints: `upload.py` (POST /api/upload), `status.py` (GET /api/batch/{id}), `preview.py`, `download.py`, `health.py`
- `services/job_store.py` — Thread-safe in-memory job/batch store with auto-cleanup (10 min TTL, 60s sweep)
- `services/processor.py` — ThreadPoolExecutor(2) dispatcher. Uses `threading.Timer` (not `asyncio.create_task`) to avoid TestClient race conditions. 60s timeout per job.
- `services/pdf_processor.py` — 5-strategy watermark detection using PyMuPDF: common text across pages, large light text, platform fingerprints (StuDocu/Scribd/CourseHero), repeated images, banner-shaped images
- `services/pdf_watermark_remover.py` — pypdf object-level removal (no rasterization): separate content streams, annotation removal, inline BT/ET text block removal, XObject overlay removal
- `services/image_processor.py` — OpenCV watermark detection (blur diff + Canny edges) and Telea inpainting. Optional LaMa ONNX model (not included).
- `services/rate_limiter.py` — Sliding window per-IP rate limiting (upload: 10/min, poll: 60/min)

### Frontend (`frontend/src/`)

Three-view SPA controlled by `view` state in `App.jsx`: upload → processing → result.

- `api.js` — Fetch client for all backend endpoints
- `components/UploadZone.jsx` — Drag-and-drop with client-side validation
- `components/ProcessingView.jsx` — 2s interval polling with status indicators
- `components/ResultView.jsx` — Results grid with download buttons
- `components/BeforeAfterSlider.jsx` — Interactive comparison slider (mouse + touch)
- `index.css` — Tailwind v4 theme: warm dark (#0c0a09 base, #e8a849 accent), Instrument Serif + DM Sans fonts, glass-morphism effects

### Key Constraints

- File types: `.png`, `.jpg`, `.jpeg`, `.pdf`
- Max file size: 10 MB; max files per batch: 5; max PDF pages: 20
- Python 3.13 with pinned versions: pymupdf 1.27.2, pypdf >=4.0.0, opencv-python-headless 4.10.0.84, numpy 2.1.3
- Backend venv at `backend/.venv`
- All errors return `{error: str, detail: str}` format

### Testing Patterns

- `tests/conftest.py` provides `client` fixture with fresh `app.state` (JobStore, RateLimiters)
- Tests use `TestClient` from FastAPI — no real server needed
- PDF/image fixtures created inline in tests (minimal fitz/PIL documents)
- Rate limiter tests manipulate internal timestamp lists directly
