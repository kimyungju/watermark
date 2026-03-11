import io
import os
import tempfile

import fitz
import pytest
from pypdf import PdfReader

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
