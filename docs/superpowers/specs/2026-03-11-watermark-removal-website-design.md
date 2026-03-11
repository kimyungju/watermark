# Watermark Removal Website — Design Spec

## Overview

A public web application that removes watermarks from images and PDFs. Users upload files, the system automatically detects and removes watermarks, and users preview before/after results and download cleaned files. Free to use, no signup required.

## Target Users

General public — anyone who needs to remove text watermarks, logo watermarks, or stock photo watermarks from images or PDF documents.

## Architecture

### Frontend
- **Stack:** React + Vite, Tailwind CSS
- **Hosting:** Vercel (free tier)
- **Responsibilities:** File upload (drag & drop), processing status, before/after preview with slider, download

### Backend
- **Stack:** FastAPI (Python)
- **Hosting:** Render (free tier)
- **Responsibilities:** File processing, watermark detection and removal, serving previews and downloads

### Communication
- REST API over HTTPS
- Async processing with polling (upload returns batch ID + job IDs, frontend polls for status)

### Free Tier Constraints
- Max file size: 10 MB
- Max PDF page count: 20 pages
- Batch limit: 5 files per upload
- Processing timeout: 60 seconds per file
- No persistent storage — files auto-deleted after processing
- Jobs cleaned up 10 minutes after completion
- Render free tier: 512 MB RAM, service spins down after ~15 min inactivity

### Render Cold Start Handling
Render free tier restarts the service after inactivity. On cold start, all in-memory jobs are lost. The frontend must handle this gracefully:
- If polling returns 404 for a job ID, show "Session expired — please re-upload your files"
- The LaMa ONNX model is loaded lazily on first request (not at startup) to keep cold start time reasonable

## UI Design

### Layout
Single page, centered layout (similar to remove.bg). Everything happens on one page with state transitions: Landing → Processing → Result.

### Components

| Component | Responsibility |
|---|---|
| `App` | Top-level layout, manages view state (upload → processing → result) |
| `UploadZone` | Drag & drop area, file type/size validation, triggers upload |
| `ProcessingView` | Progress cards per file, polls `/api/status`, shows spinner and status |
| `ResultView` | Before/after slider preview, individual + batch download, "Remove more" reset |

### UI Flow
1. **Landing** — Hero text ("Remove Watermarks Instantly") + centered upload zone. Accepts PNG, JPG, JPEG, PDF up to 10 MB.
2. **Processing** — Upload zone replaced by progress cards. Each card shows filename, spinner, and status text (queued/processing/done/error).
3. **Result** — Before/after comparison with draggable slider for each file. Individual download buttons per file. "Download All" button (zip) for batch uploads. "Remove more" button resets to landing.

### Styling
- Dark theme
- Tailwind CSS utility classes
- Responsive (mobile-friendly, desktop-optimized)

## Processing Pipeline

### PDF Watermark Removal
1. Parse PDF structure with PyMuPDF (fitz)
2. Identify watermark elements by detecting:
   - Semi-transparent text or images
   - Elements repeated on every page
   - Items in the background layer
   - Common watermark text patterns ("DRAFT", "CONFIDENTIAL", "SAMPLE", etc.)
3. Remove matched elements using pikepdf for low-level PDF object manipulation (pikepdf is better at surgically removing specific PDF objects without corrupting the document structure; PyMuPDF is used for detection and rendering)
4. Re-render and return cleaned PDF
5. **Fallback:** If watermark is flattened/rasterized into the page, convert each page to image (via PyMuPDF at 150 DPI), run through the image pipeline, then reassemble into a PDF. Output is always a PDF.
6. **Preview:** For multi-page PDFs, the preview shows the first page only (rendered as PNG at 150 DPI via PyMuPDF). Both `?type=original` and default serve rendered page images (original vs cleaned). The download provides the full cleaned PDF.

### Image Watermark Removal
1. Auto-detect watermark region using OpenCV (edge detection, frequency analysis, repeated pattern detection)
2. If no watermark detected, return the file unchanged with status `done` and a flag `"watermark_detected": false`. Frontend shows a notice: "No watermark detected — file returned as-is."
3. Generate a binary mask of the watermark area
4. Run LaMa inpainting model (ONNX runtime, CPU inference) to fill masked region. Use the LaMa-small variant (~50 MB) to fit within Render's 512 MB memory limit alongside other dependencies.
5. Return before/after preview. Output format matches input format (JPEG in → JPEG out, PNG in → PNG out). OpenCV encodes output to match the original.
6. **Stretch goal:** Allow user to manually adjust the detection mask

### Temporary File Management
- All uploaded and processed files stored in system temp directory (`/tmp`)
- Each job gets a unique subdirectory: `/tmp/watermark-{job_id}/`
- Subdirectory deleted immediately when job is cleaned up (10 min after completion)
- On upload, best-effort check of available disk space; reject if < 100 MB free (concurrent requests may pass simultaneously — acceptable tradeoff)

### Concurrency
- CPU-bound processing (OpenCV, LaMa inference) runs in a thread pool executor
- Max 2 concurrent processing workers to stay within memory limits
- Additional jobs remain in `queued` state until a worker is free
- Frontend shows "queued" status so user knows their job is waiting

## API Design

### Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `GET /api/health` | GET | Health check. Returns `{"status": "ok"}`. Frontend calls on page load to wake backend from cold start. |
| `POST /api/upload` | POST | Upload file(s) via multipart form data. Returns batch ID + job IDs. |
| `GET /api/status/{job_id}` | GET | Poll single job status. Returns status + preview URLs when done. |
| `GET /api/batch/{batch_id}` | GET | Poll all jobs in a batch. Returns array of job statuses. |
| `GET /api/preview/{job_id}` | GET | Serve preview image. Query param `?type=original` for before image. |
| `GET /api/download/{job_id}` | GET | Download single processed file with `Content-Disposition: attachment; filename="{original_name}"`. |
| `GET /api/download-all/{batch_id}` | GET | Download all successfully processed files in batch as a zip. Skips errored jobs. Returns 404 if no jobs succeeded. |

### Job Lifecycle
- States: `queued` → `processing` → `done` | `error`
- Storage: In-memory dictionary (no database)
- Cleanup: Jobs auto-deleted 10 minutes after completion
- Unknown job IDs return 404

### Polling Strategy
- Frontend polls `GET /api/batch/{batch_id}` every 2 seconds while any job is `queued` or `processing`
- Stops polling when all jobs are `done` or `error`
- If 404 returned (cold start wiped jobs), show session-expired message

### Request/Response Examples

**Upload:**
```json
POST /api/upload
Content-Type: multipart/form-data

Response 200:
{
  "batch_id": "batch_xyz",
  "jobs": [
    { "id": "abc123", "filename": "photo.jpg", "status": "queued" },
    { "id": "def456", "filename": "report.pdf", "status": "queued" }
  ],
  "errors": [
    { "filename": "readme.txt", "error": "Unsupported file type. Accepted: PNG, JPG, JPEG, PDF" }
  ]
}
```
Partial success: valid files are accepted, invalid files listed in `errors` array. If ALL files are invalid, response is still 200 with empty `jobs` array and populated `errors` array. If zero files are sent, return 400.

**Batch Status:**
```json
GET /api/batch/batch_xyz

Response 200:
{
  "batch_id": "batch_xyz",
  "jobs": [
    { "id": "abc123", "status": "done", "preview_url": "/api/preview/abc123", "original_url": "/api/preview/abc123?type=original" },
    { "id": "def456", "status": "processing" }
  ]
}
```

**Single Job Status:**
```json
GET /api/status/abc123

Response 200:
{ "id": "abc123", "status": "done", "watermark_detected": true, "preview_url": "/api/preview/abc123", "original_url": "/api/preview/abc123?type=original" }
```

The `watermark_detected` field is always present when status is `done`. Set to `false` when no watermark was found (file returned unchanged).

**Download All:**
```
GET /api/download-all/batch_xyz

Response 200: application/zip with Content-Disposition: attachment; filename="watermark-removed.zip"
```

### Error Response Schema
All error responses use a consistent format:
```json
{
  "error": "Short error code",
  "detail": "Human-readable explanation"
}
```
HTTP status codes: 400 (bad request/validation), 404 (job not found), 413 (file too large), 429 (rate limited), 500 (server error).

### Rate Limiting
- 10 upload requests per IP per minute (each request may contain up to 5 files)
- 60 status/batch polls per IP per minute
- Returns 429 with `Retry-After` header when exceeded
- Implemented via in-memory counter per IP (simple, no external dependency)
- Note: rate limit state resets on cold start — acceptable tradeoff for free tier simplicity

## Error Handling
- File type validation on upload — unsupported formats rejected, valid files in same batch still processed
- File size validation — reject files > 10 MB with 413 status
- PDF page count validation — reject PDFs with > 20 pages
- Processing timeout — 60 second limit per file via `asyncio.wait_for` wrapping the executor call; job transitions to `error` state
- Model failure fallback — if inpainting fails, job transitions to `error` with explanation
- Cold start recovery — 404 on unknown job IDs, frontend shows re-upload prompt
- CORS — configured via environment variable `FRONTEND_ORIGIN` (e.g., `https://watermark-app.vercel.app`)

## Tech Stack Summary

| Layer | Technology | Purpose |
|---|---|---|
| Frontend framework | React + Vite | UI |
| Styling | Tailwind CSS | Utility-first CSS |
| Frontend hosting | Vercel (free) | Static hosting + CDN |
| Backend framework | FastAPI | Async Python API |
| PDF processing | PyMuPDF (fitz) | PDF parsing, watermark detection, rendering |
| PDF structure editing | pikepdf | Low-level PDF object removal when needed |
| Image detection | OpenCV | Watermark region detection |
| Image inpainting | LaMa-small (ONNX Runtime, CPU) | ~50 MB model for watermark fill |
| Backend hosting | Render (free) | 512 MB RAM, auto-sleep |

## Out of Scope (v1)
- User accounts / authentication
- Processing history
- API access for developers
- Video watermark removal
- Manual mask editing (stretch goal, not v1)
- Payment / premium tiers
