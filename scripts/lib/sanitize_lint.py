#!/usr/bin/env python3
from __future__ import annotations
"""Lint repository files for PII / secret patterns before commit."""

import argparse
import re
import sys
from pathlib import Path

PATTERNS = [
    ("openai_api_key", r"sk-[A-Za-z0-9_-]{20,}"),
    ("anthropic_api_key", r"sk-ant-[A-Za-z0-9_-]{20,}"),
    ("notion_token", r"secret_[A-Za-z0-9]{20,}"),
    ("discord_bot_token", r"[MN][A-Za-z\d]{23,}\.[\w-]{6,}\.[\w-]{20,}"),
    ("google_oauth_client_secret", r"GOCSPX-[A-Za-z0-9_-]+"),
    ("github_token", r"gh[pousr]_[A-Za-z0-9_]{30,}"),
    ("aws_access_key", r"AKIA[0-9A-Z]{16}"),
    ("private_key_header", r"-----BEGIN (RSA |OPENSSH |EC |)PRIVATE KEY-----"),
    ("ipv4_public", r"\b(?!(10|127|172\.(1[6-9]|2\d|3[01])|192\.168)\.)\d{1,3}(?:\.\d{1,3}){3}\b"),
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("phone_jp", r"\b0[789]0[- ]?\d{4}[- ]?\d{4}\b"),
    ("postal_jp", r"\b\d{3}-\d{4}\b"),
    ("discord_snowflake", r"\b\d{17,20}\b"),
    ("ssh_private_path", r"\b\.ssh/[A-Za-z0-9._-]+\b"),
    ("pem_filename", r"\b[A-Za-z0-9._-]+\.pem\b"),
    ("env_assignment_secret", r"(?i)\b(token|secret|password|passwd|api[_-]?key)\s*=\s*['\"]?[^'\"\s]+"),
    ("cloudflare_tunnel_token", r"eyJhIjoi[A-Za-z0-9._-]{40,}"),
    ("basic_auth_url", r"https?://[^/\s:@]+:[^/\s:@]+@"),
    ("slack_token", r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    ("stripe_key", r"sk_(live|test)_[A-Za-z0-9]{20,}"),
    ("line_token", r"[A-Za-z0-9+/]{80,}={0,2}"),
    ("ssid_phrase", r"(?i)\b(ssid|wi-?fi|wifi)\s*[:=]\s*\S+"),
    ("personal_placeholder_required", r"\b(real name|home address|birthday|family name)\b"),
]

SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".mypy_cache", ".pytest_cache"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz"}

def iter_files(paths: list[Path]):
    for path in paths:
        if path.is_file():
            yield path
            continue
        for child in path.rglob("*"):
            if child.is_dir():
                continue
            if any(part in SKIP_DIRS for part in child.parts):
                continue
            if child.suffix.lower() in SKIP_SUFFIXES:
                continue
            yield child

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["."])
    parser.add_argument("--max-bytes", type=int, default=1_000_000)
    args = parser.parse_args()

    compiled = [(name, re.compile(pattern)) for name, pattern in PATTERNS]
    findings = []

    for file_path in iter_files([Path(p) for p in args.paths]):
        try:
            raw = file_path.read_bytes()
        except OSError:
            continue
        if len(raw) > args.max_bytes or b"\0" in raw:
            continue
        text = raw.decode("utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            for name, pattern in compiled:
                if pattern.search(line):
                    findings.append((file_path, line_no, name, line[:160]))

    for file_path, line_no, name, line in findings:
        print(f"{file_path}:{line_no}: {name}: {line}")

    return 1 if findings else 0

if __name__ == "__main__":
    sys.exit(main())
