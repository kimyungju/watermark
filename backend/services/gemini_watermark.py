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
    with open(os.path.join(asset_dir, PROFILE_NAME), encoding="utf-8") as f:
        profile = json.load(f)

    alpha_path = os.path.join(asset_dir, ALPHA_MAP_NAME)
    alpha = None
    if os.path.exists(alpha_path):
        raw = cv2.imread(alpha_path, cv2.IMREAD_GRAYSCALE)
        if raw is not None:
            alpha = raw.astype(np.float32) / 255.0
    profile["alpha"] = alpha
    return profile


def reverse_alpha(
    watermarked: np.ndarray,
    alpha: np.ndarray,
    logo_color: float = 255.0,
    alpha_clamp: float = 0.95,
) -> np.ndarray:
    """Invert watermarked = a*logo + (1-a)*original to recover original.

    watermarked: float32 HxWx3. alpha: float32 HxW in [0,1).
    Alpha is clamped to alpha_clamp so the (1-a) denominator stays bounded.
    """
    a = np.clip(alpha, 0.0, alpha_clamp).astype(np.float32)[..., None]
    original = (watermarked - a * logo_color) / (1.0 - a)
    return np.clip(original, 0.0, 255.0).astype(np.uint8)


def _select_variant(img_shape, variants):
    max_dim = max(img_shape[0], img_shape[1])
    sorted_v = sorted(variants, key=lambda x: x["max_dim_lt"])
    for v in sorted_v:
        if max_dim < v["max_dim_lt"]:
            return v
    return sorted_v[-1]  # largest bucket; must index the SORTED list


def locate(img: np.ndarray, variants: list, alpha: np.ndarray, search_pad: int = 12):
    """Return (box=(x,y,w,h), confidence). Confidence is the max NCC of the
    alpha template against the local grayscale around the expected box."""
    h, w = img.shape[:2]
    variant = _select_variant(img.shape, variants)
    mr, mb, bw, bh = variant["box"]

    px = max(0, w - mr - bw)
    py = max(0, h - mb - bh)
    sx0 = max(0, px - search_pad)
    sy0 = max(0, py - search_pad)
    sx1 = min(w, px + bw + search_pad)
    sy1 = min(h, py + bh + search_pad)

    # NCC the alpha template directly against the float grayscale crop.
    # TM_CCOEFF_NORMED subtracts each window's mean and normalizes, so the
    # template's absolute scale is irrelevant and a roughly-flat background
    # cancels out — the logo's alpha pattern dominates the local variance.
    # (A medianBlur high-pass fails here: a small kernel sits entirely inside
    # a tens-of-px logo, giving ~0 interior response and ~0 correlation.)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    search = gray[sy0:sy1, sx0:sx1]

    template = cv2.resize(alpha, (bw, bh)).astype(np.float32)
    if search.shape[0] < bh or search.shape[1] < bw:
        return (px, py, bw, bh), 0.0

    res = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    bx = sx0 + max_loc[0]
    by = sy0 + max_loc[1]
    return (bx, by, bw, bh), float(max_val)


class GeminiWatermarkRemover:
    def __init__(self, asset_dir: str):
        self.profile = load_profile(asset_dir)

    @property
    def has_alpha(self) -> bool:
        return self.profile.get("alpha") is not None
