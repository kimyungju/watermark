import json
import os

import cv2
import numpy as np

from services.calibrate_gemini import extract_alpha


def test_extract_alpha_recovers_known_alpha_from_solid_bg():
    # Ground truth: solid background O, white logo L=255, known alpha.
    size = 48
    bg = (60, 60, 60)
    true_alpha = np.zeros((size, size), np.float32)
    cv2.circle(true_alpha, (24, 24), 15, 0.8, -1)

    O = np.full((size, size, 3), bg, np.uint8).astype(np.float32)
    a = true_alpha[..., None]
    watermarked = (a * 255 + (1 - a) * O).astype(np.uint8)

    recovered = extract_alpha(watermarked, bg_color=bg, logo_color=255.0)

    assert recovered.shape == (size, size)
    assert float(np.abs(recovered - true_alpha).max()) <= 0.03


def test_extract_alpha_clips_to_unit_range():
    size = 16
    watermarked = np.full((size, size, 3), 255, np.uint8)
    recovered = extract_alpha(watermarked, bg_color=(0, 0, 0), logo_color=255.0)
    assert recovered.min() >= 0.0 and recovered.max() <= 1.0
