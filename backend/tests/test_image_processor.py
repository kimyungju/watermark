import os
import shutil
import tempfile

import cv2
import numpy as np
import pytest

from services.gemini_watermark import GeminiWatermarkRemover
from services.image_processor import ImageProcessor


@pytest.fixture
def processor():
    return ImageProcessor()


@pytest.fixture
def sample_image_path():
    """Create a test image with a simulated text watermark."""
    img = np.ones((200, 300, 3), dtype=np.uint8) * 200  # Light gray background
    # Add "watermark" text in semi-transparent style
    cv2.putText(img, "SAMPLE", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (180, 180, 180), 3)
    path = os.path.join(tempfile.gettempdir(), "test_watermark.png")
    cv2.imwrite(path, img)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def clean_image_path():
    """Create a test image without watermark."""
    img = np.ones((200, 300, 3), dtype=np.uint8) * 100
    path = os.path.join(tempfile.gettempdir(), "test_clean.png")
    cv2.imwrite(path, img)
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_detect_watermark_returns_mask(processor, sample_image_path):
    img = cv2.imread(sample_image_path)
    mask = processor.detect_watermark(img)
    assert mask is not None
    assert mask.shape[:2] == img.shape[:2]
    assert mask.dtype == np.uint8


def test_process_returns_output_path(processor, sample_image_path):
    output_dir = tempfile.mkdtemp()
    result = processor.process(sample_image_path, output_dir)
    assert "output_path" in result
    assert os.path.exists(result["output_path"])


def test_process_preserves_format_jpg(processor):
    img = np.ones((200, 300, 3), dtype=np.uint8) * 200
    cv2.putText(img, "SAMPLE", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (180, 180, 180), 3)
    path = os.path.join(tempfile.gettempdir(), "test_wm.jpg")
    cv2.imwrite(path, img)
    output_dir = tempfile.mkdtemp()

    result = processor.process(path, output_dir)
    assert result["output_path"].endswith(".jpg")


def test_process_clean_image_returns_unchanged(processor, clean_image_path):
    output_dir = tempfile.mkdtemp()
    result = processor.process(clean_image_path, output_dir)
    assert result["watermark_detected"] is False


GEM_ASSET = os.path.join(os.path.dirname(__file__), "..", "assets", "gemini")


def _calibrated_dir(tmp_path):
    a = np.zeros((48, 48), np.float32)
    cv2.circle(a, (24, 24), 16, 1.0, -1)
    a = cv2.GaussianBlur(a, (5, 5), 0) * 0.7
    d = str(tmp_path)
    shutil.copy(os.path.join(GEM_ASSET, "gemini_profile.json"),
                os.path.join(d, "gemini_profile.json"))
    cv2.imwrite(os.path.join(d, "gemini_alpha_map.png"), (a * 255).astype(np.uint8))
    return d, a


def test_process_removes_gemini_watermark(processor, tmp_path, monkeypatch):
    d, alpha = _calibrated_dir(tmp_path)
    monkeypatch.setattr("services.image_processor.GEMINI_ASSET_DIR", d)
    img = np.full((600, 800, 3), 90, np.uint8)
    x0, y0 = 800 - 32 - 48, 600 - 32 - 48
    base = img[y0:y0 + 48, x0:x0 + 48].astype(np.float32)
    a = alpha[..., None]
    img[y0:y0 + 48, x0:x0 + 48] = (a * 255 + (1 - a) * base).astype(np.uint8)
    p = os.path.join(tempfile.gettempdir(), "gem_in.png")
    cv2.imwrite(p, img)
    out_dir = tempfile.mkdtemp()

    result = processor.process(p, out_dir)

    assert result["watermark_detected"] is True
    cleaned = cv2.imread(result["output_path"])
    assert np.abs(cleaned[y0:y0 + 48, x0:x0 + 48].astype(int) - 90).max() <= 14


def test_process_non_gemini_still_uses_generic_path(processor, sample_image_path):
    # Existing generic SAMPLE-text fixture must keep working (no regression).
    out_dir = tempfile.mkdtemp()
    result = processor.process(sample_image_path, out_dir)
    assert os.path.exists(result["output_path"])
    assert result["watermark_detected"] is True


def test_process_falls_back_to_generic_when_gemini_declines(
    processor, sample_image_path, monkeypatch
):
    # Deterministic: force Gemini to decline -> generic path MUST run and
    # still detect the SAMPLE watermark (proves fall-through, not accident).
    monkeypatch.setattr(
        GeminiWatermarkRemover, "remove", lambda self, img: (img, False)
    )
    out_dir = tempfile.mkdtemp()
    result = processor.process(sample_image_path, out_dir)
    assert os.path.exists(result["output_path"])
    assert result["watermark_detected"] is True


def test_process_falls_back_to_generic_when_gemini_raises(
    processor, sample_image_path, monkeypatch
):
    # The except-Exception fail-open path: a Gemini-path crash must not
    # break processing; the generic detector still produces a result.
    def _boom(self, img):
        raise RuntimeError("simulated gemini failure")

    monkeypatch.setattr(GeminiWatermarkRemover, "remove", _boom)
    out_dir = tempfile.mkdtemp()
    result = processor.process(sample_image_path, out_dir)
    assert os.path.exists(result["output_path"])
    assert result["watermark_detected"] is True
