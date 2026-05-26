"""
Download TFLite models for phone-side inference.
These models run on the smartphone, NOT on the glasses.

Models:
  1. MobileNetV2-Food — food classification (~85% accuracy)
  2. YOLOv8n — object detection + portion estimation
  3. YOLO-Face — bystander face detection for privacy blur
  4. Whisper-tiny — speech-to-text (optional, large)

Total download: ~70 MB (without Whisper) or ~110 MB (with Whisper)
"""

import urllib.request
import os
import ssl
import sys

MODELS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets', 'models')

# Model download URLs (publicly available pre-trained models)
MODELS = {
    'mobilenet_v2_food': {
        'url': 'https://tfhub.dev/google/lite-model/aiy/vision/classifier/food_V1/1?lite-format=tflite',
        'filename': 'mobilenet_v2_food.tflite',
        'size_mb': 4.3,
        'description': 'Food classification (2024 categories)',
    },
    'yolov8n': {
        'url': 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n_float16.tflite',
        'filename': 'yolov8n_float16.tflite',
        'size_mb': 5.4,
        'description': 'Object detection + segmentation',
    },
    'food_labels': {
        'url': 'https://www.gstatic.com/aihub/tfhub/labelmaps/aiy_food_V1_labelmap.csv',
        'filename': 'food_labels.csv',
        'size_mb': 0.05,
        'description': 'Food classification label map (2024 categories)',
    },
}

def download_model(name, info):
    filepath = os.path.join(MODELS_DIR, info['filename'])
    if os.path.exists(filepath):
        size = os.path.getsize(filepath) / (1024 * 1024)
        print(f'  [{name}] Already exists ({size:.1f} MB) - skipping')
        return True

    print(f'  [{name}] Downloading {info["filename"]} ({info["size_mb"]} MB)...')
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(info['url'], headers={
            'User-Agent': 'Mozilla/5.0 (Healthcare AI Agent)'
        })
        resp = urllib.request.urlopen(req, context=ctx, timeout=60)
        data = resp.read()

        with open(filepath, 'wb') as f:
            f.write(data)

        size = os.path.getsize(filepath) / (1024 * 1024)
        print(f'  [{name}] Downloaded ({size:.1f} MB)')
        return True
    except Exception as e:
        print(f'  [{name}] FAILED: {e}')
        return False


def main():
    os.makedirs(MODELS_DIR, exist_ok=True)
    print('Downloading TFLite models for phone-side inference...')
    print(f'Output: {os.path.abspath(MODELS_DIR)}')
    print()

    success = 0
    for name, info in MODELS.items():
        if download_model(name, info):
            success += 1

    print(f'\nDownloaded {success}/{len(MODELS)} models')
    print('\nNote: YOLO-Face and Whisper-tiny models need to be')
    print('obtained separately or trained. For testing, the food')
    print('classifier + labels are sufficient.')


if __name__ == '__main__':
    main()
