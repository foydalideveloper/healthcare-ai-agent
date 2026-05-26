"""
AIMB-G1 WiFi Protocol Probe
===========================

One-time discovery script. Tells us what HTTP endpoints, ports, and auth the
AIMB-G1 glasses expose over WiFi so we can build reverse_lifelog_watcher.py.

USAGE
-----
1. Put on the glasses and START a recording (so they actively broadcast WiFi).
2. On your PC: Settings -> Network & Internet -> WiFi.
3. Look for a network named like "AIMB-G1_DD75" (or similar with DD75 suffix).
4. Connect your PC to that network. If it asks for a password, try common
   defaults in this order: 12345678 / 00000000 / aimbg1 / 88888888.
5. While connected to the glasses' WiFi, run this script:

     C:\\Users\\tripleh\\AppData\\Local\\Python\\pythoncore-3.11-64\\python.exe ^
       glasses_watcher\\probe_aimb_g1.py

6. The script writes a full report to probe_report.txt next to itself.
   Send me that file (or paste its contents) and I'll build the watcher.

NOTES
-----
- Your PC will lose internet access while connected to the glasses' WiFi.
  That's expected. Reconnect to your normal WiFi after the probe finishes.
- The script is read-only. It does not change anything on the glasses.
- Total runtime: ~60 seconds.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import httpx

REPORT_FILE = Path(__file__).parent / "probe_report.txt"

# Ports commonly used by IP cameras / AI glasses / IoT devices.
PORTS_TO_SCAN = [
    21, 22, 23, 25, 53, 69, 80, 88, 110, 143, 443, 445, 554, 631,
    1080, 1900, 2049, 3000, 3306, 3389, 3702, 4000, 5000, 5001,
    5060, 5353, 5555, 5566, 6000, 6666, 6688, 7000, 7777, 8000,
    8001, 8008, 8080, 8081, 8088, 8089, 8090, 8091, 8443, 8554,
    8888, 8899, 8999, 9000, 9001, 9090, 9091, 9100, 9999, 10000,
    10080, 12345, 18080, 31337, 49152, 50000,
]

# HTTP paths commonly used by camera/glasses firmware.
HTTP_PATHS = [
    "/", "/index.html", "/index.json",
    "/api", "/api/v1", "/api/v1/files", "/api/v1/file/list",
    "/api/file", "/api/file/list", "/api/files", "/api/list",
    "/api/media", "/api/storage", "/api/info", "/api/state",
    "/api/device", "/api/system", "/api/version",
    "/files", "/file", "/file/list", "/list",
    "/storage", "/storage/list", "/media", "/media/list",
    "/videos", "/photos", "/recording", "/recordings",
    "/dcim", "/DCIM", "/dcim/list",
    "/cgi-bin/", "/cgi-bin/list", "/cgi-bin/files.cgi",
    "/cgi-bin/api.cgi", "/cgi-bin/get_file_list",
    "/cgi-bin/Param.cgi", "/cgi-bin/hi3510/",
    "/state", "/status", "/info", "/device", "/system",
    "/version", "/config", "/help", "/doc", "/swagger",
    "/onvif/device_service",
    "/proxy/storage/list",
    "/get_file_list", "/get_files", "/list_files",
    "/v1/files", "/v2/files", "/v3/files",
]

# ─── helpers ──────────────────────────────────────────────────────────


def section(title: str) -> str:
    bar = "=" * 70
    return f"\n{bar}\n{title}\n{bar}\n"


def run_cmd(args: list[str]) -> str:
    for enc in ("utf-8", "cp949", "cp1252", "latin-1"):
        try:
            return subprocess.check_output(args, text=True, encoding=enc,
                                          errors="replace", timeout=10)
        except (UnicodeDecodeError, LookupError):
            continue
        except Exception as e:
            return f"(command failed: {e})"
    return "(could not decode command output)"


def get_default_gateway() -> Optional[str]:
    """Find the default gateway IP from ipconfig output."""
    out = run_cmd(["ipconfig"])
    gateways: list[str] = []
    for line in out.split("\n"):
        if ("Default Gateway" in line or "기본 게이트웨이" in line
                or "默认网关" in line):
            parts = line.split(":")
            if len(parts) > 1:
                ip = parts[-1].strip()
                if ip and "." in ip and not ip.startswith("0."):
                    gateways.append(ip)
    return gateways[0] if gateways else None


def get_local_ip() -> Optional[str]:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return None
    finally:
        s.close()


def get_wifi_info() -> str:
    return run_cmd(["netsh", "wlan", "show", "interfaces"])


def scan_port(host: str, port: int, timeout: float = 1.5) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def banner_grab(host: str, port: int, timeout: float = 2.5) -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        try:
            data = s.recv(1024)
            if data:
                return data.decode("utf-8", errors="replace")[:600]
        except socket.timeout:
            pass
        # Nudge with a generic HTTP request
        try:
            s.sendall(b"GET / HTTP/1.0\r\nHost: " + host.encode() + b"\r\n\r\n")
            data = s.recv(1024)
            return data.decode("utf-8", errors="replace")[:600]
        except Exception as e:
            return f"(no banner: {type(e).__name__})"
    except Exception as e:
        return f"(connect failed: {type(e).__name__}: {e})"
    finally:
        s.close()


def http_probe(base_url: str, path: str, timeout: float = 4.0) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    try:
        with httpx.Client(timeout=timeout, verify=False,
                          follow_redirects=False) as client:
            r = client.get(url, headers={"User-Agent": "AIMB-G1-Probe/1.0"})
        body = (r.text or "")[:400].replace("\n", " ").replace("\r", "")
        return {
            "url": url,
            "status": r.status_code,
            "content_type": r.headers.get("content-type", ""),
            "content_length": r.headers.get("content-length", "?"),
            "server": r.headers.get("server", ""),
            "body_preview": body,
            "header_keys": list(r.headers.keys()),
        }
    except Exception as e:
        return {"url": url, "status": None,
                "error": f"{type(e).__name__}: {str(e)[:100]}"}


def mdns_discover(host: str, timeout: float = 3.0) -> str:
    """Quick mDNS query to see if glasses advertise services."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        # mDNS query for "_services._dns-sd._udp.local"
        query = bytes([
            0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x09, 0x5f, 0x73, 0x65,
            0x72, 0x76, 0x69, 0x63, 0x65, 0x73, 0x07, 0x5f,
            0x64, 0x6e, 0x73, 0x2d, 0x73, 0x64, 0x04, 0x5f,
            0x75, 0x64, 0x70, 0x05, 0x6c, 0x6f, 0x63, 0x61,
            0x6c, 0x00, 0x00, 0x0c, 0x00, 0x01,
        ])
        s.sendto(query, ("224.0.0.251", 5353))
        try:
            data, addr = s.recvfrom(2048)
            return f"mDNS reply from {addr}: {data[:300].hex()}"
        except socket.timeout:
            return "(no mDNS reply)"
        finally:
            s.close()
    except Exception as e:
        return f"(mDNS probe failed: {type(e).__name__})"


# ─── main ─────────────────────────────────────────────────────────────


def main() -> None:
    log_lines: list[str] = []

    def log(msg: str) -> None:
        print(msg)
        log_lines.append(msg)

    log(section("AIMB-G1 WiFi Protocol Probe"))
    log(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # 1) WiFi info
    log(section("[1/5] Connected WiFi info"))
    log(get_wifi_info())

    # 2) Network identity
    log(section("[2/5] Local IP and default gateway"))
    local_ip = get_local_ip()
    gateway = get_default_gateway()
    log(f"  Local IP:        {local_ip}")
    log(f"  Default gateway: {gateway}")

    if not gateway:
        log("\n  ERROR: no gateway. Are you connected to the glasses' WiFi?")
        log("         Reconnect to AIMB-G1_* WiFi network and re-run.")
        REPORT_FILE.write_text("\n".join(log_lines), encoding="utf-8")
        return

    # 3) Port scan
    log(section(f"[3/5] TCP port scan on {gateway}  (~30s)"))
    open_ports: list[int] = []
    with ThreadPoolExecutor(max_workers=30) as ex:
        futures = {ex.submit(scan_port, gateway, p): p for p in PORTS_TO_SCAN}
        for fut in as_completed(futures):
            port = futures[fut]
            try:
                if fut.result():
                    open_ports.append(port)
                    log(f"  OPEN: {port}")
            except Exception:
                pass

    if not open_ports:
        log("\n  WARNING: no open TCP ports found.")
        log("  Possible causes:")
        log("   - glasses use UDP only (RTSP, mDNS)")
        log("   - glasses are not actively transferring (try recording first)")
        log("   - firewall on glasses or PC")
        log("   - non-standard port outside our scan list")

    # 4) Banner grabs
    if open_ports:
        log(section("[4/5] Banner / response grab on each open port"))
        for port in sorted(open_ports):
            log(f"\n--- Port {port} ---")
            log(banner_grab(gateway, port))

    # 5) HTTP endpoint probing
    if open_ports:
        log(section("[5/5] HTTP path probing on each likely-HTTP port"))
        # Probe HTTP on every open port (cameras often use weird port numbers)
        for port in sorted(open_ports):
            scheme = "https" if port in (443, 8443) else "http"
            base = f"{scheme}://{gateway}:{port}"
            log(f"\n===== Probing base {base} =====")
            interesting = 0
            for path in HTTP_PATHS:
                r = http_probe(base, path)
                status = r.get("status")
                # Only log "interesting" responses (anything that's NOT 404 / connect error)
                if status is None:
                    continue
                if status == 404:
                    continue
                interesting += 1
                log(f"\n  PATH: {path}")
                log(f"    status:       {status}")
                log(f"    content-type: {r.get('content_type', '?')}")
                log(f"    length:       {r.get('content_length', '?')}")
                if r.get("server"):
                    log(f"    server:       {r['server']}")
                log(f"    body preview: {r.get('body_preview', '')[:200]}")
            if interesting == 0:
                log(f"  (no non-404 responses on this port)")

    # mDNS quick check
    log(section("[bonus] mDNS / Bonjour service discovery"))
    log(mdns_discover(gateway))

    # Done
    log(section("DONE"))
    log(f"Full report saved to: {REPORT_FILE}")
    log("Send the contents of probe_report.txt back so the next step can be designed.")
    log("Reminder: reconnect to your normal WiFi to restore internet access.")

    REPORT_FILE.write_text("\n".join(log_lines), encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[interrupted]")
        sys.exit(1)
