"""Gemini ("Nano Banana") visible-logo removal via Reverse Alpha Blending.

Inverts  watermarked = a*L + (1-a)*original. NOTE: `logo_color` is treated as
a single scalar (white = 255) — Gemini's logo is white. A future tinted logo
variant would silently degrade the math without a regression test catching it;
revisit logo_color handling if a non-white variant appears. SynthID (invisible
watermark) is explicitly out of scope.
"""

import json
import os

import cv2
import numpy as np

ALPHA_MAP_NAME = "gemini_alpha_map.png"
PROFILE_NAME = "gemini_profile.json"


def load_profile(asset_dir: str) -> dict:
    """Load geometry profile and (if present) the calibrated alpha map."""
    with open(os.path.join(asset_dir, PROFILE_NAME)) as f:
        profile = json.load(f)

    alpha_path = os.path.join(asset_dir, ALPHA_MAP_NAME)
    alpha = None
    if os.path.exists(alpha_path):
        raw = cv2.imread(alpha_path, cv2.IMREAD_GRAYSCALE)
        if raw is not None:
            alpha = raw.astype(np.float32) / 255.0
    profile["alpha"] = alpha
    return profile


class GeminiWatermarkRemover:
    def __init__(self, asset_dir: str):
        self.profile = load_profile(asset_dir)

    @property
    def has_alpha(self) -> bool:
        return self.profile.get("alpha") is not None
