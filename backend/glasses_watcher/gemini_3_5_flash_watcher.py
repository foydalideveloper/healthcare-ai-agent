"""Single-arm watcher: Gemini 3.5 Flash (Google AI Studio).

Reuses the existing gemini REST path; _arm_helpers sets GEMINI_MODEL=
gemini-3.5-flash for this arm, so events land with
source_model="gemini_3_5_flash".

Usage:
  py gemini_3_5_flash_watcher.py "path/to/clip.mp4"
  py gemini_3_5_flash_watcher.py --watch
"""
from _arm_helpers import main

if __name__ == "__main__":
    main("gemini_3_5_flash")
