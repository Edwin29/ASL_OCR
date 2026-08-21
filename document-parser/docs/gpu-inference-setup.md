# PaddleOCR-VL GPU Inference — Verified Setup

## Status

**Working and reproducible, as of 2026-08-21**, in a dedicated virtual environment. Do **not** run GPU inference in the same environment used for anything else in this project (tests, the accessibility subsystem, EasyOCR, etc.) — see "Root cause" below for why mixing environments breaks it.

## Why a separate environment

Every earlier attempt to enable GPU inference in this project's normal shared Python environment crashed with `OSError: [WinError 127]` deep inside `paddlex`'s model-loading code (`Error loading "...\\nvidia\\cudnn\\bin\\cudnn_cnn64_9.dll" or one of its dependencies`), or later, once that was worked around, an equivalent crash loading `torch`'s own bundled cuDNN copy from `torch\lib\`.

**Root cause, confirmed empirically**: `torch` was present in the shared environment as an incidental transitive dependency — `paddlex` imports `modelscope` for optional model-hub integration features this project never uses, and `modelscope` imports `torch` if it's installed. `torch`'s pip wheel bundles its own complete copy of the CUDA/cuDNN runtime DLLs inside `torch\lib\`, physically separate from the `nvidia-cudnn-cu12` pip package's copy that `paddlepaddle-gpu` needs. When both get loaded into the same Windows process, Windows' DLL loader resolves same-named DLLs (`cudnn64_9.dll`, `cudnn_cnn64_9.dll`, etc.) to whichever copy happened to load *first* by that basename — so whichever of paddle/torch loads second gets silently bound to the *other one's* mismatched build and crashes.

**The fix is not a workaround, it's removing the unnecessary dependency**: `torch` is not actually required anywhere in this project's OCR pipeline. `modelscope` already handles its absence gracefully (`modelscope/utils/logger.py` guards its torch-dependent import behind `importlib.util.find_spec('torch') is not None`) — so a virtual environment that simply never has `torch` installed avoids the collision entirely, with no monkeypatching or DLL-preload tricks needed.

## Setup

```bash
python -m venv /d/venvs/gpu_ocr_test          # any path outside the repo is fine
/d/venvs/gpu_ocr_test/Scripts/pip install --upgrade pip
/d/venvs/gpu_ocr_test/Scripts/pip install paddlepaddle-gpu==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
/d/venvs/gpu_ocr_test/Scripts/pip install -r requirements-gpu.txt
```

`requirements-gpu.txt` (repo root) records the exact top-level pins; `requirements-gpu.freeze.txt` is a full `pip freeze` snapshot of a verified-working install, for exact reproduction if a future `paddlex`/`paddleocr` release changes a transitive pin.

**Never `pip install torch` into this environment**, and never install `paddlepaddle-gpu` into the project's regular/shared environment (that environment should keep the plain CPU `paddlepaddle` package, which has no cuDNN dependency and therefore no collision risk, and can safely coexist with `torch` if anything else ever needs it).

### Verify

```bash
/d/venvs/gpu_ocr_test/Scripts/python -c "import paddle; print(paddle.device.is_compiled_with_cuda())"
# -> True
```

If this prints `False`, the CPU `paddlepaddle` package got installed instead of `paddlepaddle-gpu` (pip allows both to exist in the same environment and does not warn about the conflict — check `pip list | grep paddle`).

### Running the OCR pipeline against this environment

Use the venv's `python.exe` in place of the project's normal interpreter for any OCR-VL tool, e.g.:

```bash
/d/venvs/gpu_ocr_test/Scripts/python tools/paddleocr_vl_text_ir.py --device gpu:0 --page-id p008
```

(`document_parser` itself is not installed into this venv as a package — the tools add `src/` to `sys.path` directly, so no extra install step is needed there.)

## Known benign warning

```
WARNING: device: 0. The installed Paddle is compiled with CUDNN 9.9, but CUDNN version
in your machine is 9.5, which may cause serious incompatible bug.
```

This prints on every run in the verified setup above and inference completes correctly despite it — paddle's own version check is more conservative than the actual compatibility. Not investigated further since it hasn't caused an observed failure; worth revisiting if a future run does fail with a cuDNN-shaped error.

## Verified timing baseline (2026-08-21)

Single warm process, `PaddleOcrVlAdapter` reused across calls (model loaded once, ~7-8s), RTX 4060:

| page | elapsed | blocks |
|---|---|---|
| p008 (1st call, includes model load) | 52.85s | 7 |
| p008 (2nd call, same page, warm) | 44.61s | 7 |
| p012 | 152.71s | 33 |
| p018 | 51.48s | 18 |

Per-page time scales with content, not randomly — the same page processed twice gave consistent timing and identical output. CPU inference on the same hardware/page took 10+ minutes; GPU is roughly 8-15x faster depending on page content.

### Full 17-page survey (2026-08-21)

All 17 sample pages under `data/pages_pdf300/`, one warm process, GPU. Raw per-page results in `data/debug/gpu_timing_survey.json`. **0 errors across all 17 pages.**

- **sum 1056.0s (17.6 min) for 17 pages, avg 62.1s/page, median 45.6s/page, min 28.7s, max 176.4s.**
- Time does **not** scale linearly with block count — `s/block` ranges from 1.20 to 6.28 across pages. p008 (7 blocks, 43.95s, 6.28s/block) and p102 (16 blocks, 88.17s, 5.51s/block) are slow *despite* having few blocks; p004 (32 blocks, 40.59s, 1.27s/block) is fast *despite* having many. The likely driver is **content complexity per block** (dense math/LaTeX generation takes longer to autoregressively generate than plain text), not block count itself — p102 is independently documented elsewhere in this repo as the most layout-complex sample page (two-column), and p008/p012/p003 are math- or content-dense pages. p012 (173.97s) and p003 (176.40s) were the two clear outliers; excluding them, the remaining 15 pages average 47.0s.
- No instability/non-termination observed across any of the 17 pages (contrast with an earlier, since-corrected false alarm in project history that was actually a wall-clock measurement error, not a real hang).

| page | seconds | blocks | s/block |
|---|---|---|---|
| p003 | 176.40 | 31 | 5.69 |
| p012 | 173.97 | 33 | 5.27 |
| p102 | 88.17 | 16 | 5.51 |
| p088 | 71.30 | 26 | 2.74 |
| p030 | 55.73 | 14 | 3.98 |
| p018 | 50.34 | 18 | 2.80 |
| p058 | 50.25 | 30 | 1.68 |
| p010 | 46.82 | 28 | 1.67 |
| p066 | 45.63 | 18 | 2.54 |
| p008 | 43.95 | 7 | 6.28 |
| p019 | 43.73 | 22 | 1.99 |
| p004 | 40.59 | 32 | 1.27 |
| p038 | 40.17 | 22 | 1.83 |
| p054 | 35.84 | 29 | 1.24 |
| p020 | 33.10 | 26 | 1.27 |
| p024 | 31.29 | 26 | 1.20 |
| p005 | 28.69 | 16 | 1.79 |
