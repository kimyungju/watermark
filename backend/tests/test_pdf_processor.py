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
