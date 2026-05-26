"""
Korean Food Classification Fine-Tuning Script
================================================
EfficientNetV2-S backbone with 3-phase progressive training.
Designed for RTX 4070 SUPER (12GB VRAM).

Usage:
    python finetune_korean_food.py

Dependencies:
    torch torchvision pillow numpy scikit-learn tqdm

Data layout expected:
    ../data/aihub_korean_food/
        class_a/
            img001.jpg
            img002.jpg
        class_b/
            ...

Output written to:
    ../output/
"""

import os
import sys
import copy
import random
import logging
import argparse
from pathlib import Path
from typing import Tuple, List, Optional, Dict

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset, Subset
from torchvision import transforms, models
from torchvision.datasets import ImageFolder
from PIL import Image
from sklearn.model_selection import train_test_split
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_ROOT = SCRIPT_DIR / ".." / "data" / "aihub_korean_food"
OUTPUT_DIR = SCRIPT_DIR / ".." / "output"

SEED = 42
VAL_SPLIT = 0.12
TEST_SPLIT = 0.03
LABEL_SMOOTHING = 0.1
NUM_WORKERS = 4

PHASE_CONFIG = [
    {
        "name": "Phase1_Frozen",
        "image_size": 224,
        "batch_size": 64,
        "lr": 1e-3,
        "epochs": 8,
        "unfreeze": "head",
    },
    {
        "name": "Phase2_PartialUnfreeze",
        "image_size": 300,
        "batch_size": 32,
        "lr": 1e-4,
        "epochs": 8,
        "unfreeze": "last80",
    },
    {
        "name": "Phase3_FullFinetune",
        "image_size": 384,
        "batch_size": 16,
        "lr": 2e-5,
        "epochs": 6,
        "unfreeze": "all",
    },
]

TTA_TRANSFORMS_COUNT = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------

class FlexibleImageDataset(Dataset):
    """Wraps a list of (path, label) pairs and applies a given transform."""

    def __init__(self, samples: List[Tuple[str, int]], transform: transforms.Compose):
        self.samples = samples
        self.transform = transform

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        path, label = self.samples[idx]
        image = Image.open(path).convert("RGB")
        image = self.transform(image)
        return image, label


def build_splits(
    data_root: Path, val_split: float, test_split: float, seed: int
) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]], List[Tuple[str, int]], List[str]]:
    """Scan *data_root* via ImageFolder, then stratified split."""
    full_dataset = ImageFolder(root=str(data_root))
    all_samples = full_dataset.samples  # list of (path, class_idx)
    class_names = full_dataset.classes
    targets = [s[1] for s in all_samples]

    # First split: separate test set
    train_val_samples, test_samples, train_val_targets, _ = train_test_split(
        all_samples, targets, test_size=test_split, random_state=seed, stratify=targets
    )

    # Second split: separate val from train
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


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------

def get_train_transform(image_size: int) -> transforms.Compose:
    return transforms.Compose([
        transforms.RandomResizedCrop(image_size, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(p=0.2),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.05),
        transforms.RandomAffine(degrees=0, translate=(0.1, 0.1)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        transforms.RandomErasing(p=0.25),
    ])


def get_val_transform(image_size: int) -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize(int(image_size * 1.143)),  # ~256 for 224
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])


def get_tta_transforms(image_size: int) -> List[transforms.Compose]:
    """Return a list of TTA transform pipelines."""
    base_resize = int(image_size * 1.143)
    tta_list = [
        # Original center crop
        transforms.Compose([
            transforms.Resize(base_resize),
            transforms.CenterCrop(image_size),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]),
        # Horizontal flip
        transforms.Compose([
            transforms.Resize(base_resize),
            transforms.CenterCrop(image_size),
            transforms.RandomHorizontalFlip(p=1.0),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]),
        # Slight rotation
        transforms.Compose([
            transforms.Resize(base_resize),
            transforms.CenterCrop(image_size),
            transforms.RandomRotation(degrees=(10, 10)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]),
        # Slight zoom
        transforms.Compose([
            transforms.RandomResizedCrop(image_size, scale=(0.85, 1.0)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]),
        # Color jitter
        transforms.Compose([
            transforms.Resize(base_resize),
            transforms.CenterCrop(image_size),
            transforms.ColorJitter(brightness=0.15, contrast=0.15),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]),
    ]
    return tta_list


# ---------------------------------------------------------------------------
# Mixup & CutMix
# ---------------------------------------------------------------------------

def mixup_data(
    x: torch.Tensor, y: torch.Tensor, alpha: float = 0.4
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
    lam = np.random.beta(alpha, alpha) if alpha > 0 else 1.0
    batch_size = x.size(0)
    index = torch.randperm(batch_size, device=x.device)
    mixed_x = lam * x + (1.0 - lam) * x[index]
    return mixed_x, y, y[index], lam


def cutmix_data(
    x: torch.Tensor, y: torch.Tensor, alpha: float = 1.0
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
    lam = np.random.beta(alpha, alpha) if alpha > 0 else 1.0
    batch_size = x.size(0)
    index = torch.randperm(batch_size, device=x.device)

    _, _, H, W = x.shape
    cut_rat = np.sqrt(1.0 - lam)
    cut_w = int(W * cut_rat)
    cut_h = int(H * cut_rat)

    cx = np.random.randint(W)
    cy = np.random.randint(H)
    x1 = np.clip(cx - cut_w // 2, 0, W)
    y1 = np.clip(cy - cut_h // 2, 0, H)
    x2 = np.clip(cx + cut_w // 2, 0, W)
    y2 = np.clip(cy + cut_h // 2, 0, H)

    mixed_x = x.clone()
    mixed_x[:, :, y1:y2, x1:x2] = x[index, :, y1:y2, x1:x2]
    lam = 1.0 - ((x2 - x1) * (y2 - y1) / (W * H))
    return mixed_x, y, y[index], lam


def mixup_criterion(
    criterion: nn.Module, pred: torch.Tensor, y_a: torch.Tensor, y_b: torch.Tensor, lam: float
) -> torch.Tensor:
    return lam * criterion(pred, y_a) + (1.0 - lam) * criterion(pred, y_b)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def build_model(num_classes: int, device: torch.device) -> nn.Module:
    """EfficientNetV2-S with a custom classification head."""
    weights = models.EfficientNet_V2_S_Weights.IMAGENET1K_V1
    model = models.efficientnet_v2_s(weights=weights)

    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=0.3, inplace=True),
        nn.Linear(in_features, 512),
        nn.ReLU(inplace=True),
        nn.Dropout(p=0.2),
        nn.Linear(512, num_classes),
    )
    model = model.to(device)
    param_count = sum(p.numel() for p in model.parameters()) / 1e6
    logger.info("Model parameters: %.2fM", param_count)
    return model


def freeze_backbone(model: nn.Module) -> None:
    """Freeze everything except the classifier head."""
    for name, param in model.named_parameters():
        if "classifier" not in name:
            param.requires_grad = False


def unfreeze_last_n(model: nn.Module, n: int) -> None:
    """Unfreeze the classifier + last *n* backbone parameters."""
    all_params = list(model.named_parameters())
    # First freeze everything
    for _, param in all_params:
        param.requires_grad = False
    # Unfreeze classifier
    for name, param in all_params:
        if "classifier" in name:
            param.requires_grad = True
    # Unfreeze last n backbone params
    backbone_params = [(n_, p) for n_, p in all_params if "classifier" not in n_]
    for _, param in backbone_params[-n:]:
        param.requires_grad = True

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    logger.info("Trainable: %d / %d (%.1f%%)", trainable, total, 100.0 * trainable / total)


def unfreeze_all(model: nn.Module) -> None:
    for param in model.parameters():
        param.requires_grad = True
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("All %d parameters unfrozen.", trainable)


# ---------------------------------------------------------------------------
# Class weight computation
# ---------------------------------------------------------------------------

def compute_class_weights(samples: List[Tuple[str, int]], num_classes: int, device: torch.device) -> torch.Tensor:
    counts = np.zeros(num_classes, dtype=np.float64)
    for _, label in samples:
        counts[label] += 1.0
    total = counts.sum()
    weights = total / (num_classes * counts + 1e-6)
    weights = weights / weights.sum() * num_classes  # normalize
    logger.info("Class weight range: [%.4f, %.4f]", weights.min(), weights.max())
    return torch.tensor(weights, dtype=torch.float32, device=device)


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train_one_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    optimizer: optim.Optimizer,
    scheduler: optim.lr_scheduler._LRScheduler,
    device: torch.device,
    epoch: int,
    use_augmix: bool = True,
) -> Tuple[float, float]:
    model.train()
    running_loss = 0.0
    correct = 0
    total = 0

    pbar = tqdm(loader, desc=f"  Train epoch {epoch+1}", leave=False)
    for images, labels in pbar:
        images, labels = images.to(device, non_blocking=True), labels.to(device, non_blocking=True)

        # Randomly choose mixup or cutmix (50/50)
        if use_augmix and random.random() < 0.5:
            if random.random() < 0.5:
                images, targets_a, targets_b, lam = mixup_data(images, labels)
            else:
                images, targets_a, targets_b, lam = cutmix_data(images, labels)
            outputs = model(images)
            loss = mixup_criterion(criterion, outputs, targets_a, targets_b, lam)
            # For accuracy tracking, use the dominant label
            _, predicted = outputs.max(1)
            correct += (lam * predicted.eq(targets_a).sum().item()
                        + (1.0 - lam) * predicted.eq(targets_b).sum().item())
        else:
            outputs = model(images)
            loss = criterion(outputs, labels)
            _, predicted = outputs.max(1)
            correct += predicted.eq(labels).sum().item()

        total += labels.size(0)
        running_loss += loss.item() * labels.size(0)

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        scheduler.step()

        pbar.set_postfix(loss=f"{loss.item():.4f}", lr=f"{scheduler.get_last_lr()[0]:.2e}")

    epoch_loss = running_loss / total
    epoch_acc = correct / total
    return epoch_loss, epoch_acc


@torch.no_grad()
def evaluate(
    model: nn.Module, loader: DataLoader, criterion: nn.Module, device: torch.device
) -> Tuple[float, float]:
    model.eval()
    running_loss = 0.0
    correct = 0
    total = 0

    for images, labels in tqdm(loader, desc="  Validating", leave=False):
        images, labels = images.to(device, non_blocking=True), labels.to(device, non_blocking=True)
        outputs = model(images)
        loss = criterion(outputs, labels)
        running_loss += loss.item() * labels.size(0)
        _, predicted = outputs.max(1)
        correct += predicted.eq(labels).sum().item()
        total += labels.size(0)

    return running_loss / total, correct / total


# ---------------------------------------------------------------------------
# Test-Time Augmentation
# ---------------------------------------------------------------------------

@torch.no_grad()
def evaluate_tta(
    model: nn.Module,
    samples: List[Tuple[str, int]],
    image_size: int,
    device: torch.device,
    batch_size: int = 16,
) -> Tuple[float, Dict]:
    """Evaluate with TTA: average softmax across augmented views."""
    model.eval()
    tta_tfms = get_tta_transforms(image_size)

    all_labels = np.array([s[1] for s in samples])
    num_samples = len(samples)
    num_classes = model.classifier[-1].out_features

    avg_probs = np.zeros((num_samples, num_classes), dtype=np.float64)

    for t_idx, tfm in enumerate(tta_tfms):
        dataset = FlexibleImageDataset(samples, tfm)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=False,
                            num_workers=NUM_WORKERS, pin_memory=True)
        offset = 0
        for images, _ in tqdm(loader, desc=f"  TTA view {t_idx+1}/{len(tta_tfms)}", leave=False):
            images = images.to(device, non_blocking=True)
            logits = model(images)
            probs = torch.softmax(logits, dim=1).cpu().numpy()
            bsz = probs.shape[0]
            avg_probs[offset:offset + bsz] += probs
            offset += bsz

    avg_probs /= len(tta_tfms)
    predictions = avg_probs.argmax(axis=1)
    accuracy = (predictions == all_labels).mean()

    # Per-class accuracy
    per_class: Dict[int, float] = {}
    for c in range(num_classes):
        mask = all_labels == c
        if mask.sum() > 0:
            per_class[c] = float((predictions[mask] == c).mean())

    return accuracy, per_class


# ---------------------------------------------------------------------------
# ONNX export
# ---------------------------------------------------------------------------

def export_onnx(model: nn.Module, image_size: int, num_classes: int, output_path: Path, device: torch.device) -> None:
    model.eval()
    dummy = torch.randn(1, 3, image_size, image_size, device=device)
    onnx_path = output_path / "korean_food_classifier.onnx"
    torch.onnx.export(
        model,
        dummy,
        str(onnx_path),
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
    )
    size_mb = onnx_path.stat().st_size / (1024 * 1024)
    logger.info("ONNX exported to %s (%.1f MB)", onnx_path, size_mb)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Korean Food Classification Fine-Tuning")
    parser.add_argument("--data-root", type=str, default=str(DATA_ROOT), help="Path to image dataset root")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR), help="Path to output directory")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--workers", type=int, default=NUM_WORKERS)
    parser.add_argument("--skip-tta", action="store_true", help="Skip TTA evaluation")
    parser.add_argument("--skip-onnx", action="store_true", help="Skip ONNX export")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    seed_everything(args.seed)

    # Device setup
    if not torch.cuda.is_available():
        logger.warning("CUDA not available. Training on CPU (will be very slow).")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem = torch.cuda.get_device_properties(0).total_mem / (1024 ** 3)
        logger.info("GPU: %s (%.1f GB)", gpu_name, gpu_mem)

    # Data splits
    train_samples, val_samples, test_samples, class_names = build_splits(
        data_root, VAL_SPLIT, TEST_SPLIT, args.seed
    )
    num_classes = len(class_names)

    # Save class names
    class_file = output_dir / "class_names.txt"
    with open(class_file, "w", encoding="utf-8") as f:
        for name in class_names:
            f.write(name + "\n")
    logger.info("Class names saved to %s", class_file)

    # Build model
    model = build_model(num_classes, device)

    # Class weights for imbalanced data
    class_weights = compute_class_weights(train_samples, num_classes, device)

    best_val_acc = 0.0
    best_model_state = None

    # -----------------------------------------------------------------------
    # 3-Phase Progressive Training
    # -----------------------------------------------------------------------
    for phase_idx, phase in enumerate(PHASE_CONFIG):
        logger.info("=" * 70)
        logger.info(
            "PHASE %d/%d: %s | img=%d | bs=%d | lr=%.1e | epochs=%d",
            phase_idx + 1, len(PHASE_CONFIG), phase["name"],
            phase["image_size"], phase["batch_size"], phase["lr"], phase["epochs"],
        )
        logger.info("=" * 70)

        # Freeze / unfreeze strategy
        if phase["unfreeze"] == "head":
            freeze_backbone(model)
            trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
            logger.info("Backbone frozen. Trainable params: %d", trainable)
        elif phase["unfreeze"] == "last80":
            unfreeze_last_n(model, 80)
        elif phase["unfreeze"] == "all":
            unfreeze_all(model)

        # Build dataloaders for this phase
        img_size = phase["image_size"]
        train_ds = FlexibleImageDataset(train_samples, get_train_transform(img_size))
        val_ds = FlexibleImageDataset(val_samples, get_val_transform(img_size))

        train_loader = DataLoader(
            train_ds, batch_size=phase["batch_size"], shuffle=True,
            num_workers=args.workers, pin_memory=True, drop_last=True,
        )
        val_loader = DataLoader(
            val_ds, batch_size=phase["batch_size"], shuffle=False,
            num_workers=args.workers, pin_memory=True,
        )

        # Optimizer & scheduler
        trainable_params = [p for p in model.parameters() if p.requires_grad]
        optimizer = optim.AdamW(trainable_params, lr=phase["lr"], weight_decay=1e-4)
        total_steps = phase["epochs"] * len(train_loader)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total_steps, eta_min=1e-7)

        # Loss with label smoothing + class weights
        criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=LABEL_SMOOTHING)

        # Training epochs
        for epoch in range(phase["epochs"]):
            train_loss, train_acc = train_one_epoch(
                model, train_loader, criterion, optimizer, scheduler, device, epoch,
                use_augmix=(phase_idx >= 1),  # skip mixup/cutmix in phase 1 for stability
            )
            val_loss, val_acc = evaluate(model, val_loader, criterion, device)

            logger.info(
                "[%s] Epoch %d/%d -> train_loss=%.4f train_acc=%.4f | val_loss=%.4f val_acc=%.4f",
                phase["name"], epoch + 1, phase["epochs"],
                train_loss, train_acc, val_loss, val_acc,
            )

            # Save best model
            if val_acc > best_val_acc:
                best_val_acc = val_acc
                best_model_state = copy.deepcopy(model.state_dict())
                ckpt_path = output_dir / "best_model.pt"
                torch.save({
                    "state_dict": best_model_state,
                    "val_acc": best_val_acc,
                    "num_classes": num_classes,
                    "class_names": class_names,
                    "phase": phase["name"],
                    "epoch": epoch + 1,
                    "image_size": img_size,
                }, str(ckpt_path))
                logger.info("  -> New best model saved (val_acc=%.4f)", best_val_acc)

        # Save phase checkpoint
        phase_ckpt = output_dir / f"{phase['name']}_checkpoint.pt"
        torch.save(model.state_dict(), str(phase_ckpt))
        logger.info("Phase checkpoint saved to %s", phase_ckpt)

    # -----------------------------------------------------------------------
    # Load best model for final evaluation
    # -----------------------------------------------------------------------
    logger.info("=" * 70)
    logger.info("FINAL EVALUATION (best val_acc=%.4f)", best_val_acc)
    logger.info("=" * 70)

    if best_model_state is not None:
        model.load_state_dict(best_model_state)

    # Standard test evaluation
    final_img_size = PHASE_CONFIG[-1]["image_size"]
    test_ds = FlexibleImageDataset(test_samples, get_val_transform(final_img_size))
    test_loader = DataLoader(
        test_ds, batch_size=16, shuffle=False,
        num_workers=args.workers, pin_memory=True,
    )
    criterion_eval = nn.CrossEntropyLoss(label_smoothing=0.0)
    test_loss, test_acc = evaluate(model, test_loader, criterion_eval, device)
    logger.info("Test (standard) -> loss=%.4f acc=%.4f", test_loss, test_acc)

    # TTA evaluation
    if not args.skip_tta:
        logger.info("Running Test-Time Augmentation (%d views)...", TTA_TRANSFORMS_COUNT)
        tta_acc, per_class_acc = evaluate_tta(
            model, test_samples, final_img_size, device, batch_size=16
        )
        logger.info("Test (TTA) -> acc=%.4f", tta_acc)

        # Log worst classes
        if per_class_acc:
            sorted_classes = sorted(per_class_acc.items(), key=lambda x: x[1])
            logger.info("Bottom-5 classes by accuracy:")
            for cls_idx, acc in sorted_classes[:5]:
                logger.info("  %s: %.4f", class_names[cls_idx], acc)

    # -----------------------------------------------------------------------
    # ONNX Export
    # -----------------------------------------------------------------------
    if not args.skip_onnx:
        logger.info("Exporting model to ONNX...")
        export_onnx(model, final_img_size, num_classes, output_dir, device)

    # Save final model
    final_path = output_dir / "final_model.pt"
    torch.save({
        "state_dict": model.state_dict(),
        "num_classes": num_classes,
        "class_names": class_names,
        "image_size": final_img_size,
        "best_val_acc": best_val_acc,
        "test_acc": test_acc,
    }, str(final_path))
    logger.info("Final model saved to %s", final_path)

    logger.info("=" * 70)
    logger.info("TRAINING COMPLETE")
    logger.info("  Best validation accuracy: %.4f", best_val_acc)
    logger.info("  Test accuracy (standard): %.4f", test_acc)
    if not args.skip_tta:
        logger.info("  Test accuracy (TTA):      %.4f", tta_acc)
    logger.info("  Output directory: %s", output_dir.resolve())
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
