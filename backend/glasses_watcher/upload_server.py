"""
Upload Server — HTTP endpoint that drops uploaded files into the watcher inbox.

Dual purpose:
  1. iOS Shortcut: POST /upload from iPhone Photos app
  2. Mentra Live (future): POST from camera webhook (same endpoint)

Files are renamed with today's date prefix so watcher.py picks them up.

Run:
  python backend/glasses_watcher/upload_server.py

Listens on 0.0.0.0:8765 (change PORT below if needed).
"""

import io
import os
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

PROJECT_ROOT = Path(__file__).parent.parent.parent
INBOX = PROJECT_ROOT / "backend" / "glasses_watcher" / "inbox"
KST = timezone(timedelta(hours=9))
PORT = 8765

AUTH_TOKEN = os.environ.get("UPLOAD_TOKEN", "triple-h-dev-token")

CONTENT_TYPE_TO_EXT = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/heic": ".heic",
    "image/heif": ".heic",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
}


def today_prefix() -> str:
    return datetime.now(KST).strftime("%Y%m%d_%H%M%S")


def ext_from_content_type(ct: str) -> str:
    ct = (ct or "").split(";")[0].strip().lower()
    return CONTENT_TYPE_TO_EXT.get(ct, "")


def ensure_today_name(original: str, content_type: str = "") -> str:
    """Watcher only processes files with today's date + recognized extension. Fix up if missing."""
    today = datetime.now(KST).strftime("%Y%m%d")
    stem, ext = os.path.splitext(original)
    if not ext or ext.lower() not in {".jpg", ".jpeg", ".png", ".heic", ".webp",
                                       ".mp4", ".mov", ".mkv", ".avi",
                                       ".m4a", ".mp3", ".wav", ".aac", ".ogg"}:
        ext = ext_from_content_type(content_type) or ".mp4"
    if today in original and ext.lower() in original.lower():
        return original
    return f"{today_prefix()}_{stem or 'upload'}{ext}"


class UploadHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{datetime.now(KST).strftime('%H:%M:%S')}] {self.address_string()} {format % args}")

    def _send(self, status: int, body: str = "", content_type: str = "text/plain"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Filename")
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_OPTIONS(self):
        self._send(204)

    def do_GET(self):
        if self.path in ("/", "/health"):
            self._send(200, "glasses-upload-server OK\n")
        else:
            self._send(404, "not found\n")

    def do_POST(self):
        if self.path not in ("/upload", "/api/v1/glass-webhook"):
            self._send(404, "unknown endpoint\n")
            return

        auth = self.headers.get("Authorization", "")
        if AUTH_TOKEN and auth.replace("Bearer ", "").strip() != AUTH_TOKEN:
            hint = self.headers.get("X-Auth-Token", "")
            if hint != AUTH_TOKEN:
                self._send(401, "unauthorized\n")
                return

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            self._send(400, "empty body\n")
            return

        content_type = self.headers.get("Content-Type", "")
        raw_name = self.headers.get("X-Filename") or f"upload_{uuid.uuid4().hex[:8]}"
        safe_name = os.path.basename(raw_name).replace("\\", "_").replace("/", "_")
        final_name = ensure_today_name(safe_name, content_type)

        INBOX.mkdir(parents=True, exist_ok=True)
        dest = INBOX / final_name

        start = time.time()
        written = 0
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with tmp.open("wb") as fp:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    fp.write(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
            tmp.rename(dest)
        except Exception as e:
            try:
                tmp.unlink(missing_ok=True)
            except Exception:
                pass
            self._send(500, f"write error: {e}\n")
            return

        elapsed = time.time() - start
        rate_mb = (written / 1024 / 1024) / max(elapsed, 0.001)
        print(f"  -> saved {dest.name} ({written/1024:.0f} KB in {elapsed:.1f}s, {rate_mb:.1f} MB/s)")
        self._send(200, f"ok {dest.name}\n")


def main():
    INBOX.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("GLASSES UPLOAD SERVER")
    print("=" * 60)
    print(f"Listening on: http://0.0.0.0:{PORT}")
    print(f"Inbox:        {INBOX}")
    print(f"Auth token:   {AUTH_TOKEN}")
    print("Endpoints:")
    print(f"  POST http://<pc-ip>:{PORT}/upload                  (iOS Shortcut)")
    print(f"  POST http://<pc-ip>:{PORT}/api/v1/glass-webhook    (Mentra Live, future)")
    print(f"  GET  http://<pc-ip>:{PORT}/health")
    print("-" * 60)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), UploadHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
