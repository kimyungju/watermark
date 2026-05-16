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
    """region_bgr: HxWx3 uint8 watermark region over a solid bg_color.
    Solves a = (W - O) / (L - O) per channel, averaged, clipped to [0,1]."""
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
    with open(profile_path, encoding="utf-8") as f:
        profile = json.load(f)
    profile["calibrated_box"] = [x, y, w, h]
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    print(f"wrote {os.path.join(args.out, 'gemini_alpha_map.png')} "
          f"({w}x{h}); updated {profile_path}")


if __name__ == "__main__":
    main()
