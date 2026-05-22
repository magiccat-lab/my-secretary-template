#!/usr/bin/env python3
from __future__ import annotations
"""Sample task: ping a health endpoint and report status."""

import os
import shutil
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False

def main() -> int:
    checks = {
        "root_exists": ROOT.exists(),
        "python": shutil.which("python3") is not None,
        "env_exists": (ROOT / ".env").exists(),
    }
    port = os.environ.get("HEALTHCHECK_PORT")
    if port:
        checks[f"port_{port}"] = port_open("127.0.0.1", int(port))

    ok = all(checks.values())
    for key, value in checks.items():
        print(f"{key}: {'ok' if value else 'ng'}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
