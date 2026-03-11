# Smart Watermark Removal Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix watermark removal destroying nearby content on image-based PDF pages by using targeted inpainting instead of white-fill redaction.

**Architecture:** Pages are classified as "image-based" (content stored as images covering >40% of page) or "text-based". Text-based pages use fast PyMuPDF redaction (preserves text selectability). Image-based pages use rasterize → targeted mask → OpenCV inpaint (preserves underlying content). The mask is built from the exact watermark bounding boxes already detected by `detect_watermarks()`.

**Tech Stack:** PyMuPDF (fitz), OpenCV (cv2), NumPy

---

## Root Cause Analysis

**Problem:** `_remove_text_watermarks()` and `_remove_image_watermarks()` both use `page.add_redact_annot(area, fill=(1, 1, 1))` which draws a white rectangle. On pages where content is stored as images (common for StuDocu cheat sheets), the white rectangle covers both the watermark AND the underlying content image.

**Evidence** (from the real StuDocu PDF `cs2106-midterm-cheat-sheet`):
- Pages 1-2: Content is two large images (~50% page each, left/right halves)
- Banner watermark `(271,552,571,580)` overlaps content images by 150x29 and 162x29 pixels
- Text watermark "messages.downloaded_by" overlaps content images by ~100x11 pixels
- Redaction destroys these overlapping content regions → visible white boxes

**Fix:** For image-based pages, rasterize the page, build a pixel-precise mask from watermark bboxes, and inpaint only those masked pixels using `cv2.inpaint()`.

---

## Chunk 1: Core Implementation

### Task 1: Add `_is_image_based_page` helper

**Files:**
- Modify: `backend/services/pdf_processor.py`
- Test: `backend/tests/test_pdf_processor.py`

- [ ] **Step 1: Write the failing test**

Add to `test_pdf_processor.py`:

```python
def test_is_image_based_page_with_full_page_images(processor):
    """Pages with large images covering >40% should be classified as image-based."""
    doc = fitz.open()
    page = doc.new_page(width=842, height=596)
    # Insert a large image covering the left half of the page
    import numpy as np
    import cv2
    img = np.zeros((596, 421, 3), dtype=np.uint8)
    _, png = cv2.imencode(".png", img)
    page.insert_image(fitz.Rect(0, 0, 421, 596), stream=png.tobytes())
    assert processor._is_image_based_page(page) is True
    doc.close()


def test_is_image_based_page_text_only(processor):
    """Pages with only text should not be classified as image-based."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Just text content here.", fontsize=12)
    assert processor._is_image_based_page(page) is False
    doc.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_is_image_based_page_with_full_page_images tests/test_pdf_processor.py::test_is_image_based_page_text_only -v`
Expected: FAIL with `AttributeError: 'PdfProcessor' object has no attribute '_is_image_based_page'`

- [ ] **Step 3: Implement `_is_image_based_page`**

Add to `PdfProcessor` class in `backend/services/pdf_processor.py`:

```python
def _is_image_based_page(self, page: fitz.Page) -> bool:
    """Check if a page's content is primarily stored as images."""
    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        return False

    image_area = 0
    blocks = page.get_text("dict")["blocks"]
    for block in blocks:
        if "image" in block:
            bbox = block.get("bbox", (0, 0, 0, 0))
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            image_area += w * h

    return image_area / page_area > 0.4
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_is_image_based_page_with_full_page_images tests/test_pdf_processor.py::test_is_image_based_page_text_only -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/pdf_processor.py backend/tests/test_pdf_processor.py
git commit -m "feat: add _is_image_based_page helper for page classification"
```

---

### Task 2: Add `_build_watermark_mask` method

**Files:**
- Modify: `backend/services/pdf_processor.py`
- Test: `backend/tests/test_pdf_processor.py`

- [ ] **Step 1: Write the failing test**

Add to `test_pdf_processor.py`:

```python
def test_build_watermark_mask_creates_correct_mask(processor):
    """Mask should have white pixels only in watermark regions."""
    import numpy as np

    page_width, page_height = 842.0, 596.0
    dpi = 150
    scale = dpi / 72.0

    watermarks_on_page = [
        {"type": "text", "bbox": (373.8, 578.1, 468.5, 589.1)},
    ]

    mask = processor._build_watermark_mask(
        page_width, page_height, dpi, watermarks_on_page
    )

    img_w = int(page_width * scale)
    img_h = int(page_height * scale)
    assert mask.shape == (img_h, img_w)
    assert mask.dtype == np.uint8

    # Mask should have non-zero pixels in the watermark region
    assert np.any(mask > 0), "Mask should have non-zero pixels"

    # Mask should be mostly zero (watermark is small relative to page)
    ratio = np.count_nonzero(mask) / mask.size
    assert ratio < 0.1, f"Mask covers {ratio*100:.1f}% — too much"
    assert ratio > 0.0, "Mask should cover something"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_build_watermark_mask_creates_correct_mask -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement `_build_watermark_mask`**

Add to `PdfProcessor` class in `backend/services/pdf_processor.py`:

```python
def _build_watermark_mask(
    self,
    page_width: float,
    page_height: float,
    dpi: int,
    watermarks_on_page: list[dict],
    pixel_size: tuple[int, int] | None = None,
) -> np.ndarray:
    """Build a binary mask from watermark bounding boxes in pixel coordinates.

    Args:
        page_width: PDF page width in points.
        page_height: PDF page height in points.
        dpi: Rasterization DPI.
        watermarks_on_page: List of dicts with 'bbox' key (x0, y0, x1, y1) in PDF coords.
        pixel_size: Optional (width, height) tuple of actual pixmap dimensions.
            If provided, overrides computed dimensions to avoid off-by-one mismatches.

    Returns:
        Binary mask (uint8) at rasterized resolution. 255 = watermark, 0 = keep.
    """
    scale = dpi / 72.0
    if pixel_size:
        img_w, img_h = pixel_size
    else:
        img_w = int(page_width * scale)
        img_h = int(page_height * scale)
    mask = np.zeros((img_h, img_w), dtype=np.uint8)

    pad = int(2 * scale)  # Small padding around each watermark region
    for wm in watermarks_on_page:
        bbox = wm["bbox"]
        x0 = max(0, int(bbox[0] * scale) - pad)
        y0 = max(0, int(bbox[1] * scale) - pad)
        x1 = min(img_w, int(bbox[2] * scale) + pad)
        y1 = min(img_h, int(bbox[3] * scale) + pad)
        mask[y0:y1, x0:x1] = 255

    return mask
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_build_watermark_mask_creates_correct_mask -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/pdf_processor.py backend/tests/test_pdf_processor.py
git commit -m "feat: add _build_watermark_mask for precise inpainting masks"
```

---

### Task 3: Add `_inpaint_page` method

**Files:**
- Modify: `backend/services/pdf_processor.py`
- Test: `backend/tests/test_pdf_processor.py`

- [ ] **Step 1: Write the failing test**

Add to `test_pdf_processor.py`:

```python
def test_inpaint_page_preserves_content(processor):
    """Inpainting should remove watermark text without destroying surrounding content."""
    import numpy as np
    import cv2

    doc = fitz.open()
    page = doc.new_page(width=842, height=596)

    # Create a content image (colored rectangle with text-like pattern)
    content = np.full((596, 842, 3), 200, dtype=np.uint8)  # Light gray background
    cv2.rectangle(content, (100, 100), (742, 496), (50, 50, 50), -1)  # Dark content area
    _, png = cv2.imencode(".png", content)
    page.insert_image(page.rect, stream=png.tobytes())

    # Add watermark text at bottom
    page.insert_text((374, 580), "messages.downloaded_by", fontsize=8, color=(0.3, 0.3, 0.3))

    watermarks_on_page = [
        {"type": "text", "bbox": (374, 572, 469, 583)},
    ]

    result_img = processor._inpaint_page(page, watermarks_on_page, dpi=150)

    assert result_img is not None
    assert len(result_img.shape) == 3  # Color image
    assert result_img.shape[2] == 3    # BGR

    # The content area (dark rectangle at center) should still be mostly dark
    scale = 150 / 72.0
    center_y = int(300 * scale)
    center_x = int(421 * scale)
    center_pixel = result_img[center_y, center_x]
    assert np.mean(center_pixel) < 100, f"Center content should be dark, got {center_pixel}"

    doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_inpaint_page_preserves_content -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement `_inpaint_page`**

Add to `PdfProcessor` class in `backend/services/pdf_processor.py`. Add `import cv2` at the top of the method (lazy import to avoid import at module level):

```python
def _inpaint_page(
    self, page: fitz.Page, watermarks_on_page: list[dict], dpi: int = 150
) -> np.ndarray:
    """Rasterize a page and inpaint watermark regions.

    Returns:
        Inpainted image as BGR numpy array.
    """
    import cv2

    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

    if pix.n == 4:
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    else:
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    mask = self._build_watermark_mask(
        page.rect.width, page.rect.height, dpi, watermarks_on_page,
        pixel_size=(pix.width, pix.height),
    )

    if not np.any(mask):
        return img_bgr

    return cv2.inpaint(img_bgr, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_inpaint_page_preserves_content -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/pdf_processor.py backend/tests/test_pdf_processor.py
git commit -m "feat: add _inpaint_page for content-preserving watermark removal"
```

---

### Task 4: Collect watermark bounding boxes per page during detection

**Files:**
- Modify: `backend/services/pdf_processor.py`
- Test: `backend/tests/test_pdf_processor.py`

The current `detect_watermarks()` returns watermarks but not all of them have bbox info. We need bboxes for every watermark on every page to build accurate masks.

- [ ] **Step 1: Write the failing test**

Add to `test_pdf_processor.py`:

```python
@pytest.fixture
def image_page_studocu_pdf_path():
    """PDF mimicking StuDocu with image-based content pages."""
    import numpy as np
    import cv2

    path = os.path.join(tempfile.gettempdir(), "test_image_studocu.pdf")
    doc = fitz.open()

    for i in range(2):
        page = doc.new_page(width=842, height=596)
        # Content as image (simulating a cheat sheet)
        content = np.full((596, 842, 3), 220, dtype=np.uint8)
        cv2.putText(content, f"Content page {i+1}", (50, 300),
                    cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 0), 3)
        _, png = cv2.imencode(".png", content)
        page.insert_image(page.rect, stream=png.tobytes())
        # Watermark text
        page.insert_text((374, 580), "messages.downloaded_by", fontsize=8, color=(0.3, 0.3, 0.3))

    doc.save(path)
    doc.close()
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_detect_returns_bboxes_for_text_watermarks(processor, image_page_studocu_pdf_path):
    """Text watermarks should include bbox_by_page mapping."""
    doc = fitz.open(image_page_studocu_pdf_path)
    watermarks = processor.detect_watermarks(doc)
    doc.close()

    text_wms = [w for w in watermarks if w["type"] == "text"]
    assert len(text_wms) > 0

    # At least one watermark should have bbox_by_page
    has_bboxes = any("bbox_by_page" in w for w in text_wms)
    assert has_bboxes, "Text watermarks should include bbox_by_page mapping"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_detect_returns_bboxes_for_text_watermarks -v`
Expected: FAIL (no `bbox_by_page` key in current watermark dicts)

- [ ] **Step 3: Add `bbox_by_page` to watermark detection output**

Modify `detect_watermarks()` in `backend/services/pdf_processor.py`. After the deduplication step (line ~184), add a pass that enriches text watermarks with per-page bounding boxes by calling `page.search_for()`:

```python
# --- After deduplication (line ~195), before return ---
# Enrich text watermarks with per-page bounding boxes for targeted removal
for w in unique:
    if w["type"] == "text":
        bbox_by_page = {}
        for page_num, page in enumerate(doc):
            areas = page.search_for(w["text"])
            if areas:
                bbox_by_page[page_num] = [
                    (a.x0, a.y0, a.x1, a.y1) for a in areas
                ]
        w["bbox_by_page"] = bbox_by_page

return unique
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_detect_returns_bboxes_for_text_watermarks -v`
Expected: PASS

- [ ] **Step 5: Run ALL existing tests to ensure no regressions**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/pdf_processor.py backend/tests/test_pdf_processor.py
git commit -m "feat: enrich detected watermarks with per-page bounding boxes"
```

---

### Task 5: Rewrite `process()` to use smart removal strategy

**Files:**
- Modify: `backend/services/pdf_processor.py`
- Test: `backend/tests/test_pdf_processor.py`

- [ ] **Step 1: Write the failing test**

Add to `test_pdf_processor.py`:

```python
def test_process_image_page_no_white_boxes(processor, image_page_studocu_pdf_path):
    """Processing image-based pages should NOT produce white boxes over content."""
    import numpy as np
    import cv2

    output_dir = tempfile.mkdtemp()
    result = processor.process(image_page_studocu_pdf_path, output_dir)

    assert result["watermark_detected"] is True

    # Open the output and check the content area is preserved (not white)
    out_doc = fitz.open(result["output_path"])
    page = out_doc[0]
    pix = page.get_pixmap(dpi=72)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)

    # The watermark region (bottom of page, around y=560-590 in PDF coords)
    # Should NOT be pure white — inpainting should blend with surroundings
    wm_region = img[550:585, 370:470]  # Approximate watermark region in pixels at 72dpi
    mean_val = np.mean(wm_region)

    # Pure white = 255. Content background is ~220 (light gray).
    # After inpainting, the region should blend with surroundings (~220), not be pure white (255).
    assert mean_val < 250, (
        f"Watermark region mean={mean_val:.1f} — looks like a white box. "
        f"Expected inpainted content (~220)."
    )

    out_doc.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_process_image_page_no_white_boxes -v`
Expected: FAIL (current code produces white boxes)

- [ ] **Step 3: Rewrite `process()` method**

Replace the removal logic in `process()` with smart routing. Keep `_remove_text_watermarks` and `_remove_image_watermarks` for text-based pages. Add new path for image-based pages:

```python
def process(self, input_path: str, output_dir: str) -> dict:
    """Process a PDF file. Returns dict with output_path and watermark_detected."""
    doc = fitz.open(input_path)
    page_count = len(doc)

    if page_count > MAX_PDF_PAGES:
        doc.close()
        raise ValueError(
            f"PDF has {page_count} pages. Maximum is {MAX_PDF_PAGES} pages"
        )

    watermarks = self.detect_watermarks(doc)
    output_path = os.path.join(output_dir, "output.pdf")

    if not watermarks:
        doc.close()
        shutil.copy2(input_path, output_path)
        return {"output_path": output_path, "watermark_detected": False}

    # Check if any page with watermarks is image-based
    has_image_pages = any(
        self._is_image_based_page(doc[pno])
        for pno in range(len(doc))
    )

    doc.close()

    if has_image_pages:
        self._remove_watermarks_inpaint(input_path, output_path, watermarks)
    else:
        # Text-based pages: use fast redaction (preserves text selectability)
        text_watermarks = [w for w in watermarks if w["type"] == "text"]
        image_watermarks = [w for w in watermarks if w["type"] == "image"]

        if text_watermarks:
            self._remove_text_watermarks(input_path, output_path, watermarks)
            if image_watermarks:
                temp_path = output_path + ".tmp"
                os.rename(output_path, temp_path)
                self._remove_image_watermarks(temp_path, output_path, watermarks)
                os.remove(temp_path)
        elif image_watermarks:
            self._remove_image_watermarks(input_path, output_path, watermarks)

    return {"output_path": output_path, "watermark_detected": True}
```

- [ ] **Step 4: Implement `_remove_watermarks_inpaint`**

Add to `PdfProcessor` class:

```python
def _remove_watermarks_inpaint(
    self, input_path: str, output_path: str, watermarks: list[dict]
) -> None:
    """Remove watermarks using targeted inpainting. Preserves content under watermarks."""
    import cv2

    doc = fitz.open(input_path)
    output_doc = fitz.open()
    dpi = 150

    for page_num, page in enumerate(doc):
        # Collect watermark bboxes for this page
        wm_bboxes = []
        for w in watermarks:
            if w["type"] == "text" and "bbox_by_page" in w:
                bboxes = w["bbox_by_page"].get(page_num, [])
                for bbox in bboxes:
                    wm_bboxes.append({"type": "text", "bbox": bbox})
            elif w["type"] == "image" and page_num in w.get("pages", []):
                # Match exact image blocks by comparing rounded signatures
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

        if wm_bboxes and self._is_image_based_page(page):
            # Inpaint this page
            img_bgr = self._inpaint_page(page, wm_bboxes, dpi=dpi)
            new_page = output_doc.new_page(
                width=page.rect.width, height=page.rect.height
            )
            _, png_bytes = cv2.imencode(".png", img_bgr)
            new_page.insert_image(new_page.rect, stream=png_bytes.tobytes())
        elif wm_bboxes:
            # Text-based page with watermarks: use redaction
            output_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            out_page = output_doc[-1]
            for w in watermarks:
                if w["type"] == "text":
                    areas = out_page.search_for(w["text"])
                    for area in areas:
                        out_page.add_redact_annot(area, fill=(1, 1, 1))
                elif w["type"] == "image" and page_num in w.get("pages", []):
                    sig = w["bbox_signature"]
                    rect = fitz.Rect(sig[0], sig[1], sig[0] + sig[2], sig[1] + sig[3])
                    out_page.add_redact_annot(rect, fill=(1, 1, 1))
            out_page.apply_redactions()
        else:
            # No watermarks on this page: copy as-is
            output_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

    output_doc.save(output_path)
    output_doc.close()
    doc.close()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_process_image_page_no_white_boxes -v`
Expected: PASS

- [ ] **Step 6: Run ALL tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add backend/services/pdf_processor.py backend/tests/test_pdf_processor.py
git commit -m "feat: smart watermark removal with inpainting for image-based pages"
```

---

## Chunk 2: Integration Testing & Edge Cases

### Task 6: Test with the real StuDocu PDF

- [ ] **Step 1: Run full pipeline on the real PDF**

```bash
cd backend && python -c "
from services.pdf_processor import PdfProcessor
import tempfile, os
proc = PdfProcessor()
with tempfile.TemporaryDirectory() as d:
    result = proc.process(r'C:\Users\yjkim\Downloads\cs2106-midterm-cheat-sheet-operating-system-caller-stack-management (1).pdf', d)
    print(f'Detected: {result[\"watermark_detected\"]}')
    size = os.path.getsize(result['output_path'])
    print(f'Output size: {size//1024}KB')
    # Copy to Desktop for manual inspection
    import shutil
    out = os.path.expanduser('~/Desktop/watermark_removed_test.pdf')
    shutil.copy2(result['output_path'], out)
    print(f'Saved to: {out}')
"
```

- [ ] **Step 2: Manually inspect the output PDF**

Open `~/Desktop/watermark_removed_test.pdf` and verify:
- No white boxes where watermarks were
- Content underneath watermark regions is preserved/blended
- Cover page (page 0) watermark text is removed
- StuDocu banner on page 1 is removed without destroying content

### Task 7: Edge case — mixed text-only and image pages

- [ ] **Step 1: Write test for mixed PDF**

Add to `test_pdf_processor.py`:

```python
def test_process_mixed_pdf_handles_both_page_types(processor):
    """PDFs with both text-only and image-based pages should use appropriate strategy per page."""
    import numpy as np
    import cv2

    path = os.path.join(tempfile.gettempdir(), "test_mixed.pdf")
    doc = fitz.open()

    # Page 0: text-only with watermark
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 72), "Text content page.", fontsize=12)
    page.insert_text((200, 800), "messages.downloaded_by", fontsize=8, color=(0.3, 0.3, 0.3))

    # Page 1: image-based with watermark
    page = doc.new_page(width=842, height=596)
    content = np.full((596, 842, 3), 200, dtype=np.uint8)
    _, png = cv2.imencode(".png", content)
    page.insert_image(page.rect, stream=png.tobytes())
    page.insert_text((374, 580), "messages.downloaded_by", fontsize=8, color=(0.3, 0.3, 0.3))

    doc.save(path)
    doc.close()

    output_dir = tempfile.mkdtemp()
    result = processor.process(path, output_dir)
    assert result["watermark_detected"] is True
    assert os.path.exists(result["output_path"])

    # Verify output has 2 pages
    out_doc = fitz.open(result["output_path"])
    assert len(out_doc) == 2
    out_doc.close()

    os.remove(path)
```

- [ ] **Step 2: Run test**

Run: `cd backend && python -m pytest tests/test_pdf_processor.py::test_process_mixed_pdf_handles_both_page_types -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_pdf_processor.py
git commit -m "test: add edge case tests for mixed page types and real PDF"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `backend/services/pdf_processor.py` | Add `_is_image_based_page()`, `_build_watermark_mask()`, `_inpaint_page()`, `_remove_watermarks_inpaint()`. Modify `detect_watermarks()` to include `bbox_by_page`. Modify `process()` to route to inpainting for image-based pages. |
| `backend/tests/test_pdf_processor.py` | Add 5 new tests: page classification, mask building, content preservation, white box absence, mixed pages. |
