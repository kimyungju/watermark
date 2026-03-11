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
    if len(writer.pages) < 2:
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

                    # Cross-page Form XObjects with watermark markers
                    if not is_watermark and name in cross_page_xobjects:
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
