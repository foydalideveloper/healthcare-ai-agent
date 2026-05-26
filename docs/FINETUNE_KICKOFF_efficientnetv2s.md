# EfficientNetV2-S Korean Food Fine-Tune — Kickoff Package

**Target machine:** RTX 4070 SUPER server (Win11, 12 GB VRAM, i9-14900KF, 64 GB RAM)
**Source machine for this prep:** i3-12100 dev sandbox (where this doc was written)
**Script:** [ml/training/finetune_korean_food.py](../ml/training/finetune_korean_food.py)
**Data:** `ml/data/aihub_korean_food/` (verified present, 16 GB, ~150K images, 150 leaf classes)
**Expected runtime:** ~15h (3-phase progressive: 8 + 8 + 6 epochs)
**Date prepared:** 2026-04-28

---

## ⚠ Pre-flight blocker — data layout mismatches script

**Issue.** The script uses `torchvision.datasets.ImageFolder` which treats the **immediate subdirectories of the data root** as class labels. The actual data is **3 levels deep**:

```
aihub_korean_food/
├── 구이/                   ← 27 top-level dirs (cooking method)
│   └── 구이/                ← duplicated mid-level (AI Hub packaging artifact)
│       ├── 갈비구이/        ← ~150 leaf dirs (actual dish class — this is what we want)
│       │   ├── Img_xxx_0001.jpg
│       │   └── ...
│       ├── 갈치구이/
│       └── ...
├── 국/
│   └── 국/
│       ├── 계란국/
│       └── ...
└── ... (27 cooking-method roots total)
```

**Verified counts (just measured):**
- 27 cooking-method directories at depth 1
- 150 leaf dish directories at depth 3

**What `ImageFolder` would do (broken).** It would assign every image under `구이/...` the class label `구이` regardless of the dish, recursively walking down. Result: **27 super-coarse classes** (cooking method) instead of **150 fine-grained dish classes**.

For healthcare calorie/nutrition lookup this is unusable — calorie counts vary wildly within a cooking method (e.g., 갈비구이 ≈ 400 kcal/serving vs 황태구이 ≈ 150 kcal/serving, both under `구이`).

**You MUST resolve this before launching the 15h run.** Two options:

### Option A — Patch the script (recommended)

Add a `LeafImageFolder` class that scans `data_root` recursively for leaf directories containing image files, and uses the **leaf directory name** as the class label.

Replace the `build_splits` function in [ml/training/finetune_korean_food.py](../ml/training/finetune_korean_food.py) with:

```python
def build_splits(
    data_root: Path, val_split: float, test_split: float, seed: int
) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]], List[Tuple[str, int]], List[str]]:
    """Scan *data_root* recursively for leaf class dirs (containing images), then stratified split.

    Unlike ImageFolder which treats immediate subdirs as classes, this walks the
    full tree and uses the LEAF directory name as the class label. Required for
    AI Hub Korean food data where classes live at depth 3 under cooking-method roots.
    """
    IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    leaf_dirs: Dict[str, List[str]] = {}
    for path in data_root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMG_EXTS:
            class_name = path.parent.name
            leaf_dirs.setdefault(class_name, []).append(str(path))

    if not leaf_dirs:
        raise RuntimeError(f"No images found under {data_root}")

    class_names = sorted(leaf_dirs.keys())
    class_to_idx = {name: idx for idx, name in enumerate(class_names)}

    all_samples: List[Tuple[str, int]] = []
    for name, paths in leaf_dirs.items():
        idx = class_to_idx[name]
        for p in paths:
            all_samples.append((p, idx))

    targets = [s[1] for s in all_samples]

    train_val_samples, test_samples, train_val_targets, _ = train_test_split(
        all_samples, targets, test_size=test_split, random_state=seed, stratify=targets
    )
    relative_val = val_split / (1.0 - test_split)
    train_samples, val_samples = train_test_split(
        train_val_samples,
        test_size=relative_val,
        random_state=seed,
        stratify=train_val_targets,
    )

    logger.info(
        "Split sizes -> train: %d | val: %d | test: %d | classes: %d",
        len(train_samples), len(val_samples), len(test_samples), len(class_names),
    )
    return train_samples, val_samples, test_samples, class_names
```

After applying, the unused `from torchvision.datasets import ImageFolder` import can stay or be removed. No other function in the script references `ImageFolder`.

**Why this is safe.** It returns the same 4-tuple shape (`train_samples, val_samples, test_samples, class_names`) and uses the same `(path, label)` sample format the rest of the script consumes. The change is local to one function.

### Option B — Restructure the data on disk

Flatten the directory tree by moving every leaf class directory up to the root:

```bash
cd ml/data/aihub_korean_food
for method in */; do
    if [ -d "$method$method" ]; then
        mv "$method$method"*/ ./
        rmdir "$method$method" "$method"
    fi
done
```

**Don't pick this** unless you have a backup. It's irreversible without restoring from the original AI Hub download. Option A is purely additive.

---

## Smoke test (mandatory before 15h run)

A 15h training run is the most expensive thing the project will do this month. Burn 30 minutes on a smoke test first.

After applying Option A, run on a small subset to confirm:

```powershell
# On RTX 4070 SUPER server, from the project root
cd C:\path\to\healthcare-ai-agent\ml\training
python finetune_korean_food.py --skip-tta --skip-onnx 2>&1 | tee smoke.log
```

Then immediately Ctrl+C after Phase 1 epoch 1 completes (~5-10 min). Inspect `smoke.log` for:
- ✅ `GPU: NVIDIA GeForce RTX 4070 SUPER (12.0 GB)`
- ✅ `Split sizes -> train: ~127K | val: ~17K | test: ~5K | classes: 150` ← **150, not 27**
- ✅ `Model parameters: ~21.5M`
- ✅ Loss decreasing across batches in Phase 1 epoch 1
- ✅ No CUDA OOM, no `FileNotFoundError`, no Korean encoding errors in logs

If any of those fail, fix before relaunching.

---

## Pre-flight checklist (RTX 4070 SUPER side)

Run these before kicking off the full 15h run.

1. **GPU free**
   ```powershell
   nvidia-smi
   ```
   Confirm 4070 SUPER is idle (no Gemma server, no Qwen training, no other CUDA process). If `llama-server.exe` is still bound from the Gemma benchmark, kill it first.

2. **Disk space**
   ```powershell
   Get-PSDrive C
   ```
   Need ~30 GB free for: data (16 GB already there), checkpoints (3 phase × ~250 MB), best/final/onnx (~750 MB), logs.

3. **Dependencies**
   ```powershell
   pip show torch torchvision pillow numpy scikit-learn tqdm onnx
   ```
   All must be present. If `torch` is CPU-only (no `+cu121` suffix), reinstall with CUDA build.

4. **Python version**
   Script targets 3.10+ (uses `Tuple`, `List`, `Optional`, `Dict` typing — works on 3.9+ as well).

5. **Output directory**
   ```powershell
   mkdir C:\path\to\healthcare-ai-agent\ml\output
   ```
   Will hold `best_model.pt`, `final_model.pt`, `korean_food_classifier.onnx`, `class_names.txt`, phase checkpoints.

6. **Logs directory** — pipe output to a log file so you can review remotely.

---

## Full launch command (after smoke test passes)

```powershell
# On RTX 4070 SUPER server, from project root
cd C:\path\to\healthcare-ai-agent\ml\training

# Background the run, log to file
Start-Process -FilePath "python" `
  -ArgumentList "finetune_korean_food.py" `
  -RedirectStandardOutput "..\output\train_$(Get-Date -Format yyyyMMdd_HHmm).log" `
  -RedirectStandardError "..\output\train_$(Get-Date -Format yyyyMMdd_HHmm).err" `
  -NoNewWindow
```

Or simpler if you want to watch live:

```powershell
python finetune_korean_food.py 2>&1 | Tee-Object -FilePath ..\output\train.log
```

Expected timeline:
- Phase 1 (frozen, 224px, bs=64, 8 epochs): ~3h
- Phase 2 (last80 unfrozen, 300px, bs=32, 8 epochs): ~5h
- Phase 3 (full unfreeze, 384px, bs=16, 6 epochs): ~6h
- Final eval + TTA + ONNX export: ~30 min
- **Total: ~14-15h**

---

## What "good" looks like at the end

- `output/best_model.pt` exists with `val_acc > 0.85` (target — adjust based on AI Hub's known difficulty)
- `output/final_model.pt` exists with similar test_acc
- `output/korean_food_classifier.onnx` exists, ~85 MB (EfficientNetV2-S backbone)
- `output/class_names.txt` lists 150 Korean leaf-class names
- TTA test acc ≥ standard test acc (TTA should help, not hurt)

If TTA degrades accuracy, `--skip-tta` was the right call and the model needs more epochs in Phase 3.

---

## Why this can't be auto-launched from the i3-12100

- This kickoff doc was written on the i3-12100 dev sandbox.
- The script + data + GPU all live on the RTX 4070 SUPER server, a separate machine.
- Auto-launching across machines requires SSH/RDP/network share, none of which are documented in the project.
- Plus: a 15h training run that produces a load-bearing model artifact deserves a human-in-the-loop kickoff after reviewing the script patch above.

---

## After the run

Update memory:
- Add `project_healthcare_efficientnetv2s_results.md` to `~/.claude/projects/C--Users-tripleh/memory/` with: best val_acc, test acc, TTA acc, top-10 worst classes, ONNX size, training duration.
- Update [docs/daily_reports/2026-04-XX_report.md](daily_reports/) with the run's wall-clock time and final metrics.
- Bump priority of "Knowledge distillation: EfficientNetV2-S → small TFLite student" in handoff §8 (it becomes the next blocker).
