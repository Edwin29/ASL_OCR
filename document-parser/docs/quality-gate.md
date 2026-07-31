# Image Quality Gate

## Current Scope

This milestone implements the OCR preflight layer for page images.

- Load image metadata without modifying the source file.
- Compute pixel dimensions, color mode, format, SHA-256, aspect ratio, and long edge.
- Estimate blur with a Pillow + NumPy Laplacian variance check.
- Classify pages into `PASS`, `PASS_WITH_CORRECTION`, `LOW_QUALITY`, or `REJECTED`.
- Emit quality issues as explicit report data.

## Current Rules

| Rule | Issue | Result |
|---|---|---|
| Long edge below 1800px | `LOW_RESOLUTION` | `LOW_QUALITY` |
| Long edge from 1800px to below 2800px | `BELOW_RECOMMENDED_RESOLUTION` | `PASS_WITH_CORRECTION` |
| Aspect ratio outside 0.68-0.82 | `ASPECT_RATIO_OUT_OF_PROFILE` | `PASS_WITH_CORRECTION` unless other issues are worse |
| Color mode outside RGB/RGBA/L | `UNSUPPORTED_COLOR_MODE` | `PASS_WITH_CORRECTION` unless other issues are worse |
| Low Laplacian variance | `POSSIBLE_BLUR` | `PASS_WITH_CORRECTION` unless other issues are worse |

## Verified Result

The generated report at `data/debug/image_quality_report.json` compares the ZIP images and PDF 300dpi renders for pages 3, 4, 8, 12, 19, 20, 54, and 102.

- ZIP samples: 8 `LOW_QUALITY`
- PDF 300dpi samples: 8 `PASS`

This confirms the implementation-plan assumption that the ZIP images should be treated as a low-resolution regression set while PDF 300dpi renders should be used for the OCR baseline.

