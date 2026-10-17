"""Real-Time Local Training & Download Monitor for SQLWhisperer.

Monitors training in the background and prints a clean status update
every 10 seconds without flooding or flickering your terminal:

    python scripts/monitor_training.py
"""

from __future__ import annotations

import datetime
import os
import re
import sys
import time
from pathlib import Path

# Configure UTF-8 for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Find the most recently active task log
LOG_DIR = Path(r"C:\Users\admin\.gemini\antigravity-ide\brain\b720dd9a-ef1f-4cf9-bdc6-cfc6c293cde2\.system_generated\tasks")
INTERVAL_SECONDS = 10  # 10-second heartbeat to prevent flooding


def find_latest_log() -> Path | None:
    if not LOG_DIR.exists():
        return None
    logs = list(LOG_DIR.glob("*.log"))
    if not logs:
        return None
    logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return logs[0]


def render_progress_bar(percent: float, width: int = 30) -> str:
    filled = int(width * (max(0.0, min(100.0, percent)) / 100.0))
    empty = max(0, width - filled)
    return "=" * filled + "-" * empty


def main():
    log_file = find_latest_log()
    print("=" * 70)
    print("[*] SQLWhisperer Live Training Monitor (Heartbeat: every 10s)")
    print(f"[*] Reading Log: {log_file.name if log_file else 'Searching...'}")
    print("    (Press Ctrl+C to exit monitor at any time — training keeps running!)")
    print("=" * 70)

    while True:
        if not log_file or not log_file.exists():
            log_file = find_latest_log()
            time.sleep(INTERVAL_SECONDS)
            continue

        try:
            # Read tail of log file
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 15000), os.SEEK_SET)
                chunk = f.read()

            lines = [l.strip() for l in chunk.splitlines() if l.strip()]

            # 1. Check for ModelSafetensors Download progress
            dl_matches = re.findall(r"model\.safetensors:\s*(\d+)%\|.*?\|\s*([\d\.]+[MGK]?B?)/([\d\.]+[MGK]?B?)\s*\[(.*?)[<,](.*?)\]", chunk)

            # 2. Check for Training Step progress
            train_matches = re.findall(r"\{\s*'loss':\s*([\d\.]+).*?'step':\s*(\d+)", chunk)
            step_progress = re.findall(r"(\d+)%\|.*?\|\s*(\d+)/(\d+)\s*\[(.*?)[<,](.*?)\]", chunk)

            now_str = datetime.datetime.now().strftime("%H:%M:%S")

            if "Local Fine-Tuning Complete" in chunk or "Saving fine-tuned LoRA" in chunk:
                print(f"[{now_str}] [+] TRAINING COMPLETE! LoRA Adapter saved in models/sqlwhisperer-slm-lora/!")
                break

            elif step_progress and "Training" in chunk:
                pct, step, total_steps, elapsed, rate = step_progress[-1]
                p_val = float(pct)
                bar = render_progress_bar(p_val)
                loss_str = f"Loss: {train_matches[-1][0]}" if train_matches else "Computing..."
                print(f"[{now_str}] [Phase 2: GPU Training] [{bar}] Step {step}/{total_steps} ({p_val:.1f}%) | {loss_str} | {rate.strip()}")

            elif dl_matches:
                pct, current, total, elapsed, rate = dl_matches[-1]
                p_val = float(pct)
                bar = render_progress_bar(p_val)
                print(f"[{now_str}] [Phase 1: Downloading Base Model] [{bar}] {p_val:>5.1f}% | {current}/{total} | {rate.strip()}")

            elif lines:
                last_line = lines[-1][:75]
                print(f"[{now_str}] [*] {last_line}")

        except Exception:
            pass

        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[*] Monitor detached. Training continues in background!")
