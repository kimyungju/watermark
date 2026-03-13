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
    _is_watermark_stream,
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

    def test_removes_uri_platform_annotation(self):
        """Annotations linking to known platform URIs should be removed."""
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

        annot = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/Rect"): ArrayObject(
                    [NumberObject(72), NumberObject(700), NumberObject(200), NumberObject(720)]
                ),
                NameObject("/A"): DictionaryObject(
                    {
                        NameObject("/S"): NameObject("/URI"),
                        NameObject("/URI"): TextStringObject("https://www.studocu.com/doc/123"),
                    }
                ),
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


class TestOutputCompression:
    """Verify output PDF is compressed."""

    def test_output_not_larger_than_input(self):
        """Output should not be significantly larger than input for clean PDFs."""
        doc = fitz.open()
        for i in range(5):
            page = doc.new_page()
            page.insert_text((72, 100), f"Page {i+1} content " * 20, fontsize=12)
        pdf_bytes = doc.tobytes()
        doc.close()

        result = remove_watermark(pdf_bytes)
        # Output should not be more than 2x the input size
        assert len(result) < len(pdf_bytes) * 2, (
            f"Output ({len(result)}) is more than 2x input ({len(pdf_bytes)})"
        )

    def test_compression_reduces_duplicate_objects(self):
        """PDFs with duplicate objects should benefit from compression."""
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text((72, 100), f"Content page {i+1}", fontsize=12)
            page.insert_text((200, 400), "CONFIDENTIAL", fontsize=48, color=(0.9, 0.9, 0.9))
        pdf_bytes = doc.tobytes()
        doc.close()

        result = remove_watermark(pdf_bytes)
        # Just verify it completes without error and produces valid PDF
        reader = PdfReader(io.BytesIO(result))
        assert len(reader.pages) == 3


class TestCoverPageDetection:
    """Test detection and removal of platform-injected cover pages."""

    def _make_pdf_with_cover(self, cover_text, body_texts, trailing_text=None):
        """Helper: create a PDF with a cover page, body pages, and optional trailing page.

        Args:
            cover_text: text content for the cover page (platform branding)
            body_texts: list of text strings, one per body page
            trailing_text: optional text for a trailing cover page
        """
        doc = fitz.open()

        # Cover page
        page = doc.new_page()
        page.insert_text((72, 100), cover_text, fontsize=14)

        # Body pages
        for text in body_texts:
            page = doc.new_page()
            page.insert_text((72, 100), text, fontsize=12)

        # Optional trailing page
        if trailing_text:
            page = doc.new_page()
            page.insert_text((72, 100), trailing_text, fontsize=14)

        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    def test_detects_studocu_cover_page(self):
        """A page with only StuDocu branding text is a cover page."""
        from services.pdf_watermark_remover import _detect_cover_pages

        pdf_bytes = self._make_pdf_with_cover(
            "Downloaded by User (user@email.com)\nlOMoARcPSD|12345678\nStuDocu is not sponsored or endorsed by any college",
            ["This is the actual lecture content about thermodynamics.", "More content here."],
        )
        reader = PdfReader(io.BytesIO(pdf_bytes))
        cover_indices = _detect_cover_pages(reader)
        assert 0 in cover_indices
        assert 1 not in cover_indices
        assert 2 not in cover_indices

    def test_does_not_flag_body_pages(self):
        """Pages with real content are not cover pages."""
        from services.pdf_watermark_remover import _detect_cover_pages

        pdf_bytes = self._make_pdf_with_cover(
            "Downloaded by User\nlOMoARcPSD|12345678",
            ["Lecture 1: Introduction to Computer Science\nThis course covers algorithms and data structures."],
        )
        reader = PdfReader(io.BytesIO(pdf_bytes))
        cover_indices = _detect_cover_pages(reader)
        assert 0 in cover_indices
        assert 1 not in cover_indices

    def test_detects_trailing_cover_page(self):
        """A trailing platform page is also detected."""
        from services.pdf_watermark_remover import _detect_cover_pages

        pdf_bytes = self._make_pdf_with_cover(
            "Downloaded by User\nlOMoARcPSD|12345678",
            ["Real content page."],
            trailing_text="Get the app\nStuDocu is not sponsored or endorsed",
        )
        reader = PdfReader(io.BytesIO(pdf_bytes))
        cover_indices = _detect_cover_pages(reader)
        assert 0 in cover_indices
        assert 2 in cover_indices
        assert 1 not in cover_indices

    def test_single_page_pdf_never_stripped(self):
        """Single-page PDFs are never stripped (early return for len <= 1)."""
        from services.pdf_watermark_remover import _detect_cover_pages

        pdf_bytes = self._make_pdf_with_cover(
            "Downloaded by User\nlOMoARcPSD|12345678",
            [],  # No body pages — only the cover
        )
        reader = PdfReader(io.BytesIO(pdf_bytes))
        cover_indices = _detect_cover_pages(reader)
        assert len(cover_indices) == 0

    def test_all_cover_pages_multipage_returns_empty(self):
        """If ALL pages are cover pages, keep them all (safety guard)."""
        from services.pdf_watermark_remover import _detect_cover_pages

        # Both pages are platform branding — safety guard prevents stripping all
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), "Downloaded by User\nlOMoARcPSD|12345678", fontsize=14)
        page = doc.new_page()
        page.insert_text((72, 100), "Get the app\nStuDocu is not sponsored or endorsed", fontsize=14)
        pdf_bytes = doc.tobytes()
        doc.close()

        reader = PdfReader(io.BytesIO(pdf_bytes))
        cover_indices = _detect_cover_pages(reader)
        # Safety: never strip all pages
        assert len(cover_indices) == 0

    def test_cover_pages_removed_from_output(self):
        """End-to-end: remove_watermark strips cover pages from final output."""
        pdf_bytes = self._make_pdf_with_cover(
            "Downloaded by User\nlOMoARcPSD|12345678\nStuDocu is not sponsored",
            ["Real content page 1.", "Real content page 2."],
        )
        result = remove_watermark(pdf_bytes)
        reader = PdfReader(io.BytesIO(result))
        # Cover page should be gone: 3 pages -> 2 pages
        assert len(reader.pages) == 2

    def test_image_heavy_page_not_stripped(self):
        """Pages with large images should never be flagged as cover pages,
        even if their only text is watermark text."""
        from services.pdf_watermark_remover import _detect_cover_pages

        # Create a 3-page PDF:
        # Page 0: StuDocu cover (text only, platform patterns)
        # Page 1: Content with large image + watermark text only
        # Page 2: Content with large image + watermark text only
        doc = fitz.open()

        # Page 0: cover page
        p0 = doc.new_page()
        p0.insert_text((72, 100), "studocu.com", fontsize=20)
        p0.insert_text((72, 140), "messages.downloaded_by", fontsize=8)
        p0.insert_text((72, 160), "lOMoARcPSD|12345678", fontsize=1)

        # Page 1: image content + watermark text
        p1 = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 500), 0)
        pix.set_rect(fitz.IRect(0, 0, 400, 500), (200, 200, 200))
        p1.insert_image(fitz.Rect(0, 0, 400, 500), pixmap=pix)
        p1.insert_text((72, 550), "messages.downloaded_by", fontsize=8, color=(0.3, 0.3, 0.3))

        # Page 2: same as page 1
        p2 = doc.new_page()
        p2.insert_image(fitz.Rect(0, 0, 400, 500), pixmap=pix)
        p2.insert_text((72, 550), "messages.downloaded_by", fontsize=8, color=(0.3, 0.3, 0.3))

        pdf_bytes = doc.tobytes()
        doc.close()

        reader = PdfReader(io.BytesIO(pdf_bytes))
        result = _detect_cover_pages(reader)

        # Page 0 should be flagged as cover (text-only, all platform)
        # Pages 1-2 should NOT be flagged (they have large images)
        assert 0 in result, "Page 0 (cover) should be detected"
        assert 1 not in result, "Page 1 (image content) should NOT be stripped"
        assert 2 not in result, "Page 2 (image content) should NOT be stripped"

    def test_page_with_mixed_content_not_stripped(self):
        """A page with some platform text but also substantial content is kept."""
        from services.pdf_watermark_remover import _detect_cover_pages

        pdf_bytes = self._make_pdf_with_cover(
            "Downloaded by User\nlOMoARcPSD|12345678\n"
            "Chapter 1: Introduction\nThis chapter explores the fundamental concepts of "
            "quantum mechanics including wave-particle duality and the uncertainty principle.",
            ["More real content."],
        )
        reader = PdfReader(io.BytesIO(pdf_bytes))
        cover_indices = _detect_cover_pages(reader)
        # Page 0 has substantial non-platform text — should NOT be stripped
        assert 0 not in cover_indices
