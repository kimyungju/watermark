import io
import os
import shutil
from collections import Counter

import fitz  # PyMuPDF

from services.constants import PLATFORM_PATTERNS, CLASSIC_WATERMARK_PATTERNS, IGNORE_COMMON_TEXT

MAX_PDF_PAGES = 20

# Alias for backward compatibility within this file
WATERMARK_PATTERNS = CLASSIC_WATERMARK_PATTERNS


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

    def _remove_text_watermarks_fitz(self, input_bytes: bytes, watermarks: list[dict]) -> bytes:
        """Remove pattern-matched text watermarks using fitz redaction.

        Only redacts text matching PLATFORM_PATTERNS or CLASSIC_WATERMARK_PATTERNS,
        not all cross-page text (which may include legitimate headers/footers).
        """
        # Filter to text watermarks matching known patterns
        texts_to_redact = set()
        for w in watermarks:
            if w.get("type") != "text":
                continue
            text = w.get("text", "")
            if PLATFORM_PATTERNS.search(text) or CLASSIC_WATERMARK_PATTERNS.search(text):
                texts_to_redact.add(text)

        if not texts_to_redact:
            return input_bytes

        doc = fitz.open(stream=input_bytes, filetype="pdf")
        redacted_any = False

        for page in doc:
            page_had_redactions = False
            for text in texts_to_redact:
                instances = page.search_for(text)
                for inst in instances:
                    page.add_redact_annot(inst, fill=(1, 1, 1))
                    page_had_redactions = True
            if page_had_redactions:
                page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
                redacted_any = True

        if not redacted_any:
            doc.close()
            return input_bytes

        buf = io.BytesIO()
        doc.save(buf)
        doc.close()
        return buf.getvalue()

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

        with open(input_path, "rb") as f:
            pdf_bytes = f.read()

        # Phase 1: fitz redaction for pattern-matched text watermarks
        pdf_bytes = self._remove_text_watermarks_fitz(pdf_bytes, watermarks)

        # Phase 2: pypdf structural removal (annotations, XObjects, cross-page heuristics, cover pages)
        from services.pdf_watermark_remover import remove_watermark

        cleaned_bytes = remove_watermark(pdf_bytes)

        with open(output_path, "wb") as f:
            f.write(cleaned_bytes)

        return {"output_path": output_path, "watermark_detected": True}
