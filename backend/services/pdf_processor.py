import os
import re
from collections import Counter

import fitz  # PyMuPDF
import numpy as np

from services.image_processor import ImageProcessor

MAX_PDF_PAGES = 20

WATERMARK_PATTERNS = re.compile(
    r"\b(DRAFT|CONFIDENTIAL|SAMPLE|COPY|DO NOT DISTRIBUTE|WATERMARK|PREVIEW)\b",
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

        # Strategy 1: Find text that appears on every page
        page_texts = []
        for page in doc:
            blocks = page.get_text("dict")["blocks"]
            texts = set()
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text = span["text"].strip()
                            if text:
                                texts.add(text)
            page_texts.append(texts)

        if len(page_texts) > 1:
            # Text appearing on every page is likely a watermark
            common_texts = page_texts[0]
            for texts in page_texts[1:]:
                common_texts = common_texts & texts

            for text in common_texts:
                if WATERMARK_PATTERNS.search(text):
                    watermarks.append({"type": "text", "text": text})

        # Strategy 2: Check for light-colored (near white/gray) large text
        for page_num, page in enumerate(doc):
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            color = span.get("color", 0)
                            size = span.get("size", 12)
                            text = span["text"].strip()

                            # Large, light-colored text is likely a watermark
                            if size > 24 and text:
                                r = (color >> 16) & 0xFF
                                g = (color >> 8) & 0xFF
                                b = color & 0xFF
                                # Light gray or near-white
                                if r > 180 and g > 180 and b > 180:
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

        # Deduplicate
        seen = set()
        unique = []
        for w in watermarks:
            key = (w["type"], w["text"])
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

    def _rasterize_and_inpaint(self, input_path: str, output_path: str) -> None:
        """Fallback: convert pages to images, inpaint, reassemble as PDF."""
        import cv2

        doc = fitz.open(input_path)
        output_doc = fitz.open()

        for page in doc:
            # Render page to image at 150 DPI
            pix = page.get_pixmap(dpi=150)
            img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n
            )
            if pix.n == 4:  # RGBA
                img_bgr = cv2.cvtColor(img_data, cv2.COLOR_RGBA2BGR)
            else:
                img_bgr = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)

            # Detect and remove watermark
            mask = self._image_processor.detect_watermark(img_bgr)
            if mask is not None:
                img_bgr = self._image_processor.inpaint(img_bgr, mask)

            # Convert back to RGB for PDF
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

            # Create new page with same dimensions
            new_page = output_doc.new_page(
                width=page.rect.width, height=page.rect.height
            )
            # Encode cleaned image as PNG bytes and insert
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
            # No watermark detected — copy original
            import shutil

            shutil.copy2(input_path, output_path)
            return {"output_path": output_path, "watermark_detected": False}

        # Try text-based removal first
        text_watermarks = [w for w in watermarks if w["type"] == "text"]
        if text_watermarks:
            self._remove_text_watermarks(input_path, output_path, watermarks)
        else:
            # Fallback to rasterize + inpaint
            self._rasterize_and_inpaint(input_path, output_path)

        return {"output_path": output_path, "watermark_detected": True}
