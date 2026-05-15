import json
import os

from services.gemini_watermark import GeminiWatermarkRemover, load_profile

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
