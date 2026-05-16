# Gemini watermark calibration assets

- `gemini_profile.json` — committed. Geometry catalog: per-size-bucket
  `box = [margin_from_right, margin_from_bottom, width, height]`, logo color,
  alpha clamp, NCC search padding and confidence threshold.
- `gemini_alpha_map.png` — NOT committed (gitignored; may be proprietary).
  Generated once by `python -m services.calibrate_gemini` (see Task 7).
  Until present, the Gemini path is skipped and the generic detector runs.

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

## Before activating in production: false-positive sanity sweep

The Gemini path only runs when `locate()` NCC confidence ≥ `confidence_threshold`
(default 0.45 in `gemini_profile.json`). This default is validated against flat,
noisy, and gradient backgrounds but NOT against natural non-Gemini photos with
bright/structured content in the bottom-right corner (sun, lamp, white object,
scanned-page corner).

After generating `gemini_alpha_map.png`, before relying on the feature, run a
handful of clean non-Gemini images (especially ones with bright bottom-right
content) through the pipeline and confirm none are altered. If any clean image
has its corner modified, raise `confidence_threshold` in `gemini_profile.json`
until it stops, then re-verify a real Gemini sample is still cleaned.
