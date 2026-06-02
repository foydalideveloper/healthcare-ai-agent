"""Single-arm watcher: Gemma 4 only.

Usage:
  py gemma4_watcher.py "path/to/clip.mp4"        # process one file
  py gemma4_watcher.py --watch                   # poll AIMB-Bridge for new files
"""
from _arm_helpers import main

if __name__ == "__main__":
    main("gemma")
