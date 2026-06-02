"""Single-arm watcher: Llama 4 Maverick only (NVIDIA NIM cloud).

Usage:
  py llama_watcher.py "path/to/clip.mp4"
  py llama_watcher.py --watch
"""
from _arm_helpers import main

if __name__ == "__main__":
    main("llama4")
