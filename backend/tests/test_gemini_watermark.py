import os

import numpy as np

from services.gemini_watermark import GeminiWatermarkRemover, load_profile, reverse_alpha

ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "gemini")


def test_load_profile_reads_catalog():
    profile = load_profile(ASSET_DIR)
    assert profile["logo_color"] == [255, 255, 255]
    assert 0.0 < profile["alpha_clamp"] < 1.0
    assert len(profile["variants"]) >= 1
    v = profile["variants"][0]
    assert {"max_dim_lt", "box"} <= set(v.keys())
    assert len(v["box"]) == 4  # [margin_right, margin_bottom, w, h]


def test_load_profile_missing_alpha_is_graceful():
    profile = load_profile(ASSET_DIR)
    # alpha map PNG is not committed; loader must not raise.
    assert profile["alpha"] is None or profile["alpha"].ndim == 2


def test_remover_constructs_without_asset():
    r = GeminiWatermarkRemover(ASSET_DIR)
    assert r.has_alpha in (True, False)


def _composite(original, alpha, logo=255.0):
    a = alpha[..., None]
    return a * logo + (1.0 - a) * original  # stays float; uint8 cast would amplify rounding error


def test_reverse_alpha_recovers_original_within_tolerance():
    h, w = 48, 48
    rng = np.random.default_rng(0)
    original = rng.integers(20, 200, size=(h, w, 3)).astype(np.uint8)
    yy = np.linspace(0.0, 0.9, h, dtype=np.float32)
    alpha = np.tile(yy[:, None], (1, w))  # 0.0 .. 0.9 ramp, all < clamp
    watermarked = _composite(original, alpha).astype(np.float32)

    recovered = reverse_alpha(watermarked, alpha, logo_color=255.0, alpha_clamp=0.95)

    assert recovered.dtype == np.uint8
    assert recovered.shape == (h, w, 3)
    assert int(np.abs(recovered.astype(int) - original.astype(int)).max()) <= 3


def test_reverse_alpha_handles_saturated_alpha_without_nan():
    h, w = 16, 16
    original = np.full((h, w, 3), 100, np.uint8)
    alpha = np.full((h, w), 0.999, np.float32)  # above clamp
    watermarked = _composite(original, alpha).astype(np.float32)

    recovered = reverse_alpha(watermarked, alpha, logo_color=255.0, alpha_clamp=0.95)

    assert np.isfinite(recovered).all()
    assert recovered.min() >= 0 and recovered.max() <= 255
