# Fix Removal Quality & Multi-Page Preview Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two bugs: (1) watermark removal creates white boxes that hide content on image-based pages, and (2) before/after preview only shows page 0 of multi-page PDFs.

**Architecture:** For issue 1, skip image watermarks (banners) on image-based pages during inpainting — only remove text watermarks. Banners are too large for inpainting and create visible white boxes; the text beneath them is recoverable. Confirmed: text-only masking produces mean=238.6 (close to original 228.9) vs full masking's 254.7 (white box). For issue 2, add `page` query parameter to the preview endpoint with per-page/per-type caching, expose `page_count` in the job status response, and add page navigation arrows to the frontend BeforeAfterSlider.

**Tech Stack:** PyMuPDF (fitz), OpenCV, FastAPI, React, Tailwind CSS

---

## Root Cause Analysis

### Issue 1: White boxes on image-based pages

The `_remove_watermarks_inpaint` method masks BOTH text and image watermarks. On image-based pages (StuDocu cheat sheets), the banner watermark is a 300x29pt strip at the bottom overlapping content images. OpenCV inpainting fills this large masked area with near-white (254.7) because the surrounding page margin is white. Meanwhile, text-only masking produces 238.6 (blends with the banner's own background color).

**Fix:** In `_remove_watermarks_inpaint`, skip image watermarks on image-based pages. Only inpaint text watermarks. The banner stays (minor visual artifact) but content is preserved.

### Issue 2: Preview shows only page 0

`_render_pdf_preview()` always renders `doc[0]`. Additionally, the cache uses a single filename `preview.png` shared between original and processed types — whichever is requested first gets cached and returned for both (a correctness bug that can make before/after show the same image).

**Fix:** Add `page` query parameter to preview endpoint, use `preview_{type}_p{page}.png` cache filenames, expose `page_count` in job status, and add page navigation to the frontend slider.

---

## Chunk 1: Backend Fixes

### Task 1: Skip image watermarks on image-based pages

**Files:**
- Modify: `backend/services/pdf_processor.py` (the `_remove_watermarks_inpaint` method)
- Test: `backend/tests/test_pdf_processor.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_pdf_processor.py`:

```python
def test_inpaint_skips_banner_on_image_pages(processor):
    """Image watermarks (banners) should NOT be masked on image-based pages."""
    doc = fitz.open()
    page = doc.new_page(width=842, height=596)

    # Full-page content image (gray)
    content = np.full((596, 842, 3), 180, dtype=np.uint8)
    _, png = cv2.imencode(".png", content)
    page.insert_image(page.rect, stream=png.tobytes())

    # Banner watermark image at bottom (distinct color so we can check it survives)
    banner = np.full((30, 300, 3), 100, dtype=np.uint8)
    _, banner_png = cv2.imencode(".png", banner)
    page.insert_image(fitz.Rect(271, 552, 571, 582), stream=banner_png.tobytes())

    # Text watermark
    page.insert_text((374, 580), "messages.downloaded_by", fontsize=8, color=(0.3, 0.3, 0.3))

    # Build only text watermarks for this page (no image watermarks)
    text_bboxes = [{"type": "text", "bbox": (374, 572, 469, 583)}]

    result = processor._inpaint_page(page, text_bboxes, dpi=150)

    # Banner region should be preserved (dark ~100), not white-boxed (~255)
    scale = 150 / 72.0
    by0 = int(555 * scale)
    by1 = int(570 * scale)
    bx0 = int(350 * scale)
    bx1 = int(500 * scale)
    banner_region = result[by0:by1, bx0:bx1]
    assert np.mean(banner_region) < 200, (
        f"Banner region mean={np.mean(banner_region):.0f} — should be preserved (~100-180), not white"
    )
    doc.close()
```

- [ ] **Step 2: Run test to verify it passes (this tests the filtering, not the code change)**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_inpaint_skips_banner_on_image_pages -v`
Expected: PASS (the test feeds text-only bboxes directly to `_inpaint_page`, which already works correctly)

- [ ] **Step 3: Write the integration test that currently fails**

Add to `backend/tests/test_pdf_processor.py`:

```python
def test_process_image_page_preserves_banner_region(processor):
    """Full pipeline should not white-box the banner area on image-based pages."""
    path = os.path.join(tempfile.gettempdir(), "test_banner_preserve.pdf")
    doc = fitz.open()

    for _ in range(2):
        page = doc.new_page(width=842, height=596)
        content = np.full((596, 842, 3), 180, dtype=np.uint8)
        _, png = cv2.imencode(".png", content)
        page.insert_image(page.rect, stream=png.tobytes())
        # Banner image
        banner = np.full((30, 300, 3), 100, dtype=np.uint8)
        _, bpng = cv2.imencode(".png", banner)
        page.insert_image(fitz.Rect(271, 552, 571, 582), stream=bpng.tobytes())
        # Text watermark
        page.insert_text((374, 580), "messages.downloaded_by", fontsize=8, color=(0.3, 0.3, 0.3))

    doc.save(path)
    doc.close()

    output_dir = tempfile.mkdtemp()
    result = processor.process(path, output_dir)
    assert result["watermark_detected"] is True

    out_doc = fitz.open(result["output_path"])
    page = out_doc[0]
    pix = page.get_pixmap(dpi=72)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

    # Banner area should NOT be pure white
    banner_region = img[540:570, 300:550]
    mean_val = np.mean(banner_region)
    assert mean_val < 220, (
        f"Banner region mean={mean_val:.0f} — looks white-boxed. "
        f"Banner should be preserved, not inpainted."
    )
    out_doc.close()
    os.remove(path)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_process_image_page_preserves_banner_region -v`
Expected: FAIL (current code masks both text and image watermarks)

- [ ] **Step 5: Fix `_remove_watermarks_inpaint` to skip image watermarks on image-based pages**

In `backend/services/pdf_processor.py`, modify the `_remove_watermarks_inpaint` method. Change the bbox collection loop to skip image watermarks when the page is image-based:

```python
# Replace this section in _remove_watermarks_inpaint:
            if wm_bboxes and self._is_image_based_page(page):
```

with this logic:

```python
            is_image_page = self._is_image_based_page(page)

            if wm_bboxes and is_image_page:
```

And change the bbox collection to filter out image watermarks on image-based pages. Replace the inner loop:

```python
        for page_num, page in enumerate(doc):
            # Collect watermark bboxes for this page
            wm_bboxes = []
            is_image_page = self._is_image_based_page(page)

            for w in watermarks:
                if w["type"] == "text" and "bbox_by_page" in w:
                    bboxes = w["bbox_by_page"].get(page_num, [])
                    for bbox in bboxes:
                        wm_bboxes.append({"type": "text", "bbox": bbox})
                elif w["type"] == "image" and page_num in w.get("pages", []):
                    # Skip image watermarks on image-based pages —
                    # banner removal creates large white boxes that destroy content.
                    # Text watermarks are small enough for clean inpainting.
                    if is_image_page:
                        continue
                    sig = w["bbox_signature"]
                    blocks = page.get_text("dict")["blocks"]
                    for block in blocks:
                        if "image" in block:
                            bbox = block.get("bbox", (0, 0, 0, 0))
                            block_sig = (
                                round(bbox[0], -1),
                                round(bbox[1], -1),
                                round(bbox[2] - bbox[0], -1),
                                round(bbox[3] - bbox[1], -1),
                            )
                            if block_sig == sig:
                                wm_bboxes.append({"type": "image", "bbox": bbox})

            if wm_bboxes and is_image_page:
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_process_image_page_preserves_banner_region -v`
Expected: PASS

- [ ] **Step 7: Run ALL tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add backend/services/pdf_processor.py backend/tests/test_pdf_processor.py
git commit -m "fix: skip banner removal on image pages to prevent white boxes"
```

---

### Task 2: Fix preview cache bug and add multi-page support

**Files:**
- Modify: `backend/routers/preview.py`
- Modify: `backend/routers/status.py`
- Test: `backend/tests/test_preview.py`

- [ ] **Step 1: Write failing test for cache bug**

Add to `backend/tests/test_preview.py`:

```python
def test_preview_original_vs_processed_are_different(client, job_store):
    """Original and processed previews must return different images."""
    import fitz
    import tempfile
    import os

    # Create two distinct PDFs
    job_dir = os.path.join(tempfile.gettempdir(), "watermark-testcache")
    os.makedirs(job_dir, exist_ok=True)

    for name, color in [("input.pdf", (1, 0, 0)), ("output.pdf", (0, 0, 1))]:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), f"This is {name}", fontsize=24, color=color)
        doc.save(os.path.join(job_dir, name))
        doc.close()

    job_store.create_batch([{"filename": "test.pdf"}])
    job_id = list(job_store._jobs.keys())[0]
    job_store.update_job(
        job_id,
        status="done",
        input_path=os.path.join(job_dir, "input.pdf"),
        output_path=os.path.join(job_dir, "output.pdf"),
        watermark_detected=True,
    )

    resp_orig = client.get(f"/api/preview/{job_id}?type=original")
    resp_proc = client.get(f"/api/preview/{job_id}?type=processed")

    assert resp_orig.status_code == 200
    assert resp_proc.status_code == 200
    # The two responses must have different content
    assert resp_orig.content != resp_proc.content, "Original and processed previews are identical!"

    import shutil
    shutil.rmtree(job_dir, ignore_errors=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_preview.py::test_preview_original_vs_processed_are_different -v`
Expected: FAIL (both return the same cached `preview.png`)

- [ ] **Step 3: Fix preview cache and add page parameter**

Rewrite `backend/routers/preview.py`:

```python
import os
import tempfile

import fitz  # PyMuPDF
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import FileResponse

from services.job_store import JobStore

router = APIRouter(prefix="/api")


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def _render_pdf_preview(pdf_path: str, job_id: str, preview_type: str, page: int) -> str:
    """Render a specific page of a PDF as PNG at 150 DPI."""
    preview_path = os.path.join(
        tempfile.gettempdir(),
        f"watermark-{job_id}",
        f"preview_{preview_type}_p{page}.png",
    )
    if os.path.exists(preview_path):
        return preview_path
    doc = fitz.open(pdf_path)
    if page >= len(doc):
        doc.close()
        raise HTTPException(status_code=400, detail=f"Page {page} out of range (0-{len(doc)-1})")
    pix = doc[page].get_pixmap(dpi=150)
    pix.save(preview_path)
    doc.close()
    return preview_path


def _get_pdf_page_count(pdf_path: str) -> int:
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count


@router.get("/preview/{job_id}")
async def get_preview(
    job_id: str,
    type: str = "processed",
    page: int = Query(default=0, ge=0),
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

    if path.lower().endswith(".pdf"):
        path = _render_pdf_preview(path, job_id, type, page)

    return FileResponse(path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_preview.py::test_preview_original_vs_processed_are_different -v`
Expected: PASS

- [ ] **Step 5: Add `page_count` to job status response**

In `backend/routers/status.py`, modify `_job_to_response`:

```python
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
        resp["page_count"] = job.get("page_count", 1)
    if job["status"] == "error":
        resp["error"] = job.get("error", "Processing failed")
    return resp
```

- [ ] **Step 6: Store `page_count` during processing**

In `backend/services/processor.py`, modify `_process_job` to store page count. After `result = _pdf_processor.process(...)`, add:

```python
        if ext in PDF_EXTENSIONS:
            result = _pdf_processor.process(input_path, output_dir)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        # Get page count for PDF preview navigation
        page_count = 1
        if ext in PDF_EXTENSIONS:
            import fitz
            doc = fitz.open(result["output_path"])
            page_count = len(doc)
            doc.close()

        store.update_job(
            job_id,
            status="done",
            output_path=result["output_path"],
            watermark_detected=result["watermark_detected"],
            page_count=page_count,
        )
```

- [ ] **Step 7: Run ALL backend tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add backend/routers/preview.py backend/routers/status.py backend/services/processor.py backend/tests/test_preview.py
git commit -m "fix: preview cache bug + add multi-page preview support"
```

---

## Chunk 2: Frontend Multi-Page Navigation

### Task 3: Add page navigation to BeforeAfterSlider

**Files:**
- Modify: `frontend/src/components/BeforeAfterSlider.jsx`
- Modify: `frontend/src/components/ResultView.jsx`
- Modify: `frontend/src/api.js`

- [ ] **Step 1: Update API helper to accept page parameter**

In `frontend/src/api.js`, modify `previewUrl`:

```javascript
export function previewUrl(jobId, type = "processed", page = 0) {
  const params = new URLSearchParams();
  if (type === "original") params.set("type", "original");
  if (page > 0) params.set("page", page);
  const qs = params.toString();
  return `${API_BASE}/preview/${jobId}${qs ? "?" + qs : ""}`;
}
```

- [ ] **Step 2: Add page navigation to BeforeAfterSlider**

Rewrite `frontend/src/components/BeforeAfterSlider.jsx` to accept `pageCount` prop and manage current page:

```jsx
import { useState, useEffect, useRef, useCallback } from "react";

export default function BeforeAfterSlider({
  beforeSrc,
  afterSrc,
  pageCount = 1,
  onPageChange,
}) {
  const [position, setPosition] = useState(50);
  const [containerWidth, setContainerWidth] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [currentPage, setCurrentPage] = useState(0);
  const containerRef = useRef(null);
  const dragging = useRef(false);

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

  const handleMouseDown = (e) => {
    e.preventDefault();
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

  const goToPage = (page) => {
    setCurrentPage(page);
    setLoaded(false);
    if (onPageChange) onPageChange(page);
  };

  // Derive actual image URLs based on current page
  const actualBefore =
    typeof beforeSrc === "function" ? beforeSrc(currentPage) : beforeSrc;
  const actualAfter =
    typeof afterSrc === "function" ? afterSrc(currentPage) : afterSrc;

  return (
    <div className="space-y-3">
      {/* Slider */}
      <div
        ref={containerRef}
        className="group relative cursor-col-resize select-none overflow-hidden rounded-xl"
        style={{ border: "1px solid var(--color-border)" }}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onTouchMove={handleTouchMove}
      >
        {/* After image (full, bottom layer) */}
        <img
          src={actualAfter}
          alt="After"
          className="block w-full"
          draggable={false}
          onLoad={() => setLoaded(true)}
        />

        {/* Before image (clipped) */}
        <div
          className="absolute inset-0 overflow-hidden"
          style={{ width: `${position}%` }}
        >
          <img
            src={actualBefore}
            alt="Before"
            className="block h-full object-cover object-left"
            style={{ width: `${containerWidth}px` }}
            draggable={false}
          />
        </div>

        {/* Divider line with glow */}
        <div
          className="slider-glow pointer-events-none absolute top-0 bottom-0 w-[2px] bg-[var(--color-accent)]"
          style={{
            left: `${position}%`,
            transform: "translateX(-50%)",
          }}
        />

        {/* Slider handle */}
        <div
          className="absolute top-0 bottom-0 z-10 w-10 cursor-col-resize"
          style={{
            left: `${position}%`,
            transform: "translateX(-50%)",
          }}
          onMouseDown={handleMouseDown}
          onTouchStart={handleMouseDown}
        >
          <div
            className="absolute top-1/2 left-1/2 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full transition-transform duration-150 group-hover:scale-110"
            style={{
              background: "var(--color-accent)",
              boxShadow:
                "0 0 0 3px var(--color-base), 0 2px 12px var(--color-accent-glow)",
            }}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="var(--color-base)"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <path d="M5 4L2 8l3 4" />
              <path d="M11 4l3 4-3 4" />
            </svg>
          </div>
        </div>

        {/* Labels */}
        {loaded && (
          <>
            <div
              className="animate-fade-in absolute top-3 left-3 rounded-md px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider"
              style={{
                background: "rgba(0, 0, 0, 0.65)",
                backdropFilter: "blur(8px)",
                color: "var(--color-text-muted)",
              }}
            >
              Before
            </div>
            <div
              className="animate-fade-in absolute top-3 right-3 rounded-md px-2.5 py-1 text-[11px] font-medium uppercase tracking-wider"
              style={{
                background: "rgba(0, 0, 0, 0.65)",
                backdropFilter: "blur(8px)",
                color: "var(--color-text-muted)",
              }}
            >
              After
            </div>
          </>
        )}
      </div>

      {/* Page navigation */}
      {pageCount > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => goToPage(Math.max(0, currentPage - 1))}
            disabled={currentPage === 0}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] transition-all hover:border-[var(--color-border-hover)] hover:text-[var(--color-text)] disabled:opacity-30 disabled:pointer-events-none"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M8 3L4 7l4 4" />
            </svg>
          </button>
          <span className="text-xs text-[var(--color-text-muted)] tabular-nums">
            Page {currentPage + 1} of {pageCount}
          </span>
          <button
            onClick={() => goToPage(Math.min(pageCount - 1, currentPage + 1))}
            disabled={currentPage >= pageCount - 1}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text-muted)] transition-all hover:border-[var(--color-border-hover)] hover:text-[var(--color-text)] disabled:opacity-30 disabled:pointer-events-none"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M6 3l4 4-4 4" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Update ResultView to pass page info and URL builders**

In `frontend/src/components/ResultView.jsx`, update the BeforeAfterSlider usage to pass function-based URLs and `pageCount`:

```jsx
            {job.watermark_detected !== false && (
              <div className="p-4">
                <BeforeAfterSlider
                  beforeSrc={(page) => previewUrl(job.id, "original", page)}
                  afterSrc={(page) => previewUrl(job.id, "processed", page)}
                  pageCount={job.page_count || 1}
                />
              </div>
            )}
```

- [ ] **Step 4: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.js frontend/src/components/BeforeAfterSlider.jsx frontend/src/components/ResultView.jsx
git commit -m "feat: multi-page before/after preview with page navigation"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `backend/services/pdf_processor.py` | Skip image watermarks on image-based pages in `_remove_watermarks_inpaint` |
| `backend/routers/preview.py` | Fix cache key (type+page), add `page` query param, add page range validation |
| `backend/routers/status.py` | Include `page_count` in job response |
| `backend/services/processor.py` | Store `page_count` after processing |
| `backend/tests/test_pdf_processor.py` | Add 2 tests for banner preservation |
| `backend/tests/test_preview.py` | Add test for cache correctness |
| `frontend/src/api.js` | Add `page` param to `previewUrl()` |
| `frontend/src/components/BeforeAfterSlider.jsx` | Add page navigation, accept function-based URLs |
| `frontend/src/components/ResultView.jsx` | Pass page count and URL builders to slider |
