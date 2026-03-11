import os
import tempfile

import cv2
import numpy as np
import pytest

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
