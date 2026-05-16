import os
import tempfile

import cv2
import numpy as np

from services.gemini_watermark import GeminiWatermarkRemover, load_profile, locate, residual_inpaint, reverse_alpha

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


def _star_alpha(size):
    a = np.zeros((size, size), np.float32)
    cv2.circle(a, (size // 2, size // 2), size // 3, 1.0, -1)
    return cv2.GaussianBlur(a, (5, 5), 0) * 0.7


def test_locate_finds_bottom_right_box_on_composite():
    img = np.full((600, 800, 3), 90, np.uint8)
    alpha = _star_alpha(48)
    x0, y0 = 800 - 32 - 48, 600 - 32 - 48
    region = img[y0:y0 + 48, x0:x0 + 48].astype(np.float32)
    a = alpha[..., None]
    img[y0:y0 + 48, x0:x0 + 48] = (a * 255 + (1 - a) * region).astype(np.uint8)

    variant = {"max_dim_lt": 1024, "box": [32, 32, 48, 48]}
    box, confidence = locate(img, [variant], alpha, search_pad=12)

    bx, by, bw, bh = box
    assert abs(bx - x0) <= 12 and abs(by - y0) <= 12
    assert (bw, bh) == (48, 48)
    assert confidence >= 0.45


def test_locate_low_confidence_on_clean_image():
    img = np.full((600, 800, 3), 90, np.uint8)
    alpha = _star_alpha(48)
    variant = {"max_dim_lt": 1024, "box": [32, 32, 48, 48]}
    _, confidence = locate(img, [variant], alpha, search_pad=12)
    assert confidence < 0.45


def test_locate_discriminates_textured_background():
    """A busy photo-like background must NOT trip the Gemini path, but the
    same background WITH the watermark must. If the no-watermark case here
    exceeds 0.45, raise confidence_threshold in gemini_profile.json."""
    variant = {"max_dim_lt": 1024, "box": [32, 32, 48, 48]}
    alpha = _star_alpha(48)
    rng = np.random.default_rng(7)
    textured = rng.integers(50, 200, size=(600, 800, 3)).astype(np.uint8)

    _, conf_clean = locate(textured.copy(), [variant], alpha, search_pad=12)
    assert conf_clean < 0.45  # textured but no logo -> must not trigger

    wm = textured.copy()
    x0, y0 = 800 - 32 - 48, 600 - 32 - 48
    base = wm[y0:y0 + 48, x0:x0 + 48].astype(np.float32)
    a = alpha[..., None]
    wm[y0:y0 + 48, x0:x0 + 48] = (a * 255 + (1 - a) * base).astype(np.uint8)
    _, conf_wm = locate(wm, [variant], alpha, search_pad=12)
    assert conf_wm >= 0.45  # same background, logo present -> must trigger


def test_residual_inpaint_reduces_max_error_after_jpeg_roundtrip():
    h, w = 64, 64
    rng = np.random.default_rng(1)
    original = rng.integers(40, 180, size=(h, w, 3)).astype(np.uint8)
    yy = np.linspace(0.0, 0.85, h, dtype=np.float32)
    alpha = np.tile(yy[:, None], (1, w))
    a = alpha[..., None]
    wm = (a * 255 + (1 - a) * original).astype(np.uint8)

    # JPEG round-trip degrades the perfect-inverse assumption.
    fd, p = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    try:
        cv2.imwrite(p, wm, [cv2.IMWRITE_JPEG_QUALITY, 80])
        wm_rt = cv2.imread(p).astype(np.float32)
    finally:
        os.remove(p)

    recovered = reverse_alpha(wm_rt, alpha)
    cleaned = residual_inpaint(recovered, alpha, low=0.15, high=0.85)

    err_before = np.abs(recovered.astype(int) - original.astype(int)).max()
    err_after = np.abs(cleaned.astype(int) - original.astype(int)).max()
    assert cleaned.shape == original.shape
    # strict <: passes only if inpaint actually runs (a broken no-op would
    # give err_after == err_before). Empirical gap here is large (>100).
    assert err_after < err_before


def _make_remover_with_alpha(tmp_path, alpha):
    import shutil
    d = str(tmp_path)
    shutil.copy(os.path.join(ASSET_DIR, "gemini_profile.json"),
                os.path.join(d, "gemini_profile.json"))
    cv2.imwrite(os.path.join(d, "gemini_alpha_map.png"),
                (alpha * 255).astype(np.uint8))
    return GeminiWatermarkRemover(d)


def test_remove_recovers_composited_watermark(tmp_path):
    alpha = _star_alpha(48)
    r = _make_remover_with_alpha(tmp_path, alpha)
    img = np.full((600, 800, 3), 90, np.uint8)
    x0, y0 = 800 - 32 - 48, 600 - 32 - 48
    base = img[y0:y0 + 48, x0:x0 + 48].astype(np.float32)
    a = alpha[..., None]
    img[y0:y0 + 48, x0:x0 + 48] = (a * 255 + (1 - a) * base).astype(np.uint8)

    out, removed = r.remove(img)
    assert removed is True
    patch_err = np.abs(
        out[y0:y0 + 48, x0:x0 + 48].astype(int) - 90
    ).max()
    assert patch_err <= 12  # recovered close to flat background


def test_remove_skips_clean_image(tmp_path):
    alpha = _star_alpha(48)
    r = _make_remover_with_alpha(tmp_path, alpha)
    img = np.full((600, 800, 3), 90, np.uint8)
    expected = img.copy()
    out, removed = r.remove(img)
    assert removed is False
    assert np.array_equal(out, expected)


def test_remove_skips_when_no_alpha_asset(tmp_path):
    # Use an isolated dir with ONLY the profile (no alpha PNG). Must not point
    # at the real ASSET_DIR — once Task 7 calibration is run, a real
    # gemini_alpha_map.png lands there and this test would falsely fail.
    import shutil
    d = str(tmp_path)
    shutil.copy(os.path.join(ASSET_DIR, "gemini_profile.json"),
                os.path.join(d, "gemini_profile.json"))
    r = GeminiWatermarkRemover(d)
    assert r.has_alpha is False
    img = np.full((600, 800, 3), 90, np.uint8)
    expected = img.copy()
    out, removed = r.remove(img)
    assert removed is False
    assert np.array_equal(out, expected)
