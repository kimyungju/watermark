import os
import re
import shutil
from collections import Counter

import fitz  # PyMuPDF
import numpy as np

from services.image_processor import ImageProcessor

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
    def __init__(self):
        self._image_processor = ImageProcessor()

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
        # Any text on every page is suspicious (watermarks, branding, tracking).
        # No keyword filtering — real watermarks don't say "WATERMARK".
        if len(page_texts) > 1:
            common_texts = page_texts[0]
            for texts in page_texts[1:]:
                common_texts = common_texts & texts

            for text in common_texts:
                # Skip very short text (page numbers, bullets) and known harmless
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
        # Scan ALL text for known platform signatures
        for page_num, text, size, color, bbox in all_spans:
            if PLATFORM_PATTERNS.search(text):
                watermarks.append({
                    "type": "text",
                    "text": text,
                    "page": page_num,
                })

        # ── Strategy 4: Repeated images across pages (banners/logos) ──
        # Detect image blocks at similar positions on multiple pages
        page_images = {}  # page_num -> list of (bbox, width, height)
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

        # Find images that appear at similar positions across 2+ pages
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
        # Catches single-page banners like StuDocu footer logos
        for page_num, imgs in page_images.items():
            page_h = doc[page_num].rect.height if page_num < len(doc) else 842
            for bbox, w, h in imgs:
                render_w = bbox[2] - bbox[0]
                render_h = max(bbox[3] - bbox[1], 1)
                aspect = render_w / render_h
                y_ratio = bbox[1] / max(page_h, 1)

                # Banner-like: very wide and at top or bottom of page
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

    def _remove_text_watermarks(
        self, input_path: str, output_path: str, watermarks: list[dict]
    ) -> None:
        """Remove detected text watermarks using redaction."""
        doc = fitz.open(input_path)
        watermark_texts = {w["text"] for w in watermarks if w["type"] == "text"}

        for page in doc:
            for text in watermark_texts:
                areas = page.search_for(text)
                for area in areas:
                    page.add_redact_annot(area, fill=(1, 1, 1))
            page.apply_redactions()

        doc.save(output_path)
        doc.close()

    def _remove_image_watermarks(
        self, doc_path: str, output_path: str, watermarks: list[dict]
    ) -> None:
        """Remove detected image watermarks by whiting out their areas."""
        doc = fitz.open(doc_path)
        image_watermarks = [w for w in watermarks if w["type"] == "image"]

        for wm in image_watermarks:
            sig = wm["bbox_signature"]
            for page_num in wm.get("pages", []):
                if page_num < len(doc):
                    page = doc[page_num]
                    # Find matching image blocks and white them out
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
                                rect = fitz.Rect(bbox)
                                page.add_redact_annot(rect, fill=(1, 1, 1))
                    page.apply_redactions()

        doc.save(output_path)
        doc.close()

    def _rasterize_and_inpaint(self, input_path: str, output_path: str) -> None:
        """Fallback: convert pages to images, inpaint, reassemble as PDF."""
        import cv2

        doc = fitz.open(input_path)
        output_doc = fitz.open()

        for page in doc:
            pix = page.get_pixmap(dpi=150)
            img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 4:
                img_bgr = cv2.cvtColor(img_data, cv2.COLOR_RGBA2BGR)
            else:
                img_bgr = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)

            mask = self._image_processor.detect_watermark(img_bgr)
            if mask is not None:
                img_bgr = self._image_processor.inpaint(img_bgr, mask)

            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

            new_page = output_doc.new_page(
                width=page.rect.width, height=page.rect.height
            )
            _, png_bytes = cv2.imencode(".png", cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR))
            new_page.insert_image(new_page.rect, stream=png_bytes.tobytes())

        output_doc.save(output_path)
        output_doc.close()
        doc.close()

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

        text_watermarks = [w for w in watermarks if w["type"] == "text"]
        image_watermarks = [w for w in watermarks if w["type"] == "image"]

        # Step 1: Remove text watermarks via redaction
        if text_watermarks:
            self._remove_text_watermarks(input_path, output_path, watermarks)
            # Step 2: Remove image watermarks from the already-redacted file
            if image_watermarks:
                temp_path = output_path + ".tmp"
                os.rename(output_path, temp_path)
                self._remove_image_watermarks(temp_path, output_path, watermarks)
                os.remove(temp_path)
        elif image_watermarks:
            self._remove_image_watermarks(input_path, output_path, watermarks)
        else:
            self._rasterize_and_inpaint(input_path, output_path)

        return {"output_path": output_path, "watermark_detected": True}
