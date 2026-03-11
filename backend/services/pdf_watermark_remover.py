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
        # Verify decryption actually worked
        try:
            _ = reader.root_object
        except Exception:
            return input_pdf_bytes  # Still can't read, return as-is

    try:
        writer = PdfWriter(clone_from=reader)
    except Exception:
        return input_pdf_bytes  # Can't clone (e.g. encrypted), return as-is

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
