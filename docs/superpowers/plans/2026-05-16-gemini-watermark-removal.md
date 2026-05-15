# Gemini Nano Banana Watermark Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add near-lossless removal of the *visible* Gemini ("Nano Banana") corner logo to the image pipeline using Reverse Alpha Blending, calibrated from a real Gemini sample.

**Architecture:** A new `GeminiWatermarkRemover` (`backend/services/gemini_watermark.py`) loads a calibrated per-pixel alpha map + geometry profile, locates the bottom-right logo via a size catalog + normalized cross-correlation, inverts the alpha-compositing equation `original = (watermarked − α·L) / (1−α)` to recover original pixels, then runs a thin residual inpaint pass for recompressed inputs. `ImageProcessor.process()` tries this high-confidence path first and falls through to the existing generic detector unchanged when confidence is low or the asset is absent. An offline `calibrate_gemini.py` script derives the real alpha map from a user-supplied Gemini image over a solid background.

**Tech Stack:** Python 3.13, OpenCV (`opencv-python-headless` 4.10), NumPy 2.1.3, pytest. No new dependencies. SynthID (invisible) is explicitly **out of scope** — visible logo only.

**Scope boundary:** Backend-only. No frontend/UI changes — the pipeline auto-detects, so existing `processor.py:53` routing is untouched in behavior. SynthID is not addressed (technically infeasible; entangled with image features).

**Testing strategy (important):** The real proprietary alpha map cannot live in tests. Every test composites a *known original* with a *known synthetic alpha map* and white logo to produce the "watermarked" input, then asserts recovery within rounding tolerance. The real asset is produced operationally by running Task 7's script once on the user's Gemini sample.

**Empirically verified geometry (sample: `Gemini_Generated_Image_wctytwwctytwwcty.png`, 1536×2816):** logo measured at exactly **96×96 px** with **64 px** right/bottom margins on a near-uniform background (BGR ≈ `(93, 143, 176)`). Logo is white but semi-transparent — peak alpha ≈ 0.55. This confirms the large-bucket catalog entry `box: [64, 64, 96, 96]` below is correct, not guessed.

---

### Task 1: Asset scaffolding + profile loader

**Files:**
- Create: `backend/assets/gemini/gemini_profile.json`
- Create: `backend/assets/gemini/README.md`
- Create: `backend/services/gemini_watermark.py`
- Create: `backend/tests/test_gemini_watermark.py`
- Modify: `backend/.gitignore` (create if absent)

- [ ] **Step 1: Write the failing test**

`backend/tests/test_gemini_watermark.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_gemini_watermark.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.gemini_watermark'`

- [ ] **Step 3: Create assets and implementation**

`backend/assets/gemini/gemini_profile.json`:

```json
{
  "logo_color": [255, 255, 255],
  "alpha_clamp": 0.95,
  "search_pad": 12,
  "confidence_threshold": 0.45,
  "variants": [
    { "max_dim_lt": 1024, "box": [32, 32, 48, 48] },
    { "max_dim_lt": 100000, "box": [64, 64, 96, 96] }
  ]
}
```

`backend/assets/gemini/README.md`:

```markdown
# Gemini watermark calibration assets

- `gemini_profile.json` — committed. Geometry catalog: per-size-bucket
  `box = [margin_from_right, margin_from_bottom, width, height]`, logo color,
  alpha clamp, NCC search padding and confidence threshold.
- `gemini_alpha_map.png` — NOT committed (gitignored; may be proprietary).
  Generated once by `python -m services.calibrate_gemini` (see Task 7).
  Until present, the Gemini path is skipped and the generic detector runs.
```

`backend/.gitignore` (append, create if missing):

```
assets/gemini/gemini_alpha_map.png
```

`backend/services/gemini_watermark.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_gemini_watermark.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/gemini_watermark.py backend/tests/test_gemini_watermark.py backend/assets/gemini/ backend/.gitignore
git commit -m "feat: scaffold gemini watermark profile loader and assets"
```

---

### Task 2: Reverse alpha math (`reverse_alpha`)

**Files:**
- Modify: `backend/services/gemini_watermark.py`
- Modify: `backend/tests/test_gemini_watermark.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_gemini_watermark.py`:

```python
import numpy as np

from services.gemini_watermark import reverse_alpha


def _composite(original, alpha, logo=255.0):
    a = alpha[..., None]
    return (a * logo + (1.0 - a) * original).astype(np.uint8)


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_gemini_watermark.py -k reverse_alpha -v`
Expected: FAIL — `ImportError: cannot import name 'reverse_alpha'`

- [ ] **Step 3: Write minimal implementation**

Add to `backend/services/gemini_watermark.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_gemini_watermark.py -k reverse_alpha -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/gemini_watermark.py backend/tests/test_gemini_watermark.py
git commit -m "feat: add reverse alpha blending core math"
```

---

### Task 3: Watermark localization (`locate`)

**Files:**
- Modify: `backend/services/gemini_watermark.py`
- Modify: `backend/tests/test_gemini_watermark.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_gemini_watermark.py`:

```python
from services.gemini_watermark import locate


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_gemini_watermark.py -k locate -v`
Expected: FAIL — `ImportError: cannot import name 'locate'`

- [ ] **Step 3: Write minimal implementation**

Add to `backend/services/gemini_watermark.py`:

```python
def _select_variant(img_shape, variants):
    max_dim = max(img_shape[0], img_shape[1])
    for v in sorted(variants, key=lambda x: x["max_dim_lt"]):
        if max_dim < v["max_dim_lt"]:
            return v
    return variants[-1]


def locate(img: np.ndarray, variants: list, alpha: np.ndarray, search_pad: int = 12):
    """Return (box=(x,y,w,h), confidence). Confidence is max NCC of the
    alpha template against the local brightening the logo introduces."""
    h, w = img.shape[:2]
    variant = _select_variant(img.shape, variants)
    mr, mb, bw, bh = variant["box"]

    px = max(0, w - mr - bw)
    py = max(0, h - mb - bh)
    sx0 = max(0, px - search_pad)
    sy0 = max(0, py - search_pad)
    sx1 = min(w, px + bw + search_pad)
    sy1 = min(h, py + bh + search_pad)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bright = cv2.subtract(gray, cv2.medianBlur(gray, 5))
    search = bright[sy0:sy1, sx0:sx1].astype(np.float32)

    template = (cv2.resize(alpha, (bw, bh)) * 255.0).astype(np.float32)
    if search.shape[0] < bh or search.shape[1] < bw:
        return (px, py, bw, bh), 0.0

    res = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    bx = sx0 + max_loc[0]
    by = sy0 + max_loc[1]
    return (bx, by, bw, bh), float(max_val)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_gemini_watermark.py -k locate -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/gemini_watermark.py backend/tests/test_gemini_watermark.py
git commit -m "feat: add gemini watermark localization via NCC"
```

---

### Task 4: Residual cleanup (`residual_inpaint`)

**Files:**
- Modify: `backend/services/gemini_watermark.py`
- Modify: `backend/tests/test_gemini_watermark.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_gemini_watermark.py`:

```python
import os
import tempfile

from services.gemini_watermark import residual_inpaint, reverse_alpha


def test_residual_inpaint_reduces_max_error_after_jpeg_roundtrip():
    h, w = 64, 64
    rng = np.random.default_rng(1)
    original = rng.integers(40, 180, size=(h, w, 3)).astype(np.uint8)
    yy = np.linspace(0.0, 0.85, h, dtype=np.float32)
    alpha = np.tile(yy[:, None], (1, w))
    a = alpha[..., None]
    wm = (a * 255 + (1 - a) * original).astype(np.uint8)

    # JPEG round-trip degrades the perfect-inverse assumption.
    p = os.path.join(tempfile.gettempdir(), "gem_rt.jpg")
    cv2.imwrite(p, wm, [cv2.IMWRITE_JPEG_QUALITY, 80])
    wm_rt = cv2.imread(p).astype(np.float32)

    recovered = reverse_alpha(wm_rt, alpha)
    cleaned = residual_inpaint(recovered, alpha, low=0.15, high=0.85)

    err_before = np.abs(recovered.astype(int) - original.astype(int)).max()
    err_after = np.abs(cleaned.astype(int) - original.astype(int)).max()
    assert cleaned.shape == original.shape
    assert err_after <= err_before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_gemini_watermark.py -k residual -v`
Expected: FAIL — `ImportError: cannot import name 'residual_inpaint'`

- [ ] **Step 3: Write minimal implementation**

Add to `backend/services/gemini_watermark.py`:

```python
def residual_inpaint(
    region: np.ndarray,
    alpha: np.ndarray,
    low: float = 0.15,
    high: float = 0.85,
) -> np.ndarray:
    """Inpaint the thin band where alpha is mid-strength — the area most
    sensitive to recompression error in the reverse-alpha estimate."""
    a = cv2.resize(alpha, (region.shape[1], region.shape[0]))
    mask = ((a >= low) & (a <= high)).astype(np.uint8) * 255
    if mask.max() == 0:
        return region
    return cv2.inpaint(region, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_gemini_watermark.py -k residual -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/gemini_watermark.py backend/tests/test_gemini_watermark.py
git commit -m "feat: add residual inpaint cleanup for recompressed inputs"
```

---

### Task 5: `remove()` orchestration

**Files:**
- Modify: `backend/services/gemini_watermark.py`
- Modify: `backend/tests/test_gemini_watermark.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_gemini_watermark.py`:

```python
def _make_remover_with_alpha(tmp_path, size, alpha):
    import json
    import shutil
    d = str(tmp_path)
    shutil.copy(os.path.join(ASSET_DIR, "gemini_profile.json"),
                os.path.join(d, "gemini_profile.json"))
    cv2.imwrite(os.path.join(d, "gemini_alpha_map.png"),
                (alpha * 255).astype(np.uint8))
    return GeminiWatermarkRemover(d)


def test_remove_recovers_composited_watermark(tmp_path):
    alpha = _star_alpha(48)
    r = _make_remover_with_alpha(tmp_path, 48, alpha)
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
    r = _make_remover_with_alpha(tmp_path, 48, alpha)
    img = np.full((600, 800, 3), 90, np.uint8)
    out, removed = r.remove(img)
    assert removed is False
    assert np.array_equal(out, img)


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
    out, removed = r.remove(img)
    assert removed is False
    assert np.array_equal(out, img)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_gemini_watermark.py -k remove -v`
Expected: FAIL — `AttributeError: 'GeminiWatermarkRemover' object has no attribute 'remove'`

- [ ] **Step 3: Write minimal implementation**

Add the `remove` method to `GeminiWatermarkRemover` in `backend/services/gemini_watermark.py`:

```python
    def remove(self, img: np.ndarray):
        """Return (image, removed: bool). Non-destructive when confidence is
        low or no calibrated alpha map is present."""
        alpha = self.profile.get("alpha")
        if alpha is None:
            return img, False

        variants = self.profile["variants"]
        pad = self.profile.get("search_pad", 12)
        threshold = self.profile.get("confidence_threshold", 0.45)
        logo = float(self.profile.get("logo_color", [255, 255, 255])[0])
        clamp = float(self.profile.get("alpha_clamp", 0.95))

        box, confidence = locate(img, variants, alpha, search_pad=pad)
        if confidence < threshold:
            return img, False

        x, y, bw, bh = box
        out = img.copy()
        region = out[y:y + bh, x:x + bw].astype(np.float32)
        a = cv2.resize(alpha, (bw, bh))
        recovered = reverse_alpha(region, a, logo_color=logo, alpha_clamp=clamp)
        recovered = residual_inpaint(recovered, a)
        out[y:y + bh, x:x + bw] = recovered
        return out, True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_gemini_watermark.py -k remove -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/gemini_watermark.py backend/tests/test_gemini_watermark.py
git commit -m "feat: add gemini watermark remove orchestration"
```

---

### Task 6: Integrate into `ImageProcessor.process()`

**Files:**
- Modify: `backend/services/image_processor.py:95-112` (the `process` method)
- Modify: `backend/tests/test_image_processor.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_image_processor.py`:

```python
import shutil

from services.gemini_watermark import GeminiWatermarkRemover

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
    monkeypatch.setattr(
        "services.image_processor.GEMINI_ASSET_DIR", d, raising=False
    )
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_image_processor.py -k gemini -v`
Expected: FAIL — `AttributeError` on `services.image_processor.GEMINI_ASSET_DIR` / Gemini path not invoked

- [ ] **Step 3: Write minimal implementation**

In `backend/services/image_processor.py`, add near the top imports:

```python
from services.gemini_watermark import GeminiWatermarkRemover

GEMINI_ASSET_DIR = os.path.join(
    os.path.dirname(__file__), "..", "assets", "gemini"
)
```

Replace the body of `process` (currently `backend/services/image_processor.py:95-112`) with:

```python
    def process(self, input_path: str, output_dir: str) -> dict:
        """Process a single image. Returns dict with output_path and watermark_detected."""
        img = cv2.imread(input_path)
        if img is None:
            raise ValueError(f"Cannot read image: {input_path}")

        ext = os.path.splitext(input_path)[1].lower()
        output_path = os.path.join(output_dir, f"output{ext}")

        # High-confidence Gemini logo path first (near-lossless reverse-alpha).
        try:
            gem = GeminiWatermarkRemover(GEMINI_ASSET_DIR)
            gem_out, gem_removed = gem.remove(img)
            if gem_removed:
                cv2.imwrite(output_path, gem_out)
                return {"output_path": output_path, "watermark_detected": True}
        except Exception:
            pass  # any failure → fall back to generic detector below

        mask = self.detect_watermark(img)
        if mask is None:
            cv2.imwrite(output_path, img)
            return {"output_path": output_path, "watermark_detected": False}

        result = self.inpaint(img, mask)
        cv2.imwrite(output_path, result)
        return {"output_path": output_path, "watermark_detected": True}
```

Note: `import os` already exists at `backend/services/image_processor.py:1`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_image_processor.py -v`
Expected: PASS (all, including the two new tests and the 4 pre-existing tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/image_processor.py backend/tests/test_image_processor.py
git commit -m "feat: route images through gemini reverse-alpha path first"
```

---

### Task 7: Offline calibration script

**Files:**
- Create: `backend/services/calibrate_gemini.py`
- Create: `backend/tests/test_calibrate_gemini.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_calibrate_gemini.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_calibrate_gemini.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.calibrate_gemini'`

- [ ] **Step 3: Write implementation**

`backend/services/calibrate_gemini.py`:

```python
"""Offline one-time calibration.

Derive the Gemini logo's per-pixel alpha map from a real sample placed over a
solid background. Solves alpha from  W = a*L + (1-a)*O  ->  a = (W-O)/(L-O),
averaged over channels.

Usage:
    python -m services.calibrate_gemini \
        --sample path/to/gemini_sample.png \
        --bg 60 60 60 \
        --box X Y W H \
        --out backend/assets/gemini
"""

import argparse
import json
import os

import cv2
import numpy as np


def extract_alpha(region_bgr: np.ndarray, bg_color, logo_color: float = 255.0) -> np.ndarray:
    """region_bgr: HxWx3 uint8 watermark region over a solid bg_color (B,G,R-agnostic
    here since bg is gray-ish; use per-channel then average)."""
    w = region_bgr.astype(np.float32)
    o = np.array(bg_color, np.float32).reshape(1, 1, 3)
    denom = (logo_color - o)
    denom[denom == 0] = 1e-6
    a = (w - o) / denom
    a = a.mean(axis=2)
    return np.clip(a, 0.0, 1.0).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--bg", nargs=3, type=int, required=True,
                    help="solid background color the sample was generated over (B G R)")
    ap.add_argument("--box", nargs=4, type=int, required=True,
                    help="watermark region in the sample: X Y W H")
    ap.add_argument("--out", required=True, help="assets/gemini dir")
    args = ap.parse_args()

    img = cv2.imread(args.sample)
    if img is None:
        raise SystemExit(f"cannot read sample: {args.sample}")
    x, y, w, h = args.box
    region = img[y:y + h, x:x + w]
    alpha = extract_alpha(region, bg_color=tuple(args.bg))

    os.makedirs(args.out, exist_ok=True)
    cv2.imwrite(os.path.join(args.out, "gemini_alpha_map.png"),
                (alpha * 255).astype(np.uint8))

    profile_path = os.path.join(args.out, "gemini_profile.json")
    with open(profile_path) as f:
        profile = json.load(f)
    profile["calibrated_box"] = [x, y, w, h]
    with open(profile_path, "w") as f:
        json.dump(profile, f, indent=2)

    print(f"wrote {os.path.join(args.out, 'gemini_alpha_map.png')} "
          f"({w}x{h}); updated {profile_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_calibrate_gemini.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/services/calibrate_gemini.py backend/tests/test_calibrate_gemini.py
git commit -m "feat: add offline gemini alpha-map calibration script"
```

---

### Task 8: Docs + full-suite verification + operational calibration note

**Files:**
- Modify: `CLAUDE.md` (Backend services list + Key Constraints)
- Modify: `backend/assets/gemini/README.md`

- [ ] **Step 1: Update CLAUDE.md**

In `CLAUDE.md` under the `### Backend (\`backend/\`)` services list, add after the `services/image_processor.py` bullet:

```markdown
- `services/gemini_watermark.py` — Gemini ("Nano Banana") visible-logo removal via Reverse Alpha Blending (`original = (watermarked − α·L)/(1−α)`). Loads a calibrated alpha map + geometry profile from `assets/gemini/`. Tried first in `ImageProcessor.process()`; falls through to the generic detector when confidence < threshold or no alpha map present. Visible logo ONLY — SynthID (invisible) is out of scope.
- `services/calibrate_gemini.py` — offline one-time script deriving the real alpha map from a Gemini sample over a solid background.
```

- [ ] **Step 2: Append operational instructions to the asset README**

Append to `backend/assets/gemini/README.md`:

```markdown

## Generating the real alpha map (one time)

Any Gemini Nano Banana image over a *solid* background works (the bg need not
be gray — `extract_alpha` solves per-channel for any flat color).

For the verified sample `Gemini_Generated_Image_wctytwwctytwwcty.png`
(1536×2816, bg BGR (93,143,176), logo at x=2656 y=1376, 96×96), the exact
ready-to-run command is:

```
cd backend && python -m services.calibrate_gemini \
    --sample "C:/Users/yjkim/Downloads/Gemini_Generated_Image_wctytwwctytwwcty.png" \
    --bg 93 143 176 --box 2656 1376 96 96 \
    --out assets/gemini
```

For a different sample: read its dimensions, sample a flat patch away from the
logo for `--bg` (B G R), and measure the bottom-right logo box for `--box`
(X Y W H). This writes `gemini_alpha_map.png` (gitignored); the Gemini path
then activates automatically with no code change.
```

- [ ] **Step 3: Run the full backend suite**

First capture the actual pre-change baseline (don't trust a hardcoded count):

Run: `cd backend && git stash --include-untracked && python -m pytest tests/ --collect-only -q | tail -1 && git stash pop`
(Record that number as the baseline.)

Then run the full suite with the new code:

Run: `cd backend && python -m pytest tests/ -v`
Expected: PASS — every pre-existing test (the recorded baseline) plus the new `test_gemini_watermark.py`, `test_calibrate_gemini.py`, and the added `test_image_processor.py` cases. Zero regressions in the pre-existing set.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md backend/assets/gemini/README.md
git commit -m "docs: document gemini watermark removal and calibration"
```

---

## Self-Review

**Spec coverage:**
- Reverse Alpha Blending core math → Task 2 ✓
- Calibrated alpha map source (user choice: self-calibration) → Task 7 + operational note Task 8 ✓
- Localization (size catalog + NCC) → Task 3 ✓
- Residual cleanup for recompressed inputs → Task 4 ✓
- Orchestration + graceful skip when no asset / low confidence → Task 5 ✓
- Pipeline integration without regressing generic/PDF paths → Task 6 (explicit no-regression test) ✓
- SynthID explicitly out of scope → stated in header, CLAUDE.md note Task 8 ✓
- Backend-only scope, no frontend change → header; `processor.py` untouched ✓

**Placeholder scan:** No TBD/TODO. Every code step has full code. The only "manual" element (running calibration on the real sample) is an *operational* step with an exact command, not a code placeholder — tests use synthetic ground-truth composites and pass without the real asset.

**Type consistency:** `reverse_alpha(watermarked, alpha, logo_color, alpha_clamp)`, `locate(img, variants, alpha, search_pad) -> (box, confidence)`, `residual_inpaint(region, alpha, low, high)`, `GeminiWatermarkRemover.remove(img) -> (img, bool)`, `load_profile(asset_dir) -> dict` with `profile["alpha"]`, `extract_alpha(region_bgr, bg_color, logo_color)` — names and signatures are consistent across Tasks 1–8. Profile JSON keys (`logo_color`, `alpha_clamp`, `search_pad`, `confidence_threshold`, `variants[].box`) are consistent between Task 1 asset and Tasks 3/5 consumers.
