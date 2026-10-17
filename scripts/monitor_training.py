"""Real-Time Local Training & Download Monitor for SQLWhisperer.

Run in your terminal to see a live visual progress bar and GPU metrics:
    python scripts/monitor_training.py
"""

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


def find_latest_log():
    if not LOG_DIR.exists():
        return None
    logs = list(LOG_DIR.glob("*.log"))
    if not logs:
        return None
    # Sort by modification time
    logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return logs[0]


def render_progress_bar(percent: float, width: int = 35) -> str:
    filled = int(width * (percent / 100.0))
    empty = max(0, width - filled)
    return "=" * filled + "-" * empty


def main():
    log_file = find_latest_log()
    print("=" * 65)
    print("[*] SQLWhisperer Live Training & GPU Dashboard")
    print(f"[*] Monitoring Task Log: {log_file.name if log_file else 'Searching...'}")
    print("    (Press Ctrl+C to exit monitor at any time without stopping training)")
    print("=" * 65)

    last_render = ""

    while True:
        if not log_file or not log_file.exists():
            log_file = find_latest_log()
            time.sleep(1)
            continue

        try:
            # Read last 8KB of log
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 12000), os.SEEK_SET)
                chunk = f.read()

            lines = [l.strip() for l in chunk.splitlines() if l.strip()]

            # 1. Check for ModelSafetensors Download progress
            dl_matches = re.findall(r"model\.safetensors:\s*(\d+)%\|.*?\|\s*([\d\.]+[MGK]?B?)/([\d\.]+[MGK]?B?)\s*\[(.*?)[<,](.*?)\]", chunk)
            
            # 2. Check for Training Step progress
            train_matches = re.findall(r"\{\s*'loss':\s*([\d\.]+).*?'step':\s*(\d+)", chunk)
            step_progress = re.findall(r"(\d+)%\|.*?\|\s*(\d+)/(\d+)\s*\[(.*?)[<,](.*?)\]", chunk)

            status_line = ""

            if dl_matches:
                pct, current, total, elapsed, rate = dl_matches[-1]
                p_val = float(pct)
                bar = render_progress_bar(p_val)
                status_line = f"\r[Phase 1: Downloading Base Model] [{bar}] {p_val:>5.1f}% | {current}/{total} | {rate.strip()}"

            elif step_progress and "Training" in chunk:
                pct, step, total_steps, elapsed, rate = step_progress[-1]
                p_val = float(pct)
                bar = render_progress_bar(p_val)
                loss_str = f"Loss: {train_matches[-1][0]}" if train_matches else "Training..."
                status_line = f"\r[Phase 2: RTX 4050 Training] [{bar}] Step {step}/{total_steps} ({p_val:.1f}%) | {loss_str} | {rate.strip()}"

            elif "Local Fine-Tuning Complete" in chunk or "Saving fine-tuned LoRA" in chunk:
                status_line = "\r[+] TRAINING COMPLETE! LoRA Adapter saved in models/sqlwhisperer-slm-lora/!\n"
                sys.stdout.write(status_line)
                sys.stdout.flush()
                break

            elif lines:
                last_line = lines[-1][:80]
                status_line = f"\r[*] {last_line}"

            if status_line and status_line != last_render:
                sys.stdout.write(status_line)
                sys.stdout.flush()
                last_render = status_line

        except Exception:
            pass

        time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[*] Monitor detached. Training continues in background!")
