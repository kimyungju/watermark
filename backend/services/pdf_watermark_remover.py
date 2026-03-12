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
)

from services.constants import (
    PLATFORM_PATTERNS,
    CLASSIC_WATERMARK_PATTERNS,
    IGNORE_COMMON_TEXT,
)

# Tracking ID pattern (only used in removal, not detection)
TRACKING_ID_PATTERN = re.compile(r"^[A-Za-z0-9|_-]{8,}$")


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

    non_empty = [t for t in page_texts if t]
    if not non_empty:
        return set()
    common = non_empty[0]
    for texts in non_empty[1:]:
        common = common & texts

    return common


def _detect_cover_pages(reader):
    """Detect platform-injected cover pages that aren't part of the original document.

    A cover page is one where:
    - The majority of text (>60%) matches platform patterns
    - There's very little non-platform text (< 50 chars of real content)

    Safety: never returns all page indices (would leave empty PDF).
    Single-page PDFs always return empty set.

    Returns:
        set of page indices to remove
    """
    if len(reader.pages) <= 1:
        return set()

    cover_indices = set()

    for page_idx, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            continue

        if not text.strip():
            continue

        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if not lines:
            continue

        platform_chars = 0
        total_chars = 0

        for line in lines:
            total_chars += len(line)
            if PLATFORM_PATTERNS.search(line):
                platform_chars += len(line)

        if total_chars == 0:
            continue

        platform_ratio = platform_chars / total_chars
        non_platform_chars = total_chars - platform_chars

        # Cover page: mostly platform text, very little real content
        if platform_ratio > 0.6 and non_platform_chars < 50:
            cover_indices.add(page_idx)

    # Safety: never strip all pages
    if len(cover_indices) >= len(reader.pages):
        return set()

    return cover_indices


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

    # Check if ALL readable text is watermark-related.
    # Skip CID/binary-encoded text (font glyph indices, not human-readable).
    for text_bytes in texts:
        text = text_bytes.decode("latin-1", errors="ignore").strip()
        if not text:
            continue
        # Skip binary/CID-encoded strings (>30% non-printable bytes)
        non_printable = sum(1 for b in text_bytes if b < 32 or b > 126)
        if non_printable > len(text_bytes) * 0.3:
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
    text_blocks = []  # list of (text, is_watermark)

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

    # Detect cover pages from original (before removal alters text)
    cover_pages = _detect_cover_pages(reader)

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

    # Strip cover pages (remove in reverse order to preserve indices)
    if cover_pages:
        for idx in sorted(cover_pages, reverse=True):
            if len(writer.pages) > 1:  # Safety: never leave empty PDF
                del writer.pages[idx]

    # Compress output: deduplicate identical objects and remove orphans
    writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
