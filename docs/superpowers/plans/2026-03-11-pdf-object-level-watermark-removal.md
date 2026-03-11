# PDF Object-Level Watermark Removal Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace rasterization-based watermark removal with PDF-object-level manipulation using pypdf, preserving all original content, fonts, images, and formatting without ever flattening the PDF.

**Architecture:** Create a new `pdf_watermark_remover.py` module that operates directly on PDF objects using pypdf. It implements 4 removal methods targeting different watermark injection techniques: separate content streams, annotation-based, inline content stream operators, and XObject overlays. Detection uses content-stream parsing (text extraction, color analysis, cross-page repetition) plus known platform fingerprints. The existing fitz-based detection in `pdf_processor.py` remains as the "should we clean?" gate and UI indicator; `process()` delegates actual removal to the new module. Old fitz/OpenCV removal methods are deleted.

**Tech Stack:** pypdf 4.x+ (PDF object manipulation), PyMuPDF/fitz (detection + preview, existing), FastAPI (API layer, existing)

---

## Architectural Overview

### Current Flow (being replaced)
```
pdf_processor.process()
  → detect_watermarks() [fitz, 5-strategy]
  → _remove_watermarks_inpaint() [fitz + OpenCV rasterization]
     → Rasterize page → Build mask → cv2.inpaint → Re-embed as PNG
     ❌ Destroys text selectability
     ❌ Creates white boxes from inpainting
     ❌ 10-20x output file inflation
```

### New Flow
```
pdf_processor.process()
  → detect_watermarks() [fitz, 5-strategy — UNCHANGED]
  → pdf_watermark_remover.remove_watermark(pdf_bytes)
     → Method 2: Remove /Watermark annotations
     → Method 4: Remove watermark XObject overlays
     → Method 1: Remove watermark content streams from /Contents arrays
     → Method 3: Remove inline watermark operators from content streams
     ✅ Preserves text selectability
     ✅ Preserves all fonts, images, formatting
     ✅ Minimal output size change
```

### Limitation
Raster-embedded watermarks (watermarks burned into JPEG/PNG pixel data inside the PDF) cannot be removed at the PDF object level. These require image-level inpainting, which is out of scope for this plan.

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `backend/services/pdf_watermark_remover.py` | CREATE | Core pypdf-based watermark removal (4 methods) |
| `backend/tests/test_pdf_watermark_remover.py` | CREATE | Tests for new module |
| `backend/services/pdf_processor.py` | MODIFY | Use new remover, delete old removal methods |
| `backend/tests/test_pdf_processor.py` | MODIFY | Remove inpainting tests, update integration tests |
| `backend/requirements.txt` | MODIFY | Add pypdf dependency |

---

## Chunk 1: Core Module + Detection + Methods 2 & 3

### Task 1: Module skeleton with helpers, constants, and detection

**Files:**
- Create: `backend/services/pdf_watermark_remover.py`
- Create: `backend/tests/test_pdf_watermark_remover.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 0: Add pypdf dependency**

Add to `backend/requirements.txt`:

```
pypdf>=4.0.0
```

Run: `cd backend && source .venv/Scripts/activate && pip install "pypdf>=4.0.0"`
Expected: Successfully installed (or already satisfied)

- [ ] **Step 1: Write failing tests for text extraction and watermark classification**

Create `backend/tests/test_pdf_watermark_remover.py`:

```python
import io
import os
import tempfile

import fitz
import pytest

from services.pdf_watermark_remover import (
    _extract_text_from_block,
    _is_watermark_text,
    _is_light_color,
    _should_remove_block,
    _collect_cross_page_texts,
    remove_watermark,
)


class TestExtractText:
    def test_extract_from_tj(self):
        from pypdf.generic import TextStringObject

        ops = [
            ([], b"BT"),
            ([TextStringObject("Hello world")], b"Tj"),
            ([], b"ET"),
        ]
        assert _extract_text_from_block(ops) == "Hello world"

    def test_extract_from_tj_array(self):
        from pypdf.generic import ArrayObject, NumberObject, TextStringObject

        arr = ArrayObject(
            [TextStringObject("He"), NumberObject(-50), TextStringObject("llo")]
        )
        ops = [
            ([], b"BT"),
            ([arr], b"TJ"),
            ([], b"ET"),
        ]
        assert _extract_text_from_block(ops) == "Hello"

    def test_empty_block(self):
        ops = [([], b"BT"), ([], b"ET")]
        assert _extract_text_from_block(ops) == ""


class TestIsWatermarkText:
    def test_studocu_pattern(self):
        assert _is_watermark_text("messages.downloaded_by") is True

    def test_tracking_id(self):
        assert _is_watermark_text("lOMoARcPSD|12930651") is True

    def test_normal_text(self):
        assert _is_watermark_text("This is normal content.") is False

    def test_classic_watermark(self):
        assert _is_watermark_text("CONFIDENTIAL") is True
        assert _is_watermark_text("DRAFT") is True

    def test_cross_page_text(self):
        cross = {"Custom footer text"}
        assert _is_watermark_text("Custom footer text", cross) is True

    def test_short_text_ignored(self):
        assert _is_watermark_text("ab") is False

    def test_page_number_ignored(self):
        assert _is_watermark_text("42") is False


class TestIsLightColor:
    def test_light_gray(self):
        assert _is_light_color((0.8, 0.8, 0.8)) is True

    def test_dark_color(self):
        assert _is_light_color((0.3, 0.3, 0.3)) is False

    def test_none(self):
        assert _is_light_color(None) is False

    def test_black(self):
        assert _is_light_color((0.0, 0.0, 0.0)) is False


class TestShouldRemoveBlock:
    def test_removes_platform_pattern(self):
        assert _should_remove_block("messages.downloaded_by", None, 8, set()) is True

    def test_removes_classic_keyword(self):
        assert _should_remove_block("CONFIDENTIAL", None, 48, set()) is True

    def test_removes_tracking_id_small_font_cross_page(self):
        cross = {"lOMoARcPSD|12930651"}
        assert _should_remove_block("lOMoARcPSD|12930651", None, 1, cross) is True

    def test_removes_cross_page_light_color(self):
        cross = {"Custom branding footer"}
        assert _should_remove_block("Custom branding footer", (0.8, 0.8, 0.8), 10, cross) is True

    def test_removes_large_light_non_keyword_text(self):
        """Large (>24pt) light-colored text should be removed even without keyword match."""
        assert _should_remove_block("Property of ACME Corp", (0.85, 0.85, 0.85), 48, set()) is True

    def test_keeps_normal_dark_text(self):
        assert _should_remove_block("Normal content text.", (0, 0, 0), 12, set()) is False

    def test_keeps_page_number(self):
        cross = {"42"}
        assert _should_remove_block("42", None, 10, cross) is False

    def test_keeps_empty_text(self):
        assert _should_remove_block("", None, 12, set()) is False


class TestCollectCrossPageTexts:
    def test_finds_repeated_text(self):
        path = os.path.join(tempfile.gettempdir(), "test_cross_page.pdf")
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page {i+1} unique content", fontsize=12)
            page.insert_text(
                (200, 800), "Repeated watermark text", fontsize=8
            )
        doc.save(path)
        doc.close()

        with open(path, "rb") as f:
            pdf_bytes = f.read()

        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter(clone_from=reader)

        cross = _collect_cross_page_texts(writer)
        assert "Repeated watermark text" in cross
        os.remove(path)

    def test_single_page_returns_empty(self):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Single page content", fontsize=12)
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()

        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(buf.getvalue()))
        writer = PdfWriter(clone_from=reader)

        cross = _collect_cross_page_texts(writer)
        assert len(cross) == 0


class TestRemoveWatermarkPassthrough:
    def test_clean_pdf_returns_valid(self):
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Clean content only.", fontsize=12)
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()

        result = remove_watermark(buf.getvalue())

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(result))
        assert len(reader.pages) == 1

    def test_encrypted_pdf_returns_as_is(self):
        """Password-protected PDFs that can't be decrypted return unchanged."""
        from pypdf import PdfWriter as PW

        pw = PW()
        pw.add_blank_page(width=595, height=842)
        pw.encrypt("secretpassword")
        buf = io.BytesIO()
        pw.write(buf)

        original_bytes = buf.getvalue()
        result = remove_watermark(original_bytes)
        assert result == original_bytes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_pdf_watermark_remover.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.pdf_watermark_remover'`

- [ ] **Step 3: Create module with helpers, constants, and skeleton**

Create `backend/services/pdf_watermark_remover.py`:

```python
"""PDF object-level watermark removal using pypdf.

Operates directly on PDF objects (content streams, annotations, XObjects)
to remove watermarks without rasterizing. Preserves all original content,
fonts, images, and formatting.
"""

import io
import re
from collections import Counter

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

# Known watermark platform patterns
PLATFORM_PATTERNS = re.compile(
    r"(studocu|scribd|coursehero|chegg|bartleby|"
    r"lOMoARcPSD|"
    r"messages\.downloaded_by|messages\.pdf_cover|messages\.studocu|"
    r"downloaded\s+by|uploaded\s+by|"
    r"this\s+document\s+is\s+available\s+on|"
    r"get\s+the\s+app|"
    r"not[\s_]sponsored[\s_]or[\s_]endorsed)",
    re.IGNORECASE,
)

# Classic watermark keywords
CLASSIC_WATERMARK_PATTERNS = re.compile(
    r"\b(DRAFT|CONFIDENTIAL|SAMPLE|COPY|DO NOT DISTRIBUTE|WATERMARK|PREVIEW)\b",
    re.IGNORECASE,
)

# Tracking ID pattern (alphanumeric with pipes/dashes, 8+ chars)
TRACKING_ID_PATTERN = re.compile(r"^[A-Za-z0-9|_-]{8,}$")

# Legitimate repeated text to ignore
IGNORE_COMMON_TEXT = re.compile(
    r"^(\d{1,4}|[ivxlcdm]+|page\s*\d+|©.*|\s*)$",
    re.IGNORECASE,
)


def _extract_text_from_block(block_ops):
    """Extract readable text from a list of content stream operations (BT...ET block)."""
    texts = []
    for operands, operator in block_ops:
        if operator == b"Tj" and operands:
            texts.append(str(operands[0]))
        elif operator == b"TJ" and operands:
            for item in operands[0]:
                if isinstance(item, (int, float, NumberObject)):
                    continue  # kerning adjustment
                texts.append(str(item))
        elif operator in (b"'", b'"') and operands:
            texts.append(str(operands[-1]))
    return "".join(texts)


def _is_light_color(color):
    """Check if a color is light (likely watermark gray/white)."""
    if color is None:
        return False
    return all(c > 0.7 for c in color)


def _is_watermark_text(text, cross_page_texts=None):
    """Determine if text is a watermark based on content heuristics."""
    text = text.strip()
    if not text or len(text) <= 2:
        return False
    if IGNORE_COMMON_TEXT.match(text):
        return False

    # Known platform patterns
    if PLATFORM_PATTERNS.search(text):
        return True

    # Classic watermark keywords
    if CLASSIC_WATERMARK_PATTERNS.search(text):
        return True

    # Cross-page repeated text
    if cross_page_texts and text in cross_page_texts:
        return True

    return False


def _should_remove_block(text, color, font_size, cross_page_texts):
    """Decide whether a text block should be removed from the content stream."""
    text = text.strip()
    if not text:
        return False

    # Platform patterns — always remove
    if PLATFORM_PATTERNS.search(text):
        return True

    # Classic watermark keywords — always remove
    if CLASSIC_WATERMARK_PATTERNS.search(text):
        return True

    # Tracking IDs: very small font, alphanumeric, on every page
    if (
        TRACKING_ID_PATTERN.match(text)
        and font_size is not None
        and font_size <= 2
        and cross_page_texts
        and text in cross_page_texts
    ):
        return True

    # Cross-page repeated text that's light-colored
    if cross_page_texts and text in cross_page_texts and _is_light_color(color):
        return True

    # Cross-page repeated text with small font (watermark footers)
    if (
        cross_page_texts
        and text in cross_page_texts
        and font_size is not None
        and font_size <= 10
        and not IGNORE_COMMON_TEXT.match(text)
    ):
        return True

    # Large light-colored text (classic overlaid watermarks like "DRAFT")
    if _is_light_color(color) and font_size is not None and font_size > 24:
        return True

    return False


def _collect_cross_page_texts(writer):
    """Find text that appears on every page of the document."""
    if len(writer.pages) <= 1:
        return set()

    page_texts = []
    for page in writer.pages:
        try:
            content = page.get_contents()
        except Exception:
            page_texts.append(set())
            continue

        if content is None:
            page_texts.append(set())
            continue

        texts = set()
        try:
            ops = content.operations
            i = 0
            while i < len(ops):
                if ops[i][1] == b"BT":
                    block = [ops[i]]
                    i += 1
                    while i < len(ops) and ops[i][1] != b"ET":
                        block.append(ops[i])
                        i += 1
                    if i < len(ops):
                        block.append(ops[i])
                        i += 1
                    text = _extract_text_from_block(block).strip()
                    if text and len(text) > 2 and not IGNORE_COMMON_TEXT.match(text):
                        texts.add(text)
                else:
                    i += 1
        except Exception:
            pass

        page_texts.append(texts)

    common = page_texts[0]
    for texts in page_texts[1:]:
        common = common & texts

    return common


def _remove_watermark_annotations(writer):
    """Method 2: Remove watermark annotations from all pages."""
    pass


def _remove_watermark_streams(writer, cross_page_texts):
    """Method 1: Remove watermark-containing content streams from /Contents arrays."""
    pass


def _remove_inline_watermarks(writer, cross_page_texts):
    """Method 3: Remove inline watermark operators from content streams."""
    pass


def _remove_watermark_xobjects(writer, cross_page_texts):
    """Method 4: Remove watermark XObject overlays."""
    pass


def remove_watermark(input_pdf_bytes: bytes) -> bytes:
    """Remove watermarks from a PDF. Returns cleaned PDF bytes.

    Handles 4 watermark injection methods:
    1. Separate content streams (last stream often contains watermark)
    2. Annotation-based watermarks (/Watermark subtype, platform URIs)
    3. Inline watermarks in content stream (text operators with known patterns)
    4. Page-level XObject overlays (Form XObjects with watermark content)

    Never rasterizes — works at the PDF object level to preserve all
    original content, fonts, images, and formatting.
    """
    reader = PdfReader(io.BytesIO(input_pdf_bytes))

    # Handle encrypted PDFs
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            return input_pdf_bytes  # Can't decrypt, return as-is

    writer = PdfWriter(clone_from=reader)

    # Analyze cross-page text patterns
    cross_page_texts = _collect_cross_page_texts(writer)

    # Apply removal methods (order matters: annotations first, inline last)
    _remove_watermark_annotations(writer)
    _remove_watermark_xobjects(writer, cross_page_texts)
    _remove_watermark_streams(writer, cross_page_texts)
    _remove_inline_watermarks(writer, cross_page_texts)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_pdf_watermark_remover.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/pdf_watermark_remover.py backend/tests/test_pdf_watermark_remover.py
git commit -m "feat: add pdf_watermark_remover module skeleton with detection helpers"
```

---

### Task 2: Method 2 — Annotation-based watermark removal

**Files:**
- Modify: `backend/services/pdf_watermark_remover.py` (implement `_remove_watermark_annotations`)
- Modify: `backend/tests/test_pdf_watermark_remover.py`

- [ ] **Step 1: Write failing test for annotation removal**

Add to `backend/tests/test_pdf_watermark_remover.py`:

```python
class TestRemoveWatermarkAnnotations:
    def test_removes_watermark_subtype_annotation(self):
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import (
            ArrayObject,
            DictionaryObject,
            NameObject,
            NumberObject,
            TextStringObject,
        )

        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        page = writer.pages[0]

        # Add /Watermark annotation
        annot = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Watermark"),
                NameObject("/Rect"): ArrayObject(
                    [NumberObject(0), NumberObject(0), NumberObject(595), NumberObject(842)]
                ),
                NameObject("/Contents"): TextStringObject("CONFIDENTIAL"),
            }
        )
        annot_ref = writer._add_object(annot)
        page[NameObject("/Annots")] = ArrayObject([annot_ref])

        buf = io.BytesIO()
        writer.write(buf)

        result = remove_watermark(buf.getvalue())

        reader = PdfReader(io.BytesIO(result))
        annots = reader.pages[0].get("/Annots")
        assert annots is None or len(annots) == 0

    def test_preserves_non_watermark_annotations(self):
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import (
            ArrayObject,
            DictionaryObject,
            NameObject,
            NumberObject,
            TextStringObject,
        )

        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        page = writer.pages[0]

        # Add a /Link annotation (not watermark)
        link_annot = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/Rect"): ArrayObject(
                    [NumberObject(72), NumberObject(700), NumberObject(200), NumberObject(720)]
                ),
            }
        )
        link_ref = writer._add_object(link_annot)
        page[NameObject("/Annots")] = ArrayObject([link_ref])

        buf = io.BytesIO()
        writer.write(buf)

        result = remove_watermark(buf.getvalue())

        reader = PdfReader(io.BytesIO(result))
        annots = reader.pages[0].get("/Annots")
        assert annots is not None and len(annots) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_pdf_watermark_remover.py::TestRemoveWatermarkAnnotations -v`
Expected: FAIL (first test — annotation not removed because method is `pass`)

- [ ] **Step 3: Implement `_remove_watermark_annotations`**

Replace the stub in `backend/services/pdf_watermark_remover.py`:

```python
def _remove_watermark_annotations(writer):
    """Method 2: Remove watermark annotations from all pages.

    Targets:
    - /Subtype /Watermark annotations
    - /Stamp annotations containing watermark text
    - Annotations with platform-specific URIs (studocu.com, etc.)
    """
    for page in writer.pages:
        if "/Annots" not in page:
            continue

        try:
            annots = page["/Annots"]
            if not isinstance(annots, ArrayObject):
                annots = annots.get_object()
            if not isinstance(annots, ArrayObject):
                continue
        except Exception:
            continue

        indices_to_remove = []
        for i in range(len(annots)):
            try:
                annot = annots[i].get_object()
            except Exception:
                continue

            subtype = str(annot.get("/Subtype", ""))

            # /Watermark subtype
            if subtype == "/Watermark":
                indices_to_remove.append(i)
                continue

            # /Stamp with watermark content
            if subtype == "/Stamp":
                contents = str(annot.get("/Contents", ""))
                nm = str(annot.get("/NM", ""))
                if PLATFORM_PATTERNS.search(contents) or PLATFORM_PATTERNS.search(nm):
                    indices_to_remove.append(i)
                    continue
                if CLASSIC_WATERMARK_PATTERNS.search(contents):
                    indices_to_remove.append(i)
                    continue

            # URI-based platform links
            if "/A" in annot:
                try:
                    action = annot["/A"].get_object()
                    uri = str(action.get("/URI", ""))
                    if any(
                        d in uri
                        for d in [
                            "studocu.com",
                            "coursehero.com",
                            "scribd.com",
                            "chegg.com",
                            "bartleby.com",
                        ]
                    ):
                        indices_to_remove.append(i)
                        continue
                except Exception:
                    pass

        # Remove in reverse order to preserve indices
        for i in reversed(indices_to_remove):
            del annots[i]

        if len(annots) == 0:
            del page[NameObject("/Annots")]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_pdf_watermark_remover.py::TestRemoveWatermarkAnnotations -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/pdf_watermark_remover.py backend/tests/test_pdf_watermark_remover.py
git commit -m "feat: implement annotation-based watermark removal (Method 2)"
```

---

### Task 3: Method 3 — Inline watermark removal from content streams

This is the most impactful method — handles StuDocu/Scribd tracking IDs and "downloaded by" text embedded directly in content streams.

**Files:**
- Modify: `backend/services/pdf_watermark_remover.py` (implement `_remove_inline_watermarks`)
- Modify: `backend/tests/test_pdf_watermark_remover.py`

- [ ] **Step 1: Write failing test for StuDocu inline watermark removal**

Add to `backend/tests/test_pdf_watermark_remover.py`:

```python
from pypdf import PdfReader


class TestRemoveInlineWatermarks:
    def test_removes_studocu_watermark_text(self):
        """StuDocu platform fingerprints in content stream should be removed."""
        doc = fitz.open()
        for _ in range(3):
            page = doc.new_page()
            page.insert_text((72, 72), "Normal content here.", fontsize=12)
            page.insert_text(
                (200, 800),
                "messages.downloaded_by",
                fontsize=8,
                color=(0.3, 0.3, 0.3),
            )
            page.insert_text((250, 10), "lOMoARcPSD|12930651", fontsize=1)
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()

        result = remove_watermark(buf.getvalue())

        reader = PdfReader(io.BytesIO(result))
        for page in reader.pages:
            text = page.extract_text()
            assert "messages.downloaded_by" not in text
            assert "lOMoARcPSD" not in text

    def test_preserves_normal_content(self):
        """Normal text content must survive watermark removal."""
        doc = fitz.open()
        for _ in range(3):
            page = doc.new_page()
            page.insert_text((72, 72), "Important content to keep.", fontsize=12)
            page.insert_text(
                (200, 800),
                "messages.downloaded_by",
                fontsize=8,
                color=(0.3, 0.3, 0.3),
            )
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()

        result = remove_watermark(buf.getvalue())

        reader = PdfReader(io.BytesIO(result))
        for page in reader.pages:
            text = page.extract_text()
            assert "Important content to keep" in text

    def test_removes_classic_large_light_watermark(self):
        """Large light-colored text like CONFIDENTIAL/DRAFT should be removed."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Normal content.", fontsize=12)
        page.insert_text(
            (100, 400), "CONFIDENTIAL", fontsize=48, color=(0.8, 0.8, 0.8)
        )
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()

        result = remove_watermark(buf.getvalue())

        reader = PdfReader(io.BytesIO(result))
        text = reader.pages[0].extract_text()
        assert "CONFIDENTIAL" not in text
        assert "Normal content" in text

    def test_removes_large_light_non_keyword_watermark(self):
        """Large light custom text (not a classic keyword) should be removed."""
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Normal content.", fontsize=12)
        page.insert_text(
            (100, 400), "Property of ACME Corp", fontsize=48, color=(0.85, 0.85, 0.85)
        )
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()

        result = remove_watermark(buf.getvalue())

        reader = PdfReader(io.BytesIO(result))
        text = reader.pages[0].extract_text()
        assert "Property of ACME Corp" not in text
        assert "Normal content" in text

    def test_preserves_page_count(self):
        """Output PDF should have same number of pages as input."""
        doc = fitz.open()
        for i in range(5):
            page = doc.new_page()
            page.insert_text((72, 72), f"Page {i+1}", fontsize=12)
            page.insert_text(
                (200, 800), "messages.downloaded_by", fontsize=8
            )
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()

        result = remove_watermark(buf.getvalue())

        reader = PdfReader(io.BytesIO(result))
        assert len(reader.pages) == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_pdf_watermark_remover.py::TestRemoveInlineWatermarks -v`
Expected: FAIL — watermark text still present in output

- [ ] **Step 3: Implement `_remove_inline_watermarks`**

Replace the stub in `backend/services/pdf_watermark_remover.py`:

```python
def _remove_inline_watermarks(writer, cross_page_texts):
    """Method 3: Remove inline watermark operators from content streams.

    Parses each page's content stream into BT...ET text blocks.
    For each block, extracts text and checks against watermark heuristics
    (known patterns, cross-page repetition, light color, small font).
    Removes entire BT...ET blocks identified as watermarks.
    Non-text operators (images, paths, graphics) are never touched.
    """
    for page in writer.pages:
        try:
            content = page.get_contents()
        except Exception:
            continue
        if content is None:
            continue

        try:
            ops = content.operations
        except Exception:
            continue

        new_ops = []
        # Track graphics state for color/font detection
        current_color = None
        current_font_size = None
        state_stack = []

        i = 0
        while i < len(ops):
            operands, operator = ops[i]

            # Track graphics state stack (q saves, Q restores)
            if operator == b"q":
                state_stack.append((current_color, current_font_size))
                new_ops.append((operands, operator))
                i += 1
                continue
            elif operator == b"Q":
                if state_stack:
                    current_color, current_font_size = state_stack.pop()
                new_ops.append((operands, operator))
                i += 1
                continue

            # Track fill color outside text blocks
            if operator == b"rg" and len(operands) == 3:
                try:
                    current_color = tuple(float(o) for o in operands)
                except (TypeError, ValueError):
                    pass
            elif operator == b"g" and len(operands) == 1:
                try:
                    gray = float(operands[0])
                    current_color = (gray, gray, gray)
                except (TypeError, ValueError):
                    pass

            # Track font size outside text blocks
            if operator == b"Tf" and len(operands) >= 2:
                try:
                    current_font_size = float(operands[1])
                except (TypeError, ValueError):
                    pass

            # Collect entire BT...ET text block
            if operator == b"BT":
                block = [(operands, operator)]
                block_color = current_color
                block_font_size = current_font_size
                i += 1

                while i < len(ops) and ops[i][1] != b"ET":
                    inner_operands, inner_op = ops[i]
                    block.append((inner_operands, inner_op))

                    # Track state changes within block
                    if inner_op == b"rg" and len(inner_operands) == 3:
                        try:
                            block_color = tuple(float(o) for o in inner_operands)
                        except (TypeError, ValueError):
                            pass
                    elif inner_op == b"g" and len(inner_operands) == 1:
                        try:
                            gray = float(inner_operands[0])
                            block_color = (gray, gray, gray)
                        except (TypeError, ValueError):
                            pass
                    elif inner_op == b"Tf" and len(inner_operands) >= 2:
                        try:
                            block_font_size = float(inner_operands[1])
                        except (TypeError, ValueError):
                            pass

                    i += 1

                # Include the ET operator
                if i < len(ops):
                    block.append(ops[i])
                    i += 1

                # Extract text and decide whether to remove
                text = _extract_text_from_block(block)
                if _should_remove_block(
                    text, block_color, block_font_size, cross_page_texts
                ):
                    continue  # Skip entire BT...ET block
                else:
                    new_ops.extend(block)
                    continue

            new_ops.append((operands, operator))
            i += 1

        content.operations = new_ops
        page.replace_contents(content)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_pdf_watermark_remover.py::TestRemoveInlineWatermarks -v`
Expected: ALL PASS

- [ ] **Step 5: Run all module tests**

Run: `cd backend && python -m pytest tests/test_pdf_watermark_remover.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/pdf_watermark_remover.py backend/tests/test_pdf_watermark_remover.py
git commit -m "feat: implement inline watermark removal from content streams (Method 3)"
```

---

## Chunk 2: Methods 1 & 4 + Integration

### Task 4: Method 1 — Separate content stream removal + Method 4 — XObject overlay removal

**Files:**
- Modify: `backend/services/pdf_watermark_remover.py`
- Modify: `backend/tests/test_pdf_watermark_remover.py`

- [ ] **Step 1: Write tests for stream and XObject detection**

Add to `backend/tests/test_pdf_watermark_remover.py`:

```python
from services.pdf_watermark_remover import _is_watermark_stream  # add to existing import block


class TestRemoveWatermarkStreams:
    def test_detects_watermark_stream(self):
        """Stream containing only watermark text should be detected."""
        data = b"BT /F1 8 Tf 200 800 Td (messages.downloaded_by) Tj ET"
        cross = {"messages.downloaded_by"}
        assert _is_watermark_stream(data, cross) is True

    def test_normal_stream_not_detected(self):
        """Stream with normal content should not be detected."""
        data = b"BT /F1 12 Tf 72 700 Td (Normal content here) Tj ET"
        assert _is_watermark_stream(data, set()) is False

    def test_multi_stream_pdf_removes_watermark_stream(self):
        """Watermark in separate content stream should be removed."""
        from pypdf import PdfWriter as PW
        from pypdf.generic import (
            ArrayObject,
            DecodedStreamObject,
            DictionaryObject,
            NameObject,
        )

        pw = PW()
        pw.add_blank_page(width=595, height=842)
        page = pw.pages[0]

        # Main content stream
        main = DecodedStreamObject()
        main.set_data(b"BT /F1 12 Tf 72 700 Td (Normal content) Tj ET")
        main_ref = pw._add_object(main)

        # Watermark stream
        wm = DecodedStreamObject()
        wm.set_data(
            b"BT /F1 8 Tf 200 800 Td (messages.downloaded_by) Tj ET"
        )
        wm_ref = pw._add_object(wm)

        page[NameObject("/Contents")] = ArrayObject([main_ref, wm_ref])

        # Add font resources
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        font_ref = pw._add_object(font)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_ref}
                )
            }
        )

        buf = io.BytesIO()
        pw.write(buf)

        result = remove_watermark(buf.getvalue())

        reader = PdfReader(io.BytesIO(result))
        text = reader.pages[0].extract_text()
        # Normal content should survive
        assert "Normal content" in text
        # Watermark should be gone (removed either by stream removal or inline)
        assert "messages.downloaded_by" not in text


class TestRemoveWatermarkXObjects:
    def test_removes_watermark_form_xobject(self):
        """Form XObject containing watermark text should be removed."""
        from pypdf import PdfWriter as PW
        from pypdf.generic import (
            ArrayObject,
            DecodedStreamObject,
            DictionaryObject,
            NameObject,
            NumberObject,
        )

        pw = PW()
        pw.add_blank_page(width=595, height=842)
        page = pw.pages[0]

        # Watermark Form XObject
        form = DecodedStreamObject()
        form.set_data(
            b"BT /F1 48 Tf 0.8 0.8 0.8 rg 100 400 Td (WATERMARK) Tj ET"
        )
        form[NameObject("/Type")] = NameObject("/XObject")
        form[NameObject("/Subtype")] = NameObject("/Form")
        form[NameObject("/BBox")] = ArrayObject(
            [NumberObject(0), NumberObject(0), NumberObject(595), NumberObject(842)]
        )
        form_ref = pw._add_object(form)

        # Font resource
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        font_ref = pw._add_object(font)

        # Content stream that draws XObject then normal text
        content = DecodedStreamObject()
        content.set_data(
            b"q /WM0 Do Q BT /F1 12 Tf 72 700 Td (Normal content) Tj ET"
        )
        content_ref = pw._add_object(content)
        page[NameObject("/Contents")] = content_ref

        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_ref}
                ),
                NameObject("/XObject"): DictionaryObject(
                    {NameObject("/WM0"): form_ref}
                ),
            }
        )

        buf = io.BytesIO()
        pw.write(buf)

        result = remove_watermark(buf.getvalue())

        reader = PdfReader(io.BytesIO(result))
        page_out = reader.pages[0]

        # Watermark XObject should be removed from resources
        xobjects = page_out.get("/Resources", {}).get("/XObject")
        if xobjects:
            assert "/WM0" not in xobjects
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_pdf_watermark_remover.py::TestRemoveWatermarkStreams tests/test_pdf_watermark_remover.py::TestRemoveWatermarkXObjects -v`
Expected: FAIL

- [ ] **Step 3: Implement `_is_watermark_stream` and `_remove_watermark_streams`**

Replace the stub in `backend/services/pdf_watermark_remover.py`. Also add the `_is_watermark_stream` function (new public helper):

```python
def _is_watermark_stream(data: bytes, cross_page_texts: set) -> bool:
    """Check if a content stream contains only watermark content.

    Uses byte-level scanning for platform markers, then extracts text
    via regex to verify all content is watermark-related.
    """
    data_lower = data.lower()

    # Must contain known markers
    markers = [
        b"downloaded_by", b"lomoarcpsd", b"studocu", b"coursehero",
        b"scribd", b"chegg", b"bartleby", b"not_sponsored",
    ]
    if not any(m in data_lower for m in markers):
        return False

    # Extract parenthesized strings (PDF text operands)
    texts = re.findall(rb"\(([^)]*)\)", data)
    if not texts:
        return True  # Has marker bytes but no extractable text

    # Check if ALL extracted text is watermark-related
    for text_bytes in texts:
        text = text_bytes.decode("latin-1", errors="ignore").strip()
        if not text:
            continue
        if not _is_watermark_text(text, cross_page_texts):
            return False  # Found non-watermark text — keep the stream

    return True


def _remove_watermark_streams(writer, cross_page_texts):
    """Method 1: Remove watermark-containing content streams from /Contents arrays.

    When a page's /Contents is an ArrayObject with multiple streams,
    scans each stream for watermark-only content and removes it.
    Only removes streams where ALL text is watermark-related.
    Single-stream pages are handled by Method 3 (inline removal).
    """
    for page in writer.pages:
        contents_ref = page.get("/Contents")
        if contents_ref is None:
            continue

        try:
            contents_obj = contents_ref.get_object()
        except Exception:
            continue

        if not isinstance(contents_obj, ArrayObject):
            continue  # Single stream — handled by Method 3

        if len(contents_obj) <= 1:
            continue

        new_streams = ArrayObject()
        for stream_ref in contents_obj:
            try:
                stream = stream_ref.get_object()
                data = stream.get_data()
            except Exception:
                new_streams.append(stream_ref)
                continue

            if _is_watermark_stream(data, cross_page_texts):
                continue  # Remove this stream

            new_streams.append(stream_ref)

        if len(new_streams) < len(contents_obj) and len(new_streams) > 0:
            page[NameObject("/Contents")] = new_streams
```

- [ ] **Step 4: Implement `_remove_watermark_xobjects`**

Replace the stub in `backend/services/pdf_watermark_remover.py`:

```python
def _remove_watermark_xobjects(writer, cross_page_texts):
    """Method 4: Remove watermark XObject overlays.

    Detects Form XObjects that contain watermark text or appear as overlays
    on every page. Removes their /Do references from content streams
    and deletes them from /Resources/XObject.
    """
    # First pass: count which XObjects appear on how many pages
    xobj_page_count = Counter()
    total_pages = len(writer.pages)

    for page in writer.pages:
        try:
            content = page.get_contents()
            if content is None:
                continue
            for operands, operator in content.operations:
                if operator == b"Do" and operands:
                    name = str(operands[0])
                    xobj_page_count[name] += 1
        except Exception:
            continue

    # XObjects on every page are suspicious
    cross_page_xobjects = {
        name
        for name, count in xobj_page_count.items()
        if count >= total_pages and total_pages > 1
    }

    for page in writer.pages:
        if "/Resources" not in page:
            continue
        try:
            resources = page["/Resources"].get_object()
        except Exception:
            continue
        if "/XObject" not in resources:
            continue

        try:
            xobjects = resources["/XObject"].get_object()
        except Exception:
            continue

        watermark_names = set()

        for name in list(xobjects.keys()):
            try:
                xobj = xobjects[name].get_object()
            except Exception:
                continue

            subtype = str(xobj.get("/Subtype", ""))
            is_watermark = False

            # Check Form XObjects for watermark content
            if subtype == "/Form":
                try:
                    data = xobj.get_data()
                    data_lower = data.lower()
                    for marker in [
                        b"watermark", b"draft", b"confidential", b"sample",
                        b"downloaded_by", b"lomoarcpsd", b"studocu",
                        b"coursehero", b"scribd",
                    ]:
                        if marker in data_lower:
                            is_watermark = True
                            break
                except Exception:
                    pass

                # Cross-page Form XObjects with watermark markers
                if not is_watermark and name in cross_page_xobjects:
                    try:
                        data = xobj.get_data()
                        data_lower = data.lower()
                        if any(
                            m in data_lower
                            for m in [
                                b"watermark", b"downloaded", b"studocu",
                                b"coursehero", b"scribd",
                            ]
                        ):
                            is_watermark = True
                    except Exception:
                        pass

            if is_watermark:
                watermark_names.add(name)

        if not watermark_names:
            continue

        # Remove Do references from content stream
        try:
            content = page.get_contents()
            if content is not None:
                new_ops = []
                for operands, operator in content.operations:
                    if operator == b"Do" and operands:
                        xobj_name = str(operands[0])
                        if xobj_name in watermark_names:
                            continue
                    new_ops.append((operands, operator))
                content.operations = new_ops
                page.replace_contents(content)
        except Exception:
            pass

        # Remove XObject entries from resources
        for name in watermark_names:
            try:
                del xobjects[NameObject(name)]
            except (KeyError, Exception):
                pass
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_pdf_watermark_remover.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/pdf_watermark_remover.py backend/tests/test_pdf_watermark_remover.py
git commit -m "feat: implement stream removal (Method 1) and XObject removal (Method 4)"
```

---

### Task 5: Integration with pdf_processor.py

**Files:**
- Modify: `backend/services/pdf_processor.py`
- Modify: `backend/tests/test_pdf_processor.py`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Simplify `pdf_processor.py` — replace removal methods with new module**

In `backend/services/pdf_processor.py`, make the following changes:

**Remove these imports** (no longer needed for removal):
```python
import numpy as np
```

**Remove these methods entirely:**
- `_is_image_based_page`
- `_build_watermark_mask`
- `_inpaint_page`
- `_remove_text_watermarks`
- `_remove_image_watermarks`
- `_rasterize_and_inpaint`
- `_remove_watermarks_inpaint`

**Replace the `process` method** with:

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
        doc.close()

        output_path = os.path.join(output_dir, "output.pdf")

        if not watermarks:
            shutil.copy2(input_path, output_path)
            return {"output_path": output_path, "watermark_detected": False}

        # PDF object-level removal (no rasterization)
        from services.pdf_watermark_remover import remove_watermark

        with open(input_path, "rb") as f:
            pdf_bytes = f.read()

        cleaned_bytes = remove_watermark(pdf_bytes)

        with open(output_path, "wb") as f:
            f.write(cleaned_bytes)

        return {"output_path": output_path, "watermark_detected": True}
```

The full file after modification should be:

```python
import os
import re
import shutil
from collections import Counter

import fitz  # PyMuPDF

MAX_PDF_PAGES = 20

# Classic watermark keywords
WATERMARK_PATTERNS = re.compile(
    r"\b(DRAFT|CONFIDENTIAL|SAMPLE|COPY|DO NOT DISTRIBUTE|WATERMARK|PREVIEW)\b",
    re.IGNORECASE,
)

# Platform-specific signatures (StuDocu, Scribd, CourseHero, etc.)
PLATFORM_PATTERNS = re.compile(
    r"(studocu|scribd|coursehero|chegg|bartleby|"
    r"lOMoARcPSD|"
    r"messages\.downloaded_by|messages\.pdf_cover|messages\.studocu|"
    r"downloaded\s+by|uploaded\s+by|"
    r"this\s+document\s+is\s+available\s+on|"
    r"get\s+the\s+app|"
    r"not[\s_]sponsored[\s_]or[\s_]endorsed)",
    re.IGNORECASE,
)

# Text that is legitimately repeated and should NOT be flagged
IGNORE_COMMON_TEXT = re.compile(
    r"^(\d{1,4}|[ivxlcdm]+|page\s*\d+|©.*)$",
    re.IGNORECASE,
)


class PdfProcessor:
    def detect_watermarks(self, doc: fitz.Document) -> list[dict]:
        """Detect watermark elements across all pages."""
        watermarks = []

        if len(doc) < 1:
            return watermarks

        # Collect per-page text spans with metadata
        page_texts = []
        all_spans = []  # (page_num, text, size, color, bbox)
        for page_num, page in enumerate(doc):
            blocks = page.get_text("dict")["blocks"]
            texts = set()
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if text:
                                texts.add(text)
                                all_spans.append((
                                    page_num,
                                    text,
                                    span.get("size", 12),
                                    span.get("color", 0),
                                    span.get("bbox", (0, 0, 0, 0)),
                                ))
            page_texts.append(texts)

        # ── Strategy 1: Text appearing on EVERY page ──
        if len(page_texts) > 1:
            common_texts = page_texts[0]
            for texts in page_texts[1:]:
                common_texts = common_texts & texts

            for text in common_texts:
                if len(text) <= 2 or IGNORE_COMMON_TEXT.match(text):
                    continue
                watermarks.append({"type": "text", "text": text})

        # ── Strategy 2: Large light-colored text (any page) ──
        for page_num, page in enumerate(doc):
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            color = span.get("color", 0)
                            size = span.get("size", 12)
                            text = span["text"].strip()

                            if size > 24 and text:
                                r = (color >> 16) & 0xFF
                                g = (color >> 8) & 0xFF
                                b = color & 0xFF
                                if r > 150 and g > 150 and b > 150:
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

        # ── Strategy 3: Platform fingerprinting ──
        for page_num, text, size, color, bbox in all_spans:
            if PLATFORM_PATTERNS.search(text):
                watermarks.append({
                    "type": "text",
                    "text": text,
                    "page": page_num,
                })

        # ── Strategy 4: Repeated images across pages (banners/logos) ──
        page_images = {}
        for page_num, page in enumerate(doc):
            blocks = page.get_text("dict")["blocks"]
            imgs = []
            for block in blocks:
                if "image" in block:
                    bbox = block.get("bbox", (0, 0, 0, 0))
                    w = block.get("width", 0)
                    h = block.get("height", 0)
                    imgs.append((bbox, w, h))
            page_images[page_num] = imgs

        if len(page_images) > 1:
            all_image_sigs = []
            for page_num, imgs in page_images.items():
                for bbox, w, h in imgs:
                    sig = (
                        round(bbox[0], -1),
                        round(bbox[1], -1),
                        round(bbox[2] - bbox[0], -1),
                        round(bbox[3] - bbox[1], -1),
                    )
                    all_image_sigs.append((sig, page_num, bbox))

            sig_counts = Counter(s[0] for s in all_image_sigs)
            for sig, count in sig_counts.items():
                if count >= 2:
                    watermarks.append({
                        "type": "image",
                        "bbox_signature": sig,
                        "pages": [s[1] for s in all_image_sigs if s[0] == sig],
                    })

        # ── Strategy 5: Banner-shaped images (high aspect ratio at page edges) ──
        for page_num, imgs in page_images.items():
            page_h = doc[page_num].rect.height if page_num < len(doc) else 842
            for bbox, w, h in imgs:
                render_w = bbox[2] - bbox[0]
                render_h = max(bbox[3] - bbox[1], 1)
                aspect = render_w / render_h
                y_ratio = bbox[1] / max(page_h, 1)

                if aspect > 4 and (y_ratio > 0.8 or y_ratio < 0.15):
                    sig = (
                        round(bbox[0], -1),
                        round(bbox[1], -1),
                        round(render_w, -1),
                        round(render_h, -1),
                    )
                    watermarks.append({
                        "type": "image",
                        "bbox_signature": sig,
                        "pages": [page_num],
                    })

        # Deduplicate
        seen = set()
        unique = []
        for w in watermarks:
            if w["type"] == "text":
                key = ("text", w["text"])
            else:
                key = ("image", w.get("bbox_signature", ()))
            if key not in seen:
                seen.add(key)
                unique.append(w)

        return unique

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
        doc.close()

        output_path = os.path.join(output_dir, "output.pdf")

        if not watermarks:
            shutil.copy2(input_path, output_path)
            return {"output_path": output_path, "watermark_detected": False}

        # PDF object-level removal (no rasterization)
        from services.pdf_watermark_remover import remove_watermark

        with open(input_path, "rb") as f:
            pdf_bytes = f.read()

        cleaned_bytes = remove_watermark(pdf_bytes)

        with open(output_path, "wb") as f:
            f.write(cleaned_bytes)

        return {"output_path": output_path, "watermark_detected": True}
```

- [ ] **Step 2: Update test_pdf_processor.py — remove inpainting tests, update integration tests**

In `backend/tests/test_pdf_processor.py`:

**Remove these tests** (they test deleted methods):
- `test_is_image_based_page_with_full_page_images`
- `test_is_image_based_page_text_only`
- `test_build_watermark_mask_creates_correct_mask`
- `test_inpaint_page_preserves_content`
- `test_detect_returns_bboxes_for_text_watermarks`
- `test_process_image_page_no_white_boxes`
- `test_process_mixed_pdf_handles_both_page_types`

**Remove the fixtures** that are only used by deleted tests:
- `image_page_studocu_pdf_path`

**Remove these imports** (no longer needed):
```python
import cv2
import numpy as np
```

**Add new integration test:**

```python
def test_process_preserves_text_selectability(processor):
    """Output PDF should preserve text selectability (no rasterization)."""
    path = os.path.join(tempfile.gettempdir(), "test_text_selectable.pdf")
    doc = fitz.open()
    for _ in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), "Selectable text content.", fontsize=12)
        page.insert_text(
            (200, 800), "messages.downloaded_by", fontsize=8, color=(0.3, 0.3, 0.3)
        )
    doc.save(path)
    doc.close()

    output_dir = tempfile.mkdtemp()
    result = processor.process(path, output_dir)
    assert result["watermark_detected"] is True

    # Verify text is still selectable (not rasterized)
    out_doc = fitz.open(result["output_path"])
    text = out_doc[0].get_text()
    assert "Selectable text content" in text
    out_doc.close()
    os.remove(path)
```

The full updated test file:

```python
import os
import tempfile

import fitz
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
        page.insert_text((72, 72), "This is normal content.", fontsize=12)
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


@pytest.fixture
def studocu_pdf_path():
    """Create a test PDF mimicking StuDocu platform watermarks."""
    path = os.path.join(tempfile.gettempdir(), "test_studocu.pdf")
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"Page {i+1} content here.", fontsize=12)
        page.insert_text(
            (200, 800),
            "messages.downloaded_by",
            fontsize=8,
            color=(0.3, 0.3, 0.3),
        )
        page.insert_text(
            (250, 10),
            "lOMoARcPSD|12930651",
            fontsize=1,
            color=(0, 0, 0),
        )
    doc.save(path)
    doc.close()
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_detect_studocu_watermark(processor, studocu_pdf_path):
    """Platform watermarks like StuDocu must be detected."""
    doc = fitz.open(studocu_pdf_path)
    watermarks = processor.detect_watermarks(doc)
    doc.close()
    assert len(watermarks) > 0
    texts = {w["text"] for w in watermarks if w["type"] == "text"}
    assert "messages.downloaded_by" in texts


def test_process_studocu_pdf_detects_watermark(processor, studocu_pdf_path):
    """StuDocu PDFs must report watermark_detected=True."""
    output_dir = tempfile.mkdtemp()
    result = processor.process(studocu_pdf_path, output_dir)
    assert result["watermark_detected"] is True
    assert os.path.exists(result["output_path"])


@pytest.fixture
def repeated_text_pdf_path():
    """PDF with non-keyword text repeated on every page (e.g. branding footer)."""
    path = os.path.join(tempfile.gettempdir(), "test_repeated.pdf")
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), f"Chapter {i+1} content.", fontsize=12)
        page.insert_text(
            (150, 820),
            "This document is available on MyPlatform",
            fontsize=8,
            color=(0.5, 0.5, 0.5),
        )
    doc.save(path)
    doc.close()
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_detect_repeated_non_keyword_text(processor, repeated_text_pdf_path):
    """Text on every page should be detected even without matching keywords."""
    doc = fitz.open(repeated_text_pdf_path)
    watermarks = processor.detect_watermarks(doc)
    doc.close()
    assert len(watermarks) > 0
    texts = {w["text"] for w in watermarks if w["type"] == "text"}
    assert "This document is available on MyPlatform" in texts


def test_process_preserves_text_selectability(processor):
    """Output PDF should preserve text selectability (no rasterization)."""
    path = os.path.join(tempfile.gettempdir(), "test_text_selectable.pdf")
    doc = fitz.open()
    for _ in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), "Selectable text content.", fontsize=12)
        page.insert_text(
            (200, 800), "messages.downloaded_by", fontsize=8, color=(0.3, 0.3, 0.3)
        )
    doc.save(path)
    doc.close()

    output_dir = tempfile.mkdtemp()
    result = processor.process(path, output_dir)
    assert result["watermark_detected"] is True

    # Verify text is still selectable (not rasterized)
    out_doc = fitz.open(result["output_path"])
    text = out_doc[0].get_text()
    assert "Selectable text content" in text
    out_doc.close()
    os.remove(path)
```

- [ ] **Step 3: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add backend/services/pdf_processor.py backend/services/pdf_watermark_remover.py backend/tests/test_pdf_processor.py backend/tests/test_pdf_watermark_remover.py backend/requirements.txt
git commit -m "feat: replace rasterization with PDF object-level watermark removal"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `backend/services/pdf_watermark_remover.py` | NEW: 4-method pypdf-based watermark removal |
| `backend/services/pdf_processor.py` | Simplified: removed 7 methods, delegates removal to new module |
| `backend/tests/test_pdf_watermark_remover.py` | NEW: 20+ tests for all 4 removal methods |
| `backend/tests/test_pdf_processor.py` | Updated: removed inpainting tests, added text selectability test |
| `backend/requirements.txt` | Added pypdf dependency |

## What's Removed from pdf_processor.py

| Method | Reason |
|--------|--------|
| `_is_image_based_page()` | No longer needed — no rasterization path |
| `_build_watermark_mask()` | No longer needed — no pixel-level masking |
| `_inpaint_page()` | No longer needed — no OpenCV inpainting |
| `_remove_text_watermarks()` | Replaced by Method 3 (inline removal) |
| `_remove_image_watermarks()` | Replaced by Method 4 (XObject removal) |
| `_remove_watermarks_inpaint()` | Replaced by `remove_watermark()` |
| `_rasterize_and_inpaint()` | Eliminated — never rasterize |
| `numpy` import | No longer needed for removal |
| `ImageProcessor` import + `__init__` | Dead code — no longer used by any method |

## Limitations

1. **Raster-embedded watermarks**: Watermarks burned into JPEG/PNG pixel data inside the PDF cannot be removed at the PDF object level. These require image-level processing (out of scope).
2. **ExtGState transparency**: The current implementation doesn't track `/ExtGState` transparency parameters (`/ca`, `/CA`). Watermarks using only transparency (no text content) won't be detected by Method 3.
3. **Custom encodings**: Some PDFs use custom font encodings that make text extraction from content streams unreliable. The regex-based fallback in `_is_watermark_stream` partially mitigates this.
