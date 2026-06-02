"""Single-arm watcher: Qwen 3.5 VLM only (local Ollama).

Usage:
  py qwen_watcher.py "path/to/clip.mp4"
  py qwen_watcher.py --watch
"""
from _arm_helpers import main

if __name__ == "__main__":
    main("qwen")
