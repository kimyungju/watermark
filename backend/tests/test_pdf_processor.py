import os
import tempfile

import fitz  # PyMuPDF
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
        # Normal content
        page.insert_text((72, 72), "This is normal content.", fontsize=12)
        # Watermark: light gray text repeated on every page
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
        # StuDocu-style watermark: appears on every page
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
        # Branding footer on every page — not in WATERMARK_PATTERNS
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
