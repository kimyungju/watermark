# Gemini watermark calibration assets

- `gemini_profile.json` — committed. Geometry catalog: per-size-bucket
  `box = [margin_from_right, margin_from_bottom, width, height]`, logo color,
  alpha clamp, NCC search padding and confidence threshold.
- `gemini_alpha_map.png` — NOT committed (gitignored; may be proprietary).
  Generated once by `python -m services.calibrate_gemini` (see Task 7).
  Until present, the Gemini path is skipped and the generic detector runs.
