# Fix White Box Artifacts in PDF Watermark Removal

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate white rectangles left behind when removing watermarks from single-stream PDFs (StuDocu, etc.)

**Architecture:** Watermark overlays are structured as `q...Q` graphics state groups containing both a white background rectangle (`re`/`f` operators) and text (`BT...ET` blocks). Current Method 3 only removes text blocks, leaving orphaned white rectangles. The fix enhances Method 3 to detect and remove entire `q...Q` groups when all their text content is watermark-related.

**Tech Stack:** Python 3.13, pypdf 6.8.0, pytest

---

## Root Cause Analysis

StuDocu and similar platforms inject watermarks as graphics state groups:

```
q                         ← save graphics state
  1 1 1 rg                ← set fill to white
  0 700 612 92 re         ← rectangle path
  f                       ← fill (draws white box)
  BT ... watermark ... ET ← watermark text on top
Q                         ← restore graphics state
```

Current `_remove_inline_watermarks()` (Method 3) only removes `BT...ET` blocks.
The `q`, color, `re`, `f`, `Q` operators pass through untouched → **white box artifact**.

**Evidence:** Reproduction confirms the bug:
- Multi-stream PDFs: Method 1 removes entire streams → **clean** (no white box)
- Single-stream PDFs: Method 3 removes only text → **white rectangles remain**

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `backend/services/pdf_watermark_remover.py` | Modify | Rewrite `_remove_inline_watermarks()` with q...Q group awareness |
| `backend/tests/test_pdf_watermark_remover.py` | Modify | Add tests for white-box scenario and q...Q group removal |

No new files needed. The fix is entirely within the existing removal module.

---

## Task 1: Add Failing Tests for White Box Bug

**Files:**
- Modify: `backend/tests/test_pdf_watermark_remover.py`

- [ ] **Step 1.1: Write test for white rectangle artifact in single-stream PDF**

Add a new test class after the existing `TestRemoveInlineWatermarks` class:

```python
class TestWhiteBoxArtifactRemoval:
    """Tests for removing white rectangle artifacts from watermark groups."""

    def _make_single_stream_pdf(self, content_stream_bytes: bytes) -> bytes:
        """Helper: create a 1-page PDF with a single raw content stream."""
        from pypdf import PdfWriter
        from pypdf.generic import (
            DecodedStreamObject,
            DictionaryObject,
            NameObject,
        )

        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        stream = DecodedStreamObject()
        stream.set_data(content_stream_bytes)
        s_ref = writer._add_object(stream)
        page[NameObject("/Contents")] = s_ref

        font_dict = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        font_ref = writer._add_object(font_dict)
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_ref}
                )
            }
        )
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()

    def test_removes_white_rect_with_watermark_text(self):
        """A q...Q group with white rect + watermark text should be fully removed."""
        pdf_bytes = self._make_single_stream_pdf(
            b"q\n"
            b"BT /F1 12 Tf 100 700 Td (Legitimate content.) Tj ET\n"
            b"q\n"
            b"1 1 1 rg\n"
            b"0 0 612 50 re\n"
            b"f\n"
            b"BT /F1 8 Tf 100 20 Td (Downloaded by Test User) Tj ET\n"
            b"BT /F1 6 Tf 400 20 Td (lOMoARcPSD|12345678) Tj ET\n"
            b"Q\n"
            b"Q\n"
        )
        result = remove_watermark(pdf_bytes)
        reader = PdfReader(io.BytesIO(result))
        data = reader.pages[0].get_contents().get_data()

        assert b"1 1 1 rg" not in data, "White color operator should be removed"
        assert b"612 50 re" not in data, "Rectangle operator should be removed"
        assert b"Downloaded" not in data, "Watermark text should be removed"
        assert b"lOMoARcPSD" not in data, "Tracking ID should be removed"
        assert b"Legitimate content" in data, "Content must be preserved"

    def test_removes_multiple_watermark_groups(self):
        """Multiple watermark q...Q groups on one page should all be removed."""
        pdf_bytes = self._make_single_stream_pdf(
            b"q\n"
            b"BT /F1 12 Tf 100 700 Td (Page content here.) Tj ET\n"
            b"q\n"
            b"1 1 1 rg\n"
            b"0 700 612 92 re\n"
            b"f\n"
            b"BT /F1 10 Tf 50 750 Td (Downloaded by Test User) Tj ET\n"
            b"Q\n"
            b"q\n"
            b"0.9 0.9 0.9 rg\n"
            b"0 0 612 40 re\n"
            b"f\n"
            b"BT /F1 6 Tf 200 15 Td (lOMoARcPSD|12345678) Tj ET\n"
            b"Q\n"
            b"Q\n"
        )
        result = remove_watermark(pdf_bytes)
        reader = PdfReader(io.BytesIO(result))
        data = reader.pages[0].get_contents().get_data()

        assert b"1 1 1 rg" not in data
        assert b"0.9 0.9 0.9 rg" not in data
        assert b" re" not in data
        assert b"Page content here" in data

    def test_preserves_non_watermark_graphics_group(self):
        """A q...Q group with legitimate text must NOT be removed."""
        pdf_bytes = self._make_single_stream_pdf(
            b"q\n"
            b"q\n"
            b"0.95 0.95 0.95 rg\n"
            b"50 600 200 100 re\n"
            b"f\n"
            b"BT /F1 10 Tf 60 650 Td (Important highlighted note.) Tj ET\n"
            b"Q\n"
            b"Q\n"
        )
        result = remove_watermark(pdf_bytes)
        reader = PdfReader(io.BytesIO(result))
        data = reader.pages[0].get_contents().get_data()

        assert b"Important highlighted note" in data
        assert b"50 600 200 100 re" in data or b" re" in data

    def test_mixed_group_only_removes_text(self):
        """A q...Q group with BOTH watermark and legitimate text: only remove watermark BT...ET."""
        pdf_bytes = self._make_single_stream_pdf(
            b"q\n"
            b"q\n"
            b"0.9 0.9 0.9 rg\n"
            b"0 0 612 50 re\n"
            b"f\n"
            b"BT /F1 12 Tf 50 30 Td (Important footer content.) Tj ET\n"
            b"BT /F1 6 Tf 400 10 Td (lOMoARcPSD|99999999) Tj ET\n"
            b"Q\n"
            b"Q\n"
        )
        result = remove_watermark(pdf_bytes)
        reader = PdfReader(io.BytesIO(result))
        data = reader.pages[0].get_contents().get_data()

        assert b"lOMoARcPSD" not in data, "Watermark text removed"
        assert b"Important footer content" in data, "Legit text preserved"

    def test_removes_top_level_watermark_group_no_outer_q(self):
        """Watermark q...Q at stream top level (no outer q wrapper) should be removed."""
        pdf_bytes = self._make_single_stream_pdf(
            b"BT /F1 12 Tf 100 700 Td (Legitimate content here.) Tj ET\n"
            b"q\n"
            b"1 1 1 rg\n"
            b"0 0 612 50 re\n"
            b"f\n"
            b"BT /F1 8 Tf 100 20 Td (Downloaded by Test User) Tj ET\n"
            b"BT /F1 6 Tf 400 20 Td (lOMoARcPSD|12345678) Tj ET\n"
            b"Q\n"
        )
        result = remove_watermark(pdf_bytes)
        reader = PdfReader(io.BytesIO(result))
        data = reader.pages[0].get_contents().get_data()

        assert b"1 1 1 rg" not in data, "White color should be removed"
        assert b"612 50 re" not in data, "Rectangle should be removed"
        assert b"Downloaded" not in data, "Watermark text should be removed"
        assert b"Legitimate content here" in data, "Content must be preserved"

    def test_preserves_empty_text_block_group(self):
        """A q...Q group with only empty BT...ET blocks should NOT be removed."""
        pdf_bytes = self._make_single_stream_pdf(
            b"q\n"
            b"0.95 0.95 0.95 rg\n"
            b"50 600 200 100 re\n"
            b"f\n"
            b"BT ET\n"
            b"Q\n"
        )
        result = remove_watermark(pdf_bytes)
        reader = PdfReader(io.BytesIO(result))
        data = reader.pages[0].get_contents().get_data()

        # Group should be preserved (empty text is not watermark)
        assert b"50 600 200 100 re" in data or b" re" in data

    def test_no_white_box_on_multipage_studocu_style(self):
        """Multi-page single-stream StuDocu-style PDF should have no white artifacts."""
        pages_data = []
        for i in range(3):
            pages_data.append(
                f"q\n"
                f"BT /F1 12 Tf 100 700 Td (Page {i+1} real content.) Tj ET\n"
                f"q\n"
                f"1 1 1 rg\n"
                f"0 750 612 42 re\n"
                f"f\n"
                f"BT /F1 8 Tf 50 760 Td (messages.downloaded_by) Tj ET\n"
                f"Q\n"
                f"q\n"
                f"0.85 0.85 0.85 rg\n"
                f"0 0 612 30 re\n"
                f"f\n"
                f"BT /F1 5 Tf 250 10 Td (lOMoARcPSD|12345678) Tj ET\n"
                f"Q\n"
                f"Q\n"
            )

        from pypdf import PdfWriter
        from pypdf.generic import (
            DecodedStreamObject,
            DictionaryObject,
            NameObject,
        )

        writer = PdfWriter()
        for page_data in pages_data:
            page = writer.add_blank_page(width=612, height=792)
            stream = DecodedStreamObject()
            stream.set_data(page_data.encode())
            s_ref = writer._add_object(stream)
            page[NameObject("/Contents")] = s_ref
            font_dict = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            )
            font_ref = writer._add_object(font_dict)
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/Font"): DictionaryObject(
                        {NameObject("/F1"): font_ref}
                    )
                }
            )

        buf = io.BytesIO()
        writer.write(buf)

        result = remove_watermark(buf.getvalue())
        reader = PdfReader(io.BytesIO(result))

        for i, page in enumerate(reader.pages):
            data = page.get_contents().get_data()
            assert b"1 1 1 rg" not in data, f"Page {i}: white rect remains"
            assert b"0.85 0.85" not in data, f"Page {i}: gray rect remains"
            assert f"Page {i+1} real content".encode() in data, f"Page {i}: content lost"
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_pdf_watermark_remover.py::TestWhiteBoxArtifactRemoval -v`

Expected: 5 of 7 tests FAIL (the `test_mixed_group_only_removes_text` and `test_preserves_non_watermark_graphics_group` pass with current code; the other 5 fail because white rectangles remain).

- [ ] **Step 1.3: Commit failing tests**

```bash
git add backend/tests/test_pdf_watermark_remover.py
git commit -m "test: add failing tests for white box artifact in watermark removal"
```

---

## Task 2: Implement q...Q Group-Aware Watermark Removal

**Files:**
- Modify: `backend/services/pdf_watermark_remover.py:337-464` (the `_remove_inline_watermarks` function)

### Algorithm Design

Replace the current linear BT...ET scan with a **two-level approach**:

1. **Outer loop**: Walk operations tracking `q`/`Q` nesting depth
2. **For every `q...Q` group** (any depth): collect all ops until matching `Q` (handling nested q/Q correctly)
3. **Classify the group**: extract text from all BT...ET blocks in the group
   - If group has BT...ET blocks AND **all** text is watermark → **remove entire group** (including rect/fill ops)
   - If group has BT...ET blocks with **mixed** content → **keep group structure**, remove only watermark BT...ET blocks (existing behavior)
   - If group has **no** BT...ET blocks → **keep as-is**
4. **Top-level BT...ET blocks** (not inside any q...Q): apply existing block-level removal

- [ ] **Step 2.1: Add helper function `_classify_group_ops`**

Add this function before `_remove_inline_watermarks` in `pdf_watermark_remover.py`:

```python
def _classify_group_ops(group_ops, cross_page_texts):
    """Classify a q...Q group's text content as watermark or legitimate.

    Args:
        group_ops: list of (operands, operator) tuples between q and Q (exclusive)
        cross_page_texts: set of text appearing on every page

    Returns:
        "all_watermark" - every BT...ET block is watermark (remove entire group)
        "mixed"         - some watermark, some legitimate (remove only watermark blocks)
        "no_text"       - no BT...ET blocks at all (keep as-is)
        "clean"         - has text, none is watermark (keep as-is)
    """
    text_blocks = []  # list of (text, color, font_size, is_watermark)

    current_color = None
    current_font_size = None

    i = 0
    while i < len(group_ops):
        operands, operator = group_ops[i]

        # Track color
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
        elif operator == b"k" and len(operands) == 4:
            try:
                c, m, y, kk = (float(o) for o in operands)
                current_color = ((1 - c) * (1 - kk), (1 - m) * (1 - kk), (1 - y) * (1 - kk))
            except (TypeError, ValueError):
                pass

        # Track font size
        if operator == b"Tf" and len(operands) >= 2:
            try:
                current_font_size = float(operands[1])
            except (TypeError, ValueError):
                pass

        # Collect BT...ET block
        if operator == b"BT":
            block = [(operands, operator)]
            block_color = current_color
            block_font_size = current_font_size
            i += 1
            while i < len(group_ops) and group_ops[i][1] != b"ET":
                inner_ops, inner_op = group_ops[i]
                block.append((inner_ops, inner_op))
                if inner_op == b"rg" and len(inner_ops) == 3:
                    try:
                        block_color = tuple(float(o) for o in inner_ops)
                    except (TypeError, ValueError):
                        pass
                elif inner_op == b"g" and len(inner_ops) == 1:
                    try:
                        gray = float(inner_ops[0])
                        block_color = (gray, gray, gray)
                    except (TypeError, ValueError):
                        pass
                elif inner_op == b"k" and len(inner_ops) == 4:
                    try:
                        c, m, y, kk = (float(o) for o in inner_ops)
                        block_color = ((1 - c) * (1 - kk), (1 - m) * (1 - kk), (1 - y) * (1 - kk))
                    except (TypeError, ValueError):
                        pass
                elif inner_op == b"Tf" and len(inner_ops) >= 2:
                    try:
                        block_font_size = float(inner_ops[1])
                    except (TypeError, ValueError):
                        pass
                i += 1
            if i < len(group_ops):
                block.append(group_ops[i])  # ET
                i += 1

            text = _extract_text_from_block(block)
            is_wm = _should_remove_block(text, block_color, block_font_size, cross_page_texts)
            text_blocks.append((text.strip(), is_wm))
            continue

        i += 1

    if not text_blocks:
        return "no_text"

    non_empty = [(t, wm) for t, wm in text_blocks if t]
    if not non_empty:
        return "no_text"  # Only empty text blocks — treat as no text

    all_wm = all(is_wm for _, is_wm in non_empty)
    any_wm = any(is_wm for _, is_wm in non_empty)

    if all_wm:
        return "all_watermark"
    elif any_wm:
        return "mixed"
    else:
        return "clean"
```

- [ ] **Step 2.2: Rewrite `_remove_inline_watermarks` with group awareness**

Replace the function body (lines 337-464) with:

```python
def _remove_inline_watermarks(writer, cross_page_texts):
    """Method 3: Remove inline watermark operators from content streams.

    Parses each page's content stream. For q...Q groups whose text is
    entirely watermark-related, removes the whole group (including background
    rectangles). For mixed groups, removes only watermark BT...ET blocks.
    Non-text operators outside watermark groups are never touched.
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

        new_ops = _filter_watermark_ops(ops, cross_page_texts)

        content.operations = new_ops
        page.replace_contents(content)


def _filter_watermark_ops(ops, cross_page_texts):
    """Recursively filter operations, removing watermark groups and text blocks.

    When a q...Q group contains only watermark text,
    the whole group (including rectangles) is dropped.
    """
    new_ops = []
    current_color = None
    current_font_size = None

    i = 0
    while i < len(ops):
        operands, operator = ops[i]

        # Track color state
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
        elif operator == b"k" and len(operands) == 4:
            try:
                c, m, y, kk = (float(o) for o in operands)
                current_color = ((1 - c) * (1 - kk), (1 - m) * (1 - kk), (1 - y) * (1 - kk))
            except (TypeError, ValueError):
                pass

        # Track font size
        if operator == b"Tf" and len(operands) >= 2:
            try:
                current_font_size = float(operands[1])
            except (TypeError, ValueError):
                pass

        # Handle q...Q groups
        if operator == b"q":
            # Collect all ops until matching Q
            group_ops = []
            nesting = 1
            i += 1
            while i < len(ops) and nesting > 0:
                g_operands, g_operator = ops[i]
                if g_operator == b"q":
                    nesting += 1
                elif g_operator == b"Q":
                    nesting -= 1
                    if nesting == 0:
                        break
                group_ops.append((g_operands, g_operator))
                i += 1
            i += 1  # skip the closing Q

            # Check if entire group is watermark-only
            classification = _classify_group_ops(group_ops, cross_page_texts)
            if classification == "all_watermark":
                continue  # Drop entire group (q + contents + Q)

            # Keep group: recursively filter its contents
            filtered = _filter_watermark_ops(group_ops, cross_page_texts)
            new_ops.append((operands, b"q"))  # q
            new_ops.extend(filtered)
            new_ops.append(([], b"Q"))  # Q
            continue

        # Handle BT...ET text blocks (top-level or inside kept groups)
        if operator == b"BT":
            block = [(operands, operator)]
            block_color = current_color
            block_font_size = current_font_size
            i += 1

            while i < len(ops) and ops[i][1] != b"ET":
                inner_operands, inner_op = ops[i]
                block.append((inner_operands, inner_op))

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
                elif inner_op == b"k" and len(inner_operands) == 4:
                    try:
                        c, m, y, kk = (float(o) for o in inner_operands)
                        block_color = ((1 - c) * (1 - kk), (1 - m) * (1 - kk), (1 - y) * (1 - kk))
                    except (TypeError, ValueError):
                        pass
                elif inner_op == b"Tf" and len(inner_operands) >= 2:
                    try:
                        block_font_size = float(inner_operands[1])
                    except (TypeError, ValueError):
                        pass

                i += 1

            if i < len(ops):
                block.append(ops[i])  # ET
                i += 1

            text = _extract_text_from_block(block)
            if _should_remove_block(text, block_color, block_font_size, cross_page_texts):
                continue  # Remove watermark text block
            else:
                new_ops.extend(block)
                continue

        new_ops.append((operands, operator))
        i += 1

    return new_ops
```

- [ ] **Step 2.3: Run ALL tests**

Run: `cd backend && python -m pytest tests/ -v`

Expected: All 88 existing tests + 7 new tests pass (95 total).

- [ ] **Step 2.4: Commit implementation**

```bash
git add backend/services/pdf_watermark_remover.py backend/tests/test_pdf_watermark_remover.py
git commit -m "fix: remove white box artifacts by dropping entire watermark q...Q groups"
```

---

## Task 3: Verify with Reproduction Script

- [ ] **Step 3.1: Run the reproduction script from root-cause analysis**

```bash
cd backend && source .venv/Scripts/activate && python3 -c "
from pypdf import PdfWriter, PdfReader
from pypdf.generic import NameObject, DecodedStreamObject, DictionaryObject
import io

writer = PdfWriter()
page = writer.add_blank_page(width=612, height=792)
stream = DecodedStreamObject()
stream.set_data(b'''q
BT /F1 12 Tf 100 700 Td (This is the actual content.) Tj ET
q
1 1 1 rg
0 0 612 50 re
f
BT /F1 8 Tf 100 20 Td (Downloaded by Test User) Tj ET
BT /F1 6 Tf 400 20 Td (lOMoARcPSD|12345678) Tj ET
Q
Q
''')
s_ref = writer._add_object(stream)
page[NameObject('/Contents')] = s_ref
font_dict = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
font_ref = writer._add_object(font_dict)
page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font_ref})})
buf = io.BytesIO()
writer.write(buf)

from services.pdf_watermark_remover import remove_watermark
cleaned = remove_watermark(buf.getvalue())
reader = PdfReader(io.BytesIO(cleaned))
data = reader.pages[0].get_contents().get_data()
print(data.decode('latin-1'))
assert b'1 1 1 rg' not in data, 'FAIL: white rect remains'
assert b' re' not in data, 'FAIL: rectangle remains'
assert b'Downloaded' not in data, 'FAIL: watermark text remains'
assert b'actual content' in data, 'FAIL: content lost'
print('ALL CHECKS PASSED')
"
```

Expected: `ALL CHECKS PASSED` — no white rectangle operators in output.

---

## Summary of Changes

| What | Before | After |
|------|--------|-------|
| Watermark in q...Q group | Only BT...ET removed; rect/fill operators remain → white box | Entire q...Q group removed → clean |
| Mixed content group | N/A (treated same as watermark-only) | Only watermark BT...ET blocks removed; graphics preserved |
| Nested q...Q | Flat scan, no nesting awareness | Recursive `_filter_watermark_ops` handles arbitrary nesting |
| Top-level q...Q group | Not checked (only BT...ET scanned) | Classified and removed if all-watermark |
| Top-level BT...ET | Removed if watermark | Unchanged — still removed if watermark |
| Existing tests | 88 pass | 88 pass + 7 new = 95 |
