"""
Korean Food Classification Test -MobileNetV2-Food TFLite
Tests how well the pre-trained model recognizes Korean foods from the
Roboflow Korean Food Detector dataset (2,482 images, 136 classes from AI Hub).

Strategy:
  1. Run MobileNetV2-Food on each image
  2. Check if top-1 prediction is a known Korean food
  3. Measure confidence distribution
  4. Connect to MFDS nutrition lookup for matched foods
  5. Report which Korean foods are recognized vs missed

Usage (Python 3.11 with TensorFlow):
  cd C:\\Users\\tripleh\\projects\\healthcare-ai-agent
  C:\\Users\\tripleh\\AppData\\Local\\Python\\pythoncore-3.11-64\\python.exe ml/inference/test_korean_food_classification.py
"""

import csv
import io
import json
import os
import sqlite3
import sys
import time

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
MODEL_PATH = PROJECT_ROOT / "frontend" / "HealthGlassesApp" / "assets" / "models" / "mobilenet_v2_food.tflite"
LABELS_PATH = PROJECT_ROOT / "frontend" / "HealthGlassesApp" / "assets" / "models" / "food_labels.csv"
ROBOFLOW_DIR = PROJECT_ROOT / "ml" / "data" / "korean_food_images" / "roboflow" / "Korean Food Detector.v1i.multiclass"
MFDS_DB_PATH = PROJECT_ROOT / "backend" / "data" / "food_db" / "food_nutrition.db"
RESULTS_DIR = PROJECT_ROOT / "ml" / "inference" / "results"

# Known Korean food labels in the MobileNetV2-Food model (from food_labels.csv)
KNOWN_KOREAN_LABELS = {
    "Kimchi", "Kimchi-jjigae", "Kimchi fried rice", "Kimchi-buchimgae",
    "Bibimbap", "Bulgogi", "Japchae", "Gimbap", "Pajeon",
    "Sundubu-jjigae", "Doenjang-jjigae", "Budae jjigae", "Jjigae",
    "Galbi-jjim", "Galbi-tang", "Dak-galbi",
    "Naengmyeon", "Tteokguk", "Tteok", "Hotteok",
    "Sundae", "Chapssal-tteok", "Jeongol", "Gopchang-jeongol",
    "Nabak-kimchi", "Baek-kimchi", "Dongchimi",
    "Ramen",  # Close enough for ramyeon
}

# Korean label → Korean name for MFDS lookup
LABEL_TO_KOREAN = {
    "Kimchi": "김치",
    "Kimchi-jjigae": "김치찌개",
    "Kimchi fried rice": "김치볶음밥",
    "Kimchi-buchimgae": "김치부침개",
    "Bibimbap": "비빔밥",
    "Bulgogi": "불고기",
    "Japchae": "잡채",
    "Gimbap": "김밥",
    "Pajeon": "파전",
    "Sundubu-jjigae": "순두부찌개",
    "Doenjang-jjigae": "된장찌개",
    "Budae jjigae": "부대찌개",
    "Jjigae": "찌개",
    "Galbi-jjim": "갈비찜",
    "Galbi-tang": "갈비탕",
    "Dak-galbi": "닭갈비",
    "Naengmyeon": "냉면",
    "Tteokguk": "떡국",
    "Tteok": "떡",
    "Hotteok": "호떡",
    "Sundae": "순대",
    "Ramen": "라면",
    "Chapssal-tteok": "찹쌀떡",
    "Jeongol": "전골",
    "Dongchimi": "동치미",
    "Nabak-kimchi": "나박김치",
    "Baek-kimchi": "백김치",
    "Gopchang-jeongol": "곱창전골",
}


def load_model():
    """Load TFLite model."""
    import tensorflow as tf
    interpreter = tf.lite.Interpreter(model_path=str(MODEL_PATH))
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    input_shape = input_details[0]["shape"]
    print(f"Model: {MODEL_PATH.name}")
    print(f"  Input: {input_shape} dtype={input_details[0]['dtype']}")
    print(f"  Output: {output_details[0]['shape']}")
    return interpreter, input_details, output_details, input_shape


def load_labels() -> dict[int, str]:
    """Load food_labels.csv → {id: name}."""
    labels = {}
    with open(LABELS_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            labels[int(row["id"])] = row["name"]
    print(f"Labels: {len(labels)} classes")
    return labels


def preprocess_image(image_path: str, input_shape, input_dtype) -> np.ndarray:
    """Load and preprocess image for MobileNetV2."""
    img = Image.open(image_path).convert("RGB")
    h, w = input_shape[1], input_shape[2]
    img = img.resize((w, h), Image.BILINEAR)
    arr = np.array(img)
    if input_dtype == np.uint8:
        arr = arr.astype(np.uint8)
    else:
        arr = arr.astype(np.float32) / 255.0
    return np.expand_dims(arr, axis=0)


def classify_image(interpreter, input_details, output_details, image_array) -> list[tuple[int, float]]:
    """Run inference, return top-5 (class_id, confidence)."""
    interpreter.set_tensor(input_details[0]["index"], image_array)
    interpreter.invoke()
    output = interpreter.get_tensor(output_details[0]["index"])[0]
    if output.max() > 10:
        exp_out = np.exp(output - output.max())
        output = exp_out / exp_out.sum()
    top_indices = np.argsort(output)[::-1][:5]
    return [(int(idx), float(output[idx])) for idx in top_indices]


def lookup_mfds(food_name_kr: str) -> dict | None:
    """Look up Korean food in MFDS SQLite database."""
    if not MFDS_DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(MFDS_DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """SELECT food_name_kr, energy_kcal, protein_g, fat_g, carbohydrate_g, sodium_mg
           FROM foods WHERE food_name_kr LIKE ?
           ORDER BY LENGTH(food_name_kr) ASC LIMIT 1""",
        (f"%{food_name_kr}%",)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def run_test():
    print("=" * 70)
    print("KOREAN FOOD CLASSIFICATION TEST")
    print("MobileNetV2-Food (2,024 classes) vs Korean Food Images (2,482)")
    print("=" * 70)

    if not MODEL_PATH.exists():
        print(f"ERROR: Model not found: {MODEL_PATH}")
        return
    if not ROBOFLOW_DIR.exists():
        print(f"ERROR: Dataset not found: {ROBOFLOW_DIR}")
        return

    interpreter, input_details, output_details, input_shape = load_model()
    input_dtype = input_details[0]["dtype"]
    labels = load_labels()

    # Collect all image paths from train/valid/test
    all_images = []
    for split in ["test", "valid", "train"]:
        split_dir = ROBOFLOW_DIR / split
        if split_dir.exists():
            imgs = list(split_dir.glob("*.jpg")) + list(split_dir.glob("*.png"))
            all_images.extend([(img, split) for img in imgs])
    print(f"\nTotal images found: {len(all_images)}")

    # For speed, test on test+valid first (745 images), optionally train too
    test_images = [(img, split) for img, split in all_images if split in ("test", "valid")]
    print(f"Testing on test+valid set: {len(test_images)} images")
    if len(test_images) == 0:
        test_images = all_images[:500]
        print(f"Fallback: using first 500 images")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Run classification
    results = []
    korean_detected = 0
    prediction_counts = Counter()
    confidence_bins = {"high_90": 0, "good_70": 0, "low_50": 0, "poor_below50": 0}
    img_prefix_predictions = defaultdict(list)  # prefix → list of predictions
    mfds_hits = 0
    mfds_total = 0
    errors = 0

    print(f"\nRunning inference...")
    start_time = time.time()

    for i, (img_path, split) in enumerate(test_images):
        if (i + 1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            print(f"  [{i+1}/{len(test_images)}] {rate:.1f} img/s ...")

        try:
            img_array = preprocess_image(str(img_path), input_shape, input_dtype)
            top5 = classify_image(interpreter, input_details, output_details, img_array)
            top1_id, top1_conf = top5[0]
            top1_name = labels.get(top1_id, f"unknown_{top1_id}")

            # Track predictions
            prediction_counts[top1_name] += 1
            is_korean = top1_name in KNOWN_KOREAN_LABELS
            if is_korean:
                korean_detected += 1

            # Confidence bin
            if top1_conf >= 0.9:
                confidence_bins["high_90"] += 1
            elif top1_conf >= 0.7:
                confidence_bins["good_70"] += 1
            elif top1_conf >= 0.5:
                confidence_bins["low_50"] += 1
            else:
                confidence_bins["poor_below50"] += 1

            # Track by image prefix (original AI Hub class)
            prefix = img_path.name.split("_")[1] if "_" in img_path.name else "unknown"
            img_prefix_predictions[prefix].append(top1_name)

            # MFDS lookup for Korean predictions
            mfds_result = None
            if is_korean:
                kr_name = LABEL_TO_KOREAN.get(top1_name)
                if kr_name:
                    mfds_total += 1
                    mfds_result = lookup_mfds(kr_name)
                    if mfds_result:
                        mfds_hits += 1

            results.append({
                "image": img_path.name,
                "split": split,
                "prefix": prefix,
                "top1_label": top1_name,
                "top1_confidence": round(top1_conf, 4),
                "top5": [(labels.get(cid, "?"), round(conf, 4)) for cid, conf in top5],
                "is_korean_prediction": is_korean,
                "mfds_match": mfds_result.get("food_name_kr") if mfds_result else None,
                "mfds_kcal": mfds_result.get("energy_kcal") if mfds_result else None,
            })

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  ERROR {img_path.name}: {e}")

    elapsed = time.time() - start_time
    total = len(results)

    # ── Results ──
    print(f"\n{'=' * 70}")
    print("RESULTS")
    print(f"{'=' * 70}")
    print(f"\n  Images tested:        {total}")
    print(f"  Errors:               {errors}")
    print(f"  Inference time:       {elapsed:.1f}s ({total/elapsed:.1f} img/s)")

    print(f"\n  --- Korean Food Detection ---")
    print(f"  Predicted as Korean:  {korean_detected}/{total} = {korean_detected/max(total,1):.1%}")
    print(f"  Predicted as other:   {total - korean_detected}/{total} = {(total-korean_detected)/max(total,1):.1%}")

    print(f"\n  --- Confidence Distribution ---")
    for label, count in sorted(confidence_bins.items()):
        print(f"  {label:20s}: {count:5d} ({count/max(total,1):.1%})")

    print(f"\n  --- Top 20 Predictions (most frequent) ---")
    for pred, count in prediction_counts.most_common(20):
        is_kr = " [KR]" if pred in KNOWN_KOREAN_LABELS else ""
        print(f"  {pred:35s}: {count:5d} ({count/max(total,1):.1%}){is_kr}")

    print(f"\n  --- Korean Labels Detected ---")
    korean_preds = {k: v for k, v in prediction_counts.items() if k in KNOWN_KOREAN_LABELS}
    if korean_preds:
        for pred, count in sorted(korean_preds.items(), key=lambda x: -x[1]):
            kr_name = LABEL_TO_KOREAN.get(pred, "?")
            print(f"  {pred:25s} ({kr_name}): {count} images")
    else:
        print("  NONE -Model did not predict any Korean food labels!")

    print(f"\n  --- MFDS Nutrition Lookup ---")
    print(f"  Korean predictions with MFDS lookup: {mfds_total}")
    print(f"  Successfully found in MFDS:          {mfds_hits}/{max(mfds_total,1)}")

    # Per-prefix analysis (top prediction per original class)
    print(f"\n  --- Per Original Class (by Img prefix) ---")
    print(f"  {'Prefix':>8s}  {'Count':>5s}  {'Top Prediction':30s}  {'Korean?':>7s}")
    print(f"  {'-'*8}  {'-'*5}  {'-'*30}  {'-'*7}")
    for prefix in sorted(img_prefix_predictions.keys()):
        preds = img_prefix_predictions[prefix]
        most_common = Counter(preds).most_common(1)[0]
        is_kr = "YES" if most_common[0] in KNOWN_KOREAN_LABELS else "no"
        print(f"  {prefix:>8s}  {len(preds):>5d}  {most_common[0]:30s}  {is_kr:>7s}")

    # Save detailed results
    results_path = RESULTS_DIR / "korean_food_test_results.json"
    summary = {
        "test_date": time.strftime("%Y-%m-%d %H:%M"),
        "model": MODEL_PATH.name,
        "dataset": "Roboflow Korean Food Detector v1 (AI Hub)",
        "total_images": total,
        "errors": errors,
        "inference_time_sec": round(elapsed, 1),
        "korean_detected_count": korean_detected,
        "korean_detected_pct": round(korean_detected / max(total, 1), 4),
        "confidence_distribution": confidence_bins,
        "top_predictions": dict(prediction_counts.most_common(50)),
        "korean_predictions": korean_preds,
        "mfds_hit_rate": round(mfds_hits / max(mfds_total, 1), 4),
        "per_prefix_top_prediction": {
            prefix: Counter(preds).most_common(1)[0][0]
            for prefix, preds in img_prefix_predictions.items()
        },
    }
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved: {results_path}")

    # Verdict
    print(f"\n{'=' * 70}")
    print("VERDICT")
    print(f"{'=' * 70}")
    kr_pct = korean_detected / max(total, 1)
    if kr_pct >= 0.5:
        print("  GOOD -Model recognizes Korean food in majority of images")
        print("  Action: Use as-is for common Korean foods, fine-tune for missing ones")
    elif kr_pct >= 0.2:
        print("  MODERATE -Model recognizes some Korean foods but misclassifies many")
        print("  Action: Fine-tune on Korean food dataset for production accuracy")
    else:
        print("  POOR -Model struggles with Korean food recognition")
        print("  Action: Must fine-tune or train a Korean-specific food model")
        print("  Note: This is EXPECTED -the model has only ~28 Korean classes out of 2,024")
        print("  The model knows international cuisine well but needs Korean specialization")

    print(f"\n  Next steps:")
    print(f"  1. Fine-tune MobileNetV2 on this Korean food dataset (2,482 images)")
    print(f"  2. Or train a Korean-specific classifier (top-layer only, ~10 min on GPU)")
    print(f"  3. Map predictions to MFDS nutrition DB for pipeline integration")


if __name__ == "__main__":
    run_test()
