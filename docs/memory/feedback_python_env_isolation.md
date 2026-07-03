---
name: feedback-python-env-isolation
description: "Never pip-install heavy/contrib packages into user's nerfstudio conda env; use a separate venv per pipeline"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2bafa0a0-9d06-46c3-b673-40f3583cb0a4
---

NEVER suggest `pip install X` into the user's `nerfstudio` conda env unless X is a tiny stdlib-adjacent dep AND we've verified it won't pin-bump numpy/torch/cuda.

**Why:** On 2026-06-09 I told user to `conda activate nerfstudio; pip install opencv-contrib-python pillow numpy` to set up the pano pipeline. Two failure modes hit simultaneously:
1. `numpy` got upgraded 1.26.4 → 2.4.6 (latest opencv-contrib pulls numpy 2). nerfstudio's torch/CUDA stack expects numpy 1.x. This is the SAME class of incident as the OCR-engine-eval session ([[project_healthcare_ocr_engine_eval]] — "numpy-pin lesson") and audio preprocessing ([[project_healthcare_audio_preprocessing]] — "DLL stack safe, ADDS 2 pip packages required for fresh .venv").
2. `cv2.pyd` was locked because the splat watcher (which uses opencv-python) was running in another terminal — install failed mid-way leaving env in inconsistent state (numpy upgraded, cv2 NOT replaced).

**How to apply:** For NEW pipelines that need OpenCV / Pillow / FastAPI / similar:
- Create a fresh venv inside the pipeline folder: `python -m venv .venv` from a system Python (not from conda activate)
- Install deps there, isolated from nerfstudio
- Run-commands must `.\.venv\Scripts\Activate.ps1` (NOT `conda activate nerfstudio`)
- This matches the user's established `fresh .venv` preference and prevents touching their CUDA/torch stack

If the user has accidentally upgraded numpy in nerfstudio: fix with `pip install "numpy==1.26.4" --force-reinstall` then verify `python -c "import numpy; print(numpy.__version__)"`. Do this BEFORE touching anything else.

If a `cv2.pyd` lock blocks install: stop any running watcher/process before retrying, or just use a separate venv (preferred — avoids the question entirely).
